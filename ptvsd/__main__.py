# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import argparse
import os.path
import sys

from ptvsd._local import debug_main, run_main
from ptvsd.socket import Address
from ptvsd.version import __version__, __author__  # noqa


##################################
# the script

"""
For the PyDevd CLI handling see:

  https://github.com/fabioz/PyDev.Debugger/blob/master/_pydevd_bundle/pydevd_command_line_handling.py
  https://github.com/fabioz/PyDev.Debugger/blob/master/pydevd.py#L1450  (main func)
"""  # noqa

PYDEVD_OPTS = {
    '--file',
    '--client',
    #'--port',
    '--vm_type',
}

PYDEVD_FLAGS = {
    '--DEBUG',
    '--DEBUG_RECORD_SOCKET_READS',
    '--cmd-line',
    '--module',
    '--multiproc',
    '--multiprocess',
    '--print-in-debugger-startup',
    '--save-signatures',
    '--save-threading',
    '--save-asyncio',
    '--server',
}

USAGE = """
  {0} [-h] [--nodebug] [--host HOST | --server-host HOST] --port PORT -m MODULE [arg ...]
  {0} [-h] [--nodebug] [--host HOST | --server-host HOST] --port PORT FILENAME [arg ...]
"""  # noqa


def parse_args(argv=None):
    """Return the parsed args to use in main()."""
    if argv is None:
        argv = sys.argv
        prog = argv[0]
        if prog == __file__:
            prog = '{} -m ptvsd'.format(os.path.basename(sys.executable))
    else:
        prog = argv[0]
    argv = argv[1:]

    supported, pydevd, script = _group_args(argv)
    args = _parse_args(prog, supported)
    extra = pydevd
    if script:
        extra += script
    return args, extra


def _group_args(argv):
    supported = []
    pydevd = []
    script = []

    try:
        pos = argv.index('--')
    except ValueError:
        script = []
    else:
        script = argv[pos + 1:]
        argv = argv[:pos]

    for arg in argv:
        if arg == '-h' or arg == '--help':
            return argv, [], script

    gottarget = False
    skip = 0
    for i in range(len(argv)):
        if skip:
            skip -= 1
            continue

        arg = argv[i]
        try:
            nextarg = argv[i + 1]
        except IndexError:
            nextarg = None

        # TODO: Deprecate the PyDevd arg support.
        # PyDevd support
        if gottarget:
            script = argv[i:] + script
            break
        if arg == '--client':
            arg = '--host'
        elif arg == '--file':
            if nextarg is None:  # The filename is missing...
                pydevd.append(arg)
                continue  # This will get handled later.
            if nextarg.endswith(':') and '--module' in pydevd:
                pydevd.remove('--module')
                arg = '-m'
                argv[i + 1] = nextarg = nextarg[:-1]
            else:
                arg = nextarg
                skip += 1

        if arg in PYDEVD_OPTS:
            pydevd.append(arg)
            if nextarg is not None:
                pydevd.append(nextarg)
            skip += 1
        elif arg in PYDEVD_FLAGS:
            pydevd.append(arg)
        elif arg == '--nodebug':
            supported.append(arg)

        # ptvsd support
        elif arg in ('--host', '--server-host', '--port', '-m'):
            if arg == '-m':
                gottarget = True
            supported.append(arg)
            if nextarg is not None:
                supported.append(nextarg)
            skip += 1
        elif arg in ('--single-session',):
            supported.append(arg)
        elif not arg.startswith('-'):
            supported.append(arg)
            gottarget = True

        # unsupported arg
        else:
            supported.append(arg)
            break

    return supported, pydevd, script


def _parse_args(prog, argv):
    parser = argparse.ArgumentParser(
        prog=prog,
        usage=USAGE.format(prog),
    )
    parser.add_argument('--nodebug', action='store_true')
    host = parser.add_mutually_exclusive_group()
    host.add_argument('--host')
    host.add_argument('--server-host')
    parser.add_argument('--port', type=int, required=True)

    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('-m', dest='module')
    target.add_argument('filename', nargs='?')

    parser.add_argument('--single-session', action='store_true')

    args = parser.parse_args(argv)
    ns = vars(args)

    serverhost = ns.pop('server_host', None)
    clienthost = ns.pop('host', None)
    if serverhost:
        args.address = Address.as_server(serverhost, ns.pop('port'))
    elif not clienthost:
        if args.nodebug:
            args.address = Address.as_client(clienthost, ns.pop('port'))
        else:
            args.address = Address.as_server(clienthost, ns.pop('port'))
    else:
        args.address = Address.as_client(clienthost, ns.pop('port'))

    module = ns.pop('module')
    filename = ns.pop('filename')
    if module is None:
        args.name = filename
        args.kind = 'script'
    else:
        args.name = module
        args.kind = 'module'
    #if argv[-1] != args.name or (module and argv[-1] != '-m'):
    #    parser.error('script/module must be last arg')

    return args


def main(addr, name, kind, extra=(), nodebug=False, **kwargs):
    if nodebug:
        run_main(addr, name, kind, *extra, **kwargs)
    else:
        debug_main(addr, name, kind, *extra, **kwargs)


if __name__ == '__main__':
    args, extra = parse_args()
    main(args.address, args.name, args.kind, extra, nodebug=args.nodebug,
         singlesession=args.single_session)
