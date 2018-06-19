import os
import ptvsd
import sys
import unittest

from _pydevd_bundle.pydevd_comm import (
    CMD_REDIRECT_OUTPUT,
    CMD_RUN,
    CMD_VERSION,
    CMD_SET_PROJECT_ROOTS,
)

from . import (
    OS_ID,
    HighlevelTest,
    HighlevelFixture,
)


from ptvsd.wrapper import INITIALIZE_RESPONSE

# TODO: Make sure we are handling the following properly:
#  * initialize args
#  * capabilities (sent in a response)
#  * setting breakpoints during config
#  * sending an "exit" event.


def _get_project_dirs():
    cwd = os.getcwd()
    pyd_path = os.path.join('ptvsd', '_vendored', 'pydevd')
    paths = []
    if cwd.endswith('ptvsd') or \
       cwd.endswith(pyd_path):
        return ''
    paths.append(cwd)
    return '\t'.join(paths)


class LifecycleTests(HighlevelTest, unittest.TestCase):
    """
    See https://code.visualstudio.com/docs/extensionAPI/api-debugging#_the-vs-code-debug-protocol-in-a-nutshell
    """  # noqa

    class FIXTURE(HighlevelFixture):
        lifecycle = None  # Make sure we don't cheat.

    def attach(self, expected_os_id, attach_args):
        version = self.debugger.VERSION
        self.fix.debugger.binder.singlesession = False
        addr = (None, 8888)
        daemon = self.vsc.start(addr)
        with self.vsc.wait_for_event('output'):
            daemon.wait_until_connected()
        try:
            with self.vsc.wait_for_event('initialized'):
                # initialize
                self.set_debugger_response(CMD_VERSION, version)
                req_initialize = self.send_request('initialize', {
                    'adapterID': 'spam',
                })

                # attach
                req_attach = self.send_request('attach', attach_args)

            # configuration
            req_config = self.send_request('configurationDone')

            # Normal ops would go here.

            # end
            #req_disconnect = self.send_request('disconnect')
        finally:
            received = self.vsc.received
            with self._fix.wait_for_events(['exited', 'terminated']):
                self.fix.close_ptvsd()
            daemon.close()
            #self.fix.close_ptvsd()

        self.assert_vsc_received(received, [
            self.new_event(
                'output',
                category='telemetry',
                output='ptvsd',
                data={'version': ptvsd.__version__}),
            self.new_response(req_initialize, **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(req_attach),
            self.new_response(req_config),
            self.new_event('process', **dict(
               name=sys.argv[0],
               systemProcessId=os.getpid(),
               isLocalProcess=True,
               startMethod='attach',
            )),
        ])
        self.assert_received(self.debugger, [
            self.debugger_msgs.new_request(CMD_VERSION,
                                           *['1.1', expected_os_id, 'ID']),
            self.debugger_msgs.new_request(CMD_REDIRECT_OUTPUT),
            self.debugger_msgs.new_request(CMD_SET_PROJECT_ROOTS,
                                           _get_project_dirs()),
            self.debugger_msgs.new_request(CMD_RUN),
        ])

    def test_attach(self):
        self.attach(expected_os_id=OS_ID, attach_args={})

    @unittest.skip('not implemented')
    def test_attach_exit_during_session(self):
        # TODO: Ensure we see the "terminated" and "exited" events.
        raise NotImplementedError

    def test_attach_from_unix_os(self):
        attach_args = {'options': 'WINDOWS_CLIENT=False'}
        self.attach(expected_os_id='UNIX', attach_args=attach_args)

    def test_attach_from_windows_os(self):
        attach_args = {'options': 'WINDOWS_CLIENT=True'}
        self.attach(expected_os_id='WINDOWS', attach_args=attach_args)

    def test_launch(self):
        version = self.debugger.VERSION
        addr = (None, 8888)
        with self.vsc.start(addr):
            with self.vsc.wait_for_event('initialized'):
                # initialize
                self.set_debugger_response(CMD_VERSION, version)
                req_initialize = self.send_request('initialize', {
                    'adapterID': 'spam',
                })

                # launch
                req_launch = self.send_request('launch')

            # configuration
            req_config = self.send_request('configurationDone')
            self.wait_for_pydevd('version', 'redirect-output',
                                 'run', 'set_project_roots')

            # Normal ops would go here.

            # end
            #with self.fix.wait_for_events(['exited', 'terminated']):
            req_disconnect = self.send_request('disconnect')

        self.assert_received(self.vsc, [
            self.new_event(
                'output',
                category='telemetry',
                output='ptvsd',
                data={'version': ptvsd.__version__}),
            self.new_response(req_initialize, **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(req_launch),
            self.new_response(req_config),
            #self.new_event('process', **dict(
            #    name=sys.argv[0],
            #    systemProcessId=os.getpid(),
            #    isLocalProcess=True,
            #    startMethod='launch',
            #)),
            #self.new_event('exited', exitCode=0),
            #self.new_event('terminated'),
            self.new_response(req_disconnect),
        ])
        self.assert_received(self.debugger, [
            self.debugger_msgs.new_request(CMD_VERSION,
                                           *['1.1', OS_ID, 'ID']),
            self.debugger_msgs.new_request(CMD_REDIRECT_OUTPUT),
            self.debugger_msgs.new_request(CMD_SET_PROJECT_ROOTS,
                                           _get_project_dirs()),
            self.debugger_msgs.new_request(CMD_RUN),
        ])
