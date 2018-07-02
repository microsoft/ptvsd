import os
import ptvsd
import unittest

from tests.helpers.threading import get_locked_and_waiter
from tests.helpers.workspace import Workspace, PathEntry
from tests.helpers.vsc import parse_message, VSCMessages


class ANYType(object):
    def __repr__(self):
        return 'ANY'
ANY = ANYType()  # noqa


def _match_value(value, expected, allowextra=True):
    if expected is ANY:
        return True

    if isinstance(expected, dict):  # TODO: Support any mapping?
        if not isinstance(value, dict):
            return False
        if not allowextra and sorted(value) != sorted(expected):
            return False
        for key, val in expected.items():
            if key not in value:
                return False
            if not _match_value(value[key], val):
                return False
        return True
    elif isinstance(expected, str):  # str is a special case of sequence.
        if not isinstance(value, str):
            return False
        return value == expected
    elif isinstance(expected, (list, tuple)):  # TODO: Support any sequence?
        if not isinstance(value, (list, tuple)):
            return False
        if not allowextra and len(value) < len(expected):
            return False
        for val, exp in zip(value, expected):
            if not _match_value(val, exp):
                return False
        return True
    else:
        return value == expected


def _match_event(msg, event, **body):
    if msg.type != 'event':
        return False
    if msg.event != event:
        return False
    return _match_value(msg.body, body)


def _get_version(received, actual=ptvsd.__version__):
    version = actual
    for msg in received:
        if _match_event(msg, 'output', data={'version': ANY}):
            if msg.body['data']['version'] != actual:
                version = '0+unknown'
            break
    return version


def _find_events(received, event, **body):
    for i, msg in enumerate(received):
        if _match_event(msg, event, **body):
            yield i, msg


def _strip_messages(received, match_msg):
    msgs = iter(received)
    for msg in msgs:
        if match_msg(msg):
            break
        yield msg
    stripped = 1
    for msg in msgs:
        if match_msg(msg):
            stripped += 1
        else:
            yield msg._replace(seq=msg.seq - stripped)


def _strip_exit(received):
    def match(msg):
        if _match_event(msg, 'exited'):
            return True
        if _match_event(msg, 'terminated'):
            return True
        if _match_event(msg, 'thread', reason=u'exited'):
            return True
        return False
    return _strip_messages(received, match)


def _strip_output_event(received, output):
    matched = False

    def match(msg):
        if matched:
            return False
        else:
            return _match_event(msg, 'output', output=output)
    return _strip_messages(received, match)


def _strip_newline_output_events(received):
    def match(msg):
        return _match_event(msg, 'output', output=u'\n')
    return _strip_messages(received, match)


def _strip_pydevd_output(out):
    # TODO: Leave relevant lines from before the marker?
    pre, sep, out = out.partition(
        'pydev debugger: starting' + os.linesep + os.linesep)
    return out if sep else pre


def lifecycle_handshake(session, command='launch', options=None,
                        breakpoints=None, excbreakpoints=None,
                        threads=False):
    with session.wait_for_event('initialized'):
        req_initialize = session.send_request(
            'initialize',
            adapterID='spam',
        )
    req_command = session.send_request(command, **options or {})
    req_threads = session.send_request('threads') if threads else None

    reqs_bps = []
    reqs_exc = []
    for req in breakpoints or ():
        reqs_bps.append(
            session.send_request('setBreakpoints', **req))
    for req in excbreakpoints or ():
        reqs_bps.append(
            session.send_request('setExceptionBreakpoints', **req))

    req_done = session.send_request('configurationDone')
    return (req_initialize, req_command, req_done,
            reqs_bps, reqs_exc, req_threads)


class TestsBase(object):

    @property
    def workspace(self):
        try:
            return self._workspace
        except AttributeError:
            self._workspace = Workspace()
            self.addCleanup(self._workspace.cleanup)
            return self._workspace

    @property
    def pathentry(self):
        try:
            return self._pathentry
        except AttributeError:
            self._pathentry = PathEntry()
            self.addCleanup(self._pathentry.cleanup)
            self._pathentry.install()
            return self._pathentry

    def write_script(self, name, content):
        return self.workspace.write_python_script(name, content=content)

    def write_debugger_script(self, filename, port, run_as):
        cwd = os.getcwd()
        kwargs = {
            'filename': filename,
            'port_num': port,
            'debug_id': None,
            'debug_options': None,
            'run_as': run_as,
        }
        return self.write_script('debugger.py', """
            import sys
            sys.path.insert(0, {!r})
            from ptvsd.debugger import debug
            debug(
                {filename!r},
                {port_num!r},
                {debug_id!r},
                {debug_options!r},
                {run_as!r},
            )
            """.format(cwd, **kwargs))


class LifecycleTestsBase(TestsBase, unittest.TestCase):

    @property
    def messages(self):
        try:
            return self._messages
        except AttributeError:
            self._messages = VSCMessages()
            return self._messages

    def new_response(self, *args, **kwargs):
        return self.messages.new_response(*args, **kwargs)

    def new_event(self, *args, **kwargs):
        return self.messages.new_event(*args, **kwargs)

    def _wait_for_started(self):
        lock, wait = get_locked_and_waiter()

        # TODO: There's a race with the initial "output" event.
        def handle_msg(msg):
            if msg.type != 'event':
                return False
            if msg.event != 'output':
                return False
            lock.release()
            return True

        handlers = [
            (handle_msg, "event 'output'"),
        ]
        return handlers, (lambda: wait(reason="event 'output'"))

    def assert_received(self, received, expected):
        from tests.helpers.message import assert_messages_equal
        received = [parse_message(msg) for msg in received]
        expected = [parse_message(msg) for msg in expected]
        assert_messages_equal(received, expected)

    def assert_contains(self, received, expected):
        from tests.helpers.message import assert_contains_messages
        received = [parse_message(msg) for msg in received]
        expected = [parse_message(msg) for msg in expected]
        assert_contains_messages(received, expected)

    def new_version_event(self, received):
        version = _get_version(received)
        return self.new_event(
            'output',
            category='telemetry',
            output='ptvsd',
            data={'version': version},
        )
