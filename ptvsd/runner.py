# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import atexit
import os
import platform
import pydevd
import signal
import socket
import sys
import time
import threading
import warnings

from ptvsd.daemon import DaemonClosedError
from ptvsd import ipcjson, __version__
from ptvsd.socket import close_socket
from ptvsd.wrapper import WAIT_FOR_DISCONNECT_REQUEST_TIMEOUT, WAIT_FOR_THREAD_FINISH_TIMEOUT
from pydevd import CheckOutputThread, init_stdout_redirect, init_stderr_redirect
from _pydevd_bundle.pydevd_kill_all_pydevd_threads import kill_all_pydev_threads

def run(address, filename, run, *args, **kwargs):
    debugger = pydevd.PyDB()
    file = "/home/don/Desktop/development/pythonStuff/issueRepos/debugLocal/three.py"
    is_module = False
    debugger.init_matplotlib_support = lambda *arg: print('xxx')
    debugger.run(file=file, globals=None, locals=None, is_module=is_module, set_trace=False)
    print(debugger)
    print(address)