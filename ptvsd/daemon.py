import sys

from ptvsd import wrapper
from ptvsd.socket import close_socket
from .exit_handlers import (
    ExitHandlers, UnsupportedSignalError,
    kill_current_proc)
from .session import DebugSession


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


# TODO: Inherit from Closeable.
# TODO: Inherit from Startable?

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
        self._session = None

        self._exithandlers = ExitHandlers()
        if addhandlers:
            self.install_exit_handlers()

    @property
    def pydevd(self):
        return self._pydevd

    @property
    def session(self):
        """The current session."""
        return self._session

    def install_exit_handlers(self):
        """Set the placeholder handlers."""
        self._exithandlers.install()

        try:
            self._exithandlers.add_atexit_handler(self._handle_atexit)
        except ValueError:
            pass
        for signum in self._exithandlers.SIGNALS:
            try:
                self._exithandlers.add_signal_handler(signum,
                                                      self._handle_signal)
            except ValueError:
                # Already added.
                pass
            except UnsupportedSignalError:
                # TODO: This shouldn't happen.
                pass

    def start(self):
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
        return self._pydevd

    # TODO: Add serve_forever().

    def start_session(self, session, threadname):
        """Start the debug session and remember it.

        If "session" is a socket then a session is created from it.
        """
        if self._closed:
            raise DaemonClosedError()
        if self._pydevd is None:
            raise RuntimeError('not started yet')
        if self._session is not None:
            raise RuntimeError('session already started')

        if not isinstance(session, DebugSession):
            client = session
            session = DebugSession(
                client,
                notify_closing=self._handle_session_closing,
                ownsock=True,
            )
        self._session = session
        self._session.start(
            threadname,
            self._pydevd.pydevd_notify,
            self._pydevd.pydevd_request,
        )
        return session

    def close(self):
        """Stop all loops and release all resources."""
        if self._closed:
            raise DaemonClosedError('already closed')
        self._closed = True

        session = self._session
        if session is not None:
            self._stop_session()
            normal, abnormal = session.wait_options()
            if (normal and not self.exitcode) or (abnormal and self.exitcode):
                self.wait_on_exit()

        if self._pydevd is not None:
            close_socket(self._pydevd)

    def re_build_breakpoints(self):
        """Restore the breakpoints to their last values."""
        if self._session is None:
            return
        return self._session.re_build_breakpoints()

    # internal methods

    def _stop_session(self):
        self._session.stop(self.exitcode)
        self._session.close()
        self._session = None

    def _handle_atexit(self):
        self._exiting_via_atexit_handler = True
        if not self._closed:
            self.close()
        if self._session is not None:
            self._session.wait_until_stopped()

    def _handle_signal(self, signum, frame):
        if not self._closed:
            self.close()
        sys.exit(0)

    # internal methods for PyDevdSocket().

    def _handle_pydevd_message(self, cmdid, seq, text):
        if self._session is None:
            # TODO: Do more than ignore?
            return
        self._session.handle_pydevd_message(cmdid, seq, text)

    def _handle_pydevd_close(self):
        if self._closed:
            return
        self.close()

    def _getpeername(self):
        if self._session is None:
            raise NotImplementedError
        return self._session.socket.getpeername()

    def _getsockname(self):
        if self._session is None:
            raise NotImplementedError
        return self._session.socket.getsockname()

    # internal methods for VSCodeMessageProcessor

    def _handle_session_closing(self, kill=False):
        if not self._closed:
            self.close()
        if kill and self.killonclose and not self._exiting_via_atexit_handler:
            kill_current_proc()
