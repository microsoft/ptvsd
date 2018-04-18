import warnings

import ptvsd._vendored as _vd


# Ensure that pydevd is our vendored copy.
_unvendored, _ = _vd.check_modules('pydevd',
                                   _vd.prefix_matcher('pydev', '_pydev'))
if _unvendored:
    _unvendored = sorted(_unvendored.values())
    #raise ImportError(msg)
    warnings.warn(('incompatible copy of pydevd already imported:\n  {}'
                   ).format('\n  '.join(_unvendored)))


# Now make sure all the top-level modules and packages in pydevd are
# loaded.  Any pydevd modules that aren't loaded at this point, will
# be loaded using their parent package's __path__ (i.e. one of the
# following).
_vd.preimport('pydevd', [
    '_pydev_bundle',
    '_pydev_imps',
    '_pydev_runfiles',
    '_pydevd_bundle',
    '_pydevd_frame_eval',
    'pydev_ipython',
    'pydevd_concurrency_analyser',
    'pydevd_plugins',
    'pydevd',
])
