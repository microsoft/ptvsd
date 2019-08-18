# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import argparse
import locale
import sys

# WARNING: ptvsd and submodules must not be imported on top level in this module,
# and should be imported locally inside main() instead.


def main(args):
    import ptvsd
    from ptvsd.common import log, options
    from ptvsd.adapter import channels

    if args.cls and args.debug_server is not None:
        print("\033c")

    options.log_dir = args.log_dir
    log.stderr_levels |= {"info"}
    log.filename_prefix = "ptvsd.adapter"
    log.to_file()
    log.describe_environment("ptvsd.adapter startup environment:")

    if args.debug_server is None:
        address = None
    else:
        address = ("localhost", args.debug_server)
        # If in debugServer mode, log "debug" to stderr as well.
        log.stderr_levels |= {"debug"}

    chan = channels.Channels()
    ide = chan.connect_to_ide(address)

    ide.start()
    ide.send_event(
        "output",
        {
            "category": "telemetry",
            "output": "ptvsd.adapter",
            "data": {"version": ptvsd.__version__},
        },
    )

    # Wait until the IDE debug session is over - everything interesting is going to
    # be happening on the background threads running the IDE and the server message
    # loops from here on.
    ide.wait()

    # Make sure the server message loop is also done, but only if the server connection
    # has been established.
    server = chan.server()
    if server is not None:
        server.wait()


def _parse_argv():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-d",
        "--debug-server",
        type=int,
        nargs="?",
        default=None,
        const=8765,
        metavar="PORT",
        help="start the adapter in debugServer mode on the specified port",
    )

    parser.add_argument(
        "--cls", action="store_true", help="clear screen before starting the debuggee"
    )

    parser.add_argument(
        "--log-dir",
        type=str,
        metavar="DIR",
        help="enable logging and use DIR to save adapter logs",
    )

    return parser.parse_args()


if __name__ == "__main__":
    # ptvsd can also be invoked directly rather than via -m. In this case, the first
    # entry on sys.path is the one added automatically by Python for the directory
    # containing this file. This means that import ptvsd will not work, since we need
    # the parent directory of ptvsd/ to be in sys.path, rather than ptvsd/adapter/.
    #
    # The other issue is that many other absolute imports will break, because they
    # will be resolved relative to ptvsd/adapter/ - e.g. `import state` will then try
    # to import ptvsd/adapter/state.py.
    #
    # To fix both, we need to replace the automatically added entry such that it points
    # at parent directory of ptvsd/ instead of ptvsd/adapter, import ptvsd with that
    # in sys.path, and then remove the first entry entry altogether, so that it doesn't
    # affect any further imports we might do. For example, suppose the user did:
    #
    #   python /foo/bar/ptvsd/adapter ...
    #
    # At the beginning of this script, sys.path will contain "/foo/bar/ptvsd/adapter"
    # as the first entry. What we want is to replace it with "/foo/bar', then import
    # ptvsd with that in effect, and then remove the replaced entry before any more
    # code runs. The imported ptvsd module will remain in sys.modules, and thus all
    # future imports of it or its submodules will resolve accordingly.
    if "ptvsd" not in sys.modules:
        # Do not use dirname() to walk up - this can be a relative path, e.g. ".".
        sys.path[0] = sys.path[0] + "/../../"
        __import__("ptvsd")
        del sys.path[0]

    # Load locale settings.
    locale.setlocale(locale.LC_ALL, "")

    main(_parse_argv())
