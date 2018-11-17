# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import
import pytest
from pytests.helpers.timeline import Event


@pytest.mark.parametrize('args, count', [
    ('single', 1),
    ('multi', 3),
])
def test_multi_thread(debug_session, pyfile, run_as, start_method, args, count):
    @pyfile
    def code_to_debug():
        import threading
        import time
        import sys
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        stop = False
        def worker(tid, offset):
            i = 0
            global stop
            while not stop:
                time.sleep(0.01)
                i += 1
        threads = []
        if sys.argv[1] == 'multi':
            for i in [111, 222]:
                thread = threading.Thread(target=worker, args=(i, len(threads)))
                threads.append(thread)
                thread.start()
        print('check here')
        stop = True

    debug_session.initialize(target=(run_as, code_to_debug), start_method=start_method, program_args=[args])
    debug_session.set_breakpoints(code_to_debug, [19])
    debug_session.start_debugging()
    debug_session.wait_for_thread_stopped()
    resp_threads = debug_session.send_request('threads').wait_for_response()

    assert len(resp_threads.body['threads']) == count

    debug_session.send_request('continue').wait_for_response()
    debug_session.wait_for_next(Event('continued'))

    debug_session.wait_for_exit()
