import unittest

from ptvsd.socket import Address
from tests import PROJECT_ROOT
from tests.helpers.debugadapter import DebugAdapter
from tests.helpers.debugclient import EasyDebugClient as DebugClient
from tests.helpers.lock import LockTimeoutError
from tests.helpers.script import set_lock, set_release
from . import LifecycleTestsBase, PORT, lifecycle_handshake


class EnableAttachTests(LifecycleTestsBase, unittest.TestCase):

    def test_does_not_block(self):
        addr = Address('localhost', PORT)
        filename = self.write_script('spam.py', """
            import sys
            sys.path.insert(0, {!r})
            import ptvsd
            ptvsd.enable_attach({}, redirect_output=False)
            # <ready>
            """.format(PROJECT_ROOT, tuple(addr)),
        )
        lockfile = self.workspace.lockfile()
        _, wait = set_release(filename, lockfile, 'ready')

        #DebugAdapter.VERBOSE = True
        adapter = DebugAdapter.start_embedded(addr, filename)
        with adapter:
            wait(timeout=1)
            adapter.wait()

    def test_wait_for_attach(self):
        addr = Address('localhost', PORT)
        filename = self.write_script('spam.py', """
            import sys
            sys.path.insert(0, {!r})
            import ptvsd
            ptvsd.enable_attach({}, redirect_output=False)

            ptvsd.wait_for_attach()
            # <ready>
            # <wait>
            """.format(PROJECT_ROOT, tuple(addr)),
        )
        lockfile1 = self.workspace.lockfile()
        _, wait = set_release(filename, lockfile1, 'ready')
        lockfile2 = self.workspace.lockfile()
        done, _ = set_lock(filename, lockfile2, 'wait')

        adapter = DebugAdapter.start_embedded(addr, filename)
        with adapter:
            with DebugClient() as editor:
                session = editor.attach_socket(addr, adapter, timeout=1)
                # Ensure that it really does wait.
                with self.assertRaises(LockTimeoutError):
                    wait(timeout=0.5)

                lifecycle_handshake(session, 'attach')
                wait(timeout=1)
                done()
                adapter.wait()
