def test_in_project_roots(tmpdir):
    from _pydevd_bundle import pydevd_utils
    import os.path
    assert pydevd_utils._get_library_roots() == [
        os.path.normcase(x) for x in pydevd_utils._get_default_library_roots()]
    
    site_packages = tmpdir.mkdir('site-packages')
    project_dir = tmpdir.mkdir('project')
    
    project_dir_inside_site_packages = str(site_packages.mkdir('project'))
    site_packages_inside_project_dir = str(project_dir.mkdir('site-packages'))
    
    # Convert from pytest paths to str.
    site_packages = str(site_packages)
    project_dir = str(project_dir)
    tmpdir = str(tmpdir)
    
    # Test permutations of project dir inside site packages and vice-versa.
    pydevd_utils.set_project_roots([project_dir, project_dir_inside_site_packages])
    pydevd_utils.set_library_roots([site_packages, site_packages_inside_project_dir])

    check = [
        (tmpdir, False),
        (site_packages, False),
        (site_packages_inside_project_dir, False),
        (project_dir, True),
        (project_dir_inside_site_packages, True),
    ]
    for (check_path, find) in check[:]:
        check.append((os.path.join(check_path, 'a.py'), find))
        
    for check_path, find in check:
        assert pydevd_utils.in_project_roots(check_path) == find
