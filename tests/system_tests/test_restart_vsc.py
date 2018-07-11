import os
import os.path
import unittest

from ptvsd.wrapper import INITIALIZE_RESPONSE  # noqa

from . import (_strip_newline_output_events, lifecycle_handshake,
               LifecycleTestsBase, DebugInfo, ROOT)

TEST_FILES_DIR = os.path.join(ROOT, 'tests', 'resources', 'system_tests',
                              'test_forever')


@unittest.skip('Needs fixing in #530')
class RestartVSCTests(LifecycleTestsBase):
    def test_disconnect_without_restart(self):
        filename = os.path.join(TEST_FILES_DIR, 'launch_forever.py')
        cwd = os.path.dirname(filename)
        debug_info = DebugInfo(filename=filename, cwd=cwd)

        with self.start_debugging(debug_info) as dbg:
            (_, req_launch, _, _, _, _) = lifecycle_handshake(
                dbg.session, debug_info.starttype)

            req_launch.wait()

            dbg.session.send_request('disconnect', restart=False)

        received = list(_strip_newline_output_events(dbg.session.received))
        evts = self.find_events(received, 'terminated')
        self.assertEqual(len(evts), 1)

    def test_disconnect_with_restart(self):
        filename = os.path.join(TEST_FILES_DIR, 'launch_forever.py')
        cwd = os.path.dirname(filename)
        debug_info = DebugInfo(filename=filename, cwd=cwd)

        with self.start_debugging(debug_info) as dbg:
            (_, req_launch, _, _, _, _) = lifecycle_handshake(
                dbg.session, debug_info.starttype)

            req_launch.wait()

            dbg.session.send_request('disconnect', restart=True)

        received = list(_strip_newline_output_events(dbg.session.received))
        evts = self.find_events(received, 'terminated')
        self.assertEqual(len(evts), 0)
