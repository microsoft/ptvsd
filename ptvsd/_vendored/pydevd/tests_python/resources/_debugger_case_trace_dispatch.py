import sys


def method():
    a = 10  # add breakpoint
    b = 20
    c = 30
    d = 40
    if sys._getframe().f_trace is None:
        print('TEST SUCEEDED')
    else:
        raise AssertionError('frame.f_trace is expected to be None at this point.')


method()
