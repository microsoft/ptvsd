# Contributing to `ptvsd` 

[![Build Status](https://ptvsd.visualstudio.com/_apis/public/build/definitions/557bd35a-f98d-4c49-9bc9-c7d548f78e4d/1/badge)](https://ptvsd.visualstudio.com/ptvsd/ptvsd%20Team/_build/index?definitionId=1)
[![Build Status](https://travis-ci.org/Microsoft/ptvsd.svg?branch=master)](https://travis-ci.org/Microsoft/ptvsd)


## Contributing a pull request

### Prerequisites
These packages are needed to work with `ptvsd`:
* setuptools
* coverage
* requests
* flask
* django
* pytest

### Linting
We use `flake8` for linting. These are the settings we use with linting:
```
ignore = W,E24,E121,E123,E125,E126,E221,E226,E266,E704,E265,E722,E501,E731,E306,E401,E302,E222
exclude =
    ptvsd/_vendored/pydevd,
    ./.eggs,
    ./versioneer.py
```
VSC Python settings for Linting:
```json
    "python.linting.flake8Enabled": true,
    "python.linting.pylintEnabled": false,
    "python.linting.flake8Args": [
        "--ignore", "E24,E121,E123,E125,E126,E221,E226,E266,E704,E265,E722,E501,E731,E306,E401,E302,E222",
        "--exclude", "ptvsd/_vendored/*",
    ],
```

