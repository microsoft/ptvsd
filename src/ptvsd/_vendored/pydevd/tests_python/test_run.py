pytest_plugins = [
    str('_pytest.pytester'),
]

def _run_and_check(testdir, path):
    result = testdir.runpython(path)
    result.stdout.fnmatch_lines([
        'Worked'
    ])

def test_run(testdir):
    from tests_python import debugger_unittest
    import sys
    import os

    if debugger_unittest.IS_PY3K:
        foo_dir = debugger_unittest._get_debugger_test_file(os.path.join('resources', 'launch', 'foo'))
        foo_module = 'tests_python.resources.launch.foo'
    else:
        foo_dir = debugger_unittest._get_debugger_test_file(os.path.join('resources', 'launch_py2', 'foo'))
        foo_module = 'tests_python.resources.launch_py2.foo'

    pydevd_dir = os.path.dirname(os.path.dirname(__file__))
    assert os.path.exists(os.path.join(pydevd_dir, 'pydevd.py'))

    _run_and_check(testdir, testdir.makepyfile('''
import sys
sys.path.append(%(pydevd_dir)r)
import pydevd
py_db = pydevd.PyDB()
py_db.ready_to_run = True
py_db.run(%(foo_dir)r)
''' % locals()))

    _run_and_check(testdir, testdir.makepyfile('''
import sys
sys.path.append(%(pydevd_dir)r)
import pydevd
py_db = pydevd.PyDB()
py_db.run(%(foo_dir)r, set_trace=False)
''' % locals()))

    if sys.version_info[0:2] == (2, 6):
        # Not valid for Python 2.6
        return

    _run_and_check(testdir, testdir.makepyfile('''
import sys
sys.path.append(%(pydevd_dir)r)
sys.argv.append('--as-module')
import pydevd
py_db = pydevd.PyDB()
py_db.ready_to_run = True
py_db.run(%(foo_module)r, is_module=True)
''' % locals()))

    _run_and_check(testdir, testdir.makepyfile('''
import sys
sys.argv.append('--as-module')
sys.path.append(%(pydevd_dir)r)
import pydevd
py_db = pydevd.PyDB()
py_db.run(%(foo_module)r, is_module=True, set_trace=False)
''' % locals()))

