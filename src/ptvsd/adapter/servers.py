# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import functools
import os
import subprocess
import sys
import threading
import time

import ptvsd
from ptvsd.common import compat, fmt, json, log, messaging, sockets
from ptvsd.adapter import components

_lock = threading.RLock()

_connections = []
"""All servers that are connected to this adapter, in order in which they connected.
"""

_connections_changed = threading.Event()


class Connection(sockets.ClientConnection):
    """A debug server that is connected to the adapter.

    Servers that are not participating in a debug session are managed directly by the
    corresponding Connection instance.

    Servers that are participating in a debug session are managed by that sessions's
    Server component instance, but Connection object remains, and takes over again
    once the session ends.
    """

    def __init__(self, sock):
        from ptvsd.adapter import sessions

        self.server = None
        """The Server component, if this debug server belongs to Session.
        """

        self.pid = None

        stream = messaging.JsonIOStream.from_socket(sock, str(self))
        self.channel = messaging.JsonMessageChannel(stream, self)
        self.channel.start()

        try:
            info = self.channel.request("pydevdSystemInfo")
            process_info = info("process", json.object())
            self.pid = process_info("pid", int)
            self.ppid = process_info("ppid", int, optional=True)
            if self.ppid == ():
                self.ppid = None
            self.channel.name = stream.name = str(self)

            ptvsd_dir = os.path.dirname(os.path.dirname(ptvsd.__file__))
            # Note: we must check if 'ptvsd' is not already in sys.modules because the
            # evaluation of an import at the wrong time could deadlock Python due to
            # its import lock.
            #
            # So, in general this evaluation shouldn't do anything. It's only
            # important when pydevd attaches automatically to a subprocess. In this
            # case, we have to make sure that ptvsd is properly put back in the game
            # for users to be able to use it.v
            #
            # In this case (when the import is needed), this evaluation *must* be done
            # before the configurationDone request is sent -- if this is not respected
            # it's possible that pydevd already started secondary threads to handle
            # commands, in which case it's very likely that this command would be
            # evaluated at the wrong thread and the import could potentially deadlock
            # the program.
            #
            # Note 2: the sys module is guaranteed to be in the frame globals and
            # doesn't need to be imported.
            inject_ptvsd = """
if 'ptvsd' not in sys.modules:
    sys.path.insert(0, {ptvsd_dir!r})
    try:
        import ptvsd
    finally:
        del sys.path[0]
"""
            inject_ptvsd = fmt(inject_ptvsd, ptvsd_dir=ptvsd_dir)

            try:
                self.channel.request("evaluate", {"expression": inject_ptvsd})
            except messaging.MessageHandlingError:
                # Failure to inject is not a fatal error - such a subprocess can
                # still be debugged, it just won't support "import ptvsd" in user
                # code - so don't terminate the session.
                log.exception("Failed to inject ptvsd into {0}:", self, level="warning")

            with _lock:
                if any(conn.pid == self.pid for conn in _connections):
                    raise KeyError(
                        fmt("{0} is already connected to this adapter", self)
                    )
                _connections.append(self)
                _connections_changed.set()

        except Exception:
            log.exception("Failed to accept incoming server connection:")
            # If we couldn't retrieve all the necessary info from the debug server,
            # or there's a PID clash, we don't want to track this debuggee anymore,
            # but we want to continue accepting connections.
            self.channel.close()
            return

        parent_session = sessions.get(self.ppid)
        if parent_session is None:
            log.info("No active debug session for parent process of {0}.", self)
        else:
            try:
                parent_session.ide.notify_of_subprocess(self)
            except Exception:
                # This might fail if the IDE concurrently disconnects from the parent
                # session. We still want to keep the connection around, in case the
                # IDE reconnects later. If the parent session was "launch", it'll take
                # care of closing the remaining server connections.
                log.exception("Failed to notify parent session about {0}:", self)

    def __str__(self):
        return "Server" + fmt("[?]" if self.pid is None else "[pid={0}]", self.pid)

    def request(self, request):
        raise request.isnt_valid(
            "Requests from the debug server to the IDE are not allowed."
        )

    def event(self, event):
        pass

    def terminated_event(self, event):
        self.channel.close()

    def disconnect(self):
        with _lock:
            # If the disconnect happened while Server was being instantiated, we need
            # to tell it, so that it can clean up properly via Session.finalize(). It
            # will also take care of deregistering the connection in that case.
            if self.server is not None:
                self.server.disconnect()
            elif self in _connections:
                _connections.remove(self)
                _connections_changed.set()

    def attach_to_session(self, session):
        """Attaches this server to the specified Session as a Server component.

        Raises ValueError if the server already belongs to some session.
        """

        with _lock:
            if self.server is not None:
                raise ValueError
            log.info("Attaching {0} to {1}", self, session)
            self.server = Server(session, self)


