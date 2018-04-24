import contextlib
import threading


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
        self._resources = []
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
