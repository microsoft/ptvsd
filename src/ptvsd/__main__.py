# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, with_statement

import os.path
import pydevd
import runpy
import sys


# ptvsd can also be invoked directly rather than via -m. In this case, the
# first entry on sys.path is the one added automatically by Python for the
# directory containing this file. This means that 1) import ptvsd will not
# work, since we need the parent directory of ptvsd/ to be on path, rather
# than ptvsd/ itself, and 2) many other absolute imports will break, because
# they will be resolved relative to ptvsd/ - e.g. import socket will then
# try to import ptvsd/socket.py!
#
# To fix this, we need to replace the automatically added entry such that it
# points at the parent directory instead, import ptvsd from that directory,
# and then remove than entry altogether so that it doesn't affect any further
# imports. For example, suppose the user did:
#
#   python /foo/bar/ptvsd ...
#
# At the beginning of this script, sys.path will contain '/foo/bar/ptvsd' as
# the first entry. What we want is to replace it with '/foo/bar', then import
# ptvsd with that in effect, and then remove it before continuing execution.
if __name__ == '__main__' and 'ptvsd' not in sys.modules:
    sys.path[0] = os.path.dirname(sys.path[0])
    import ptvsd # noqa
    del sys.path[0]


import ptvsd.options
import ptvsd.version


# When forming the command line involving __main__.py, it might be tempting to
# import it as a module, and then use its __file__. However, that does not work
# reliably, because __file__ can be a relative path - and when it is relative,
# that's relative to the current directory at the time import was done, which
# may be different from the current directory at the time the path is used.
#
# So, to be able to correctly locate the script at any point, we compute the
# absolute path at import time.
__file__ = os.path.abspath(__file__)


TARGET = '<filename> | -m <module> | -c <code> | --pid <pid>'

HELP = ('''ptvsd %s
See https://aka.ms/ptvsd for documentation.

Usage: ptvsd --host <address> --port <port> [--wait] [--multiprocess]
             ''' + TARGET + '''
''') % (ptvsd.version.__version__)


# In Python 2, arguments are passed as bytestrings in locale encoding
# For uniformity, parse them into Unicode strings.
def string(s):
    if isinstance(s, bytes):
        s = s.decode(sys.getfilesystemencoding())
    return s

def in_range(parser, start, stop):
    def parse(s):
        n = parser(s)
        if start is not None and n < start:
            raise ValueError('must be >= %s' % start)
        if stop is not None and n >= stop:
            raise ValueError('must be < %s' % stop)
        return n
    return parse

port = in_range(int, 0, 2**16)

pid = in_range(int, 0, None)


def print_help_and_exit(switch, it):
    print(HELP, file=sys.stderr)
    sys.exit(0)

def print_version_and_exit(switch, it):
    print(ptvsd.version.__version__)
    sys.exit(0)

def set_arg(varname, parser):
    def action(arg, it):
        value = parser(next(it))
        setattr(ptvsd.options, varname, value)
    return action

def set_true(varname):
    def do(arg, it):
        setattr(ptvsd.options, varname, True)
    return do

def set_target(kind, parser=None):
    def do(arg, it):
        ptvsd.options.target_kind = kind
        ptvsd.options.target = arg if parser is None else parser(next(it))
    return do


switches = [
    # Switch                    Placeholder         Action                                  Required
    # ======                    ===========         ======                                  ========

    # Switches that are documented for use by end users.
    (('-?', '-h', '--help'),    None,               print_help_and_exit,                    False),
    (('-V', '--version'),       None,               print_version_and_exit,                 False),
    ('--host',                  '<address>',        set_arg('host', string),                True),
    ('--port',                  '<port>',           set_arg('port', port),                  False),
    ('--wait',                  None,               set_true('wait'),                       False),
    ('--multiprocess',          None,               set_true('multiprocess'),               False),

    # Switches that are used internally by the IDE or ptvsd itself.
    ('--nodebug',               None,               set_true('no_debug'),                   False),
    ('--client',                None,               set_true('client'),                     False),
    ('--subprocess-of',         '<pid>',            set_arg('subprocess_of', pid),          False),
    ('--subprocess-notify',     '<port>',           set_arg('subprocess_notify', port),     False),

    # Targets. The '' entry corresponds to positional command line arguments,
    # i.e. the ones not preceded by any switch name.
    ('',                        '<filename>',       set_target('file'),                     False),
    ('-m',                      '<module>',         set_target('module', string),           False),
    ('-c',                      '<code>',           set_target('code', string),             False),
    ('--pid',                   '<pid>',            set_target('pid', pid),                 False),
]