class Server(components.Component):
    """Handles the debug server side of a debug session."""

    message_handler = components.Component.message_handler

    class Capabilities(components.Capabilities):
        PROPERTIES = {
            "supportsCompletionsRequest": False,
            "supportsConditionalBreakpoints": False,
            "supportsConfigurationDoneRequest": False,
            "supportsDataBreakpoints": False,
            "supportsDelayedStackTraceLoading": False,
            "supportsDisassembleRequest": False,
            "supportsEvaluateForHovers": False,
            "supportsExceptionInfoRequest": False,
            "supportsExceptionOptions": False,
            "supportsFunctionBreakpoints": False,
            "supportsGotoTargetsRequest": False,
            "supportsHitConditionalBreakpoints": False,
            "supportsLoadedSourcesRequest": False,
            "supportsLogPoints": False,
            "supportsModulesRequest": False,
            "supportsReadMemoryRequest": False,
            "supportsRestartFrame": False,
            "supportsRestartRequest": False,
            "supportsSetExpression": False,
            "supportsSetVariable": False,
            "supportsStepBack": False,
            "supportsStepInTargetsRequest": False,
            "supportsTerminateDebuggee": False,
            "supportsTerminateRequest": False,
            "supportsTerminateThreadsRequest": False,
            "supportsValueFormattingOptions": False,
            "exceptionBreakpointFilters": [],
            "additionalModuleColumns": [],
            "supportedChecksumAlgorithms": [],
        }

    def __init__(self, session, connection):
        assert connection.server is None
        with session:
            assert not session.server
            super(Server, self).__init__(session, channel=connection.channel)

            self.connection = connection

            assert self.session.pid is None
            if self.session.launcher and self.session.launcher.pid != self.pid:
                log.warning(
                    "Launcher reported PID={0}, but server reported PID={1}",
                    self.session.pid,
                    self.pid,
                )
            self.session.pid = self.pid

            session.server = self

    @property
    def pid(self):
        """Process ID of the debuggee process, as reported by the server."""
        return self.connection.pid

    @property
    def ppid(self):
        """Parent process ID of the debuggee process, as reported by the server."""
        return self.connection.ppid

    def initialize(self, request):
        assert request.is_request("initialize")
        request = self.channel.propagate(request)
        request.wait_for_response()
        self.capabilities = self.Capabilities(self, request.response)

    # Generic request handler, used if there's no specific handler below.
    @message_handler
    def request(self, request):
        # Do not delegate requests from the server by default. There is a security
        # boundary between the server and the adapter, and we cannot trust arbitrary
        # requests sent over that boundary, since they may contain arbitrary code
        # that the IDE will execute - e.g. "runInTerminal". The adapter must only
        # propagate requests that it knows are safe.
        raise request.isnt_valid(
            "Requests from the debug server to the IDE are not allowed."
        )

    # Generic event handler, used if there's no specific handler below.
    @message_handler
    def event(self, event):
        self.ide.propagate_after_start(event)

    @message_handler
    def initialized_event(self, event):
        # pydevd doesn't send it, but the adapter will send its own in any case.
        pass

    @message_handler
    def process_event(self, event):
        # If there is a launcher, it's handling the process event.
        if not self.launcher:
            self.ide.propagate_after_start(event)

    @message_handler
    def continued_event(self, event):
        # https://github.com/microsoft/ptvsd/issues/1530
        #
        # DAP specification says that a step request implies that only the thread on
        # which that step occurred is resumed for the duration of the step. However,
        # for VS compatibility, pydevd can operate in a mode that resumes all threads
        # instead. This is set according to the value of "steppingResumesAllThreads"
        # in "launch" or "attach" request, which defaults to true. If explicitly set
        # to false, pydevd will only resume the thread that was stepping.
        #
        # To ensure that the IDE is aware that other threads are getting resumed in
        # that mode, pydevd sends a "continued" event with "allThreadsResumed": true.
        # when responding to a step request. This ensures correct behavior in VSCode
        # and other DAP-conformant clients.
        #
        # On the other hand, VS does not follow the DAP specification in this regard.
        # When it requests a step, it assumes that all threads will be resumed, and
        # does not expect to see "continued" events explicitly reflecting that fact.
        # If such events are sent regardless, VS behaves erratically. Thus, we have
        # to suppress them specifically for VS.
        if self.ide.client_id not in ("visualstudio", "vsformac"):
            self.ide.propagate_after_start(event)

    @message_handler
    def exited_event(self, event):
        # If there is a launcher, it's handling the exit code.
        if not self.launcher:
            self.ide.propagate_after_start(event)

    @message_handler
    def terminated_event(self, event):
        # Do not propagate this, since we'll report our own.
        self.channel.close()

    def detach_from_session(self):
        with _lock:
            self.is_connected = False
            self.channel.handlers = self.connection
            self.channel.name = self.channel.stream.name = str(self.connection)
            self.connection.server = None

    def disconnect(self):
        with _lock:
            _connections.remove(self.connection)
            _connections_changed.set()
        super(Server, self).disconnect()


