# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""Patterns that are specific to the Debug Adapter Protocol.
"""

from tests.patterns import some


id = some.int.in_range(0, 10000)
"""Matches a DAP "id", assuming some reasonable range for an implementation that
generates those ids sequentially.
"""


def source(path, **kwargs):
    """Matches DAP Source objects.
    """
    d = {"path": path}
    d.update(kwargs)
    return some.dict.containing(d)


def frame(source, line, **kwargs):
    """Matches DAP Frame objects.
    """
    d = {"id": some.dap.id, "column": 1}
    d.update(kwargs)
    return some.dict.containing(d)