def parse(args):
    it = iter(args)
    while True:
        try:
            arg = next(it)
        except StopIteration:
            raise ValueError('missing target: ' + TARGET)

        switch = arg if arg.startswith('-') else ''
        for i, (sw, placeholder, action, _) in enumerate(switches):
            if isinstance(sw, str):
                sw = (sw,)
            if switch in sw:
                del switches[i]
                break
        else:
            raise ValueError('unrecognized switch ' + switch)

        try:
            action(arg, it)
        except StopIteration:
            assert placeholder is not None
            raise ValueError('%s: missing %s' % (switch, placeholder))
        except Exception as ex:
            raise ValueError('invalid %s %s: %s' % (switch, placeholder, str(ex)))

        if ptvsd.options.target is not None:
            break

    for sw, placeholder, _, required in switches:
        if required:
            if not isinstance(sw, str):
                sw = sw[0]
            message = 'missing required %s' % sw
            if placeholder is not None:
                message += ' ' + placeholder
            raise ValueError(message)


def run_file():
    ptvsd.enable_attach()
    runpy.run_path(ptvsd.options.target)

def run_module():
    ptvsd.enable_attach()
    runpy.run_module(ptvsd.options.target)

def run_code():
    code = compile(ptvsd.options.target, '<string>', 'exec')
    ptvsd.enable_attach()
    eval(code, {})

def attach_to_pid():
    def quoted_str(s):
        assert not isinstance(s, bytes)
        unescaped = set(chr(ch) for ch in range(32, 127)) - {'"', "'", '\\'}
        def escape(ch):
            return ch if ch in unescaped else '\\u%04X' % ord(ch)
        return 'u"' + ''.join(map(escape, s)) + '"'

    pid = ptvsd.options.target
    host = quoted_str(ptvsd.options.host)
    port = ptvsd.options.port

    ptvsd_path = os.path.abspath(os.path.join(ptvsd.__file__, '../..'))
    if isinstance(ptvsd_path, bytes):
        ptvsd_path = ptvsd_path.decode(sys.getfilesystemencoding())
    ptvsd_path = quoted_str(ptvsd_path)

    # pydevd requires injected code to not contain any single quotes.
    code = '''
import os
assert os.getpid() == {pid}

import sys
sys.path.insert(0, {ptvsd_path})
import ptvsd
del sys.path[0]

import ptvsd.options
ptvsd.options.client = True
ptvsd.options.host = {host}
ptvsd.options.port = {port}

ptvsd.enable_attach()
'''.format(**locals())
    print(code)

    pydevd_attach_to_process_path = os.path.join(
        os.path.dirname(pydevd.__file__),
        'pydevd_attach_to_process')
    sys.path.insert(0, pydevd_attach_to_process_path)
    from add_code_to_python_process import run_python_code
    run_python_code(pid, code, connect_debugger_tracing=True)


def main(argv=sys.argv):
    try:
        parse(argv[1:])
    except Exception as ex:
        print(HELP + '\nError: ' + str(ex), file=sys.stderr)
        sys.exit(2)

    run = {
        'file': run_file,
        'module': run_module,
        'code': run_code,
        'pid': attach_to_pid,
    }[ptvsd.options.target_kind]
    run()

if __name__ == '__main__':
    main(sys.argv)
