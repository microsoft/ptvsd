import os
import os.path
from textwrap import dedent
import unittest

import ptvsd
from ptvsd.socket import Address
from ptvsd.wrapper import INITIALIZE_RESPONSE  # noqa
from tests.helpers.debugadapter import DebugAdapter
from tests.helpers.debugclient import EasyDebugClient as DebugClient
from tests.helpers.script import find_line, set_lock
from tests.helpers.vsc import parse_message, VSCMessages
from tests.helpers.workspace import Workspace, PathEntry

from . import (_get_version, _strip_pydevd_output,
    _strip_newline_output_events, lifecycle_handshake, TestsBase,
    LifecycleTestsBase)

ROOT = os.path.dirname(os.path.dirname(ptvsd.__file__))
PORT = 9876

class LifecycleTests(LifecycleTestsBase):

    def test_with_output(self):
        script = dedent("""
            import sys
            sys.stdout.write('ok')
            sys.stderr.write('ex')
            """)
        options = {'debugOptions':['RedirectOutput']}
        filename = self.write_script('spam.py', script)
        argv = [ filename]
        with DebugClient(port=PORT) as editor:
            adapter, session = editor.host_local_debugger(
                argv
            )
            with session.wait_for_event('exited'):
                with session.wait_for_event('thread'):
                    (req_initialize, req_launch, req_config, _, _, _
                     ) = lifecycle_handshake(session, 'launch', options=options)

                adapter.wait()

        # Skipping the 'thread exited' and 'terminated' messages which
        # may appear randomly in the received list.
        received = list(_strip_newline_output_events(session.received))
        self.assert_received(received, [
            self.new_version_event(session.received),
            self.new_response(req_initialize, **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(req_launch),
            self.new_response(req_config),
            self.new_event('process', **{
                'isLocalProcess': True,
                'systemProcessId': adapter.pid,
                'startMethod': 'launch',
                'name': filename,
            }),
            self.new_event('thread', reason='started', threadId=1),
            self.new_event('output', category='stdout',  output='ok'),
            self.new_event('output', category='stderr',  output='ex'),
            self.new_event('thread', reason='exited', threadId=1),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])


    def test_with_break_points(self):
        bp_line = 3
        script = dedent("""
            a = 1
            b = 2
            c = 3
            """)
        filename = self.write_script('spam.py', script)
        argv = [ filename]
        breakpoints = [{
            'source': {'path': filename},
            'breakpoints': [
                {'line': bp_line}
            ],
        }]

        with DebugClient(port=PORT, connecttimeout=3.0) as editor:
            adapter, session = editor.host_local_debugger(
                argv
            )
            with session.wait_for_event('terminated'):
                with session.wait_for_event('stopped') as result:
                    (req_initialize, req_launch, req_config, reqs_bps, _, _
                    ) = lifecycle_handshake(session, 'launch',
                                            breakpoints=breakpoints)
                req_bps, = reqs_bps  # There should only be one.
                tid = result['msg'].body['threadId']

                req_stacktrace = session.send_request(
                    'stackTrace',
                    threadId=tid,
                )

                with session.wait_for_event('continued'):
                    req_continue = session.send_request('continue', threadId=tid)

            adapter.wait()

        received = list(_strip_newline_output_events(session.received))
        del received[10]  # Module info for runpy.py
        del received[10].body.get('stackFrames')[1:3] # Ignore non-user stack trace.

        self.assert_received(received, [
            self.new_version_event(session.received),
            self.new_response(req_initialize, **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(req_launch),
            self.new_response(req_bps, **{
                'breakpoints': [{
                    'id': 1,
                    'line': bp_line,
                    'verified': True,
                }],
            }),
            self.new_response(req_config),
            self.new_event('process', **{
                'isLocalProcess': True,
                'systemProcessId': adapter.pid,
                'startMethod': 'launch',
                'name': filename,
            }),
            self.new_event('thread', reason='started', threadId=tid),
            self.new_event('stopped', reason='breakpoint', threadId=tid, text=None, description=None),
            self.new_event(
                'module',
                module={
                    'id': 1,
                    'name': '__main__',
                    'path': filename,
                    'package': None,
                },
                reason='new',
            ),
            self.new_response(req_stacktrace, seq=11, **{
                'totalFrames': 3,
                'stackFrames': [{
                    'id': 1,
                    'name': '<module>',
                    'source': {
                        'path': filename,
                        'sourceReference': 0,
                    },
                    'line': bp_line,
                    'column': 1,
                }],
            }),
            self.new_response(req_continue, seq=12),
            self.new_event('continued', seq=13, threadId=tid),
            self.new_event('thread', seq=14, reason='exited', threadId=tid),
            self.new_event('exited', seq=15, exitCode=0),
            self.new_event('terminated', seq=16),
        ])

    @unittest.skip('termination needs fixing')
    def test_with_conditional_break_points(self):
        bp_line = 4
        script = dedent("""
            a = 1
            b = 2
            for i in range(10):
                print(i)
            """)
        filename = self.write_script('spam.py', script)
        argv = [ filename]
        breakpoints = [{
            'source': {'path': filename},
            'breakpoints': [
                {'line': bp_line, 'condition':'i == 5'}
            ],
        }]
        options = {'debugOptions':['RedirectOutput']}

        with DebugClient(port=PORT, connecttimeout=3.0) as editor:
            adapter, session = editor.host_local_debugger(
                argv
            )
            with session.wait_for_event('terminated'):
                with session.wait_for_event('stopped') as result:
                    (req_initialize, req_launch, req_config, reqs_bps, _, _
                    ) = lifecycle_handshake(session, 'launch',
                                            breakpoints=breakpoints,
                                            options=options)
                req_bps, = reqs_bps  # There should only be one.
                tid = result['msg'].body['threadId']

                req_stacktrace = session.send_request(
                    'stackTrace',
                    threadId=tid,
                )

                with session.wait_for_event('continued'):
                    req_continue = session.send_request('continue', threadId=tid)

            adapter.wait()


    @unittest.skip('termination needs fixing')
    def test_terminating_program(self):
        bp_line = 10
        script = dedent("""
            import time

            while True:
                time.sleep(0.1)
            """)
        filename = self.write_script('spam.py', script)
        argv = [ filename]

        with DebugClient(port=PORT, connecttimeout=3.0) as editor:
            adapter, session = editor.host_local_debugger(
                argv
            )
            with session.wait_for_event('terminated'):
                (req_initialize, req_launch, req_config, _, _, _
                ) = lifecycle_handshake(session, 'launch')

                session.send_request('disconnect')

            adapter.wait()

    # def test_launch_ptvsd_client_with_output(self):
    #     argv = []
    #     waitscript = dedent("""
    #         import sys
    #         sys.stdout.write('ok')
    #         sys.stderr.write('ex')
    #         """)
    #     options = {'debugOptions':['RedirectOutput']}
    #     filename = self.write_script('spam.py', waitscript)
    #     script = self.write_debugger_script(filename, 9876, run_as='script')
    #     with DebugClient(port=9876) as editor:
    #         adapter, session = editor.host_local_debugger(
    #             argv,
    #             script,

    #         )
    #         with session.wait_for_event('exited'):
    #             with session.wait_for_event('thread'):
    #                 (req_initialize, req_launch, req_config, _, _, _
    #                  ) = lifecycle_handshake(session, 'launch', options=options)

    #             adapter.wait()

    #     # Skipping the 'thread exited' and 'terminated' messages which
    #     # may appear randomly in the received list.
    #     received = list(_strip_newline_output_events(session.received))
    #     self.assert_received(received, [
    #         self.new_version_event(session.received),
    #         self.new_response(req_initialize, **INITIALIZE_RESPONSE),
    #         self.new_event('initialized'),
    #         self.new_response(req_launch),
    #         self.new_response(req_config),
    #         self.new_event('process', **{
    #             'isLocalProcess': True,
    #             'systemProcessId': adapter.pid,
    #             'startMethod': 'launch',
    #             'name': filename,
    #         }),
    #         self.new_event('thread', reason='started', threadId=1),
    #         self.new_event('output', category='stdout',  output='ok'),
    #         self.new_event('output', category='stderr',  output='ex'),
    #         self.new_event('thread', reason='exited', threadId=1),
    #         self.new_event('exited', exitCode=0),
    #         self.new_event('terminated'),
    #     ])

    # def test_launch_ptvsd_client_with_break_points(self):
    #     argv = []
    #     waitscript = dedent("""
    #         a = 1
    #         b = 2
    #         c = 3
    #         """)
    #     options = {'debugOptions':['RedirectOutput']}
    #     filename = self.write_script('spam.py', waitscript)
    #     script = self.write_debugger_script(filename, 9876, run_as='script')
    #     breakpoints = [{
    #         'source': {'path': filename},
    #         'breakpoints': [
    #             {'line': 3}
    #         ],
    #     }]

    #     with DebugClient(port=9876, connecttimeout=3.0) as editor:
    #         adapter, session = editor.host_local_debugger(
    #             argv,
    #             script,

    #         )
    #         with session.wait_for_event('terminated'):
    #             with session.wait_for_event('stopped') as result:
    #                 (req_initialize, req_launch, req_config, reqs_bps, _, req_thread
    #                 ) = lifecycle_handshake(session, 'launch',
    #                                         breakpoints=breakpoints,
    #                                         options=options,
    #                                         threads=True)

    #             reqs_bp, = reqs_bps
    #             tid = result['msg'].body['threadId']
    #             req_stacktrace2 = session.send_request(
    #                 'stackTrace',
    #                 threadId=tid,
    #             )

    #             with session.wait_for_event('continued'):
    #                 session.send_request('continue', threadId= 1)

    #             adapter.wait()

    #     # Skipping the 'thread exited' and 'terminated' messages which
    #     # may appear randomly in the received list.
    #     received = list(_strip_newline_output_events(session.received))
    #     self.assert_received(received, [
    #         self.new_version_event(session.received),
    #         self.new_response(req_initialize, **INITIALIZE_RESPONSE),
    #         self.new_event('initialized'),
    #         self.new_response(req_launch),
    #         self.new_response(req_thread),
    #         self.new_response(reqs_bp),
    #         self.new_response(req_config),
    #         self.new_event('process', **{
    #             'isLocalProcess': True,
    #             'systemProcessId': adapter.pid,
    #             'startMethod': 'launch',
    #             'name': filename,
    #         }),
    #         self.new_event('thread', reason='started', threadId=tid),
    #         self.new_event('stopped', reason='breakpoint', threadId=tid),
    #         self.new_event('module'),
    #         self.new_event('module'),
    #         self.new_response(req_stacktrace2, **{
    #             'totalFrames':2,

    #         }),
    #         self.new_event('output', category='stdout',  output='bye'),
    #         self.new_event('thread', reason='exited', threadId=tid),
    #         self.new_event('exited', exitCode=0),
    #         self.new_event('terminated'),
    #     ])


