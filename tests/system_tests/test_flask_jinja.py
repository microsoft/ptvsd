import os
import os.path
import unittest

from tests.helpers.resource import TestResources
from tests.helpers.webhelper import get_web_string
from . import (
    _strip_newline_output_events, lifecycle_handshake,
    LifecycleTestsBase, DebugInfo,
)


TEST_FILES = TestResources.from_module(__name__)


class FlaskBreakpointTests(LifecycleTestsBase):
    def run_test_with_break_points(self, debug_info,
                                   bp_filename, bp_line):
        options = {'debugOptions': ['RedirectOutput']}
        breakpoints = [{
            'source': {
                'path': bp_filename
            },
            'breakpoints': [{
                'line': bp_line
            }]
        }]

        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            with session.wait_for_event('stopped') as result:
                (_, req_launch_attach, _, _, _, _,
                 ) = lifecycle_handshake(session, debug_info.starttype,
                                         options=options,
                                         breakpoints=breakpoints)
                req_launch_attach.wait()
            event = result['msg']
            tid = event.body['threadId']

            req_stacktrace = session.send_request(
                'stackTrace',
                threadId=tid,
            )
            req_stacktrace.wait()
            stacktrace = req_stacktrace.resp.body

            session.send_request(
                'continue',
                threadId=tid,
            )

        received = list(_strip_newline_output_events(session.received))

        self.assertGreaterEqual(stacktrace['totalFrames'], 1)
        self.assert_is_subset(stacktrace, {
            # We get Python and PTVSD frames as well.
            # 'totalFrames': 2,
            'stackFrames': [{
                'id': 1,
                'name': '<module>',
                'source': {
                    'sourceReference': 0
                },
                'line': bp_line,
                'column': 1,
            }],
        })

        self.assert_contains(received, [
            self.new_event(
                'stopped',
                reason='breakpoint',
                threadId=tid,
                text=None,
                description=None,
            ),
            self.new_event('continued', threadId=tid),
            self.new_event('output', category='stdout', output='yes'),
            self.new_event('output', category='stderr', output='no'),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])


class LaunchFileTests(FlaskBreakpointTests):
    @unittest.skip('Not ready')
    def test_with_route_break_points(self):
        filename = TEST_FILES.resolve('app.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_break_points(
            DebugInfo(
                module='flask',
                argv=['run', '--no-debugger', '--no-reload'],
                env={
                    'FLASK_APP': 'app.py'
                },
                cwd=cwd),
            filename, bp_line=10,
        )

    @unittest.skip('Not ready')
    def test_with_template_break_points(self):
        filename = TEST_FILES.resolve('templates', 'hello.html')
        cwd = os.path.dirname(filename)
        self.run_test_with_break_points(
            DebugInfo(
                module='flask',
                argv=['run', '--no-debugger', '--no-reload'],
                cwd=cwd),
            filename, bp_line=8,
        )
