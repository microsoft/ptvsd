# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import os
import sys

import pydevd
from _pydev_bundle import pydev_monkey
from _pydevd_bundle import pydevd_comm

import ptvsd
from ptvsd import multiproc
from ptvsd.socket import Address
from ptvsd.daemon import Daemon, DaemonStoppedError, DaemonClosedError
from ptvsd._util import debug, new_hidden_thread


def start_server(daemon, host, port, **kwargs):
    """Return a socket to a (new) local pydevd-handling daemon.

    The daemon supports the pydevd client wire protocol, sending
    requests and handling responses (and events).

    This is a replacement for _pydevd_bundle.pydevd_comm.start_server.
    """
    sock, next_session = daemon.start_server((host, port))

    def handle_next():
        try:
            session = next_session(**kwargs)
            debug('done waiting')
            return session
        except (DaemonClosedError, DaemonStoppedError):
            # Typically won't happen.
            debug('stopped')
            raise
        except Exception as exc:
            # TODO: log this?
            debug('failed:', exc, tb=True)
            return None

    def serve_forever():
        debug('waiting on initial connection')
        handle_next()
        while True:
            debug('waiting on next connection')
            try:
                handle_next()
            except (DaemonClosedError, DaemonStoppedError):
                break
        debug('done')

    t = new_hidden_thread(
        target=serve_forever,
        name='sessions',
    )
    t.start()
    return sock


def start_client(daemon, host, port, **kwargs):
    """Return a socket to an existing "remote" pydevd-handling daemon.

    The daemon supports the pydevd client wire protocol, sending
    requests and handling responses (and events).

    This is a replacement for _pydevd_bundle.pydevd_comm.start_client.
    """
    sock, start_session = daemon.start_client((host, port))
    start_session(**kwargs)
    return sock


# See pydevd/_vendored/pydevd/_pydev_bundle/pydev_monkey.py
def get_python_c_args(host, port, indC, args, setup):
    runner = '''
import sys
sys.path.append(r'{ptvsd_syspath}')
from ptvsd import multiproc
multiproc.init_subprocess(
    {initial_pid},
    {initial_request},
    {parent_pid},
    {parent_port},
    {first_port},
    {last_port},
    {pydevd_setup})
{rest}
'''

    first_port, last_port = multiproc.subprocess_port_range

    # __file__ will be .../ptvsd/__init__.py, and we want the ...
    ptvsd_syspath = os.path.join(ptvsd.__file__, '../..')

    return runner.format(
        initial_pid=multiproc.initial_pid,
        initial_request=multiproc.initial_request,
        parent_pid=os.getpid(),
        parent_port=multiproc.listener_port,
        first_port=first_port,
        last_port=last_port,
        ptvsd_syspath=ptvsd_syspath,
        pydevd_setup=setup,
        rest=args[indC + 1])


def install(pydevd_module, address,
            start_server=start_server, start_client=start_client,
            **kwargs):
    """Configure pydevd to use our wrapper.

    This is a bit of a hack to allow us to run our VSC debug adapter
    in the same process as pydevd.  Note that, as with most hacks,
    this is somewhat fragile (since the monkeypatching sites may
    change).
    """
    addr = Address.from_raw(address)
    daemon = Daemon(**kwargs)

    _start_server = (lambda p: start_server(daemon, addr.host, p))
    _start_server.orig = start_server
    _start_client = (lambda h, p: start_client(daemon, h, p))
    _start_client.orig = start_client

    # These are the functions pydevd invokes to get a socket to the client.
    pydevd_comm.start_server = _start_server
    pydevd_comm.start_client = _start_client

    # This is invoked when a child process is spawned with multiproc debugging enabled.
    pydev_monkey._get_python_c_args = get_python_c_args

    # Ensure that pydevd is using our functions.
    pydevd_module.start_server = _start_server
    pydevd_module.start_client = _start_client
    __main__ = sys.modules['__main__']
    if __main__ is not pydevd:
        if getattr(__main__, '__file__', None) == pydevd.__file__:
            __main__.start_server = _start_server
            __main__.start_client = _start_client

    return daemon
