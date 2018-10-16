# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import os.path

def get_test_root(name):
    p = os.path.join(os.path.dirname(__file__), name)
    if os.path.exists(p):
        return p
    return None
