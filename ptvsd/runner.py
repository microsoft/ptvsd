# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import atexit
import os
import platform
import pydevd
import signal
import sys
import time
import threading
import traceback

from ptvsd.daemon import DaemonClosedError
from ptvsd.pydevd_hooks import start_client
from ptvsd.socket import close_socket
from ptvsd.wrapper import (
    WAIT_FOR_THREAD_FINISH_TIMEOUT, VSCLifecycleMsgProcessor)
from pydevd import init_stdout_redirect, init_stderr_redirect


HOSTNAME = 'localhost'
WAIT_FOR_LAUNCH_REQUEST_TIMEOUT = 10000
OUTPUT_POLL_PERIOD = 0.3


def run(address, filename, is_module, *args, **kwargs):
    # TODO: client/server -> address
    if not start_message_processor(*address):
        return

    debugger = pydevd.PyDB()
    # We do not want some internal methods to get executed in non-debug mode.
    debugger.init_matplotlib_support = lambda *arg: None
    debugger.run(
        file=filename,
        globals=None,
        locals=None,
        is_module=is_module,
        set_trace=False)
    # Wait for some time (a little longer than output redirection polling).
    # This is necessary to ensure all output is captured and redirected.
    time.sleep(OUTPUT_POLL_PERIOD + 0.1)


def start_message_processor(host, port_num):
    launch_notification = threading.Event()

    daemon = Daemon(
        notify_launch=launch_notification.set,
        addhandlers=True, killonclose=True)
    start_client(daemon, host, port_num)

    return launch_notification.wait(WAIT_FOR_LAUNCH_REQUEST_TIMEOUT)


class OutputRedirection(object):

    def __init__(self, on_output=lambda category, output: None):
        self._on_output = on_output
        self._stopped = False
        self._thread = None

    def start(self):
        init_stdout_redirect()
        init_stderr_redirect()
        self._thread = threading.Thread(
            target=self._run, name='ptvsd.output.redirection')
        self._thread.pydev_do_not_trace = True
        self._thread.is_pydev_daemon_thread = True
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        if self._stopped:
            return

        self._stopped = True
        self._thread.join(WAIT_FOR_THREAD_FINISH_TIMEOUT)

    def _run(self):
        import sys
        while not self._stopped:
            self._check_output(sys.stdoutBuf, 'stdout')
            self._check_output(sys.stderrBuf, 'stderr')
            time.sleep(OUTPUT_POLL_PERIOD)

    def _check_output(self, out, category):
        '''Checks the output to see if we have to send some buffered,
        output to the debug server

        @param out: sys.stdout or sys.stderr
        @param category: stdout or stderr
        '''

        try:
            v = out.getvalue()

            if v:
                self._on_output(category, v)
        except Exception:
            traceback.print_exc()


# TODO: Inherit from ptvsd.daemon.Daemon.

class Daemon(object):
    """The process-level manager for the VSC protocol debug adapter."""

    def __init__(self,
                 notify_launch=lambda: None,
                 addhandlers=True,
                 killonclose=True):

        self.exitcode = 0
        self.exiting_via_exit_handler = False

        self.addhandlers = addhandlers
        self.killonclose = killonclose
        self._notify_launch = notify_launch

        self._closed = False
        self._client = None
        self._adapter = None

    def start(self):
        if self._closed:
            raise DaemonClosedError()

        self._output_monitor = OutputRedirection(self._send_output)
        self._output_monitor.start()

        return None

    def start_session(self, client):
        """Set the client socket to use for the debug adapter.

        A VSC message loop is started for the client.
        """
        if self._closed:
            raise DaemonClosedError()
        if self._client is not None:
            raise RuntimeError('connection already set')
        self._client = client

        self._adapter = VSCodeMessageProcessor(
            client,
            notify_disconnecting=self._handle_vsc_disconnect,
            notify_closing=self._handle_vsc_close,
            notify_launch=self._notify_launch,
        )
        self._adapter.start()
        if self.addhandlers:
            self._add_atexit_handler()
            self._set_signal_handlers()
        return self._adapter

    def close(self):
        """Stop all loops and release all resources."""
        self._output_monitor.stop()
        if self._closed:
            raise DaemonClosedError('already closed')
        self._closed = True

        if self._client is not None:
            self._release_connection()

    # internal methods

    def _add_atexit_handler(self):

        def handler():
            self.exiting_via_exit_handler = True
            if not self._closed:
                self.close()
            if self._adapter is not None:
                self._adapter._wait_for_server_thread()

        atexit.register(handler)

    def _set_signal_handlers(self):
        if platform.system() == 'Windows':
            return None

        def handler(signum, frame):
            if not self._closed:
                self.close()
            sys.exit(0)

        signal.signal(signal.SIGHUP, handler)

    def _release_connection(self):
        if self._adapter is not None:
            self._adapter.handle_stopped(self.exitcode)
            self._adapter.close()
        close_socket(self._client)

    # internal methods for VSCLifecycleProcessor

    def _handle_vsc_disconnect(self, kill=False):
        if not self._closed:
            self.close()
        if kill and self.killonclose and not self.exiting_via_exit_handler:
            os.kill(os.getpid(), signal.SIGTERM)

    def _handle_vsc_close(self):
        if self._closed:
            return
        self.close()

    def _send_output(self, category, output):
        self._adapter.send_event('output', category=category, output=output)


class VSCodeMessageProcessor(VSCLifecycleMsgProcessor):
    """IPC JSON message processor for VSC debugger protocol.

    This translates between the VSC debugger protocol and the pydevd
    protocol.
    """

    def on_invalid_request(self, request, args):
        # TODO: docstring
        self.send_response(request, success=True)
