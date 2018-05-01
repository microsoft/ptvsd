import time
import unittest

from ptvsd.socket import create_client
from tests.helpers.proc import Proc
from tests.helpers.workspace import Workspace


class RawConnectionTests(unittest.TestCase):

    def setUp(self):
        super(RawConnectionTests, self).setUp()
        self.workspace = Workspace()
        self.addCleanup(self.workspace.cleanup)

    def test_repeated(self):
        def connect(addr, wait=None):
            sock = create_client()
            try:
                sock.settimeout(1)
                sock.connect(addr)
                if wait is not None:
                    time.sleep(wait)
            finally:
                sock.close()
        filename = self.workspace.write('spam.py', content='')
        addr = ('localhost', 5678)
        proc = Proc.start_python_module('ptvsd', [
            '--server',
            '--port', '5678',
            '--file', filename,
        ])
        proc.VERBOSE = True
        with proc:
            for _ in range(10):
                try:
                    connect(addr)
                    break
                except Exception:
                    time.sleep(0.1)
            else:
                raise RuntimeError('timed out')
            # Give ptvsd long enough to try sending something.
            connect(addr, wait=0.2)
            # We should be able to handle more connections.
            connect(addr)
            connect(addr)
            connect(addr)
