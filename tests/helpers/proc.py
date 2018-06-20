import subprocess
import sys

from . import Closeable


_NOT_SET = object()


class Proc(Closeable):
    """A wrapper around a subprocess.Popen object."""

    VERBOSE = False
    #VERBOSE = True

    ARGV = [
        sys.executable,
        '-u',  # stdout/stderr unbuffered
        ]

    @classmethod
    def start_python_script(cls, filename, argv, **kwargs):
        argv = list(cls.ARGV) + [
            filename,
        ] + argv
        return cls.start(argv, **kwargs)

    @classmethod
    def start_python_module(cls, module, argv, **kwargs):
        argv = list(cls.ARGV) + [
            '-m', module,
        ] + argv
        return cls.start(argv, **kwargs)

    @classmethod
    def start(cls, argv, env=None, stdout=_NOT_SET, stderr=_NOT_SET):
        if env is None:
            env = {}
        if cls.VERBOSE:
            env.setdefault('PTVSD_DEBUG', '1')
        proc = cls._start(argv, env, stdout, stderr)
        return cls(proc, owned=True)

    @classmethod
    def _start(cls, argv, env, stdout, stderr):
        if stdout is _NOT_SET:
            stdout = subprocess.PIPE
        if stderr is _NOT_SET:
            stderr = subprocess.STDOUT
        proc = subprocess.Popen(
            argv,
            stdout=stdout,
            stderr=stderr,
            env=env,
        )
        return proc

    def __init__(self, proc, owned=False):
        super(Proc, self).__init__()
        assert isinstance(proc, subprocess.Popen)
        self._proc = proc
        if proc.stdout is sys.stdout or proc.stdout is None:
            self._output = None

    # TODO: Emulate class-only methods?
    #def __getattribute__(self, name):
    #    val = super(Proc, self).__getattribute__(name)
    #    if isinstance(type(self).__dict__.get(name), classmethod):
    #        raise AttributeError(name)
    #    return val

    def __iter__(self):
        return self

    def __next__(self):
        line = self._proc.stdout.readline()
        if not line and self._proc.poll() is not None:
            raise StopIteration
        return line

    next = __next__  # for Python 2.7

    @property
    def pid(self):
        return self._proc.pid

    @property
    def output(self):
        try:
            # TODO: Could there be more?
            return self._output
        except AttributeError:
            # TODO: Wait until proc done?  (piped output blocks)
            try:
                self._output = self._proc.stdout.read()
            except AttributeError:
                if self._proc.stdout is None:
                    return ''
                raise

            return self._output

    @property
    def exitcode(self):
        # TODO: Use proc.poll()?
        return self._proc.returncode

    def readline(self, stdout=True):
        if stdout or self._proc.stderr is None:
            try:
                return self._proc.stdout.readline()
            except AttributeError:
                if self._proc.stdout is None:
                    return ''
                raise
        else:
            return self._proc.stderr.readline()

    def wait(self):
        # TODO: Use proc.communicate()?
        self._proc.wait()

    # internal methods

    def _close(self):
        if self._proc is not None:
            try:
                self._proc.kill()
            except OSError:
                # Already killed.
                pass
            else:
                if self.VERBOSE:
                    print('proc killed')
        if self.VERBOSE:
            out = self.output
            if out is not None:
                lines = out.decode('utf-8').splitlines()
                print(' + ' + '\n + '.join(lines))
