import os
import os.path
import unittest
import sys

from . import TEST_ROOT, PROJECT_ROOT
from .__main__ import convert_argv


class ConvertArgsTests(unittest.TestCase):

    def test_no_args(self):
        runtests, lint, runtest_args = convert_argv([])

        self.assertEqual(runtest_args.argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', PROJECT_ROOT,
            ])
        self.assertEqual(runtest_args.env, {
            'HAS_NETWORK': '1',
        })
        self.assertTrue(runtests)
        self.assertFalse(lint)
        self.assertIsNone(runtest_args.junit_xml_file)

    def test_discovery_full(self):
        runtests, lint, runtest_args = convert_argv([
            '-v', '--failfast', '--full',
        ])

        self.assertEqual(runtest_args.argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', PROJECT_ROOT,
            '-v', '--failfast',
            ])
        self.assertEqual(runtest_args.env, {
            'HAS_NETWORK': '1',
        })
        self.assertTrue(runtests)
        self.assertFalse(lint)
        self.assertIsNone(runtest_args.junit_xml_file)

    def test_discovery_quick(self):
        runtests, lint, runtest_args = convert_argv([
            '-v', '--failfast', '--quick',
        ])

        self.assertEqual(runtest_args.argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', os.path.join(TEST_ROOT, 'ptvsd'),
            '-v', '--failfast',
            ])
        self.assertEqual(runtest_args.env, {
            'HAS_NETWORK': '1',
        })
        self.assertTrue(runtests)
        self.assertFalse(lint)
        self.assertIsNone(runtest_args.junit_xml_file)

    def test_modules(self):
        runtests, lint, runtest_args = convert_argv([
            '-v', '--failfast',
            'w',
            'x/y.py:Spam.test_spam'.replace('/', os.sep),
            'z:Eggs',
        ])

        self.assertEqual(runtest_args.argv, [
            sys.executable + ' -m unittest',
            '-v', '--failfast',
            'w',
            'x.y.Spam.test_spam',
            'z.Eggs',
            ])
        self.assertEqual(runtest_args.env, {
            'HAS_NETWORK': '1',
        })
        self.assertTrue(runtests)
        self.assertFalse(lint)
        self.assertIsNone(runtest_args.junit_xml_file)

    def test_no_network(self):
        runtests, lint, runtest_args = convert_argv([
            '--no-network'
            ])

        self.assertEqual(runtest_args.argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', PROJECT_ROOT,
            ])
        self.assertEqual(runtest_args.env, {})
        self.assertTrue(runtests)
        self.assertFalse(lint)
        self.assertIsNone(runtest_args.junit_xml_file)

    def test_lint(self):
        runtests, lint, runtest_args = convert_argv([
            '-v',
            '--quick',
            '--lint'
            ])

        self.assertEqual(runtest_args.argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', os.path.join(TEST_ROOT, 'ptvsd'),
            '-v',
            ])
        self.assertEqual(runtest_args.env, {
            'HAS_NETWORK': '1',
        })
        self.assertTrue(runtests)
        self.assertTrue(lint)
        self.assertIsNone(runtest_args.junit_xml_file)

    def test_lint_only(self):
        runtests, lint, runtest_args = convert_argv([
            '--quick', '--lint-only', '-v',
        ])

        self.assertIsNone(runtest_args.argv)
        self.assertIsNone(runtest_args.env)
        self.assertFalse(runtests)
        self.assertTrue(lint)
        self.assertIsNone(runtest_args.junit_xml_file)

    def test_coverage(self):
        runtests, lint, runtest_args = convert_argv([
            '--coverage'
            ])

        self.assertEqual(runtest_args.argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', PROJECT_ROOT,
            ])
        self.assertEqual(runtest_args.env, {
            'HAS_NETWORK': '1',
        })
        self.assertEqual(runtests, 'coverage')
        self.assertFalse(lint)
        self.assertIsNone(runtest_args.junit_xml_file, None)        

    def test_specify_junit_file(self):
        runtests, lint, runtest_args = convert_argv([
            '--junit-xml=./my-test-file'
        ])

        self.assertEqual(runtest_args.argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', PROJECT_ROOT,
        ])
        self.assertEqual(runtest_args.env, {
            'HAS_NETWORK': '1',
        })
        self.assertTrue(runtests)
        self.assertFalse(lint)
        self.assertEqual(runtest_args.junit_xml_file, './my-test-file')
