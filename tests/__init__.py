from __future__ import absolute_import

import os.path

# Trigger the pydevd vendoring.
import ptvsd  # noqa
from ptvsd._vendored import list_all as vendored


TEST_ROOT = os.path.dirname(__file__)  # noqa
PROJECT_ROOT = os.path.dirname(TEST_ROOT)  # noqa
VENDORED_ROOTS = vendored(resolve=True)  # noqa
