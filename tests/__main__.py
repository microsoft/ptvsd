import inspect

if __name__ == '__main__':
    import sys
    import os
    print('--- sys.path -- ')
    print('\n'.join(sorted(sys.path)))

    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'ptvsd', '_vendored', 'pydevd'))
    assert os.path.exists(sys.path[-1])

    print('\n--- pydevd library roots -- ')
    from _pydevd_bundle.pydevd_utils import _get_default_library_roots
    print('\n'.join(sorted(_get_default_library_roots())))

    import site
    print('\n--- site params -- ')
    for name in sorted(dir(site)):
        if name not in ('__doc__',):
            v = getattr(site, name)
            if inspect.isfunction(v) or inspect.ismethod(v):
                try:
                    print('site.%s = %s  (func, method)' % (name, v()))
                except:
                    print('unable to check: %s' % (v,))
    
            else:
                print('site.%s = %s' % (name, v))

    print('\n--- sysconfig -- ')
    import sysconfig
    for key, val in sysconfig.get_config_vars().items():
        print('%s - %s' % (key, val))
        
    print('\n--- sysconfig paths -- ')
    import sysconfig
    for key, val in sysconfig.get_paths().items():
        print('%s - %s' % (key, val))
    
    print('\n--- sys params -- ')
    for name in sorted(dir(sys)):
        if name not in (
            '__doc__',
            'modules',
            'builtin_module_names',
            'breakpoint',
            '__breakpoint__',
            'breakpointhook',
            '__breakpointhook__',
            'getcheckinterval',
            'setcheckinterval',
            'get_coroutine_wrapper',
            'exit',
            'call_tracing',
            'copyright',
            '_current_frames',
            '_clear_type_cache',
            'callstats',
            '_debugmallocstats',
            ):
            v = getattr(sys, name)
            if inspect.isfunction(v) or inspect.ismethod(v) or inspect.isbuiltin(v):
                try:
                    print('sys.%s = %s  (func, method)' % (name, v()))
                except:
                    print('unable to check: %s' % (v,))
    
            else:
                print('sys.%s = %s' % (name, v))

    print('\n--- site run -- ')
    sys.argv = ['']
    site._script()

