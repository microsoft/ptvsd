# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import os.path
import pytest
import subprocess
import sys
import time
import ptvsd.common.launcher
from ptvsd.common.launcher import parse, WAIT_ON_NORMAL_SWITCH, WAIT_ON_ABNORMAL_SWITCH

launcher_py = os.path.abspath(ptvsd.common.launcher.__file__)


@pytest.mark.parametrize("run_as", ["file", "module", "code"])
@pytest.mark.parametrize("mode", ["normal", "abnormal", "both", ""])
@pytest.mark.parametrize("seperator", ["separator", ""])
def test_launcher_parser(mode, seperator, run_as):
    args = []

    if mode == "normal":
        args += [WAIT_ON_NORMAL_SWITCH]
    elif mode == "abnormal":
        args += [WAIT_ON_ABNORMAL_SWITCH]
    elif mode == "both":
        args += [WAIT_ON_NORMAL_SWITCH, WAIT_ON_ABNORMAL_SWITCH]
    else:
        pass

    if seperator:
        args += ["--"]

    if run_as == "file":
        expected = ["myscript.py", "--arg1", "--arg2", "--arg3", "--", "more args"]
    elif run_as == "module":
        expected = ["-m", "myscript", "--arg1", "--arg2", "--arg3", "--", "more args"]
    else:
        expected = ["-c", "some code"]

    args += expected

    if seperator:
        actual = list(parse(args))
        assert actual == expected
    else:
        with pytest.raises(AssertionError):
            actual = parse(args)


@pytest.mark.parametrize("run_as", ["file", "module", "code"])
@pytest.mark.parametrize("mode", ["normal", "abnormal", "both", ""])
@pytest.mark.parametrize("exit_code", [0, 10])
def test_launcher(pyfile, mode, exit_code, run_as):
    @pyfile
    def code_to_run():
        import sys

        sys.exit(int(sys.argv[1]))

    args = [sys.executable, launcher_py]

    if mode == "normal":
        args += [WAIT_ON_NORMAL_SWITCH]
    elif mode == "abnormal":
        args += [WAIT_ON_ABNORMAL_SWITCH]
    elif mode == "both":
        args += [WAIT_ON_NORMAL_SWITCH, WAIT_ON_ABNORMAL_SWITCH]
    else:
        pass

    args += ["--"]

    if run_as == "file":
        args += [code_to_run.strpath, str(exit_code)]
    elif run_as == "module":
        args += ["-m", "code_to_run", str(exit_code)]
    else:
        with open(code_to_run, "r") as f:
            args += ["-c", f.read(), str(exit_code)]

    p = subprocess.Popen(
        args=args,
        bufsize=0,
        cwd=os.path.dirname(code_to_run),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )

    wait_for_user = (exit_code, mode) in [
        (0, "normal"),
        (10, "abnormal"),
        (0, "both"),
        (10, "both"),
    ]

    if wait_for_user:
        while not p.stdout.read(5).startswith(b"Press"):
            time.sleep(0.1)
        # TODO: Fix sending input to the launched process to terminate
        # p.stdin.write(b" ")
        # p.stdin.flush()

        # assert exit_code == p.wait()
        p.kill()
    else:
        assert exit_code == p.wait()
