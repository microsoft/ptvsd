from __future__ import absolute_import

import argparse
import os
import os.path
import subprocess
import sys
import unittest

from xmlrunner import XMLTestRunner

from . import TEST_ROOT, PROJECT_ROOT, VENDORED_ROOTS


def parse_cmdline(argv):
    """Obtain command line arguments and setup the test run accordingly."""

    parser = argparse.ArgumentParser(
        description="Run tests associated to the PTVSD project."
    )
    parser.add_argument(
        "-c",
        "--coverage",
        help="Generate code coverage report.",
        action="store_true"
    )
    parser.add_argument(
        "--full",
        help="Do full suite of tests (disables prior --quick options).",
        action="store_false",
        target="quick"
    )
    parser.add_argument(
        "-j",
        "--junit-xml",
        help="Output report is generated to JUnit-style XML file specified.",
        type=str
    )
    parser.add_argument(
        "-l",
        "--lint",
        help="Run and report on Linter compliance.",
        action="store_true"
    )
    parser.add_argument(
        "-L",
        "--lint-only",
        help="Run and report on Linter compliance only, do not perform tests.",
        action="store_true"
    )
    parser.add_argument(
        '-n',
        '--network',
        help="Perform tests taht require network connectivity.",
        action='store_true',
        dest='network'
    )
    parser.add_argument(
        "--no-network",
        help="Do not perform tests that require network connectivity.",
        action="store_false",
        dest='network'
    )
    parser.set_defaults(network=True)
    parser.add_argument(
        "-q",
        "--quick",
        help="Only do the tests under test/ptvsd.",
        action="store_true"
    )
    parser.add_argument(
        "--quick-py2",
        help=("Only do the tests under test/ptvsd, that are compatible "
              "with Python 2.x."),
        action="store_true"
    )
    parser.add_argument(
        "-s",
        "--start-directory",
        help="Run tests from the directory specified, not from the repo root.",
        type=str
    )
    parser.allow_abbrev = False
    parser.prog = "tests"
    parser.usage = "python -m %(prog)s OPTS"

    config, passthrough_args = parser.parse_known_args(argv)

    return config, passthrough_args


def convert_argv(argv):
    """Convert commandling args into unittest/linter/coverage input."""

    config, passthru = parse_cmdline(argv)

    modules = set()

    for arg in passthru:
        # Unittest's main has only flags and positional args.
        # So we don't worry about options with values.
        if not arg.startswith('-'):
            # It must be the name of a test, case, module, or file.
            # We convert filenames to module names.  For filenames
            # we support specifying a test name by appending it to
            # the filename with a ":" in between.
            mod, _, test = arg.partition(':')
            if mod.endswith(os.sep):
                mod = mod.rsplit(os.sep, 1)[0]
            mod = mod.rsplit('.py', 1)[0]
            mod = mod.replace(os.sep, '.')
            arg = mod if not test else mod + '.' + test
            modules.add(mod)

    env = {}
    if config.network:
        env['HAS_NETWORK'] = '1'
    # We make the "executable" a single arg because unittest.main()
    # doesn't work if we split it into 3 parts.
    cmd = [sys.executable + ' -m unittest']
    if not modules:
        # Do discovery.
        quickroot = os.path.join(TEST_ROOT, 'ptvsd')
        if config.quick:
            start = quickroot
        elif config.quick_py2 and sys.version_info[0] == 2:
            start = quickroot
        else:
            start = PROJECT_ROOT

        cmd += [
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', start,
        ]
    args = cmd + passthru

    return config, args, env


def fix_sys_path():
    pos = 1 if (not sys.path[0] or sys.path[0] == '.') else 0
    for projectroot in VENDORED_ROOTS:
        sys.path.insert(pos, projectroot)


def check_lint():
    print('linting...')
    args = [
        sys.executable,
        '-m', 'flake8',
        '--ignore', 'E24,E121,E123,E125,E126,E221,E226,E266,E704,E265',
        '--exclude', ','.join(VENDORED_ROOTS),
        PROJECT_ROOT,
    ]
    rc = subprocess.call(args)
    if rc != 0:
        print('...linting failed!')
        sys.exit(rc)
    print('...done')


def run_tests(argv, env, config):
    print('running tests...')
    if config.coverage:
        omissions = [os.path.join(root, '*') for root in VENDORED_ROOTS]
        # TODO: Drop the explicit pydevd omit once we move the subtree.
        omissions.append(os.path.join('ptvsd', 'pydevd', '*'))
        ver = 3 if sys.version_info < (3,) else 2
        omissions.append(os.path.join('ptvsd', 'reraise{}.py'.format(ver)))
        args = [
            sys.executable,
            '-m', 'coverage',
            'run',
            # We use --source instead of "--include ptvsd/*".
            '--source', 'ptvsd',
            '--omit', ','.join(omissions),
            '-m', 'unittest',
        ] + argv[1:]
        assert 'PYTHONPATH' not in env
        env['PYTHONPATH'] = os.pathsep.join(VENDORED_ROOTS)
        rc = subprocess.call(args, env=env)
        if rc != 0:
            print('...coverage failed!')
            sys.exit(rc)
        print('...done')
    elif config.junit_xml:
        os.environ.update(env)
        with open(config.junit_xml, 'wb') as output:
            unittest.main(
                testRunner=XMLTestRunner(output=output),
                module=None,
                argv=argv
            )
    else:
        os.environ.update(env)
        unittest.main(module=None, argv=argv)


if __name__ == '__main__':
    config, args, env = convert_argv(sys.argv[1:])
    fix_sys_path()
    if config.lint or config.lint_only:
        check_lint()
    if not config.lint_only:
        if config.start_directory:
            print(
                '(will look for tests under {})'
                .format(config.start_directory)
            )

        run_tests(
            args,
            env,
            config
        )
