# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import os.path


__file__ = os.path.abspath(__file__)
_ptvsd_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def attach(port, host, client, log_dir):
    try:
        import sys
        if 'threading' not in sys.modules:
            try:

                def on_warn(msg):
                    from ptvsd.commom import log
                    log.warn(msg)

                def on_exception(msg):
                    from ptvsd.common import log
                    log.exception(msg)

                def on_critical(msg):
                    from ptvsd.common import log
                    log.error(msg)

                pydevd_attach_to_process_path = os.path.join(
                    _ptvsd_dir,
                    'ptvsd',
                    '_vendored',
                    'pydevd',
                    'pydevd_attach_to_process')
                assert os.path.exists(pydevd_attach_to_process_path)
                sys.path.append(pydevd_attach_to_process_path)

                # Note that it's not a part of the pydevd PYTHONPATH
                import attach_script
                attach_script.fix_main_thread_id(
                    on_warn=on_warn, on_exception=on_exception, on_critical=on_critical)
            except:
                from ptvsd.common import log
                log.exception()

        if not log_dir:
            log_dir = None


        
        sys.path.insert(0, _ptvsd_dir)
        import ptvsd
        assert sys.path[0] == _ptvsd_dir
        del sys.path[0]

        from ptvsd.common import options as common_opts
        from ptvsd.server import options
        common_opts.log_dir = log_dir
        options.client = client
        options.host = host
        options.port = port

        from ptvsd.common import log
        log.to_file()
        log.info("Debugger injection begin")

        if client:
            ptvsd.attach((host, port))
        else:
            ptvsd.enable_attach((host, port))

        log.info("Debugger successfully injected")
    except:
        import traceback
        traceback.print_exc()