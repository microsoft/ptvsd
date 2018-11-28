# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import pytest
from pytests.helpers.pattern import ANY
from pytests.helpers.session import DebugSession
from pytests.helpers.timeline import Event


@pytest.mark.parametrize('start_method', ['attach_socket_cmdline', 'attach_socket_import'])
def test_continue_on_disconnect_for_attach(pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        import backchannel
        backchannel.write_json('continued')
    bp_line = 4
    with DebugSession() as session:
        session.initialize(
                target=(run_as, code_to_debug),
                start_method=start_method,
                ignore_unobserved=[Event('continued'), Event('exited'), Event('terminated')],
                use_backchannel=True,
            )
        session.set_breakpoints(code_to_debug, [bp_line])
        session.start_debugging()
        hit = session.wait_for_thread_stopped('breakpoint')
        frames = hit.stacktrace.body['stackFrames']
        assert frames[0]['line'] == bp_line
        session.send_request('disconnect').wait_for_response()
        session.wait_for_disconnect()
        assert 'continued' == session.read_json()


@pytest.mark.parametrize('start_method', ['launch'])
@pytest.mark.skip(reason='Bug #1052')
def test_exit_on_disconnect_for_launch(pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        import backchannel
        import atexit
        def onexit():
            backchannel.write_json('exit')
        atexit.register(onexit)
        backchannel.write_json('continue')  # should not execute this
    bp_line = 8
    with DebugSession() as session:
        session.initialize(
                target=(run_as, code_to_debug),
                start_method=start_method,
                ignore_unobserved=[Event('continued')],
                use_backchannel=True,
                expected_returncode=ANY.int,
            )
        session.set_breakpoints(code_to_debug, [bp_line])
        session.start_debugging()
        hit = session.wait_for_thread_stopped('breakpoint')
        frames = hit.stacktrace.body['stackFrames']
        assert frames[0]['line'] == bp_line
        session.send_request('disconnect').wait_for_response()
        session.wait_for_exit()
        assert 'exit' == session.read_json()
