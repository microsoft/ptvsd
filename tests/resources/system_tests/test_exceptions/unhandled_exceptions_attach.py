import sys
import ptvsd
ptvsd.enable_attach((('localhost', 9879)))
ptvsd.wait_for_attach()

raise ValueError('bad')
sys.stdout.write('end')
