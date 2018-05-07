from __future__ import print_function

import contextlib
import time
import sys
import unittest

import ptvsd._util
from ptvsd.socket import create_client, close_socket
from tests.helpers.proc import Proc
from tests.helpers.workspace import Workspace


@contextlib.contextmanager
def _retrier(timeout=1, persec=10, max=None, verbose=False):
    steps = int(timeout * persec) + 1
    delay = 1.0 / persec

    @contextlib.contextmanager
    def attempt(num):
        if verbose:
            print('*', end='')
            sys.stdout.flush()
        yield
        if verbose:
            if num % persec == 0:
                print()
            elif (num * 2) % persec == 0:
                print(' ', end='')

    def attempts():
        # The first attempt always happens.
        num = 1
        with attempt(num):
            yield num
        for num in range(2, steps):
            if max is not None and num > max:
                raise RuntimeError('too many attempts (max {})'.format(max))
            time.sleep(delay)
            with attempt(num):
                yield num
        else:
            raise RuntimeError('timed out')
    yield attempts()


class RawConnectionTests(unittest.TestCase):

    VERBOSE = False
    #VERBOSE = True

    def setUp(self):
        super(RawConnectionTests, self).setUp()
        self.workspace = Workspace()
        self.addCleanup(self.workspace.cleanup)

    def test_repeated(self):
        def connect(addr, wait=None, closeonly=False):
            sock = create_client()
            try:
                sock.settimeout(1)
                sock.connect(addr)
                if wait is not None:
                    time.sleep(wait)
            finally:
                if closeonly:
                    sock.close()
                else:
                    close_socket(sock)
        filename = self.workspace.write('spam.py', content="""
            raise Exception('should never run')
            """)
        addr = ('localhost', 5678)
        proc = Proc.start_python_module('ptvsd', [
            '--server',
            '--port', '5678',
            '--file', filename,
        ], stdout=sys.stdout if self.VERBOSE else None)
        proc.VERBOSE = self.VERBOSE
        ptvsd._util.DEBUG = self.VERBOSE
        with proc:
            # Wait for the server to spin up.
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
            connect(addr, closeonly=True)
            connect(addr)
            connect(addr)
            # TODO: wait for server to finish
