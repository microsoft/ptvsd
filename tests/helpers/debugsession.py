from __future__ import absolute_import, print_function, division

import contextlib
import json
import socket
import sys
import time
import threading
import warnings

from ptvsd._util import new_hidden_thread, Closeable, ClosedError
from .message import (
    raw_read_all as read_messages,
    raw_write_one as write_message
)
from .socket import (
    Connection, create_server, create_client, close,
    recv_as_read, send_as_write,
    timeout as socket_timeout)
from .threading import get_locked_and_waiter
from .vsc import parse_message


class DebugSessionConnection(Closeable):

    VERBOSE = False
    #VERBOSE = True

    TIMEOUT = 1.0

    @classmethod
    def create_client(cls, addr, **kwargs):
        def connect(addr, timeout):
            sock = create_client()
            for _ in range(int(timeout * 10)):
                try:
                    sock.connect(addr)
                except (OSError, socket.error):
                    if cls.VERBOSE:
                        print('+', end='')
                        sys.stdout.flush()
                    time.sleep(0.1)
                else:
                    break
            else:
                raise RuntimeError('could not connect')
            return sock
        return cls._create(connect, addr, **kwargs)

    @classmethod
    def create_server(cls, addr, **kwargs):
        def connect(addr, timeout):
            server = create_server(addr)
            with socket_timeout(server, timeout):
                client, _ = server.accept()
            return Connection(client, server)
        return cls._create(connect, addr, **kwargs)

    @classmethod
    def _create(cls, connect, addr, timeout=None):
        if timeout is None:
            timeout = cls.TIMEOUT
        sock = connect(addr, timeout)
        if cls.VERBOSE:
            print('connected')
        self = cls(sock, ownsock=True)
        self._addr = addr
        return self

    def __init__(self, sock, ownsock=False):
        super(DebugSessionConnection, self).__init__()
        self._sock = sock
        self._ownsock = ownsock

    @property
    def is_client(self):
        try:
            return self._sock.server is None
        except AttributeError:
            return True

    def iter_messages(self):
        if self.closed:
            raise RuntimeError('connection closed')

        def stop():
            return self.closed
        read = recv_as_read(self._sock)
        for msg, _, _ in read_messages(read, stop=stop):
            if self.VERBOSE:
                print(repr(msg))
            yield parse_message(msg)

    def send(self, req):
        if self.closed:
            raise RuntimeError('connection closed')

        def stop():
            return self.closed
        write = send_as_write(self._sock)
        body = json.dumps(req)
        write_message(write, body, stop=stop)

    # internal methods

    def _close(self):
        if self._ownsock:
            close(self._sock)


