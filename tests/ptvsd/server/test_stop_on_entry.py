# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from tests import debug
from tests.patterns import some


@pytest.mark.parametrize('start_method', ['launch'])
@pytest.mark.parametrize('with_bp', ['with_breakpoint', ''])
def test_stop_on_entry(pyfile, start_method, run_as, with_bp):

    @pyfile
    def code_to_debug():
        import backchannel # @bp
        # import_and_enable_debugger()
        backchannel.write_json('done')

    with debug.Session() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            debug_options=['StopOnEntry'],
            use_backchannel=True,
        )
        if bool(with_bp):
            session.set_breakpoints(code_to_debug, [code_to_debug.lines["bp"]])

        session.start_debugging()

        if bool(with_bp):
            thread_stopped, resp_stacktrace, thread_id, _ = session.wait_for_thread_stopped(reason='breakpoint')
            frames = resp_stacktrace.body['stackFrames']
            assert frames[0]['line'] == 1
            assert frames[0]['source']['path'] == some.path(code_to_debug)

            session.send_request('next', {'threadId': thread_id}).wait_for_response()
            thread_stopped, resp_stacktrace, thread_id, _ = session.wait_for_thread_stopped(reason='step')
            frames = resp_stacktrace.body['stackFrames']
            assert frames[0]['line'] == 3
            assert frames[0]['source']['path'] == some.path(code_to_debug)
        else:
            thread_stopped, resp_stacktrace, tid, _ = session.wait_for_thread_stopped(reason='entry')
            frames = resp_stacktrace.body['stackFrames']
            assert frames[0]['line'] == 1
            assert frames[0]['source']['path'] == some.path(code_to_debug)

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_termination()

        assert session.read_json() == 'done'

        session.wait_for_exit()
