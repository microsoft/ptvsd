import os
import os.path
import re
import threading
import unittest

from tests.helpers.debugsession import Awaitable
from tests.helpers.resource import TestResources
from tests.helpers.webhelper import get_web_string_no_error
from . import (
    _strip_newline_output_events, lifecycle_handshake,
    LifecycleTestsBase, DebugInfo,
)


TEST_FILES = TestResources.from_module(__name__)
re_link = r"(http(s|)\:\/\/[\w\.]*\:[0-9]{4,6}(\/|))"


class FlaskBreakpointTests(LifecycleTestsBase):
    def run_test_with_break_points(self, debug_info,
                                   bp_filename, bp_line,
                                   bp_name):
        if (debug_info.starttype == 'attach'):
            pathMappings = []
            pathMappings.append({
                'localRoot': debug_info.cwd,
                'remoteRoot': debug_info.cwd
            })
            options = {
                'debugOptions': ['RedirectOutput', 'Jinja'],
                'pathMappings': pathMappings
                }
        else:
            options = {'debugOptions': ['RedirectOutput', 'Jinja']}

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

                # wait for flask web server start
                count = 0
                path = None
                while path is None and count < 10:
                    outevent = session.get_awaiter_for_event('output')
                    Awaitable.wait_all(outevent)
                    events = self.find_events(
                        session.received, 'output', {'category': 'stderr'})
                    count += 1
                    for e in events:
                        matches = re.findall(re_link, e.body['output'])
                        if len(matches) > 0 and len(matches[0]) > 0 and \
                            len(matches[0][0].strip()) > 0:
                            path = matches[0][0]
                            break

                # connect to web server
                web_result = {}
                web_client_thread = threading.Thread(
                    target=get_web_string_no_error,
                    args=(path, web_result),
                    name='test.webClient'
                )

                web_client_thread.start()

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

            # wait for flask rendering thread to exit
            web_client_thread.join(timeout=0.1)

            # shutdown to web server
            path += 'exit' if path.endswith('/') else '/exit'
            web_client_thread = threading.Thread(
                target=get_web_string_no_error,
                args=(path, None),
                name='test.webClient.shutdown'
            )
            web_client_thread.start()
            web_client_thread.join(timeout=1)

        received = list(_strip_newline_output_events(session.received))

        self.assertGreaterEqual(stacktrace['totalFrames'], 1)
        self.assert_is_subset(stacktrace, {
            # We get Python and PTVSD frames as well.
            # 'totalFrames': 2,
            'stackFrames': [{
                'id': 1,
                'name': bp_name,
                'source': {
                    'sourceReference': 0,
                    'path': bp_filename
                },
                'line': bp_line,
                'column': 1,
            }],
        })
        self.assertTrue(web_result['content'].find('Flask-Jinja-Test') != -1)
        self.assert_contains(received, [
            self.new_event(
                'stopped',
                reason='breakpoint',
                threadId=tid,
                text=None,
                description=None,
            ),
            self.new_event('continued', threadId=tid),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])

    def run_test_with_handled_exception(self, debug_info,
                                        expected_source_name):
        if (debug_info.starttype == 'attach'):
            pathMappings = []
            pathMappings.append({
                'localRoot': debug_info.cwd,
                'remoteRoot': debug_info.cwd
            })
            options = {
                'debugOptions': ['RedirectOutput', 'Jinja'],
                'pathMappings': pathMappings
                }
        else:
            options = {'debugOptions': ['RedirectOutput', 'Jinja']}

        excbreakpoints = [{'filters': ['raised', 'uncaught']}]
        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            with session.wait_for_event('stopped') as result:
                (_, req_launch_attach, _, _, _, _,
                 ) = lifecycle_handshake(session, debug_info.starttype,
                                         options=options,
                                         excbreakpoints=excbreakpoints)
                req_launch_attach.wait()

                # wait for flask web server start
                count = 0
                base_path = None
                while base_path is None and count < 10:
                    outevent = session.get_awaiter_for_event('output')
                    Awaitable.wait_all(outevent)
                    events = self.find_events(
                        session.received, 'output', {'category': 'stderr'})
                    count += 1
                    for e in events:
                        matches = re.findall(re_link, e.body['output'])
                        if len(matches) > 0 and len(matches[0]) > 0 and \
                           len(matches[0][0].strip()) > 0:
                            base_path = matches[0][0]
                            break

                # connect to web server
                path = base_path + \
                    'handled' if base_path.endswith('/') else '/handled'
                web_result = {}
                web_client_thread = threading.Thread(
                    target=get_web_string_no_error,
                    args=(path, web_result),
                    name='test.webClient'
                )

                web_client_thread.start()

            event = result['msg']
            thread_id = event.body['threadId']

            req_exc_info = dbg.session.send_request(
                'exceptionInfo',
                threadId=thread_id,
            )
            req_exc_info.wait()
            exc_info = req_exc_info.resp.body

            self.assert_is_subset(
                exc_info, {
                    'exceptionId': 'ArithmeticError',
                    'breakMode': 'always',
                    'details': {
                        'typeName': 'ArithmeticError',
                        'source': expected_source_name
                    }
                })

            continued = dbg.session.get_awaiter_for_event('continued')
            dbg.session.send_request(
                'continue',
                threadId=thread_id,
            ).wait()
            Awaitable.wait_all(continued)

            # Shutdown webserver
            path = base_path + 'exit' if base_path.endswith('/') else '/exit'
            web_client_thread = threading.Thread(
                target=get_web_string_no_error,
                args=(path, None),
                name='test.webClient.shutdown'
            )
            web_client_thread.start()
            web_client_thread.join(timeout=1)

        received = list(_strip_newline_output_events(dbg.session.received))
        self.assert_contains(received, [
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])

    def run_test_with_unhandled_exception(self, debug_info,
                                          expected_source_name):
        if (debug_info.starttype == 'attach'):
            pathMappings = []
            pathMappings.append({
                'localRoot': debug_info.cwd,
                'remoteRoot': debug_info.cwd
            })
            options = {
                'debugOptions': ['RedirectOutput', 'Jinja'],
                'pathMappings': pathMappings
                }
        else:
            options = {'debugOptions': ['RedirectOutput', 'Jinja']}

        excbreakpoints = [{'filters': ['raised', 'uncaught']}]
        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            with session.wait_for_event('stopped') as result:
                (_, req_launch_attach, _, _, _, _,
                 ) = lifecycle_handshake(session, debug_info.starttype,
                                         options=options,
                                         excbreakpoints=excbreakpoints)
                req_launch_attach.wait()

                # wait for flask web server start
                count = 0
                base_path = None
                while base_path is None and count < 10:
                    outevent = session.get_awaiter_for_event('output')
                    Awaitable.wait_all(outevent)
                    events = self.find_events(
                        session.received, 'output', {'category': 'stderr'})
                    count += 1
                    for e in events:
                        matches = re.findall(re_link, e.body['output'])
                        if len(matches) > 0 and len(matches[0]) > 0 and \
                           len(matches[0][0].strip()) > 0:
                            base_path = matches[0][0]
                            break

                # connect to web server
                path = base_path + \
                    'unhandled' if base_path.endswith('/') else '/unhandled'
                web_result = {}
                web_client_thread = threading.Thread(
                    target=get_web_string_no_error,
                    args=(path, web_result),
                    name='test.webClient'
                )

                web_client_thread.start()

            event = result['msg']
            thread_id = event.body['threadId']

            req_exc_info = dbg.session.send_request(
                'exceptionInfo',
                threadId=thread_id,
            )
            req_exc_info.wait()
            exc_info = req_exc_info.resp.body

            self.assert_is_subset(
                exc_info, {
                    'exceptionId': 'ArithmeticError',
                    'breakMode': 'always',
                    'details': {
                        'typeName': 'ArithmeticError',
                        'source': expected_source_name
                    }
                })

            continued = dbg.session.get_awaiter_for_event('continued')
            dbg.session.send_request(
                'continue',
                threadId=thread_id,
            ).wait()
            Awaitable.wait_all(continued)

            # Shutdown webserver
            path = base_path + 'exit' if base_path.endswith('/') else '/exit'
            web_client_thread = threading.Thread(
                target=get_web_string_no_error,
                args=(path, None),
                name='test.webClient.shutdown'
            )
            web_client_thread.start()
            web_client_thread.join(timeout=1)

        received = list(_strip_newline_output_events(dbg.session.received))
        self.assert_contains(received, [
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])


