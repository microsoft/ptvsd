# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import atexit
import sys
import threading
import time

from ptvsd.__main__ import run_module, run_file, enable_attach as ptvsd_enable_attach # noqa
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


# TODO: not needed?
DONT_DEBUG = []
DEFAULT_PORT = 5678
LOCALHOST = 'localhost'

RUNNERS = {
    'module': run_module,  # python -m spam
    'script': run_file,  # python spam.py
    'code': run_file,  # python -c 'print("spam")'
    None: run_file,  # catchall
}


def debug(filename, port_num, debug_id, debug_options, run_as,
          _runners=RUNNERS, _extra=None, *args, **kwargs):
    # TODO: docstring
    if _extra is None:
        _extra = sys.argv[1:]
    address = (LOCALHOST, port_num)
    try:
        run = _runners[run_as]
    except KeyError:
        # TODO: fail?
        run = _runners[None]
    if _extra:
        args = _extra + list(args)
    run(address, filename, *args, **kwargs)


def enable_attach(address=('0.0.0.0', DEFAULT_PORT), redirect_output=True):
    ptvsd_enable_attach(address, redirect_output, _enable_attach=_enable_attach)


def _enable_attach(daemon, address, redirect_output,
                  _pydevd, _install, **kwargs):
    host, port = address

    pydevd_vm_type.setup_type()

    debugger = _pydevd.PyDB()

    # Mark connected only if it actually succeeded.
    _pydevd.bufferStdOutToServer = redirect_output
    _pydevd.bufferStdErrToServer = redirect_output

    debugger.set_trace_for_frame_and_parents(get_frame(), False,
                                            overwrite_prev_trace=False)

    CustomFramesContainer.custom_frames_lock.acquire()  # @UndefinedVariable
    try:
        for _frameId, custom_frame in dict_iter_items(
                CustomFramesContainer.custom_frames):
            debugger.set_trace_for_frame_and_parents(custom_frame.frame, False)
    finally:
        CustomFramesContainer.custom_frames_lock.release()  # @UndefinedVariable

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

    # As this is the first connection, also set tracing for any untraced threads
    debugger.set_tracing_for_untraced_contexts(ignore_frame=get_frame(),
                                                overwrite_prev_trace=False)

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

    connection_thread = threading.Thread(target=wait_for_connection,
                                        name='ptvsd.listen_for_connection')  # noqa
    connection_thread.daemon = True
    connection_thread.start()
