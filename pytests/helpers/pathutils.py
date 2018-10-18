# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import os.path

def get_test_root(name):
    pytests_dir = os.path.dirname(os.path.dirname(__file__))
    p = os.path.join(pytests_dir, 'func', 'testfiles', name)
    if os.path.exists(p):
        return p
    return None
