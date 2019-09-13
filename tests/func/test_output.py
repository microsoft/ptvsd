# coding:utf-8
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import pytest
from tests.helpers import get_marked_line_numbers
from tests.helpers.session import DebugSession
from tests.helpers.timeline import Event
from tests.helpers.pattern import ANY

def test_with_no_output(pyfile, run_as, start_method):

    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        # Do nothing, and check if there is any output

    with DebugSession() as session:
        session.initialize(target=(run_as, code_to_debug), start_method=start_method)
        session.start_debugging()
        session.wait_for_exit()
        assert b'' == session.get_stdout_as_string()
        assert b'' == session.get_stderr_as_string()


def test_with_tab_in_output(pyfile, run_as, start_method):

    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        a = '\t'.join(('Hello', 'World'))
        print(a)
        # Break here so we are sure to get the output event.
        a = 1  # @bp1

    line_numbers = get_marked_line_numbers(code_to_debug)
    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
        )

        session.set_breakpoints(code_to_debug, [line_numbers['bp1']])
        session.start_debugging()

        # Breakpoint at the end just to make sure we get all output events.
        session.wait_for_thread_stopped()
        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()

        output = session.all_occurrences_of(Event('output', ANY.dict_with({'category': 'stdout'})))
        output_str = ''.join(o.body['output'] for o in output)
        assert output_str.startswith('Hello\tWorld')

def test_non_ascii_output(pyfile, run_as, start_method):

    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        from _pydevd_bundle.pydevd_constants import IS_PY3K
        import_and_enable_debugger()
        a = b'\xc3\xa9 \xc3\xa0 \xc3\xb6 \xc3\xb9'
        if IS_PY3K:
            a = a.decode('utf8')
        print(a)
        # Break here so we are sure to get the output event.
        a = 1  # @bp1

    line_numbers = get_marked_line_numbers(code_to_debug)
    with DebugSession() as session:
        from _pydevd_bundle.pydevd_constants import IS_PY3K

        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            env={'PYTHONIOENCODING': 'utf-8'}
        )

        session.set_breakpoints(code_to_debug, [line_numbers['bp1']])
        session.start_debugging()

        # Breakpoint at the end just to make sure we get all output events.
        session.wait_for_thread_stopped()
        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()

        output = session.all_occurrences_of(Event('output', ANY.dict_with({'category': 'stdout'})))
        output_str = ''.join(o.body['output'] for o in output)
        print(type("#######################", output_str))
        assertion_value = b'\xc3\xa9 \xc3\xa0 \xc3\xb6 \xc3\xb9'
        if IS_PY3K:
            assertion_value = assertion_value.decode('utf8')
        assert output_str == assertion_value


@pytest.mark.parametrize('redirect', ['RedirectOutput', ''])
def test_redirect_output(pyfile, run_as, start_method, redirect):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()

        for i in [111, 222, 333, 444]:
            print(i)

        print() # @bp1

    line_numbers = get_marked_line_numbers(code_to_debug)
    with DebugSession() as session:
        # By default 'RedirectOutput' is always set. So using this way
        #  to override the default in session.
        session.debug_options = [redirect] if bool(redirect) else []
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
        )

        session.set_breakpoints(code_to_debug, [line_numbers['bp1']])
        session.start_debugging()

        # Breakpoint at the end just to make sure we get all output events.
        session.wait_for_thread_stopped()
        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()

        output = session.all_occurrences_of(Event('output', ANY.dict_with({'category': 'stdout'})))
        expected = ['111', '222', '333', '444'] if bool(redirect) else []
        assert expected == list(o.body['output'] for o in output if len(o.body['output']) == 3)
