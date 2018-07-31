import pydevd
import threading
import time

from _pydevd_bundle.pydevd_comm import get_global_debugger

from ptvsd._util import debug, new_hidden_thread
from ptvsd.pydevd_hooks import install, start_server
from ptvsd.socket import Address, create_server


def _pydevd_settrace(redirect_output=None, _pydevd=pydevd, **kwargs):
    if redirect_output is not None:
        kwargs.setdefault('stdoutToServer', redirect_output)
        kwargs.setdefault('stderrToServer', redirect_output)
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
    _pydevd.settrace(**kwargs)


# TODO: Split up enable_attach() to align with module organization.
# This should including making better use of Daemon (e,g, the
# start_server() method).
# Then move at least some parts to the appropriate modules.  This module
# is focused on running the debugger.
def enable_attach(address, redirect_output=True,
                  _pydevd=pydevd, _install=install,
                  on_attach=lambda: None, **kwargs):
    host, port = address

    def wait_for_connection(daemon, host, port):
        debugger = get_global_debugger()
        while debugger is None:
            time.sleep(0.1)
            debugger = get_global_debugger()

        debugger.ready_to_run = True
        server = create_server(host, port)
        client, _ = server.accept()
        daemon.start_session(client, 'ptvsd.Server')

        daemon.re_build_breakpoints()
        on_attach()

    daemon = _install(_pydevd,
                      address,
                      start_server=None,
                      start_client=(lambda daemon, h, port: daemon.start()),
                      singlesession=False,
                      **kwargs)

    connection_thread = threading.Thread(target=wait_for_connection,
                                         args=(daemon, host, port),
                                         name='ptvsd.listen_for_connection')
    connection_thread.pydev_do_not_trace = True
    connection_thread.is_pydev_daemon_thread = True
    connection_thread.daemon = True
    connection_thread.start()

    _pydevd.settrace(host=host,
                     stdoutToServer=redirect_output,
                     stderrToServer=redirect_output,
                     port=port,
                     suspend=False)

# def enable_attach(address,
#                   on_attach=(lambda: None),
#                   redirect_output=True,
#                   _pydevd=pydevd,
#                   _install=install,
#                   _settrace=_pydevd_settrace,
#                   **kwargs):
#     addr = Address.as_server(*address)
#     debug('installing ptvsd as server')
#     # pydevd.settrace() forces a "client" connection, so we trick it
#     # by setting start_client to start_server..
#     daemon = _install(
#         _pydevd,
#         addr,
#         start_client=start_server,
#         notify_session_debugger_ready=(lambda s: on_attach()),
#         singlesession=False,
#         **kwargs
#     )

#     def start_pydevd():
#         debug('enabling pydevd')
#         # Only pass the port so start_server() gets triggered.
#         # As noted above, we also have to trick settrace() because it
#         # *always* forces a client connection.
#         _settrace(
#             host=addr.host,
#             stdoutToServer=redirect_output,
#             stderrToServer=redirect_output,
#             port=addr.port,
#             suspend=False,
#             _pydevd=_pydevd,
#         )
#         debug('pydevd enabled')
#     t = new_hidden_thread('start-pydevd', start_pydevd)
#     t.start()

#     def wait(timeout=None):
#         t.join(timeout)
#         return not t.is_alive()

#     def debug_current_thread(suspend=False, **kwargs):
#         # Make sure that pydevd has finished starting before enabling
#         # in the current thread.
#         # t.join()
#         print('enabling pydevd (current thread)')
#         _settrace(
#             host=None,  # ignored
#             stdoutToServer=False,  # ignored
#             stderrToServer=False,  # ignored
#             port=None,  # ignored
#             suspend=suspend,
#             trace_only_current_thread=False,
#             overwrite_prev_trace=False,
#             patch_multiprocessing=False,
#             _pydevd=_pydevd,
#             **kwargs
#         )
#         print('pydevd enabled (current thread)')
#     return daemon, wait, debug_current_thread
