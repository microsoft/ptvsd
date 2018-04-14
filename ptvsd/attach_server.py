# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import atexit
import threading
import time

from ptvsd.__main__ import run_module, run_file, enable_attach as ptvsd_enable_attach  # noqa
import pydevd_tracing
import pydevd

from ptvsd.pydevd_hooks import install, start_server, start_client
from ptvsd.version import __version__, __author__  # noqa
from ptvsd.runner import run as no_debug_runner
from ptvsd.socket import create_client
from _pydevd_bundle import pydevd_io, pydevd_vm_type
from _pydevd_bundle.pydevd_constants import dict_iter_items, get_frame
from _pydevd_bundle.pydevd_custom_frames import CustomFramesContainer, custom_frames_container_init
from _pydevd_bundle.pydevd_additional_thread_info import PyDBAdditionalThreadInfo
from _pydevd_frame_eval.pydevd_frame_eval_main import frame_eval_func
from _pydevd_bundle.pydevd_comm import get_global_debugger, CMD_THREAD_SUSPEND

# TODO: not needed?
DONT_DEBUG = []
DEFAULT_PORT = 5678

_attached = threading.Event()


def wait_for_attach(timeout=None):
    """If a PTVS remote debugger is attached, returns immediately. Otherwise,
    blocks until a remote debugger attaches to this process, or until the
    optional timeout occurs.

    Parameters
    ----------
    timeout : float, optional
        The timeout for the operation in seconds (or fractions thereof).
    """
    _attached.wait(timeout)


def enable_attach(address=('0.0.0.0', DEFAULT_PORT), redirect_output=True):
    """Enables a client to attach to this process remotely to debug Python code.

    Parameters
    ----------
    address : (str, int), optional
        Specifies the interface and port on which the debugging server should
        listen for TCP connections. It is in the same format as used for
        regular sockets of the `socket.AF_INET` family, i.e. a tuple of
        ``(hostname, port)``. On client side, the server is identified by the
        Qualifier string in the usual ``'hostname:port'`` format, e.g.:
        ``'myhost.cloudapp.net:5678'``. Default is ``('0.0.0.0', 5678)``.
    redirect_output : bool, optional
        Specifies whether any output (on both `stdout` and `stderr`) produced
        by this program should be sent to the debugger. Default is ``True``.

    Notes
    -----
    This function returns immediately after setting up the debugging server,
    and does not block program execution. If you need to block until debugger
    is attached, call `ptvsd.wait_for_attach`. The debugger can be detached
    and re-attached multiple times after `enable_attach` is called.

    This function can only be called once during the lifetime of the process.
    On a second call, `AttachAlreadyEnabledError` is raised. In circumstances
    where the caller does not control how many times the function will be
    called (e.g. when a script with a single call is run more than once by
    a hosting app or framework), the call should be wrapped in ``try..except``.

    Only the thread on which this function is called, and any threads that are
    created after it returns, will be visible in the debugger once it is
    attached. Any threads that are already running before this function is
    called will not be visible.
    """
    if get_global_debugger() is not None:
        return
    _attached.clear()
    ptvsd_enable_attach(
        address, redirect_output, _enable_attach=_enable_attach)


def is_attached():
    """Returns ``True`` if debugger is attached, ``False`` otherwise."""
    return _attached.isSet()


def break_into_debugger():
    """If a PTVS remote debugger is attached, pauses execution of all threads,
    and breaks into the debugger with current thread as active.
    """
    debugger = get_global_debugger()
    if not _attached.isSet() or debugger is None:
        return

    t = pydevd.threadingCurrentThread()
    try:
        additional_info = t.additional_info
    except AttributeError:
        additional_info = PyDBAdditionalThreadInfo()
        t.additional_info = additional_info

    debugger.set_suspend(t, CMD_THREAD_SUSPEND)


def _enable_attach(daemon, address, redirect_output, _pydevd, _install,
                   **kwargs):
    host, port = address

    pydevd_vm_type.setup_type()

    debugger = _pydevd.PyDB()

    # Mark connected only if it actually succeeded.
    _pydevd.bufferStdOutToServer = redirect_output
    _pydevd.bufferStdErrToServer = redirect_output

    debugger.set_trace_for_frame_and_parents(
        get_frame(), False, overwrite_prev_trace=False)

    CustomFramesContainer.custom_frames_lock.acquire()
    try:
        for _frameId, custom_frame in dict_iter_items(
                CustomFramesContainer.custom_frames):
            debugger.set_trace_for_frame_and_parents(custom_frame.frame, False)
    finally:
        CustomFramesContainer.custom_frames_lock.release()

    t = _pydevd.threadingCurrentThread()
    try:
        additional_info = t.additional_info
    except AttributeError:
        additional_info = PyDBAdditionalThreadInfo()
        t.additional_info = additional_info

    frame_eval_for_tracing = debugger.frame_eval_func
    if frame_eval_func is not None and not _pydevd.forked:
        # Disable frame evaluation for Remote Debug Server
        frame_eval_for_tracing = None

    # note that we do that through pydevd_tracing.SetTrace so that the tracing
    # is not warned to the user!
    pydevd_tracing.SetTrace(debugger.trace_dispatch, frame_eval_for_tracing,
                            debugger.dummy_trace_dispatch)

    # Trace future threads?
    debugger.patch_threads()

    # Stop the tracing as the last thing before the actual shutdown for a clean exit.
    atexit.register(_pydevd.stoptrace)

    def wait_for_connection():
        debugger.connect(host, port)  # Note: connect can raise error.

        if redirect_output:
            _pydevd.init_stdout_redirect()
            _pydevd.init_stderr_redirect()

        _pydevd.patch_stdin(debugger)

        _pydevd.PyDBCommandThread(debugger).start()
        _pydevd.CheckOutputThread(debugger).start()
        daemon.re_build_breakpoints()

        _attached.set()

    connection_thread = threading.Thread(
        target=wait_for_connection, name='ptvsd.listen_for_connection')  # noqa
    connection_thread.daemon = True
    connection_thread.start()
