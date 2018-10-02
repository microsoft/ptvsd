import runpy
if __name__ == '__main__':
    
    import sys
    import os
    print('--- sys.path -- ')
    print('\n'.join(sorted(sys.path)))
    
    sys.path.append(os.path.join(os.path.dirname(__file__), 'ptvsd', '_vendored', 'pydevd'))
    assert os.path.exists(sys.path[-1])
    
    print('\n--- pydevd library roots -- ')
    from _pydevd_bundle.pydevd_utils import _get_default_library_roots
    print('\n'.join(sorted(_get_default_library_roots())))
    
    print('\n--- site run -- ')
    import site
    site._script()