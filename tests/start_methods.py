# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals


import os
import py.path
import pytest
import subprocess
import sys

from ptvsd.common import fmt
from tests import helpers
from tests.patterns import some
from tests.timeline import Event, Response
from tests import net, watchdog


PTVSD_PORT = net.get_test_server_port(5678, 5800)

# Code that is injected into the debuggee process when it does `import debug_me`,
# and start_method is attach_socket_*
PTVSD_DEBUG_ME = """
import ptvsd
ptvsd.enable_attach(("localhost", {ptvsd_port}), log_dir={log_dir})
ptvsd.wait_for_attach()
"""


class DebugStartBase(object):
    def __init__(self, session, method="base"):
        self.session = session
        self.method = method
        self.captured_output = helpers.CapturedOutput(self.session)

    def get_ignored(self):
        return []

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
        if logToFile:
            args["env"]["PTVSD_LOG_DIR"] = self.session.log_dir

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

        if run_as == "program":
            launch_args["program"] = target_str
        elif run_as == "module":
            if os.path.isfile(target_str) or os.path.isdir(target_str):
                env["PYTHONPATH"] += os.pathsep + os.path.dirname(target_str)
                try:
                    launch_args["module"] = target_str[
                        (len(os.path.dirname(target_str)) + 1): -3
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

        self._build_common_args(launch_args, **kwargs)
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


class AttachBase(DebugStartBase):
    def __init__(self, session, name):
        super().__init__(session, name)

    def configure(self, run_as, target, **kwargs):
        pass

    def start_debugging(self, **kwargs):
        pass

    def stop_debugging(self):
        pass


class AttachSocketImport(DebugStartBase):
    def __init__(self, session):
        super().__init__(session, "attach_socket_import")
        self._attach_args = {}

    def get_ignored(self):
        return [Event("exited"), Event("terminated")] + super().get_ignored()

    def _build_attach_args(
        self,
        attach_args,
        run_as,
        target,
        host="127.0.0.1",
        port=PTVSD_PORT,
        pathMappings=None,
        rules=None,
        **kwargs
    ):
        assert host is not None
        assert port is not None
        debug_options = []
        attach_args.update(
            {
                "name": "Attach",
                "type": "python",
                "request": "attach",
                "debugOptions": debug_options,
            }
        )

        attach_args["host"] = host
        attach_args["port"] = port

        if pathMappings is not None:
            attach_args["pathMappings"] = pathMappings

        if rules is not None:
            attach_args["rules"] = rules

        self._build_common_args(attach_args, **kwargs)
        return attach_args

    def _check_ready_for_import(self, path_or_code):
        if os.path.isfile(path_or_code):
            with open(path_or_code, "rb") as f:
                code = f.read()
        elif "\n" in path_or_code:
            code = path_or_code
        else:
            # path_or_code is a module name
            return
        assert b"debug_me" in code, fmt(
            "{0} is started via {1}, but it doesn't import debug_me.",
            path_or_code,
            self.method,
        )

    def configure(
        self,
        run_as,
        target,
        pythonPath=sys.executable,
        args=[],
        cwd=None,
        env=os.environ.copy(),
        **kwargs
    ):
        self._attach_args = self._build_attach_args({}, run_as, target, **kwargs)

        ptvsd_port = self._attach_args["port"]
        log_dir = (
            self.session.log_dir if self._attach_args.get("logToFile", False) else None
        )
        env["PTVSD_DEBUG_ME"] = fmt(
            PTVSD_DEBUG_ME, ptvsd_port=ptvsd_port, log_dir=log_dir
        )

        target_str = target
        if isinstance(target, py.path.local):
            target_str = target.strpath

        self._check_ready_for_import(target_str)

        cli_args = [self._attach_args.get("pythonPath", sys.executable)]
        if run_as == "program":
            cli_args += [target_str]
        elif run_as == "module":
            if os.path.isfile(target_str) or os.path.isdir(target_str):
                env["PYTHONPATH"] += os.pathsep + os.path.dirname(target_str)
                try:
                    module = target_str[(len(os.path.dirname(target_str)) + 1): -3]
                except Exception:
                    module = "code_to_debug"
            else:
                module = target_str
            cli_args += ["-m", module]
        elif run_as == "code":
            with open(target_str, "rb") as f:
                cli_args += ["-c", f.read()]
        else:
            pytest.fail()

        cli_args += args

        if cwd:
            pass
        elif os.path.isfile(target_str) or os.path.isdir(target_str):
            cwd = os.path.dirname(target_str)
        else:
            cwd = os.getcwd()

        if "pathMappings" not in self._attach_args:
            self._attach_args["pathMappings"] = [{"localRoot": cwd, "remoteRoot": "."}]

        self.debugee_process = subprocess.Popen(
            cli_args,
            cwd=cwd,
            env=env,
            bufsize=0,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.captured_output.capture(self.debugee_process)
        watchdog.register_spawn(self.debugee_process.pid, fmt("debuggee-{0}", self.session.id))

        self._attach_request = self.session.send_request("attach", self._attach_args)
        self.session.wait_for_next(Event("initialized"))

    def start_debugging(self):
        self.session.send_request("configurationDone").wait_for_response()
        if self._attach_args["noDebug"]:
            self._attach_request.wait_for_response()
        else:
            self.session.wait_for_next(Event("process"))
            self.session.wait_for_next(Response(self._attach_request))

            self.session.expect_new(
                Event(
                    "process",
                    {
                        "name": some.str,
                        "isLocalProcess": True,
                        "startMethod": "attach",
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
        try:
            self.debugee_process.wait()
        finally:
            watchdog.unregister_spawn(self.debugee_process.pid, fmt("debuggee-{0}", self.session.id))


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
