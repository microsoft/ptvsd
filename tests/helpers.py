# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import threading
from ptvsd.common import fmt, log

class CapturedOutput(object):
    """Captured stdout and stderr of the debugged process.
    """

    def __init__(self, session):
        self.session = session
        self._lock = threading.Lock()
        self._lines = {}
        self._worker_threads = []

    def __str__(self):
        return fmt("CapturedOutput({0!r})", self.session)

    def _worker(self, pipe, name):
        lines = self._lines[name]
        while True:
            try:
                line = pipe.readline()
            except Exception:
                line = None

            if line:
                log.info("{0} {1}> {2!r}", self.session, name, line)
                with self._lock:
                    lines.append(line)
            else:
                break

    def _capture(self, pipe, name):
        assert name not in self._lines
        self._lines[name] = []

        thread = threading.Thread(
            target=lambda: self._worker(pipe, name),
            name=fmt("{0} {1}", self, name)
        )
        thread.daemon = True
        thread.start()
        self._worker_threads.append(thread)

    def capture(self, process):
        """Start capturing stdout and stderr of the process.
        """
        assert not self._worker_threads
        log.info('Capturing {0} stdout and stderr', self.session)
        self._capture(process.stdout, "stdout")
        self._capture(process.stderr, "stderr")

    def wait(self, timeout=None):
        """Wait for all remaining output to be captured.
        """
        if not self._worker_threads:
            return
        log.debug('Waiting for remaining {0} stdout and stderr...', self.session)
        for t in self._worker_threads:
            t.join(timeout)
        self._worker_threads[:] = []

    def _output(self, which, encoding, lines):
        assert self.session.timeline.is_frozen

        try:
            result = self._lines[which]
        except KeyError:
            raise AssertionError(fmt("{0} was not captured for {1}", which, self.session))

        # The list might still be appended to concurrently, so take a snapshot of it.
        with self._lock:
            result = list(result)

        if encoding is not None:
            result = [s.decode(encoding) for s in result]

        if not lines:
            sep = b'' if encoding is None else u''
            result = sep.join(result)

        return result

    def stdout(self, encoding=None):
        """Returns stdout captured from the debugged process, as a single string.

        If encoding is None, returns bytes. Otherwise, returns unicode.
        """
        return self._output("stdout", encoding, lines=False)

    def stderr(self, encoding=None):
        """Returns stderr captured from the debugged process, as a single string.

        If encoding is None, returns bytes. Otherwise, returns unicode.
        """
        return self._output("stderr", encoding, lines=False)

    def stdout_lines(self, encoding=None):
        """Returns stdout captured from the debugged process, as a list of lines.

        If encoding is None, each line is bytes. Otherwise, each line is unicode.
        """
        return self._output("stdout", encoding, lines=True)

    def stderr_lines(self, encoding=None):
        """Returns stderr captured from the debugged process, as a list of lines.

        If encoding is None, each line is bytes. Otherwise, each line is unicode.
        """
        return self._output("stderr", encoding, lines=True)
