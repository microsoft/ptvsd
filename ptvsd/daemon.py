import atexit
import os
import platform
import signal
import sys

from ptvsd import wrapper
from ptvsd.socket import close_socket


def _wait_on_exit():
    if sys.__stdout__ is not None:
        try:
            import msvcrt
        except ImportError:
            sys.__stdout__.write('Press Enter to continue . . . ')
            sys.__stdout__.flush()
            sys.__stdin__.read(1)
        else:
            sys.__stdout__.write('Press any key to continue . . . ')
            sys.__stdout__.flush()
            msvcrt.getch()


class DaemonClosedError(RuntimeError):
    """Indicates that a Daemon was unexpectedly closed."""
    def __init__(self, msg='closed'):
        super(DaemonClosedError, self).__init__(msg)


class Daemon(object):
    """The process-level manager for the VSC protocol debug adapter."""

    exitcode = 0

    def __init__(self, wait_on_exit=_wait_on_exit,
                 addhandlers=True, killonclose=True):
        self.wait_on_exit = wait_on_exit
        self.killonclose = killonclose

        self._closed = False
        self._exiting_via_atexit_handler = False

        self._pydevd = None
        self._server = None
        self._client = None
        self._adapter = None

        self._signal_handlers = None
        self._atexit_handlers = None
        self._handlers_installed = False
        if addhandlers:
            self.install_exit_handlers()

    @property
    def pydevd(self):
        return self._pydevd

    @property
    def server(self):
        return self._server

    @property
    def client(self):
        return self._client

    @property
    def adapter(self):
        return self._adapter

    def start(self, server=None):
        """Return the "socket" to use for pydevd after setting it up."""
        if self._closed:
            raise DaemonClosedError()
        if self._pydevd is not None:
            raise RuntimeError('already started')
        self._pydevd = wrapper.PydevdSocket(
            self._handle_pydevd_message,
            self._handle_pydevd_close,
            self._getpeername,
            self._getsockname,
        )
        self._server = server
        return self._pydevd

    def install_exit_handlers(self):
        """Set the placeholder handlers."""
        if self._signal_handlers is not None:
            raise RuntimeError('exit handlers already installed')
        self._signal_handlers = {
            signal.SIGHUP: [],
        }
        self._atexit_handlers = []

        if platform.system() != 'Windows':
            try:
                for sig in self._signal_handlers:
                    signal.signal(sig, self._signal_handler)
            except ValueError:
                # Wasn't called in main thread!
                raise
        atexit.register(self._atexit_handler)

    def set_connection(self, client):
        """Set the client socket to use for the debug adapter.

        A VSC message loop is started for the client.
        """
        if self._closed:
            raise DaemonClosedError()
        if self._pydevd is None:
            raise RuntimeError('not started yet')
        if self._client is not None:
            raise RuntimeError('connection already set')
        self._client = client

        self._adapter = wrapper.VSCodeMessageProcessor(
            client,
            self._pydevd.pydevd_notify,
            self._pydevd.pydevd_request,
            self._handle_vsc_disconnect,
            self._handle_vsc_close,
        )
        name = 'ptvsd.Client' if self._server is None else 'ptvsd.Server'
        self._adapter.start(name)
        if self._signal_handlers is not None:
            self._add_signal_handlers()
            self._add_atexit_handler()
        return self._adapter

    def close(self):
        """Stop all loops and release all resources."""
        if self._closed:
            raise DaemonClosedError('already closed')
        self._closed = True

        if self._adapter is not None:
            normal, abnormal = self._adapter._wait_options()
            if (normal and not self.exitcode) or (abnormal and self.exitcode):
                self.wait_on_exit()

        if self._pydevd is not None:
            close_socket(self._pydevd)
        if self._client is not None:
            self._release_connection()

    def re_build_breakpoints(self):
        self.adapter.re_build_breakpoints()

    # internal methods

    def _signal_handler(self, signum, frame):
        for handle_signal in self._signal_handlers.get(signum, ()):
            handle_signal(signum, frame)

    def _atexit_handler(self):
        for handle_atexit in self._atexit_handlers:
            handle_atexit()

    def _add_atexit_handler(self):
        def handler():
            self._exiting_via_atexit_handler = True
            if not self._closed:
                self.close()
            if self._adapter is not None:
                # TODO: Do this in VSCodeMessageProcessor.close()?
                self._adapter._wait_for_server_thread()
        self._atexit_handlers.append(handler)

    def _add_signal_handlers(self):
        def handler(signum, frame):
            if not self._closed:
                self.close()
            sys.exit(0)
        self._signal_handlers[signal.SIGHUP].append(handler)

    def _release_connection(self):
        if self._adapter is not None:
            # TODO: This is not correct in the "attach" case.
            self._adapter.handle_pydevd_stopped(self.exitcode)
            self._adapter.close()
        close_socket(self._client)

    # internal methods for PyDevdSocket().

    def _handle_pydevd_message(self, cmdid, seq, text):
        if self._adapter is not None:
            self._adapter.on_pydevd_event(cmdid, seq, text)

    def _handle_pydevd_close(self):
        if self._closed:
            return
        self.close()

    def _getpeername(self):
        if self._client is None:
            raise NotImplementedError
        return self._client.getpeername()

    def _getsockname(self):
        if self._client is None:
            raise NotImplementedError
        return self._client.getsockname()

    # internal methods for VSCodeMessageProcessor

    def _handle_vsc_disconnect(self, kill=False):
        if not self._closed:
            self.close()
        if kill and self.killonclose and not self._exiting_via_atexit_handler:
            os.kill(os.getpid(), signal.SIGTERM)

    def _handle_vsc_close(self):
        if self._closed:
            return
        self.close()
