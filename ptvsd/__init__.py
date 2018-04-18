# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

__all__ = [
    '__version__', '__author__',
    'enable_attach', 'wait_for_attach', 'break_into_debugger', 'is_attached',
]


# _vendored_pydevd must be imported first to ensure that the
# ptvsd-vendored copy of pydevd gets used.
from . import _vendored_pydevd
from ptvsd.version import __version__, __author__
from ptvsd.attach_server import (
    enable_attach, wait_for_attach, break_into_debugger, is_attached,
)
del _vendored_pydevd
