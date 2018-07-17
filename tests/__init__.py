from __future__ import absolute_import

import os
import os.path
import sys
import unittest

# Importing "ptvsd" here triggers the vendoring code before any vendored
# code ever gets imported.
import ptvsd
import ptvsd.attach_server
from ptvsd._vendored import list_all as vendored


TEST_ROOT = os.path.abspath(os.path.dirname(__file__))  # noqa
RESOURCES_ROOT = os.path.join(TEST_ROOT, 'resources')  # noqa
PROJECT_ROOT = os.path.dirname(TEST_ROOT)  # noqa
VENDORED_ROOTS = vendored(resolve=True)  # noqa

# The default timeout is 1.0, which causes intermittent connection
# timeouts in tests.  So we use a much smaller timeout for the test
# suite.  In the few cases where we want a longer timeout during
# enable_attach(), individual tests can temporarily use a higher
# value.  They may also need to pass "wait=False" to the appropriate
# DebugAdapter factory methods (or pass "wait_for_connect" to
# DebugClient._launch()).
ptvsd.attach_server.WAIT_TIMEOUT = 0.1


def skip_py2(decorated=None):
    if sys.version_info[0] > 2:
        return decorated
    msg = 'not tested under Python 2'
    if decorated is None:
        raise unittest.SkipTest(msg)
    else:
        decorator = unittest.skip(msg)
    return decorator(decorated)


if sys.version_info[0] == 2:
    # Hack alert!!!
    class SkippingTestSuite(unittest.TestSuite):
        def __init__(self, tests=()):
            if tests and type(tests[0]).__name__ == 'ModuleImportFailure':
                _, exc, _ = sys.exc_info()
                if isinstance(exc, unittest.SkipTest):
                    from unittest.loader import _make_failed_load_tests
                    suite = _make_failed_load_tests(
                        tests[0]._testMethodName,
                        exc,
                        type(self),
                    )
                    tests = tuple(suite)
            unittest.TestSuite.__init__(self, tests)
    unittest.TestLoader.suiteClass = SkippingTestSuite
