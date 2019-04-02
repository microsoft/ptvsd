#!/bin/bash
set -ev

source activate build_env
conda install --yes numpy ipython pytest cython psutil

if [ "$PYDEVD_PYTHON_VERSION" = "2.6" ]; then
    conda install --yes pyqt=4
    pip install pympler==0.5
    pip install pathlib2
    # Django 1.7 does not support Python 2.6
else
    # pytest-xdist not available for python 2.6
    pip install pytest-xdist
    pip install pympler
fi

if [ "$PYDEVD_PYTHON_VERSION" = "2.7" ]; then
    conda install --yes pyqt=4 gevent
    pip install "django>=1.7,<1.8"
    pip install pathlib2

fi

if [ "$PYDEVD_PYTHON_VERSION" = "3.5" ]; then
    conda install --yes pyqt=5
    pip install "django>=2.1,<2.2"
fi

if [ "$PYDEVD_PYTHON_VERSION" = "3.6" ]; then
    conda install --yes pyqt=5 gevent
    pip install "django>=2.1,<2.2"
fi

if [ "$PYDEVD_PYTHON_VERSION" = "3.7" ]; then
    conda install --yes pyqt=5 matplotlib
    # Note: track the latest django
    pip install "django>=2.1,<2.2"
fi

pip install untangle
pip install scapy==2.4.0