listen = functools.partial(Connection.listen, name="Server")


def stop_listening():
    try:
        Connection.listener.close()
    except Exception:
        log.exception(level="warning")


def connections():
    with _lock:
        return list(_connections)


def wait_for_connection(session, predicate, timeout=None):
    """Waits until there is a server with the specified PID connected to this adapter,
    and returns the corresponding Connection.

    If there is more than one server connection already available, returns the oldest
    one.
    """

    def wait_for_timeout():
        time.sleep(timeout)
        wait_for_timeout.timed_out = True
        with _lock:
            _connections_changed.set()

    wait_for_timeout.timed_out = timeout == 0
    if timeout:
        thread = threading.Thread(
            target=wait_for_timeout, name="servers.wait_for_connection() timeout"
        )
        thread.daemon = True
        thread.start()

    if timeout != 0:
        log.info("{0} waiting for connection from debug server...", session)
    while True:
        with _lock:
            _connections_changed.clear()
            conns = (conn for conn in _connections if predicate(conn))
            conn = next(conns, None)
            if conn is not None or wait_for_timeout.timed_out:
                return conn
        _connections_changed.wait()


def wait_until_disconnected():
    """Blocks until all debug servers disconnect from the adapter.

    If there are no server connections, waits until at least one is established first,
    before waiting for it to disconnect.
    """
    while True:
        _connections_changed.wait()
        with _lock:
            _connections_changed.clear()
            if not len(_connections):
                return


def dont_expect_connections():
    """Unblocks any pending wait_until_disconnected() call that is waiting on the
    first server to connect.
    """
    with _lock:
        _connections_changed.set()


def inject(pid, ptvsd_args):
    host, port = Connection.listener.getsockname()

    cmdline = [
        sys.executable,
        compat.filename(os.path.dirname(ptvsd.__file__)),
        "--client",
        "--host",
        host,
        "--port",
        str(port),
    ]
    cmdline += ptvsd_args
    cmdline += ["--pid", str(pid)]

    log.info("Spawning attach-to-PID debugger injector: {0!r}", cmdline)
    try:
        injector = subprocess.Popen(
            cmdline,
            bufsize=0,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except Exception as exc:
        log.exception("Failed to inject debug server into process with PID={0}", pid)
        raise messaging.MessageHandlingError(
            "Failed to inject debug server into process with PID={0}: {1}", pid, exc
        )

    # We need to capture the output of the injector - otherwise it can get blocked
    # on a write() syscall when it tries to print something.

    def capture_output():
        while True:
            line = injector.stdout.readline()
            if not line:
                break
            log.info("Injector[PID={0}] output:\n{1}", pid, line.rstrip())
        log.info("Injector[PID={0}] exited.", pid)

    thread = threading.Thread(
        target=capture_output, name=fmt("Injector[PID={0}] output", pid)
    )
    thread.daemon = True
    thread.start()
