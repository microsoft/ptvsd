# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from ptvsd.common import compat
from tests import code, debug, net, test_data
from tests.patterns import some

pytestmark = pytest.mark.timeout(60)

django = net.WebServer(net.get_test_server_port(8000, 8100))


class paths:
    django1 = test_data / "django1"
    app_py = django1 / "app.py"
    hello_html = django1 / "templates" / "hello.html"
    bad_html = django1 / "templates" / "bad.html"


class lines:
    app_py = code.get_marked_line_numbers(paths.app_py)


@pytest.mark.parametrize("bp_target", ["code", "template"])
@pytest.mark.parametrize("start_method", ["launch", "attach_socket_cmdline"])
def test_django_breakpoint_no_multiproc(start_method, bp_target):
    bp_file, bp_line, bp_name = {
        "code": (paths.app_py, lines.app_py["bphome"], "home"),
        "template": (paths.hello_html, 8, "Django Template"),
    }[bp_target]
    bp_var_content = compat.force_str("Django-Django-Test")

    with debug.Session() as session:
        session.initialize(
            start_method=start_method,
            target=("file", paths.app_py),
            program_args=["runserver", "--noreload", "--", str(django.port)],
            debug_options=["Django"],
            cwd=paths.django1,
            expected_returncode=some.int,  # No clean way to kill Django server
        )

        session.set_breakpoints(bp_file, [bp_line])
        session.start_debugging()

        with django:
            home_request = django.get("/home")
            session.wait_for_stop(
                "breakpoint",
                [
                    {
                        "id": some.dap.id,
                        "name": bp_name,
                        "source": some.dap.source(bp_file),
                        "line": bp_line,
                        "column": 1,
                    }
                ],
            )

            var_content = session.get_variable("content")
            assert var_content == some.dict.containing(
                {
                    "name": "content",
                    "type": "str",
                    "value": compat.unicode_repr(bp_var_content),
                    "presentationHint": {"attributes": ["rawString"]},
                    "evaluateName": "content",
                    "variablesReference": 0,
                }
            )

            session.request_continue()
            assert bp_var_content in home_request.response_text()

        session.wait_for_exit()


@pytest.mark.parametrize("start_method", ["launch", "attach_socket_cmdline"])
def test_django_template_exception_no_multiproc(start_method):
    with debug.Session() as session:
        session.initialize(
            start_method=start_method,
            target=("file", paths.app_py),
            program_args=["runserver", "--noreload", "--nothreading", str(django.port)],
            debug_options=["Django"],
            cwd=paths.django1,
            expected_returncode=some.int,  # No clean way to kill Django server
        )
        session.request("setExceptionBreakpoints", {"filters": ["raised", "uncaught"]})
        session.start_debugging()

        with django:
            django.get("/badtemplate", log_errors=False)
            stop = session.wait_for_stop(
                "exception",
                expected_frames=[
                    some.dap.frame(
                        some.dap.source(paths.bad_html),
                        line=8,
                        name="Django TemplateSyntaxError",
                    )
                ],
            )

            # Will stop once in the plugin
            exception_info = session.request(
                "exceptionInfo", {"threadId": stop.thread_id}
            )
            assert exception_info == some.dict.containing(
                {
                    "exceptionId": some.str.ending_with("TemplateSyntaxError"),
                    "breakMode": "always",
                    "description": some.str.containing("doesnotexist"),
                    "details": some.dict.containing(
                        {
                            "message": some.str.containing("doesnotexist"),
                            "typeName": some.str.ending_with("TemplateSyntaxError"),
                        }
                    ),
                }
            )

            session.request_continue()

            # And a second time when the exception reaches the user code.
            session.wait_for_stop("exception")
            session.request_continue()

        session.wait_for_exit()


@pytest.mark.parametrize("exc_type", ["handled", "unhandled"])
@pytest.mark.parametrize("start_method", ["launch", "attach_socket_cmdline"])
def test_django_exception_no_multiproc(exc_type, start_method):
    exc_line = lines.app_py["exc_" + exc_type]

    with debug.Session() as session:
        session.initialize(
            start_method=start_method,
            target=("file", paths.app_py),
            program_args=["runserver", "--noreload", "--nothreading", str(django.port)],
            debug_options=["Django"],
            cwd=paths.django1,
            expected_returncode=some.int,  # No clean way to kill Django server
        )
        session.request("setExceptionBreakpoints", {"filters": ["raised", "uncaught"]})
        session.start_debugging()

        with django:
            django.get("/" + exc_type)
            stopped = session.wait_for_stop(
                "exception",
                expected_frames=[
                    some.dap.frame(
                        some.dap.source(paths.app_py),
                        line=exc_line,
                        name="bad_route_" + exc_type,
                    )
                ],
            ).body

            assert stopped == some.dict.containing(
                {
                    "reason": "exception",
                    "text": some.str.ending_with("ArithmeticError"),
                    "description": "Hello",
                }
            )

            exception_info = session.request(
                "exceptionInfo", {"threadId": stopped["threadId"]}
            )

            assert exception_info == {
                "exceptionId": some.str.ending_with("ArithmeticError"),
                "breakMode": "always",
                "description": "Hello",
                "details": {
                    "message": "Hello",
                    "typeName": some.str.ending_with("ArithmeticError"),
                    "source": some.path(paths.app_py),
                    "stackTrace": some.str,
                },
            }

            session.request_continue()

        session.wait_for_exit()


@pytest.mark.parametrize("start_method", ["launch"])
def test_django_breakpoint_multiproc(start_method):
    bp_line = lines.app_py["bphome"]
    bp_var_content = compat.force_str("Django-Django-Test")

    with debug.Session() as parent_session:
        parent_session.initialize(
            start_method=start_method,
            target=("file", paths.app_py),
            multiprocess=True,
            program_args=["runserver"],
            debug_options=["Django"],
            cwd=paths.django1,
            expected_returncode=some.int,  # No clean way to kill Django server
        )

        parent_session.set_breakpoints(paths.app_py, [bp_line])
        parent_session.start_debugging()

        with parent_session.attach_to_next_subprocess() as child_session:
            child_session.request(
                "setBreakpoints",
                {"source": {"path": paths.app_py}, "breakpoints": [{"line": bp_line}]},
            )
            child_session.start_debugging()

            with django:
                web_request = django.get("/home")
                child_session.wait_for_stop(
                    "breakpoint",
                    expected_frames=[
                        some.dap.frame(
                            some.dap.source(paths.app_py), line=bp_line, name="home"
                        )
                    ],
                )

                var_content = child_session.get_variable("content")
                assert var_content == some.dict.containing(
                    {
                        "name": "content",
                        "type": "str",
                        "value": compat.unicode_repr(bp_var_content),
                        "presentationHint": {"attributes": ["rawString"]},
                        "evaluateName": "content",
                    }
                )

                child_session.request_continue()
                assert bp_var_content in web_request.response_text()

            child_session.wait_for_termination()
            parent_session.wait_for_exit()
