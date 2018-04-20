import os
import unittest
import ptvsd.untangle

from ptvsd.wrapper import InternalsFilter


class InternalsFilterTests(unittest.TestCase):
    def test_internal_paths(self):
        internal_dir = os.path.dirname(
            os.path.abspath(ptvsd.untangle.__file__)
        )
        internal_files = [
            ptvsd.untangle.__file__,
            'somepath\\ptvsd_launcher.py',  # File used by VS Only
            os.path.join(internal_dir, 'somefile.py'),  # Any file under ptvsd
        ]
        for fp in internal_files:
            self.assertTrue(InternalsFilter.is_internal_path(fp))

    def test_user_file_paths(self):
        files = [
            __file__,
            'somepath\\somefile.py',
        ]
        for fp in files:
            self.assertFalse(InternalsFilter.is_internal_path(fp))