class LaunchFileTests(FlaskBreakpointTests):
    def test_with_route_break_points(self):
        filename = TEST_FILES.resolve('launch', 'app.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_break_points(
            DebugInfo(
                modulename='flask',
                argv=['run', '--no-debugger', '--no-reload', '--with-threads'],
                env={
                    'FLASK_APP': 'app.py',
                    'FLASK_ENV': 'development',
                    'FLASK_DEBUG': '0',
                    'LC_ALL': 'C.UTF-8',
                    'LANG': 'C.UTF-8'
                },
                cwd=cwd),
            filename, bp_line=10, bp_name='home'
        )

    def test_with_template_break_points(self):
        filename = TEST_FILES.resolve('launch', 'app.py')
        template = TEST_FILES.resolve('launch', 'templates', 'hello.html')
        cwd = os.path.dirname(filename)
        self.run_test_with_break_points(
            DebugInfo(
                modulename='flask',
                argv=['run', '--no-debugger', '--no-reload', '--with-threads'],
                env={
                    'FLASK_APP': 'app.py',
                    'FLASK_ENV': 'development',
                    'FLASK_DEBUG': '0',
                    'LC_ALL': 'C.UTF-8',
                    'LANG': 'C.UTF-8'
                },
                cwd=cwd),
            template, bp_line=8, bp_name='template'
        )

    def test_with_handled_exceptions(self):
        filename = TEST_FILES.resolve('launch', 'app.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_handled_exception(
            DebugInfo(
                modulename='flask',
                argv=['run', '--no-debugger', '--no-reload', '--with-threads'],
                env={
                    'FLASK_APP': 'app.py',
                    'FLASK_ENV': 'development',
                    'FLASK_DEBUG': '0',
                    'LC_ALL': 'C.UTF-8',
                    'LANG': 'C.UTF-8'
                },
                cwd=cwd),
            filename)

    def test_with_unhandled_exceptions(self):
        filename = TEST_FILES.resolve('launch', 'app.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_unhandled_exception(
            DebugInfo(
                modulename='flask',
                argv=['run', '--no-debugger', '--no-reload', '--with-threads'],
                env={
                    'FLASK_APP': 'app.py',
                    'FLASK_ENV': 'development',
                    'FLASK_DEBUG': '0',
                    'LC_ALL': 'C.UTF-8',
                    'LANG': 'C.UTF-8'
                },
                cwd=cwd),
            filename)


