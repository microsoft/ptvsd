# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""Manages the lifetime of the debugged process and its subprocesses, in scenarios
where it is controlled by the adapter (i.e. "launch").
"""

import atexit
import codecs
import collections
import functools
import locale
import os
import platform
import signal
import subprocess
import sys
import threading

import ptvsd.__main__
from ptvsd.adapter import channels, contract
from ptvsd.common import compat, fmt, json, launcher, messaging, log, singleton, socket
from ptvsd.common.compat import unicode


terminate_at_exit = True
"""Whether the debuggee process should be terminated when the adapter process exits,
or allowed to continue running.
"""

exit_code = None
"""The exit code of the debuggee process, once it has terminated."""

pid = None
"""Debuggee process ID."""

captured_output = set()
"""Categories of output which are being captured directly from the debuggee.

Corresponds to "category" in the DAP "output" event. If some category is present
in this set, then "output" events for it are being generated by the adapter, and
the corresponding events from the debug server must not be propagated to the IDE
to avoid duplicate output.
"""

_got_pid = threading.Event()
"""A threading.Event that is set when pid is set.
"""

_exited = None
"""A threading.Event that is set when the debuggee process exits.

Created when the process is spawned.
"""


SpawnInfo = collections.namedtuple(
    "SpawnInfo",
    ["console", "console_title", "cmdline", "cwd", "env", "redirect_output"],
)


def spawn_and_connect(request):
    """Spawns the process as requested by the DAP "launch" request, with the debug
    server running inside the process; and connects to that server. Returns the
    server channel.

    Caller is responsible for calling start() on the returned channel.
    """

    if request("noDebug", json.default(False)):
        _parse_request_and_spawn(request, (None, None))
    else:
        channels.Channels().accept_connection_from_server(
            ("127.0.0.1", 0),
            before_accept=lambda address: _parse_request_and_spawn(request, address),
        )


def _parse_request_and_spawn(request, address):
    spawn_info = _parse_request(request, address)
    log.debug(
        "SpawnInfo = {0!j}",
        collections.OrderedDict(
            {
                "console": spawn_info.console,
                "cwd": spawn_info.cwd,
                "cmdline": spawn_info.cmdline,
                "env": spawn_info.env,
            }
        ),
    )

    spawn = {
        "internalConsole": _spawn_popen,
        "integratedTerminal": _spawn_terminal,
        "externalTerminal": _spawn_terminal,
    }[spawn_info.console]

    global _exited
    _exited = threading.Event()
    try:
        spawn(request, spawn_info)
    finally:
        if pid is None:
            _exited.set()
        else:
            atexit.register(lambda: terminate() if terminate_at_exit else None)


def _parse_request(request, address):
    """Parses a "launch" request and returns SpawnInfo for it.

    address is (host, port) on which the adapter listener is waiting for connection
    from the debug server.
    """

    assert request.is_request("launch")
    host, port = address
    debug_options = set(request("debugOptions", json.array(unicode)))

    # Handling of properties that can also be specified as legacy "debugOptions" flags.
    # If property is explicitly set to false, but the flag is in "debugOptions", treat
    # it as an error.
    def property_or_debug_option(prop_name, flag_name):
        assert prop_name[0].islower() and flag_name[0].isupper()
        value = request(prop_name, json.default(flag_name in debug_options))
        if value is False and flag_name in debug_options:
            raise request.isnt_valid(
                '{0!r}:false and "debugOptions":[{1!r}] are mutually exclusive',
                prop_name,
                flag_name,
            )
        return value

    console = request(
        "console",
        json.enum(
            "internalConsole", "integratedTerminal", "externalTerminal", optional=True
        ),
    )
    if console != "internalConsole":
        if not contract.ide.capabilities["supportsRunInTerminalRequest"]:
            raise request.cant_handle(
                'Unable to launch via "console":{0!j}, because the IDE is does not '
                'have the "supportsRunInTerminalRequest" capability',
                console,
            )

    console_title = request("consoleTitle", json.default("Python Debug Console"))

    cmdline = []
    if property_or_debug_option("sudo", "Sudo"):
        if platform.system() == "Windows":
            raise request.cant_handle('"sudo":true is not supported on Windows.')
        else:
            cmdline += ["sudo"]

    # "pythonPath" is a deprecated legacy spelling. If "python" is missing, then try
    # the alternative. But if both are missing, the error message should say "python".
    python_key = "python"
    if python_key in request:
        if "pythonPath" in request:
            raise request.isnt_valid(
                '"pythonPath" is not valid if "python" is specified'
            )
    elif "pythonPath" in request:
        python_key = "pythonPath"
    python = request(python_key, json.array(unicode, vectorize=True, size=(1,)))
    if not len(python):
        python = [sys.executable]
    cmdline += python

    cmdline += [compat.filename(launcher.__file__)]
    if property_or_debug_option("waitOnNormalExit", "WaitOnNormalExit"):
        cmdline += ["--wait-on-normal"]
    if property_or_debug_option("waitOnAbnormalExit", "WaitOnAbnormalExit"):
        cmdline += ["--wait-on-abnormal"]

    if request("noDebug", json.default(False)):
        cmdline += ["--"]
    else:
        ptvsd_args = request("ptvsdArgs", json.array(unicode))
        cmdline += [
            "--",
            compat.filename(ptvsd.__main__.__file__),
            "--client",
            "--host",
            host,
            "--port",
            str(port),
        ] + ptvsd_args

    program = module = code = ()
    if "program" in request:
        program = request("program", json.array(unicode, vectorize=True, size=(1,)))
        cmdline += program
    if "module" in request:
        module = request("module", json.array(unicode, vectorize=True, size=(1,)))
        cmdline += ["-m"]
        cmdline += module
    if "code" in request:
        code = request("code", json.array(unicode, vectorize=True, size=(1,)))
        cmdline += ["-c"]
        cmdline += code

    num_targets = len([x for x in (program, module, code) if x != ()])
    if num_targets == 0:
        raise request.isnt_valid(
            'either "program", "module", or "code" must be specified'
        )
    elif num_targets != 1:
        raise request.isnt_valid(
            '"program", "module", and "code" are mutually exclusive'
        )

    cmdline += request("args", json.array(unicode))

    cwd = request("cwd", unicode, optional=True)
    if cwd == ():
        # If it's not specified, but we're launching a file rather than a module,
        # and the specified path has a directory in it, use that.
        cwd = None if program == () else (os.path.dirname(program) or None)

    env = request("env", json.object(unicode))

    redirect_output = "RedirectOutput" in debug_options
    if redirect_output:
        # sys.stdout buffering must be disabled - otherwise we won't see the output
        # at all until the buffer fills up.
        env["PYTHONUNBUFFERED"] = "1"

    return SpawnInfo(console, console_title, cmdline, cwd, env, redirect_output)


def _spawn_popen(request, spawn_info):
    assert spawn_info.pid_server is None

    env = os.environ.copy()
    env.update(spawn_info.env)

    if sys.version_info < (3,):
        # env is all Unicode strings at this point, but Popen() expects bytes, so we
        # need to encode. Assume that values are filenames - it's usually either that,
        # or numbers - but don't allow encoding to fail if we guessed wrong.
        encode = functools.partial(compat.filename_bytes, errors="replace")
        env = {encode(k): encode(v) for k, v in env.items()}

    close_fds = set()
    try:
        if spawn_info.redirect_output:
            # subprocess.PIPE behavior can vary substantially depending on Python version
            # and platform; using our own pipes keeps it simple, predictable, and fast.
            stdout_r, stdout_w = os.pipe()
            stderr_r, stderr_w = os.pipe()
            close_fds |= {stdout_r, stdout_w, stderr_r, stderr_w}
        else:
            # Let it write directly to stdio. If stdout is being used for the IDE DAP
            # channel, sys.stdout is already pointing to stderr.
            stdout_w = sys.stdout.fileno()
            stderr_w = sys.stderr.fileno()

        try:
            proc = subprocess.Popen(
                spawn_info.cmdline,
                cwd=spawn_info.cwd,
                env=env,
                bufsize=0,
                stdin=sys.stdin,
                stdout=stdout_w,
                stderr=stderr_w,
            )
        except Exception as exc:
            raise request.cant_handle(
                "Error launching process: {0}\n\nCommand line:{1!r}",
                exc,
                spawn_info.cmdline,
            )

        log.info("Spawned debuggee process with PID={0}.", proc.pid)

        global pid
        try:
            pid = proc.pid
            _got_pid.set()
            ProcessTracker().track(pid)
        except Exception:
            # If we can't track it, we won't be able to terminate it if asked; but aside
            # from that, it does not prevent debugging.
            log.exception(
                "Unable to track debuggee process with PID={0}.",
                pid,
                category="warning",
            )

        # Wait directly on the Popen object, instead of going via ProcessTracker. This is
        # more reliable on Windows, because Popen always has the correct process handle
        # that it gets from CreateProcess, whereas ProcessTracker will use OpenProcess to
        # get it from PID, and there's a race condition there if the process dies and its
        # PID is reused before OpenProcess is called.
        def wait_for_exit():
            global exit_code
            try:
                exit_code = proc.wait()
            except Exception:
                log.exception("Couldn't determine process exit code:")
                exit_code = -1
            finally:
                _exited.set()

        wait_thread = threading.Thread(target=wait_for_exit, name='"launch" worker')
        wait_thread.start()

        if spawn_info.redirect_output:
            global output_redirected
            output_redirected = spawn_info.redirect_output
            encoding = env.get("PYTHONIOENCODING", locale.getpreferredencoding())

            for category, fd, tee in [
                ("stdout", stdout_r, sys.stdout),
                ("stderr", stderr_r, sys.stderr),
            ]:
                CaptureOutput(category, fd, tee.fileno(), encoding)
                close_fds.remove(fd)

    finally:
        for fd in close_fds:
            try:
                os.close(fd)
            except Exception:
                log.exception()


def _spawn_terminal(request, spawn_info):
    kinds = {"integratedTerminal": "integrated", "externalTerminal": "external"}
    body = {
        "kind": kinds[spawn_info.console],
        "title": spawn_info.console_title,
        "cwd": spawn_info.cwd,
        "args": spawn_info.cmdline,
        "env": spawn_info.env,
    }

    try:
        channels.Channels().ide().request("runInTerminal", body)
    except messaging.MessageHandlingError as exc:
        exc.propagate(request)

    def after_exit(code):
        global exit_code
        exit_code = code
        _exited.set()

    global pid
    try:
        pid = spawn_info.pid_server.wait_for_pid()
        _got_pid.set()
        ProcessTracker().track(pid, after_exit=after_exit)
    except Exception as exc:
        # If we can't track it, we won't be able to terminate it if asked; but aside
        # from that, it does not prevent debugging.
        log.exception(
            "Unable to track debuggee process with PID={0}: {1}.", pid, str(exc), category="warning"
        )


def wait_for_pid(timeout=None):
    """Waits for debuggee PID to be determined.

    Returns True if PID was determined, False if the wait timed out. If it returned
    True, then pid is guaranteed to be set.
    """
    return _got_pid.wait(timeout)


def wait_for_exit(timeout=None):
    """Waits for the debugee process to exit.

    Returns True if the process exited, False if the wait timed out. If it returned
    True, then exit_code is guaranteed to be set.
    """

    if pid is None:
        # Debugee was launched with "runInTerminal", but the debug session fell apart
        # before we got a "process" event and found out what its PID is. It's not a
        # fatal error, but there's nothing to wait on. Debuggee process should have
        # exited (or crashed) by now in any case.
        return

    assert _exited is not None
    timed_out = not _exited.wait(timeout)
    if not timed_out:
        # ProcessTracker will stop tracking it by itself, but it might take a bit
        # longer for it to notice that the process is gone. If killall() is invoked
        # before that, it will try to kill that non-existing process, and log the
        # resulting error. This prevents that.
        ProcessTracker().stop_tracking(pid)
    return not timed_out


def terminate(after=0):
    """Waits for the debugee process to exit for the specified number of seconds. If
    the process or any subprocesses are still alive after that time, force-kills them.

    If any errors occur while trying to kill any process, logs and swallows them.

    If the debugee process hasn't been spawned yet, does nothing.
    """

    if _exited is None:
        return

    wait_for_exit(after)
    ProcessTracker().killall()


def register_subprocess(pid):
    """Registers a subprocess of the debuggee process."""
    ProcessTracker().track(pid)


class ProcessTracker(singleton.ThreadSafeSingleton):
    """Tracks processes that belong to the debuggee.
    """

    _processes = {}
    """Keys are PIDs, and values are handles as used by os.waitpid(). On Windows,
    handles are distinct. On all other platforms, the PID is also the handle.
    """

    _exit_codes = {}
    """Keys are PIDs, values are exit codes."""

    @singleton.autolocked_method
    def track(self, pid, after_exit=lambda _: None):
        """Starts tracking the process with the specified PID, and returns its handle.

        If the process exits while it is still being tracked, after_exit is invoked
        with its exit code.
        """

        # Register the atexit handler only once, on the first tracked process.
        if not len(self._processes):
            atexit.register(lambda: self.killall() if terminate_at_exit else None)

        self._processes[pid] = handle = _pid_to_handle(pid)
        log.debug(
            "Tracking debuggee process with PID={0} and HANDLE=0x{1:08X}.", pid, handle
        )

        def wait_for_exit():
            try:
                _, exit_code = os.waitpid(handle, 0)
            except Exception:
                exit_code = -1
                log.exception(
                    "os.waitpid() for debuggee process with HANDLE=0x{1:08X} failed:",
                    handle,
                )
            else:
                exit_code >>= 8
                log.info(
                    "Debuggee process with PID={0} exited with exitcode {1}.",
                    pid,
                    exit_code,
                )

            with self:
                if pid in self._processes:
                    self._exit_codes[pid] = exit_code
                    self.stop_tracking(pid)
                    after_exit(exit_code)

        wait_thread = threading.Thread(
            target=wait_for_exit, name=fmt("Process(pid={0}) tracker", pid)
        )
        wait_thread.daemon = True
        wait_thread.start()

        return handle

    @singleton.autolocked_method
    def stop_tracking(self, pid):
        if self._processes.pop(pid, None) is not None:
            log.debug("Stopped tracking debuggee process with PID={0}.", pid)

    @singleton.autolocked_method
    def killall(self):
        pids = list(self._processes.keys())
        for pid in pids:
            log.info("Killing debuggee process with PID={0}.", pid)
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                log.exception("Couldn't kill debuggee process with PID={0}:", pid)


if platform.system() != "Windows":
    _pid_to_handle = lambda pid: pid
else:
    import ctypes
    from ctypes import wintypes

    class ProcessAccess(wintypes.DWORD):
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        SYNCHRONIZE = 0x100000

    OpenProcess = ctypes.windll.kernel32.OpenProcess
    OpenProcess.restype = wintypes.HANDLE
    OpenProcess.argtypes = (ProcessAccess, wintypes.BOOL, wintypes.DWORD)

    def _pid_to_handle(pid):
        handle = OpenProcess(
            ProcessAccess.PROCESS_QUERY_LIMITED_INFORMATION | ProcessAccess.SYNCHRONIZE,
            False,
            pid,
        )
        if not handle:
            raise ctypes.WinError()
        return handle


class CaptureOutput(object):
    """Captures output from the specified file descriptor, and tees it into another
    file descriptor while generating DAP "output" events for it.
    """

    def __init__(self, category, fd, tee_fd, encoding):
        log.info("Capturing {0} of debuggee process with PID={1}.", category, pid)

        self._category = category
        self._fd = fd
        self._tee_fd = tee_fd

        # Do this here instead of _worker(), so that exceptions propagate to caller.
        self._ide = channels.Channels().ide()
        try:
            self._decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
        except LookupError:
            self._decoder = None
            log.warning(
                "Unable to capture {0} - unknown encoding {1!r}", category, encoding
            )
        else:
            captured_output.add(category)

        worker = threading.Thread(target=self._worker, name=category)
        worker.start()

    def __del__(self):
        fd = self._fd
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                log.exception()

    def _send_output_event(self, s, final=False):
        if self._decoder is None:
            return

        s = self._decoder.decode(s, final=final)
        if len(s) == 0:
            return

        try:
            self._ide.send_event("output", {"category": self._category, "output": s})
        except Exception:
            pass  # channel to IDE is already closed

    def _worker(self):
        while self._fd is not None:
            try:
                s = os.read(self._fd, 0x1000)
            except Exception:
                break

            size = len(s)
            if size == 0:
                break

            # Tee the output first, before sending the "output" event.
            i = 0
            while i < size:
                written = os.write(self._tee_fd, s[i:])
                i += written
                if not written:
                    # This means that the output stream was closed from the other end.
                    # Do the same to the debuggee, so that it knows as well.
                    os.close(self._fd)
                    self._fd = None
                    break

            self._send_output_event(s)

        # Flush any remaining data in the incremental decoder.
        self._send_output_event(b"", final=True)
