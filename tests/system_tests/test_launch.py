import os
import os.path
from textwrap import dedent
import unittest

import ptvsd
from ptvsd.wrapper import INITIALIZE_RESPONSE  # noqa
from tests.helpers.debugclient import EasyDebugClient as DebugClient
from tests.helpers.script import find_line

from . import (
    _strip_newline_output_events,
    lifecycle_handshake,
    LifecycleTestsBase,
)

ROOT = os.path.dirname(os.path.dirname(ptvsd.__file__))
PORT = 9876


class FileLifecycleTests(LifecycleTestsBase):
    def create_source_file(self, file_name, source):
        return self.write_script(file_name, source)

    def get_cwd(self):
        return None

    def find_line(self, filepath, label):
        with open(filepath) as scriptfile:
            script = scriptfile.read()
        return find_line(script, label)

    def get_test_info(self, source):
        filepath = self.create_source_file("spam.py", source)
        env = None
        expected_module = filepath
        argv = [filepath]
        return ("spam.py", filepath, env, expected_module, False, argv,
                self.get_cwd())

    def test_with_output(self):
        source = dedent("""
            import sys
            sys.stdout.write('ok')
            sys.stderr.write('ex')
            """)
        options = {"debugOptions": ["RedirectOutput"]}
        (filename, filepath, env, expected_module, is_module, argv,
         cwd) = self.get_test_info(source)

        with DebugClient(port=PORT) as editor:
            adapter, session = editor.host_local_debugger(
                argv, env=env, cwd=cwd)
            with session.wait_for_event("exited"):
                with session.wait_for_event("thread"):
                    (
                        req_initialize,
                        req_launch,
                        req_config,
                        _,
                        _,
                        _,
                    ) = lifecycle_handshake(
                        session, "launch", options=options)

            adapter.wait()

        # Skipping the 'thread exited' and 'terminated' messages which
        # may appear randomly in the received list.
        received = list(_strip_newline_output_events(session.received))
        self.assert_received(
            received[:-3],
            [
                self.new_version_event(session.received),
                self.new_response(req_initialize, **INITIALIZE_RESPONSE),
                self.new_event("initialized"),
                self.new_response(req_launch),
                self.new_response(req_config),
                self.new_event(
                    "process", **{
                        "isLocalProcess": True,
                        "systemProcessId": adapter.pid,
                        "startMethod": "launch",
                        "name": expected_module,
                    }),
                self.new_event("thread", reason="started", threadId=1),
                self.new_event("output", category="stdout", output="ok"),
                self.new_event("output", category="stderr", output="ex"),
            ],
        )

    def test_with_arguments(self):
        source = dedent("""
            import sys
            print(len(sys.argv))
            for arg in sys.argv:
                print(arg)
            """)
        options = {"debugOptions": ["RedirectOutput"]}
        (filename, filepath, env, expected_module, is_module, argv,
         cwd) = self.get_test_info(source)

        with DebugClient(port=PORT) as editor:
            adapter, session = editor.host_local_debugger(
                argv=argv + ["1", "Hello", "World"], env=env, cwd=cwd)
            with session.wait_for_event("exited"):
                with session.wait_for_event("thread"):
                    (
                        req_initialize,
                        req_launch,
                        req_config,
                        _,
                        _,
                        _,
                    ) = lifecycle_handshake(
                        session, "launch", options=options)

            adapter.wait()

        # Skipping the 'thread exited' and 'terminated' messages which
        # may appear randomly in the received list.
        received = list(_strip_newline_output_events(session.received))
        self.assert_received(
            received[:-3],
            [
                self.new_version_event(session.received),
                self.new_response(req_initialize, **INITIALIZE_RESPONSE),
                self.new_event("initialized"),
                self.new_response(req_launch),
                self.new_response(req_config),
                self.new_event(
                    "process", **{
                        "isLocalProcess": True,
                        "systemProcessId": adapter.pid,
                        "startMethod": "launch",
                        "name": expected_module,
                    }),
                self.new_event("thread", reason="started", threadId=1),
                self.new_event("output", category="stdout", output="4"),
                self.new_event(
                    "output", category="stdout", output=expected_module),
                self.new_event("output", category="stdout", output="1"),
                self.new_event("output", category="stdout", output="Hello"),
                self.new_event("output", category="stdout", output="World"),
            ],
        )

    def test_with_break_points(self):
        source = dedent("""
            a = 1
            b = 2
            # <Token>
            c = 3
            """)
        (filename, filepath, env, expected_module, is_module, argv,
         cwd) = self.get_test_info(source)

        bp_line = self.find_line(filepath, 'Token')
        breakpoints = [{
            "source": {
                "path": filepath
            },
            "breakpoints": [{
                "line": bp_line
            }]
        }]

        with DebugClient(port=PORT, connecttimeout=3.0) as editor:
            adapter, session = editor.host_local_debugger(
                argv, env=env, cwd=cwd)
            with session.wait_for_event("terminated"):
                with session.wait_for_event("stopped") as result:
                    (
                        req_initialize,
                        req_launch,
                        req_config,
                        reqs_bps,
                        _,
                        _,
                    ) = lifecycle_handshake(
                        session, "launch", breakpoints=breakpoints)
                req_bps, = reqs_bps  # There should only be one.
                tid = result["msg"].body["threadId"]

                req_stacktrace = session.send_request(
                    "stackTrace", threadId=tid)

                with session.wait_for_event("continued"):
                    req_continue = session.send_request(
                        "continue", threadId=tid)

            adapter.wait()

        received = list(_strip_newline_output_events(session.received))
        del received[10]  # Module info for runpy.py
        stack_frames = received[10].body.get("stackFrames")
        stack_frames[1]["id"] = 1
        del stack_frames[1:len(stack_frames)]  # Ignore non-user stack trace.
        received[10].body["totalFrames"] = 1
        # Ensure package is None, changes based on version of Python.
        received[9].body["module"]["package"] = None

        # Skipping the 'thread exited' and 'terminated' messages which
        # may appear randomly in the received list.
        self.assert_received(
            received[:-3],
            [
                self.new_version_event(session.received),
                self.new_response(req_initialize, **INITIALIZE_RESPONSE),
                self.new_event("initialized"),
                self.new_response(req_launch),
                self.new_response(
                    req_bps, **{
                        "breakpoints": [{
                            "id": 1,
                            "line": bp_line,
                            "verified": True
                        }]
                    }),
                self.new_response(req_config),
                self.new_event(
                    "process", **{
                        "isLocalProcess": True,
                        "systemProcessId": adapter.pid,
                        "startMethod": "launch",
                        "name": expected_module,
                    }),
                self.new_event("thread", reason="started", threadId=tid),
                self.new_event(
                    "stopped",
                    reason="breakpoint",
                    threadId=tid,
                    text=None,
                    description=None,
                ),
                self.new_event(
                    "module",
                    module={
                        "id": 1,
                        "name": "__main__",
                        "path": filepath,
                        "package": None,
                    },
                    reason="new",
                ),
                self.new_response(
                    req_stacktrace,
                    seq=11,
                    **{
                        "totalFrames":
                        1,
                        "stackFrames": [{
                            "id": 1,
                            "name": "<module>",
                            "source": {
                                "path": filepath,
                                "sourceReference": 0
                            },
                            "line": bp_line,
                            "column": 1,
                        }],
                    }),
                self.new_response(req_continue, seq=12),
                self.new_event("continued", seq=13, threadId=tid),
            ],
        )

    def test_with_log_points(self):
        source = dedent("""
            print('foo')
            a = 1
            for i in range(2):
                # <Token>
                b = i
            print('bar')
            """)
        (filename, filepath, env, expected_module, is_module, argv,
         cwd) = self.get_test_info(source)
        bp_line = self.find_line(filepath, 'Token')
        breakpoints = [{
            "source": {
                "path": filepath,
                "name": filename
            },
            "breakpoints": [{
                "line": bp_line,
                "logMessage": "{a + i}"
            }],
            "lines": [bp_line]
        }]
        options = {"debugOptions": ["RedirectOutput"]}

        with DebugClient(port=PORT, connecttimeout=3.0) as editor:
            adapter, session = editor.host_local_debugger(
                argv, env=env, cwd=cwd)
            with session.wait_for_event("terminated"):
                (
                    req_initialize,
                    req_launch,
                    req_config,
                    reqs_bps,
                    _,
                    _,
                ) = lifecycle_handshake(
                    session,
                    "launch",
                    breakpoints=breakpoints,
                    options=options)
                req_bps, = reqs_bps  # There should only be one.

            adapter.wait()

        # Skipping the 'thread exited' and 'terminated' messages which
        # may appear randomly in the received list.
        received = list(_strip_newline_output_events(session.received))
        self.assert_received(
            received[:-3],
            [
                self.new_version_event(session.received),
                self.new_response(req_initialize, **INITIALIZE_RESPONSE),
                self.new_event("initialized"),
                self.new_response(req_launch),
                self.new_response(
                    req_bps, **{
                        "breakpoints": [{
                            "id": 1,
                            "line": bp_line,
                            "verified": True
                        }]
                    }),
                self.new_response(req_config),
                self.new_event(
                    "process", **{
                        "isLocalProcess": True,
                        "systemProcessId": adapter.pid,
                        "startMethod": "launch",
                        "name": expected_module,
                    }),
                self.new_event("thread", reason="started", threadId=1),
                self.new_event("output", category="stdout", output="foo"),
                self.new_event("output", category="stdout", output="1" + os.linesep), # noqa
                self.new_event("output", category="stdout", output="2" + os.linesep), # noqa
                self.new_event("output", category="stdout", output="bar"),
            ],
        )

    def test_with_conditional_break_points(self):
        source = dedent("""
            a = 1
            b = 2
            for i in range(5):
                # <Token>
                print(i)
            """)
        (filename, filepath, env, expected_module, is_module, argv,
         cwd) = self.get_test_info(source)
        bp_line = self.find_line(filepath, 'Token')
        breakpoints = [{
            "source": {
                "path": filepath,
                "name": filename
            },
            "breakpoints": [{
                "line": bp_line,
                "condition": "i == 2"
            }],
            "lines": [bp_line]
        }]
        options = {"debugOptions": ["RedirectOutput"]}

        with DebugClient(port=PORT, connecttimeout=3.0) as editor:
            adapter, session = editor.host_local_debugger(
                argv, env=env, cwd=cwd)
            with session.wait_for_event("terminated"):
                with session.wait_for_event("stopped") as result:
                    (
                        req_initialize,
                        req_launch,
                        req_config,
                        reqs_bps,
                        _,
                        _,
                    ) = lifecycle_handshake(
                        session,
                        "launch",
                        breakpoints=breakpoints,
                        options=options)
                req_bps, = reqs_bps  # There should only be one.
                tid = result["msg"].body["threadId"]

                # with session.wait_for_response("stopped") as result:
                req_stacktrace = session.send_request("stackTrace",
                                                      threadId=tid,
                                                      wait=True)

                with session.wait_for_event("continued"):
                    req_continue = session.send_request("continue",
                                                        threadId=tid)

            adapter.wait()
        # Skipping the 'thread exited' and 'terminated' messages which
        # may appear randomly in the received list.
        received = list(_strip_newline_output_events(session.received))
        received = list(_strip_newline_output_events(session.received))
        del received[12]  # Module info for runpy.py
        stack_frames = received[12].body.get("stackFrames")
        stack_frames[1]["id"] = 1
        del stack_frames[1:len(stack_frames)]  # Ignore non-user stack trace.
        received[12].body["totalFrames"] = 1

        # Skipping the 'thread exited' and 'terminated' messages which
        # may appear randomly in the received list.
        self.assert_received(
            received[:-3],
            [
                self.new_version_event(session.received),
                self.new_response(req_initialize, **INITIALIZE_RESPONSE),
                self.new_event("initialized"),
                self.new_response(req_launch),
                self.new_response(
                    req_bps, **{
                        "breakpoints": [{
                            "id": 1,
                            "line": bp_line,
                            "verified": True
                        }]
                    }),
                self.new_response(req_config),
                self.new_event(
                    "process", **{
                        "isLocalProcess": True,
                        "systemProcessId": adapter.pid,
                        "startMethod": "launch",
                        "name": expected_module,
                    }),
                self.new_event("thread", reason="started", threadId=tid),
                self.new_event("output", category="stdout", output="0"),
                self.new_event("output", category="stdout", output="1"),
                self.new_event(
                    "stopped",
                    reason="breakpoint",
                    threadId=tid,
                    text=None,
                    description=None,
                ),
                self.new_event(
                    "module",
                    module={
                        "id": 1,
                        "name": "__main__",
                        "path": filepath,
                        "package": None,
                    },
                    reason="new",
                ),
                self.new_response(
                    req_stacktrace,
                    seq=13,
                    **{
                        "totalFrames":
                        1,
                        "stackFrames": [{
                            "id": 1,
                            "name": "<module>",
                            "source": {
                                "path": filepath,
                                "sourceReference": 0
                            },
                            "line": bp_line,
                            "column": 1,
                        }],
                    }),
                self.new_response(req_continue, seq=14),
                self.new_event("continued", seq=15, threadId=tid),
                self.new_event("output", category="stdout", output="2", seq=16), # noqa
                self.new_event("output", category="stdout", output="3", seq=17), # noqa
                self.new_event("output", category="stdout", output="4", seq=18), # noqa
            ],
        )

    @unittest.skip("termination needs fixing")
    def test_terminating_program(self):
        source = dedent("""
            import time

            while True:
                time.sleep(0.1)
            """)
        (filename, filepath, env, expected_module,
         argv) = self.get_test_info(source)

        with DebugClient(port=PORT, connecttimeout=3.0) as editor:
            adapter, session = editor.host_local_debugger(argv)
            with session.wait_for_event("terminated"):
                (req_initialize, req_launch, req_config, _, _,
                 _) = lifecycle_handshake(  # noqa
                     session, "launch")

                session.send_request("disconnect")

            adapter.wait()


class FileWithCWDLifecycleTests(FileLifecycleTests):
    def get_cwd(self):
        return os.path.dirname(__file__)


class ModuleLifecycleTests(FileLifecycleTests):
    def get_test_info(self, source):
        module_name = "mymod"
        filename = "__init__.py"
        self.workspace.ensure_dir(module_name)
        self.create_source_file(os.path.join(module_name, "__main__.py"), "")
        module_path = os.path.join(module_name, filename)
        filepath = self.create_source_file(module_path, source)
        env = {"PYTHONPATH": os.path.dirname(os.path.dirname(filepath))}
        expected_module = module_name + ":"
        argv = ["-m", module_name]

        return (filename, filepath, env, expected_module, True, argv,
                self.get_cwd())


class ModuleWithCWDLifecycleTests(ModuleLifecycleTests,
                                  FileWithCWDLifecycleTests):  # noqa
    def get_cwd(self):
        return os.path.dirname(__file__)
