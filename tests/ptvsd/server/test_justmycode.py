# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from tests import debug
from tests.patterns import some


@pytest.mark.parametrize('jmc', ['jmcOn', 'jmcOff'])
def test_justmycode_frames(pyfile, start_method, run_as, jmc):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        print('break here')  #@bp

    with debug.Session() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            debug_options=[] if jmc == 'jmcOn' else ['DebugStdLib']
        )

        bp_line = code_to_debug.lines["bp"]

        actual_bps = session.set_breakpoints(code_to_debug, [bp_line])
        actual_bps = [bp['line'] for bp in actual_bps]
        session.start_debugging()

        hit = session.wait_for_thread_stopped()
        frames = hit.stacktrace.body['stackFrames']
        assert frames[0] == some.dict.containing({
            'line': bp_line,
            'source': some.dict.containing({
                'path': some.path(code_to_debug)
            })
        })

        if jmc == 'jmcOn':
            assert len(frames) == 1
            session.send_request('stepIn', {'threadId': hit.thread_id}).wait_for_response()
            # 'step' should terminate the debuggee
        else:
            assert len(frames) >= 1
            session.send_request('stepIn', {'threadId': hit.thread_id}).wait_for_response()

            # 'step' should enter stdlib
            hit2 = session.wait_for_thread_stopped()
            frames2 = hit2.stacktrace.body['stackFrames']
            assert frames2[0]['source']['path'] != some.path(code_to_debug)

            # 'continue' should terminate the debuggee
            session.send_request('continue').wait_for_response(freeze=False)

        session.wait_for_exit()
