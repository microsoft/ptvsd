# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals


import os
import py.path
import pytest
import sys
import tests

from tests import helpers
from tests.patterns import some
from tests.timeline import Event, Response


class DebugStartBase(object):
    def __init__(self, session, method="base"):
        self.session = session
        self.method = method

    def configure(self, run_as, target, **kwargs):
        pass

    def start_debugging(self, **kwargs):
        pass

    def stop_debugging(self):
        pass

    def _build_common_args(
        self,
        args,
        showReturnValue=None,
        justMyCode=True,
        subProcess=None,
        django=None,
        jinja=None,
        flask=None,
        pyramid=None,
        logToFile=None,
        redirectOutput=True,
        noDebug=None,
    ):

        if showReturnValue:
            args["showReturnValue"] = showReturnValue
            args["debugOptions"] += ["ShowReturnValue"]

        if redirectOutput:
            args["redirectOutput"] = redirectOutput
            args["debugOptions"] += ["RedirectOutput"]

        if justMyCode is False:
            # default behavior is Just-my-code = true
            args["justMyCode"] = justMyCode
            args["debugOptions"] += ["DebugStdLib"]

        if django:
            args["django"] = django
            args["debugOptions"] += ["Django"]

        if jinja:
            args["jinja"] = jinja
            args["debugOptions"] += ["Jinja"]

        if flask:
            args["flask"] = flask
            args["debugOptions"] += ["Flask"]

        if pyramid:
            args["pyramid"] = pyramid
            args["debugOptions"] += ["Pyramid"]

        # VS Code uses noDebug in both attach and launch cases. Even though
        # noDebug on attach does not make any sense.
        args["noDebug"] = bool(noDebug)

        if subProcess:
            args["subProcess"] = subProcess
            args["debugOptions"] += ["Multiprocess"]

    def __str__(self):
        return self.method


class Launch(DebugStartBase):
    def __init__(self, session):
        super().__init__(session, "launch")
        self._launch_args = None
        self.captured_output = helpers.CapturedOutput(self.session)

    def _build_launch_args(
        self,
        launch_args,
        run_as,
        target,
        pythonPath=sys.executable,
        args=[],
        cwd=None,
        env=os.environ.copy(),
        stopOnEntry=None,
        gevent=None,
        sudo=None,
        waitOnNormalExit=None,
        waitOnAbnormalExit=None,
        breakOnSystemExitZero=None,
        console="internalConsole",
        internalConsoleOptions="neverOpen",
        **kwargs
    ):
        assert console in ("internalConsole", "integratedTerminal", "externalTerminal")
        debug_options = []
        launch_args.update(
            {
                "name": "Terminal",
                "type": "python",
                "request": "launch",
                "console": console,
                "env": env,
                "pythonPath": pythonPath,
                "args": args,
                "internalConsoleOptions": internalConsoleOptions,
                "debugOptions": debug_options,
            }
        )

        if launch_args:
            args["env"]["PTVSD_LOG_DIR"] = self.session.log_dir

        if stopOnEntry:
            launch_args["stopOnEntry"] = stopOnEntry
            debug_options += ["StopOnEntry"]

        if gevent:
            launch_args["gevent"] = gevent
            launch_args["env"]["GEVENT_SUPPORT"] = "True"

        if sudo:
            launch_args["sudo"] = sudo

        if waitOnNormalExit:
            debug_options += ["WaitOnNormalExit"]

        if waitOnAbnormalExit:
            debug_options += ["WaitOnAbnormalExit"]

        if breakOnSystemExitZero:
            debug_options += ["BreakOnSystemExitZero"]

        target_str = target
        if isinstance(target, py.path.local):
            target_str = target.strpath

        if cwd:
            launch_args["cwd"] = cwd
        elif os.path.isfile(target_str) or os.path.isdir(target_str):
            launch_args["cwd"] = os.path.dirname(target_str)
        else:
            launch_args["cwd"] = os.getcwd()

        if "PYTHONPATH" not in env:
            env["PYTHONPATH"] = ""

        env["PYTHONPATH"] += os.pathsep + (tests.root / "DEBUGGEE_PYTHONPATH").strpath
        env["PTVSD_SESSION_ID"] = str(self.session.id)

        if run_as == "program":
            launch_args["program"] = target_str
        elif run_as == "module":
            if os.path.isfile(target_str) or os.path.isdir(target_str):
                env["PYTHONPATH"] += os.pathsep + os.path.dirname(target_str)
                try:
                    launch_args["module"] = target_str[
                        (len(os.path.dirname(target_str)) + 1) : -3
                    ]
                except Exception:
                    launch_args["module"] = "code_to_debug"
            else:
                launch_args["module"] = target_str
        elif run_as == "code":
            with open(target_str, "rb") as f:
                launch_args["code"] = f.read()
        else:
            pytest.fail()

        self._set_common_args(launch_args, **kwargs)
        return launch_args

    def configure(self, run_as, target, **kwargs):
        self._launch_args = self._build_launch_args({}, run_as, target, **kwargs)
        self._launch_request = self.session.send_request("launch", self._launch_args)
        self.session.wait_for_next(Event("initialized"))

    def start_debugging(self):
        self.session.send_request("configurationDone").wait_for_response()
        if self._launch_args["noDebug"]:
            self._launch_request.wait_for_response()
        else:
            self.session.wait_for_next(Event("process"))
            self.session.wait_for_next(Response(self._launch_request))

            self.session.expect_new(
                Event(
                    "process",
                    {
                        "name": some.str,
                        "isLocalProcess": True,
                        "startMethod": "launch",
                        "systemProcessId": some.int,
                    },
                )
            )

            # Issue 'threads' so that we get the 'thread' event for the main thread now,
            # rather than at some random time later during the test.
            # Note: it's actually possible that the 'thread' event was sent before the 'threads'
            # request (although the 'threads' will force 'thread' to be sent if it still wasn't).
            self.session.send_request("threads").wait_for_response()
            self.session.expect_realized(Event("thread"))

    def stop_debugging(self):
        self.session.wait_for_next(Event("exited"))
        self.session.wait_for_next(Event("terminated"))


class AttachSocketImport(DebugStartBase):
    def __init__(self, session):
        super().__init__(session, "attach_socket_import")


class AttachSocketCmdLine(DebugStartBase):
    def __init__(self, session):
        super().__init__(session, "attach_socket_cmdline")


class AttachProcessId(DebugStartBase):
    def __init__(self, session):
        super().__init__(session, "attach_pid")


class CustomServer(DebugStartBase):
    def __init__(self, session):
        super().__init__(session, "custom_server")


class CustomClient(DebugStartBase):
    def __init__(self, session):
        super().__init__(session, "custom_client")


__all__ = [
    Launch,  # ptvsd --client ... foo.py
    AttachSocketCmdLine,  #  ptvsd ... foo.py
    AttachSocketImport,  #  python foo.py (foo.py must import debug_me)
    AttachProcessId,  # python foo.py && ptvsd ... --pid
    CustomClient,  # python foo.py (foo.py has to manually call ptvsd.attach)
    CustomServer,  # python foo.py (foo.py has to manually call ptvsd.enable_attach)
]
