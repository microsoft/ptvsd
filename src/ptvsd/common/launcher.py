# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

__all__ = ["main"]

import os
import os.path
import subprocess
import sys

# Force absolute path on Python 2.
__file__ = os.path.abspath(__file__)


WAIT_ON_NORMAL_SWITCH = "--wait-on-normal"
WAIT_ON_ABNORMAL_SWITCH = "--wait-on-abnormal"


_wait_on_normal_exit = False
_wait_on_abnormal_exit = False


HELP = """Usage: launcher [{normal}] [{abnormal}] <args>
python launcher.py {normal} {abnormal} -- <python args go here>
""".format(normal=WAIT_ON_NORMAL_SWITCH, abnormal=WAIT_ON_ABNORMAL_SWITCH)


def main(argv=sys.argv):
    try:
        process_args = [sys.executable] + list(parse(argv[1:]))
    except Exception as ex:
        print(HELP + "\nError: " + str(ex), file=sys.stderr)
        sys.exit(2)

    p = subprocess.Popen(args=process_args)
    _send_pid(p.pid)
    exit_code = p.wait()

    if _wait_on_normal_exit and exit_code == 0:
        _wait_for_user()
    elif _wait_on_abnormal_exit and exit_code != 0:
        _wait_for_user()

    sys.exit(exit_code)


def _wait_for_user():
    if sys.__stdout__ and sys.__stdin__:
        try:
            import msvcrt
        except ImportError:
            sys.__stdout__.write("Press Enter to continue . . . ")
            sys.__stdout__.flush()
            sys.__stdin__.read(1)
        else:
            sys.__stdout__.write("Press any key to continue . . . ")
            sys.__stdout__.flush()
            msvcrt.getch()


def parse_arg(arg):
    if arg == WAIT_ON_NORMAL_SWITCH:
        global _wait_on_normal_exit
        _wait_on_normal_exit = True
    elif arg == WAIT_ON_ABNORMAL_SWITCH:
        global _wait_on_abnormal_exit
        _wait_on_abnormal_exit = True
    else:
        raise AssertionError("Invalid argument passed to launcher.")

def parse(argv):
    it = iter(argv)
    arg = next(it)
    while arg != "--":
        parse_arg(arg)
        arg = next(it)
    return it


def _send_pid(pid):
    if "PTVSD_PID_SERVER_PORT" not in os.environ:
        return

    from ptvsd.common import socket
    port = int(os.environ["PTVSD_PID_SERVER_PORT"])
    with socket.create_client() as sock:
        sock.connect(("127.0.0.1", port))
        sock.sendall(str(pid).encode("ascii"))


if __name__ == "__main__":
    # This is so we can correctly import socket from ptvsd.common
    if "ptvsd" not in sys.modules:
        sys.path[0] = os.path.dirname(__file__) + "/../../"
        __import__("ptvsd")
        del sys.path[0]
    main()
