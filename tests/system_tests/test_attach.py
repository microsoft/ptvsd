import os
import os.path
import unittest

from textwrap import dedent

import ptvsd
from ptvsd.socket import Address
from ptvsd.wrapper import INITIALIZE_RESPONSE  # noqa
from tests.helpers.debugadapter import DebugAdapter
from tests.helpers.debugclient import EasyDebugClient as DebugClient
from tests.helpers.debugsession import Awaitable

from . import (
    _strip_newline_output_events,
    lifecycle_handshake,
    LifecycleTestsBase,
)

ROOT = os.path.dirname(os.path.dirname(ptvsd.__file__))
PORT = 9876
CONNECT_TIMEOUT = 3.0
ENV = {'PYTHONPATH': ROOT}
TEST_FILES_DIR = os.path.join(ROOT, 'tests', 'resources', 'system_tests',
                              'test_attach')


class AttachLifecycleTests(LifecycleTestsBase):
    IS_MODULE = False

    def test_with_output(self):
        addr = Address('localhost', PORT)
        script = dedent("""
            import ptvsd
            ptvsd.enable_attach({})
            ptvsd.wait_for_attach()
            import sys
            sys.stdout.write('ok')
            sys.stderr.write('ex')
            """).format(tuple(addr))
        filename = self.write_script('spam.py', script)
        with DebugAdapter.start_embedded(addr, filename, env=ENV) as adapter:
            with DebugClient() as editor:
                session = editor.attach_socket(addr, adapter)

                terminated = session.get_awaiter_for_event('terminated')
                exited = session.get_awaiter_for_event('exited')

                (req_initialize, req_launch, req_config, _, _,
                 _) = lifecycle_handshake(session, 'attach')

                Awaitable.wait_all(req_launch, terminated, exited)
                adapter.wait()

        received = list(_strip_newline_output_events(session.received))
        self.assert_contains(received, [
            self.new_version_event(session.received),
            self.new_response(req_initialize.req, **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(req_launch.req),
            self.new_response(req_config.req),
            self.new_event(
                'process', **{
                    'isLocalProcess': True,
                    'systemProcessId': adapter.pid,
                    'startMethod': 'attach',
                    'name': filename,
                }),
            self.new_event('output', output='ok', category='stdout'),
            self.new_event('output', output='ex', category='stderr'),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])

    # def test_with_break_points(self):
    #     addr = Address('localhost', PORT)
    #     script = dedent("""
    #         import ptvsd
    #         ptvsd.enable_attach({})

    #         a = 1
    #         b = 2
    #         # <Token>
    #         c = 3
    #         """).format(tuple(addr))
    #     filepath = self.write_script('spam.py', script)
    #     bp_line = self.find_line(filepath, 'Token')
    #     breakpoints = [{
    #         "source": {
    #             "path": filepath
    #         },
    #         "breakpoints": [{
    #             "line": bp_line
    #         }]
    #     }]

    #     with DebugAdapter.start_embedded(addr, filepath, env=ENV) as adapter:
    #         with DebugClient() as editor:
    #             session = editor.attach_socket(addr, adapter)

    #             terminated = session.get_awaiter_for_event('terminated')
    #             exited = session.get_awaiter_for_event('exited')

    #             with session.wait_for_event("stopped") as result:
    #                 (
    #                     req_initialize,
    #                     req_launch,
    #                     req_config,
    #                     reqs_bps,
    #                     _,
    #                     _
    #                  ) = lifecycle_handshake(session,
    #                                          'attach',
    #                                          breakpoints=breakpoints)

    #             req_bps, = reqs_bps  # There should only be one.
    #             tid = result["msg"].body["threadId"]

    #             stacktrace = session.send_request("stackTrace", threadId=tid)

    #             continued = session.get_awaiter_for_event('continued')
    #             cont = session.send_request("continue", threadId=tid)

    #         Awaitable.wait_all(terminated, exited, continued)
    #         adapter.wait()

    #     received = list(_strip_newline_output_events(session.received))
    #     print(received)
    #     self.assertGreaterEqual(stacktrace.resp.body["totalFrames"], 1)
    #     self.assert_is_subset(stacktrace.resp, self.new_response(
    #                 stacktrace.req,
    #                 **{
    #                     # We get Python and PTVSD frames as well.
    #                     # "totalFrames": 2,
    #                     "stackFrames": [{
    #                         "id": 1,
    #                         "name": "<module>",
    #                         "source": {
    #                             "path": filepath,
    #                             "sourceReference": 0
    #                         },
    #                         "line": bp_line,
    #                         "column": 1,
    #                     }],
    #                 }))

    #     # Skipping the 'thread exited' and 'terminated' messages which
    #     # may appear randomly in the received list.
    #     self.assert_contains(
    #         received,
    #         [
    #             self.new_version_event(session.received),
    #             self.new_response(req_initialize.req, **INITIALIZE_RESPONSE),
    #             self.new_event("initialized"),
    #             self.new_response(req_launch.req),
    #             self.new_response(
    #                 req_bps.req, **{
    #                     "breakpoints": [{
    #                         "id": 1,
    #                         "line": bp_line,
    #                         "verified": True
    #                     }]
    #                 }),
    #             self.new_response(req_config.req),
    #             self.new_event(
    #                 "process", **{
    #                     "isLocalProcess": True,
    #                     "systemProcessId": adapter.pid,
    #                     "startMethod": "launch",
    #                     "name": expected_module,
    #                 }),
    #             self.new_event("thread", reason="started", threadId=tid),
    #             self.new_event(
    #                 "stopped",
    #                 reason="breakpoint",
    #                 threadId=tid,
    #                 text=None,
    #                 description=None,
    #             ),
    #             self.new_response(cont.req),
    #             self.new_event("continued", threadId=tid),
    #         ],
    #     )

    @unittest.skip('Needs fixing')
    def test_with_handled_exceptions(self):
        addr = Address('localhost', PORT)
        script = dedent("""
            import ptvsd
            ptvsd.enable_attach({})
            ptvsd.wait_for_attach()

            try:
                raise ArithmeticError('Hello')
            except Exception:
                pass
            import sys
            sys.stdout.write('end')
            """).format(tuple(addr))
        filename = self.write_script('spam.py', script)
        excbreakpoints = [{"filters": ["uncaught"]}]

        with DebugAdapter.start_embedded(addr, filename, env=ENV) as adapter:
            with DebugClient() as editor:
                session = editor.attach_socket(addr, adapter)

                terminated = session.get_awaiter_for_event('terminated')
                exited = session.get_awaiter_for_event('exited')
                output = session.get_awaiter_for_event(
                    'output', lambda e: e.body["category"] == "stdout")

                (_, req_attach, _, _, _, _) = lifecycle_handshake(
                    session, 'attach', excbreakpoints=excbreakpoints)

                Awaitable.wait_all(req_attach, output, terminated, exited)
                adapter.wait()

    def test_with_raised_exceptions(self):
        addr = Address('localhost', PORT)
        filename = os.path.join(TEST_FILES_DIR,
                                'test_with_raised_exceptions.py')
        excbreakpoints = [{"filters": ["raised", "uncaught"]}]
        with DebugAdapter.start_embedded(
                addr, filename, argv=['localhost', str(PORT)],
                env=ENV) as adapter:
            with DebugClient() as editor:
                session = editor.attach_socket(addr, adapter)

                stopped = session.get_awaiter_for_event('stopped')

                (_, req_attach, _, _, _, _) = lifecycle_handshake(
                    session, 'attach', excbreakpoints=excbreakpoints)

                stopped.wait()

                thread_id = stopped.event.body["threadId"]
                ex_info = session.send_request(
                    'exceptionInfo', threadId=thread_id)
                ex_info.wait()

                terminated = session.get_awaiter_for_event('terminated')
                exited = session.get_awaiter_for_event('exited')
                output = session.get_awaiter_for_event(
                    'output', lambda e: e.body["category"] == "stdout")
                continued = session.get_awaiter_for_event('continued')
                session.send_request("continue", threadId=thread_id)

                Awaitable.wait_all(req_attach, output, terminated, exited,
                                   continued)
                adapter.wait()

        expected_trace = "  File \"{}\", line 7, in <module>\n    raise ArithmeticError('Hello')\n".format(  # noqa
            filename)
        self.assert_is_subset(
            ex_info.resp.body, {
                "exceptionId": "ArithmeticError",
                "description": "ArithmeticError('Hello',)",
                "breakMode": "always",
                "details": {
                    "typeName": "ArithmeticError",
                    "message": "ArithmeticError('Hello',)",
                    "stackTrace": expected_trace,
                    "source": filename
                }
            })
