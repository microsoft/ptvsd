import sys
import ptvsd
ptvsd.enable_attach((sys.argv[1], sys.argv[2]))
ptvsd.wait_for_attach()

try:
    raise ArithmeticError('Hello')
except Exception:
    pass
sys.stdout.write('end')