class DebugSession(Closeable):

    VERBOSE = False
    #VERBOSE = True

    HOST = 'localhost'
    PORT = 8888

    TIMEOUT = None

    @classmethod
    def create_client(cls, addr=None, **kwargs):
        if addr is None:
            addr = (cls.HOST, cls.PORT)
        conn = DebugSessionConnection.create_client(
            addr,
            timeout=kwargs.get('timeout'),
        )
        return cls(conn, owned=True, **kwargs)

    @classmethod
    def create_server(cls, addr=None, **kwargs):
        if addr is None:
            addr = (cls.HOST, cls.PORT)
        conn = DebugSessionConnection.create_server(addr, **kwargs)
        return cls(conn, owned=True, **kwargs)

    def __init__(self, conn, seq=1000, handlers=(), timeout=None, owned=False):
        super(DebugSession, self).__init__()
        self._conn = conn
        self._seq = seq
        self._timeout = timeout if timeout is not None else self.TIMEOUT
        self._owned = owned

        self._handlers = []
        for handler in handlers:
            if callable(handler):
                self._add_handler(handler)
            else:
                self._add_handler(*handler)
        self._received = []
        self._listenerthread = new_hidden_thread(
            target=self._listen,
            name='test.session',
        )
        self._listenerthread.start()

    @property
    def is_client(self):
        return self._conn.is_client

    @property
    def received(self):
        return list(self._received)

    def new_request(self, command, **args):
        seq = self._seq
        self._seq += 1
        return self._new_request(seq, command, args)

    def add_handler(self, handle_msg, **kwargs):
        if self.closed:
            raise RuntimeError('session closed')
        self._add_handler(handle_msg, **kwargs)

    def send_raw_message(self, raw):
        raw = dict(raw)
        self._conn.send(raw)

    # pending messages

    def send_request(self, command, **args):
        req = self.new_request(command, **args)
        pending = self.add_pending_response(req)
        self.send_raw_message(req)
        return SentRequest.from_pending(pending)

    def send_request_and_wait(self, command, **args):
        timeout = args.pop('timeout', None)
        sent = self.send_request(command, **args)
        sent.wait(timeout)
        return sent

    def wait_for_response(self, req, match_body=None, timeout=None):
        pending = self.add_pending_response(req, match_body)
        return self._wait_for_message(pending, timeout)

    def wait_for_event(self, event, match_body=None, timeout=None):
        pending = self.add_pending_event(event, match_body)
        return self._wait_for_message(pending, timeout)

    def add_pending_response(self, req, match_body=None):
        if isinstance(req, str):
            cmd, reqseq = req, None
            req = self.new_request(reqseq, cmd)
        else:
            cmd, reqseq = req['command'], req['seq']
            if reqseq is not None and match_body is not None:
                raise ValueError("got both req['seq'] and match_body")
        match = self._get_response_matcher(cmd, reqseq, match_body)
        pending = PendingResponse(req)
        handlername = 'response (cmd:{} reqseq:{})'.format(cmd, reqseq)
        self._add_pending_handler(match, pending, handlername)
        return pending

    def add_pending_event(self, event, match_body=None):
        match = self._get_event_matcher(event, match_body)
        pending = PendingEvent(event)
        handlername = 'event {!r}'.format(event)
        self._add_pending_handler(match, pending, handlername)
        return pending

    # internal methods

    def _close(self):
        if self._owned:
            try:
                self._conn.close()
            except ClosedError:
                pass
        if self._listenerthread != threading.current_thread():
            self._listenerthread.join(timeout=1.0)
            if self._listenerthread.is_alive():
                warnings.warn('session listener still running')
        self._check_handlers()

    def _listen(self):
        try:
            for msg in self._conn.iter_messages():
                if self.VERBOSE:
                    print(' ->', msg)
                self._receive_message(msg)
        except EOFError:
            try:
                self.close()
            except ClosedError:
                pass

    def _receive_message(self, msg):
        for i, handler in enumerate(list(self._handlers)):
            handle_message, _, _ = handler
            handled = handle_message(msg)
            try:
                msg, handled = handled
            except TypeError:
                pass
            if handled:
                self._handlers.remove(handler)
                break
        self._received.append(msg)

    def _add_handler(self, handle_msg, handlername=None, required=True):
        self._handlers.append(
            (handle_msg, handlername, required))

    def _check_handlers(self):
        unhandled = []
        for handle_msg, name, required in self._handlers:
            if not required:
                continue
            unhandled.append(name or repr(handle_msg))
        if unhandled:
            raise RuntimeError('unhandled: {}'.format(unhandled))

    def _new_request(self, seq, command, args=None):
        return {
            'type': 'request',
            'seq': seq,
            'command': command,
            'arguments': args,
        }

    def _get_response_matcher(self, cmd, reqseq, match_body=None):
        def match(msg):
            if msg.type != 'response':
                return False
            if reqseq is None:
                if msg.command != cmd:
                    return False
                if match_body is not None and not match_body(msg.body):
                    return False
            else:
                if msg.request_seq != reqseq:
                    return False
            return True
        return match

    def _get_event_matcher(self, event, match_body=None):
        def match(msg):
            if msg.type != 'event':
                return False
            if msg.event != event:
                return False
            if match_body is not None and not match_body(msg.body):
                return False
            return True
        return match

    def _add_pending_handler(self, match, pending, handlername):
        if self.closed:
            raise RuntimeError('session closed')
        lock, wait = get_locked_and_waiter()

        def handle_msg(msg):
            if not match(msg):
                return msg, False
            pending.notify(msg)
            lock.release()
            return msg, True
        self._add_handler(handle_msg, handlername)

        def _wait(timeout=self._timeout):
            wait(timeout, handlername, fail=True)
        pending.set_waiting(_wait)

    @contextlib.contextmanager
    def _wait_for_message(self, pending, timeout=None):
        wait = pending.wait
        try:
            yield pending
        except Exception:
            # At least give it a moment to finish.
            time.sleep(0.1)
            raise
        else:
            wait(timeout)


class PendingMessage(object):

    def __init__(self, type, name):
        self.type = type
        self.name = name

        self._wait = None
        self._msg = None

    def __str__(self):
        return '{} {!r}'.format(self.type.upper(), self.name)

    def __getattr__(self, name):
        if self._msg is None or name.startswith('_'):
            raise AttributeError(name)
        return getattr(self._msg, name)

    @property
    def waiting(self):
        return self._wait is not None and self._msg is None

    @property
    def message(self):
        return self._msg
    msg = message

    def notify(self, msg):
        if self._msg is not None:
            raise TypeError('already notified')
        self._msg = msg

    def set_waiting(self, wait):
        if self._wait is not None:
            raise TypeError('already waiting')
        self._wait = wait

    def wait(self, timeout=None):
        if self._msg is not None:
            return
        if self._wait is None:
            raise TimeoutError
        self._wait(timeout)


class PendingResponse(PendingMessage):

    def __init__(self, req):
        cmd = req['command']
        super(PendingResponse, self).__init__('response', cmd)
        self._req = req

    response = PendingMessage.message
    resp = PendingMessage.msg

    @property
    def request(self):
        return self._req
    req = request


class PendingEvent(PendingMessage):

    def __init__(self, event):
        super(PendingEvent, self).__init__('event', event)


def wait_all(*pending, **kwargs):
    timeout = kwargs.pop('timeout', 3.0)
    end = time.time() + timeout

    # Do at least one iteration.
    pending = _wait_each(pending, 0.1, **kwargs)
    while pending and time.time() <= end:
        pending = _wait_each(pending, 0.1, **kwargs)
    pending = [p for p in pending if p.waiting]

    if pending:
        messages = (str(p) for p in pending)
        raise TimeoutError(
            'timed out waiting for {}'.format(','.join(messages)))


def _wait_each(pendings, delay):
    if not pendings:
        return pendings
    remainder = []
    timeout = delay / len(pendings)
    for pending in pendings:
        try:
            pending.wait(timeout)
        except TimeoutError:
            remainder.append(pending)
    return remainder


class SentRequest(dict):

    _pending = None

    @classmethod
    def from_pending(cls, pending):
        req = pending.req
        self = cls(req)
        self._pending = pending
        return self

    @property
    def pending(self):
        return self._pending

    @property
    def resp(self):
        if self._pending is None:
            return None
        return self._pending.resp

    def wait(self, timeout=None):
        if self._pending is None:
            return False
        return self._pending.wait(timeout)
