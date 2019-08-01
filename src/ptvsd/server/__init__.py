# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

# "force_pydevd" must be imported first to ensure (via side effects)
# that the ptvsd-vendored copy of pydevd gets used.
import ptvsd._vendored.force_pydevd # noqa
