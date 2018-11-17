# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import


def test_with_no_output(debug_session, pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        # Do nothing, and check if there is any output

    debug_session.initialize(target=(run_as, code_to_debug), start_method=start_method)
    debug_session.start_debugging()
    debug_session.wait_for_exit()
    assert b'' == debug_session.get_stdout_as_string()
    assert b'' == debug_session.get_stderr_as_string()


def test_with_tab_in_output(debug_session, pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        print('Hello\tWorld')

    debug_session.initialize(target=(run_as, code_to_debug), start_method=start_method)
    debug_session.start_debugging()
    debug_session.wait_for_exit()
    data = debug_session.get_stdout_as_string() + debug_session.get_stderr_as_string()
    assert data.startswith(b'Hello\tWorld')
