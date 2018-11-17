# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import platform
import pytest
import sys

from pytests.helpers.pattern import ANY
from pytests.helpers.timeline import Event


@pytest.mark.parametrize('start_method', ['launch'])
def test_break_on_entry(debug_session, pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        import backchannel
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        backchannel.write_json('done')

    debug_session.debug_options += ['StopOnEntry']
    debug_session.initialize(
        target=(run_as, code_to_debug),
        start_method=start_method,
        ignore_unobserved=[Event('continued')],
        use_backchannel=True,
    )
    debug_session.start_debugging()

    thread_stopped = debug_session.wait_for_next(Event('stopped', ANY.dict_with({'reason': 'step'})))
    assert thread_stopped.body['threadId'] is not None

    tid = thread_stopped.body['threadId']

    resp_stacktrace = debug_session.send_request('stackTrace', arguments={
        'threadId': tid,
    }).wait_for_response()
    assert resp_stacktrace.body['totalFrames'] > 0
    frames = resp_stacktrace.body['stackFrames']
    assert frames[0]['line'] == 1

    debug_session.send_request('continue').wait_for_response()
    debug_session.wait_for_termination()

    assert debug_session.read_json() == 'done'

    debug_session.wait_for_exit()


@pytest.mark.parametrize('start_method', ['launch', 'attach_socket_cmdline'])
@pytest.mark.skipif(sys.version_info < (3, 0) and platform.system() == 'Windows',
                    reason="On Win32 Python2.7, unable to send key strokes to test.")
def test_wait_on_normal_exit_enabled(debug_session, pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        import backchannel
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        backchannel.write_json('done')

    debug_session.debug_options += ['WaitOnNormalExit']

    bp_line = 5
    bp_file = code_to_debug
    debug_session.initialize(
        target=(run_as, bp_file),
        start_method=start_method,
        ignore_unobserved=[Event('continued')],
        use_backchannel=True,
    )
    debug_session.set_breakpoints(bp_file, [bp_line])
    debug_session.start_debugging()

    debug_session.wait_for_next(Event('stopped', ANY.dict_with({'reason': 'breakpoint'})))
    debug_session.send_request('continue').wait_for_response()
    debug_session.proceed()

    debug_session.expected_returncode = ANY.int
    debug_session.wait_for_next(Event('exited'))

    assert debug_session.read_json() == 'done'

    debug_session.process.stdin.write(b' \r\n')
    debug_session.wait_for_exit()

    def _decode(text):
        if isinstance(text, bytes):
            return text.decode('utf-8')
        return text
    assert any(l for l in debug_session.output_data['OUT']
               if _decode(l).startswith('Press'))


@pytest.mark.parametrize('start_method', ['launch', 'attach_socket_cmdline'])
@pytest.mark.skipif(sys.version_info < (3, 0) and platform.system() == 'Windows',
                    reason="On windows py2.7 unable to send key strokes to test.")
def test_wait_on_abnormal_exit_enabled(debug_session, pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        import backchannel
        import sys
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        backchannel.write_json('done')
        sys.exit(12345)

    debug_session.debug_options += ['WaitOnAbnormalExit']

    bp_line = 7
    bp_file = code_to_debug
    debug_session.initialize(
        target=(run_as, bp_file),
        start_method=start_method,
        ignore_unobserved=[Event('continued')],
        use_backchannel=True,
    )
    debug_session.set_breakpoints(bp_file, [bp_line])
    debug_session.start_debugging()

    debug_session.wait_for_next(Event('stopped'), ANY.dict_with({'reason': 'breakpoint'}))
    debug_session.send_request('continue').wait_for_response()
    debug_session.proceed()

    debug_session.expected_returncode = ANY.int
    debug_session.wait_for_next(Event('exited'))

    assert debug_session.read_json() == 'done'

    debug_session.process.stdin.write(b' \r\n')
    debug_session.wait_for_exit()

    def _decode(text):
        if isinstance(text, bytes):
            return text.decode('utf-8')
        return text
    assert any(l for l in debug_session.output_data['OUT']
               if _decode(l).startswith('Press'))


@pytest.mark.parametrize('start_method', ['launch', 'attach_socket_cmdline'])
def test_exit_normally_with_wait_on_abnormal_exit_enabled(debug_session, pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        import backchannel
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        backchannel.write_json('done')

    debug_session.debug_options += ['WaitOnAbnormalExit']

    bp_line = 5
    bp_file = code_to_debug
    debug_session.initialize(
        target=(run_as, bp_file),
        start_method=start_method,
        ignore_unobserved=[Event('continued')],
        use_backchannel=True,
    )
    debug_session.set_breakpoints(bp_file, [bp_line])
    debug_session.start_debugging()

    debug_session.wait_for_next(Event('stopped', ANY.dict_with({'reason': 'breakpoint'})))
    debug_session.send_request('continue').wait_for_response()
    debug_session.proceed()

    debug_session.wait_for_termination()

    assert debug_session.read_json() == 'done'

    debug_session.wait_for_exit()
