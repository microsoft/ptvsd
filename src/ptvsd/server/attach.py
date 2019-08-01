# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import sys
import warnings

import ptvsd.server.log
import ptvsd.server.multiproc
import ptvsd.server.options
import pydevd
from _pydevd_bundle.pydevd_constants import get_global_debugger
from pydevd_file_utils import get_abs_path_real_path_and_base_from_frame


def wait_for_attach(timeout=None):
    """If a remote debugger is attached, returns immediately. Otherwise,
    blocks until a remote debugger attaches to this process, or until the
    optional timeout occurs.

    Parameters
    ----------
    timeout : float, optional
        The timeout for the operation in seconds (or fractions thereof).
    """
    ptvsd.server.log.info('wait_for_attach()')
    dbg = get_global_debugger()
    if not bool(dbg):
        msg = 'wait_for_attach() called before enable_attach().'
        ptvsd.server.log.info(msg)
        raise AssertionError(msg)

    pydevd._wait_for_attach()


def enable_attach(
    address=(ptvsd.server.options.host, ptvsd.server.options.port),
    log_dir=None):
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
    log_dir : str, optional
        Name of the directory that debugger will create its log files in.
        If not specified, logging is disabled.

    Notes
    -----
    This function returns immediately after setting up the debugging server,
    and does not block program execution. If you need to block until debugger
    is attached, call `ptvsd.server.wait_for_attach`. The debugger can be detached
    and re-attached multiple times after `enable_attach` is called.

    Only the thread on which this function is called, and any threads that are
    created after it returns, will be visible in the debugger once it is
    attached. Any threads that are already running before this function is
    called will not be visible.
    """

    if log_dir:
        ptvsd.common.options.log_dir = log_dir
    ptvsd.server.log.to_file()
    ptvsd.server.log.info('enable_attach{0!r}', (address,))

    if is_attached():
        ptvsd.server.log.info('enable_attach() ignored - already attached.')
        return None, None

    # Ensure port is int
    host, port = address
    address = (host, port if type(port) is int else int(port))

    ptvsd.server.options.host, ptvsd.server.options.port = pydevd._enable_attach(address)

    if ptvsd.server.options.subprocess_notify:
        ptvsd.server.multiproc.notify_root(ptvsd.options.port)

    return (ptvsd.server.options.host, ptvsd.server.options.port)


def attach(address, redirect_output=None, log_dir=None):
    """Attaches this process to the debugger listening on a given address.

    Parameters
    ----------
    address : (str, int), optional
        Specifies the interface and port on which the debugger is listening
        for TCP connections. It is in the same format as used for
        regular sockets of the `socket.AF_INET` family, i.e. a tuple of
        ``(hostname, port)``.
    redirect_output : bool, optional
        (Deprecated) Specifies whether any output (on both `stdout` and `stderr`) produced
        by this program should be sent to the debugger. Default is ``True``.
    log_dir : str, optional
        Name of the directory that debugger will create its log files in.
        If not specified, logging is disabled.
    """

    if log_dir:
        ptvsd.common.options.log_dir = log_dir
    ptvsd.server.log.to_file()
    ptvsd.server.log.info('attach{0!r}', (address, redirect_output))

    if is_attached():
        ptvsd.server.log.info('attach() ignored - already attached.')
        return None, None

    # Ensure port is int
    host, port = address
    address = (host, port if type(port) is int else int(port))

    ptvsd.server.log.debug('pydevd.settrace()')
    pydevd.settrace(
        host=host,
        port=port,
        suspend=False,
        patch_multiprocessing=ptvsd.server.options.multiprocess)


def is_attached():
    """Returns ``True`` if debugger is attached, ``False`` otherwise."""
    dbg = get_global_debugger()
    return bool(dbg) and dbg.is_attached()


def break_into_debugger():
    """If a remote debugger is attached, pauses execution of all threads,
    and breaks into the debugger with current thread as active.
    """

    ptvsd.server.log.info('break_into_debugger()')

    if not is_attached():
        ptvsd.server.log.info('break_into_debugger() ignored - debugger not attached')
        return

    # Get the first frame in the stack that's not an internal frame.
    global_debugger = get_global_debugger()
    stop_at_frame = sys._getframe().f_back
    while stop_at_frame is not None and global_debugger.get_file_type(
            get_abs_path_real_path_and_base_from_frame(stop_at_frame)) == global_debugger.PYDEV_FILE:
        stop_at_frame = stop_at_frame.f_back


    # pydevd.settrace() only enables debugging of the current
    # thread and all future threads.  PyDevd is not enabled for
    # existing threads (other than the current one).  Consequently,
    # pydevd.settrace() must be called ASAP in the current thread.
    # See issue #509.
    #
    # This is tricky, however, because settrace() will block until
    # it receives a CMD_RUN message.  You can't just call it in a
    # thread to avoid blocking; doing so would prevent the current
    # thread from being debugged.
    pydevd.settrace(
        suspend=True,
        trace_only_current_thread=True,
        patch_multiprocessing=False,
        stop_at_frame=stop_at_frame,
    )
    stop_at_frame = None


def debug_this_thread():
    pydevd.settrace(suspend=False)