class AttachFileTests(FlaskBreakpointTests):
    @unittest.skip('Needs fixing')
    def test_with_route_break_points(self):
        filename = TEST_FILES.resolve('attach', 'app.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_break_points(
            DebugInfo(
                starttype='attach',
                modulename='flask',
                argv=['run', '--no-debugger', '--no-reload', '--with-threads'],
                env={
                    'FLASK_APP': 'app.py',
                    'FLASK_ENV': 'development',
                    'FLASK_DEBUG': '0',
                    'LC_ALL': 'C.UTF-8',
                    'LANG': 'C.UTF-8'
                },
                cwd=cwd),
            filename, bp_line=10, bp_name='home'
        )

    @unittest.skip('Needs fixing')
    def test_with_template_break_points(self):
        filename = TEST_FILES.resolve('attach', 'app.py')
        template = TEST_FILES.resolve('attach', 'templates', 'hello.html')
        cwd = os.path.dirname(filename)
        self.run_test_with_break_points(
            DebugInfo(
                starttype='attach',
                modulename='flask',
                argv=['run', '--no-debugger', '--no-reload', '--with-threads'],
                env={
                    'FLASK_APP': 'app.py',
                    'FLASK_ENV': 'production',
                    'LC_ALL': 'C.UTF-8',
                    'LANG': 'C.UTF-8'
                },
                cwd=cwd),
            template, bp_line=8, bp_name='template'
        )

    @unittest.skip('Needs fixing')
    def test_with_handled_exceptions(self):
        filename = TEST_FILES.resolve('attach', 'app.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_handled_exception(
            DebugInfo(
                starttype='attach',
                modulename='flask',
                argv=['run', '--no-debugger', '--no-reload', '--with-threads'],
                env={
                    'FLASK_APP': 'app.py',
                    'FLASK_ENV': 'production',
                    'LC_ALL': 'C.UTF-8',
                    'LANG': 'C.UTF-8'
                },
                cwd=cwd),
            filename)

    @unittest.skip('Needs fixing')
    def test_with_unhandled_exceptions(self):
        filename = TEST_FILES.resolve('attach', 'app.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_unhandled_exception(
            DebugInfo(
                starttype='attach',
                modulename='flask',
                argv=['run', '--no-debugger', '--no-reload', '--with-threads'],
                env={
                    'FLASK_APP': 'app.py',
                    'FLASK_ENV': 'production',
                    'LC_ALL': 'C.UTF-8',
                    'LANG': 'C.UTF-8'
                },
                cwd=cwd),
            filename)
