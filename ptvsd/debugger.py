# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import sys

from ptvsd.__main__ import run_module, run_file, enable_attach as ptvsd_enable_attach # noqa


# TODO: not needed?
DONT_DEBUG = []
DEFAULT_PORT = 5678
LOCALHOST = 'localhost'

RUNNERS = {
    'module': run_module,  # python -m spam
    'script': run_file,  # python spam.py
    'code': run_file,  # python -c 'print("spam")'
    None: run_file,  # catchall
}


def debug(filename, port_num, debug_id, debug_options, run_as,
          _runners=RUNNERS, _extra=None, *args, **kwargs):
    # TODO: docstring
    if _extra is None:
        _extra = sys.argv[1:]
    address = (LOCALHOST, port_num)
    try:
        run = _runners[run_as]
    except KeyError:
        # TODO: fail?
        run = _runners[None]
    if _extra:
        args = _extra + list(args)
    run(address, filename, *args, **kwargs)


def enable_attach(address=('0.0.0.0', DEFAULT_PORT), redirect_output=True):
    ptvsd_enable_attach(address, redirect_output)
