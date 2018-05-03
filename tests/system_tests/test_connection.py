from __future__ import print_function

import contextlib
import time
import sys
import unittest

from ptvsd.socket import create_client
from tests.helpers.proc import Proc
from tests.helpers.workspace import Workspace


@contextlib.contextmanager
def _retrier(timeout=1, persec=10, verbose=False):
    steps = int(timeout * persec) + 1
    delay = 1.0 / persec

    def attempts():
        for attempt in range(1, steps + 1):
            if verbose:
                print('*', end='')
                sys.stdout.flush()
            yield attempt
            if verbose:
                if attempt % persec == 0:
                    print()
                elif (attempt * 2) % persec == 0:
                    print(' ', end='')
            time.sleep(delay)
        else:
            raise RuntimeError('timed out')
    yield attempts()
    print()


class RawConnectionTests(unittest.TestCase):

    VERBOSE = False
    #VERBOSE = True

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
        proc.VERBOSE = self.VERBOSE
        with proc:
            with _retrier(timeout=3, verbose=self.VERBOSE) as attempts:
                for _ in attempts:
                    try:
                        connect(addr)
                        break
                    except Exception:
                        pass
            # Give ptvsd long enough to try sending something.
            connect(addr, wait=0.2)
            # We should be able to handle more connections.
            connect(addr)
            connect(addr)
            connect(addr)
