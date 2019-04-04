def method1(n):
    if n <= 0:
        raise IndexError('foo')
    method1(n-1)

if __name__ == '__main__':
    method1(100)
    print('TEST SUCEEDED!')