import os
import os.path

from tests.helpers.debugsession import Awaitable
from tests.helpers.resource import TestResources
from . import (
    _strip_newline_output_events, lifecycle_handshake,
    LifecycleTestsBase, DebugInfo, PORT
)

TEST_FILES = TestResources.from_module(__name__)


class BreakIntoDebuggerTests(LifecycleTestsBase):
    def run_test_attach(self, debug_info):
        options = {'debugOptions': ['RedirectOutput']}
        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            stopped = dbg.session.get_awaiter_for_event('stopped')
            (_, req_launch_attach, _, _, _, _) = lifecycle_handshake(
                session,
                debug_info.starttype,
                options=options)
            Awaitable.wait_all(req_launch_attach, stopped)
            thread_id = stopped.event.body['threadId']
            session.send_request('continue', threadId=thread_id)

        received = list(_strip_newline_output_events(dbg.session.received))
        self.assert_contains(received, [
            self.new_event('output', category='stdout', output='one'),
            self.new_event('output', category='stdout', output='two'),
            self.new_event('continued', threadId=thread_id),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])

    def run_test_attach2(self, debug_info):
        options = {'debugOptions': ['RedirectOutput']}
        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            stopped = dbg.session.get_awaiter_for_event('stopped')
            (_, req_launch_attach, _, _, _, _) = lifecycle_handshake(
                session,
                debug_info.starttype,
                options=options)
            Awaitable.wait_all(req_launch_attach, stopped)
            thread_id = stopped.event.body['threadId']
            req_disconnect = session.send_request('disconnect', restart=False)
            req_disconnect.wait()
            dbg.adapter._proc.terminate()

        received = list(_strip_newline_output_events(dbg.session.received))
        self.assert_contains(received, [
            self.new_event('stopped',
                           reason='step',
                           threadId=int(thread_id),
                           text=None,
                           description=None),
        ])

    def test_attach_enable_wait_and_break(self):
        # Uses enable_attach followed by wait_for_attach
        # before calling break_into_debugger
        filename = TEST_FILES.resolve('attach_test.py')
        cwd = os.path.dirname(filename)
        debug_info = DebugInfo(
            filename=filename,
            cwd=cwd,
            argv=['localhost', str(PORT)],
            env={'PTVSD_WAIT_FOR_ATTACH': 'True'},
            starttype='attach',
            attachtype='import',
            )
        self.run_test_attach(debug_info)

    def test_attach_enable_check_and_break(self):
        # Uses enable_attach followed by a loop that checks if the
        # debugger is attached before calling break_into_debugger
        filename = TEST_FILES.resolve('attach_test.py')
        cwd = os.path.dirname(filename)
        debug_info = DebugInfo(
            filename=filename,
            cwd=cwd,
            argv=['localhost', str(PORT)],
            env={'PTVSD_IS_ATTACHED': 'True'},
            starttype='attach',
            attachtype='import',
            )
        self.run_test_attach(debug_info)

    def test_attach_enable_and_break(self):
        # Uses enable_attach followed by break_into_debugger
        # not is_attached check or wait_for_debugger
        filename = TEST_FILES.resolve('attach_test.py')
        cwd = os.path.dirname(filename)
        debug_info = DebugInfo(
            filename=filename,
            cwd=cwd,
            argv=['localhost', str(PORT)],
            starttype='attach',
            attachtype='import',
            )
        self.run_test_attach2(debug_info)

    def test_launch(self):
        filename = TEST_FILES.resolve('launch_test.py')
        cwd = os.path.dirname(filename)
        debug_info = DebugInfo(filename=filename, cwd=cwd)
        options = {'debugOptions': ['RedirectOutput']}
        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            stopped = dbg.session.get_awaiter_for_event('stopped')
            (_, req_launch_attach, _, _, _, _) = lifecycle_handshake(
                session,
                debug_info.starttype,
                options=options)
            Awaitable.wait_all(req_launch_attach, stopped)
            thread_id = stopped.event.body['threadId']
            session.send_request('continue', threadId=thread_id)

        received = list(_strip_newline_output_events(dbg.session.received))
        self.assert_contains(received, [
            self.new_event('output', category='stdout', output='one'),
            self.new_event('output', category='stdout', output='two'),
            self.new_event('continued', threadId=thread_id),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])
