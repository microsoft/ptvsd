# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals


import subprocess
import sys


_wait_on_normal_exit = False
_wait_on_abnormal_exit = False


HELP = """Usage: launcher [--wait-on-normal] [--wait-on-abnormal] <args>
python launcher.py --wait-on-normal --wait-on-abnormal myscript.py -a 123      # script with args
python launcher.py --wait-on-normal --wait-on-abnormal -m mymodule -a 123      # module with args
python launcher.py --wait-on-normal --wait-on-abnormal -c "<code>"             # run code
"""


def main(argv=sys.argv):
    try:
        process_args = list(parse(argv))
    except Exception as ex:
        print(HELP + "\nError: " + str(ex), file=sys.stderr)
        sys.exit(2)

    p = subprocess.Popen(args=process_args, executable=sys.executable)
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
    if arg == "--wait-on-normal":
        global _wait_on_normal_exit
        _wait_on_normal_exit = True
    elif arg == "--wait-on-abnormal":
        global _wait_on_abnormal_exit
        _wait_on_abnormal_exit = True
    else:
        return False
    return True


def parse(argv):
    ret_argv = []
    for arg in argv:
        if not parse_arg(arg):
            ret_argv += [arg]
    return ret_argv


if __name__ == "__main__":
    main()
