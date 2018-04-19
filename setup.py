#!/usr/bin/env python

# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import os
import os.path
import subprocess
import sys

from setuptools import setup

import versioneer
import ptvsd
import ptvsd._vendored


PYDEVD_ROOT = ptvsd._vendored.project_root('pydevd')
PTVSD_ROOT = os.path.dirname(os.path.abspath(ptvsd.__file__))


def cython_build():
    print('Compiling extension modules (set SKIP_CYTHON_BUILD=1 to omit)')
    subprocess.call([
        sys.executable,
        os.path.join(PYDEVD_ROOT, 'setup_cython.py'),
        'build_ext',
        '-i',
    ])


def iter_vendored_files():
    # Add pydevd files as data files for this package. They are not
    # treated as a package of their own, because we don't actually
    # want to provide pydevd - just use our own copy internally.
    for project in ptvsd._vendored.list_all():
        for filename in ptvsd._vendored.iter_packaging_files(project):
            yield filename


if __name__ == '__main__':
    if not os.getenv('SKIP_CYTHON_BUILD'):
        cython_build()

    setup(
        name='ptvsd',
        version=versioneer.get_version(),
        description='Remote debugging server for Python support in Visual Studio and Visual Studio Code', # noqa
        #long_description=open('DESCRIPTION.md').read(),
        #long_description_content_type='text/markdown',
        license='MIT',
        author='Microsoft Corporation',
        author_email='ptvshelp@microsoft.com',
        url='https://aka.ms/ptvs',
        classifiers=[
            'Development Status :: 3 - Alpha',
            'Programming Language :: Python',
            'Programming Language :: Python :: 2',
            'Programming Language :: Python :: 3',
            'License :: OSI Approved :: MIT License',
        ],
        packages=[
            'ptvsd',
            'ptvsd._vendored',
        ],
        package_data={
            'ptvsd': ['ThirdPartyNotices.txt'],
            'ptvsd._vendored': list(iter_vendored_files()),
        },
        cmdclass=versioneer.get_cmdclass(),
    )
