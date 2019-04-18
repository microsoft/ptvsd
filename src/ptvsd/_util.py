# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function

import contextlib
import threading
import time
import sys

import ptvsd.log


@contextlib.contextmanager
def ignore_errors(log=None):
    """A context manager that masks any raised exceptions."""
    try:
        yield
    except Exception:
        if log is not None:
            ptvsd.log.exception('Ignoring error', category='I')


def call_all(callables, *args, **kwargs):
    """Return the result of calling every given object."""
    results = []
    for call in callables:
        try:
            call(*args, **kwargs)
        except Exception as exc:
            results.append((call, exc))
        else:
            results.append((call, None))
    return results


########################
# threading stuff

try:
    ThreadError = threading.ThreadError
except AttributeError:
    ThreadError = RuntimeError


try:
    base = __builtins__.TimeoutError
except AttributeError:
    base = OSError
class TimeoutError(base):  # noqa
    """Timeout expired."""
    timeout = None
    reason = None

    @classmethod
    def from_timeout(cls, timeout, reason=None):
        """Return a TimeoutError with the given timeout."""
        msg = 'timed out (after {} seconds)'.format(timeout)
        if reason is not None:
            msg += ' ' + reason
        self = cls(msg)
        self.timeout = timeout
        self.reason = reason
        return self
del base  # noqa


def wait(check, timeout=None, reason=None):
    """Wait for the given func to return True.

    If a timeout is given and reached then raise TimeoutError.
    """
    if timeout is None or timeout <= 0:
        while not check():
            time.sleep(0.01)
    else:
        if not _wait(check, timeout):
            raise TimeoutError.from_timeout(timeout, reason)


def is_locked(lock):
    """Return True if the lock is locked."""
    if lock is None:
        return False
    if not lock.acquire(False):
        return True
    lock_release(lock)
    return False


def lock_release(lock):
    """Ensure that the lock is released."""
    if lock is None:
        return
    try:
        lock.release()
    except ThreadError:  # already unlocked
        pass


def lock_wait(lock, timeout=None, reason='waiting for lock'):
    """Wait until the lock is not locked."""
    if not _lock_acquire(lock, timeout):
        raise TimeoutError.from_timeout(timeout, reason)
    lock_release(lock)


if sys.version_info >= (3,):
    def _lock_acquire(lock, timeout):
        if timeout is None:
            timeout = -1
        return lock.acquire(timeout=timeout)
else:
    def _lock_acquire(lock, timeout):
        if timeout is None or timeout <= 0:
            return lock.acquire()

        def check():
            return lock.acquire(False)
        return _wait(check, timeout)


def _wait(check, timeout):
    if check():
        return True
    for _ in range(int(timeout * 100)):
        time.sleep(0.01)
        if check():
            return True
    else:
        return False


def new_hidden_thread(name, target, prefix='ptvsd.', daemon=True, **kwargs):
    """Return a thread that will be ignored by pydevd."""
    if prefix is not None and not name.startswith(prefix):
        name = prefix + name
    t = threading.Thread(
        name=name,
        target=target,
        **kwargs
    )
    t.pydev_do_not_trace = True
    t.is_pydev_daemon_thread = True
    if daemon:
        t.daemon = True
    return t


########################
# closing stuff

class ClosedError(RuntimeError):
    """Indicates that the object is closed."""


def close_all(closeables):
    """Return the result of closing every given object."""
    results = []
    for obj in closeables:
        try:
            obj.close()
        except Exception as exc:
            results.append((obj, exc))
        else:
            results.append((obj, None))
    return results


class Closeable(object):
    """A base class for types that may be closed."""

    NAME = None
    FAIL_ON_ALREADY_CLOSED = True

    def __init__(self):
        super(Closeable, self).__init__()
        self._closed = False
        self._closedlock = threading.Lock()
        self._handlers = []

    def __del__(self):
        try:
            self.close()
        except ClosedError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @property
    def closed(self):
        return self._closed

    def add_resource_to_close(self, resource, before=False):
        """Add a resource to be closed when closing."""
        close = resource.close
        if before:
            def handle_closing(before):
                if not before:
                    return
                close()
        else:
            def handle_closing(before):
                if before:
                    return
                close()
        self.add_close_handler(handle_closing)

    def add_close_handler(self, handle_closing, nodupe=True):
        """Add a func to be called when closing.

        The func takes one arg: True if it was called before the main
        close func and False if after.
        """
        with self._closedlock:
            if self._closed:
                if self.FAIL_ON_ALREADY_CLOSED:
                    raise ClosedError('already closed')
                return
            if nodupe and handle_closing in self._handlers:
                raise ValueError('close func already added')

            self._handlers.append(handle_closing)

    def check_closed(self):
        """Raise ClosedError if closed."""
        if self._closed:
            if self.NAME:
                raise ClosedError('{} closed'.format(self.NAME))
            else:
                raise ClosedError('closed')

    @contextlib.contextmanager
    def while_not_closed(self):
        """A context manager under which the object will not be closed."""
        with self._closedlock:
            self.check_closed()
            yield

    def close(self):
        """Release any owned resources and clean up."""
        with self._closedlock:
            if self._closed:
                if self.FAIL_ON_ALREADY_CLOSED:
                    raise ClosedError('already closed')
                return
            self._closed = True
            handlers = list(self._handlers)

        results = call_all(handlers, True)
        self._log_results(results)
        self._close()
        results = call_all(handlers, False)
        self._log_results(results)

    # implemented by subclasses

    def _close(self):
        pass

    # internal methods

    def _log_results(self, results, log=None):
        if log is None:
            return
        for obj, exc in results:
            if exc is None:
                continue
            log('failed to close {!r} ({!r})'.format(obj, exc))


########################
# running stuff

class NotRunningError(RuntimeError):
    """Something isn't currently running."""


class AlreadyStartedError(RuntimeError):
    """Something was already started."""


class AlreadyRunningError(AlreadyStartedError):
    """Something is already running."""


class Startable(object):
    """A base class for types that may be started."""

    RESTARTABLE = False
    FAIL_ON_ALREADY_STOPPED = True

    def __init__(self):
        super(Startable, self).__init__()
        self._is_running = None
        self._startlock = threading.Lock()
        self._numstarts = 0

    def is_running(self, checkclosed=True):
        """Return True if currently running."""
        if checkclosed and hasattr(self, 'check_closed'):
            self.check_closed()
        is_running = self._is_running
        if is_running is None:
            return False
        return is_running()

    def start(self, *args, **kwargs):
        """Begin internal execution."""
        with self._startlock:
            if self.is_running():
                raise AlreadyRunningError()
            if not self.RESTARTABLE and self._numstarts > 0:
                raise AlreadyStartedError()

            self._is_running = self._start(*args, **kwargs)
            self._numstarts += 1

    def stop(self, *args, **kwargs):
        """Stop execution and wait until done."""
        with self._startlock:
            # TODO: Call self.check_closed() here?
            if not self.is_running(checkclosed=False):
                if not self.FAIL_ON_ALREADY_STOPPED:
                    return
                raise NotRunningError()
            self._is_running = None

        self._stop(*args, **kwargs)

    # implemented by subclasses

    def _start(self, *args, **kwargs):
        """Return an "is_running()" func after starting."""
        raise NotImplementedError

    def _stop(self):
        raise NotImplementedError
