import sys
with open('/Users/donjayamanne/Desktop/Development/vscode/ptvsd/log.log', 'a') as fs:
    fs.write('\n1\n')
try:
    import ptvsd
    ptvsd.enable_attach((sys.argv[1], sys.argv[2]))
    ptvsd.wait_for_attach()
except Exception:
    import traceback
    with open('/Users/donjayamanne/Desktop/Development/vscode/ptvsd/log.log', 'a') as fs:
        fs.write('\n2\n')
        traceback.print_exc(file=fs)
    traceback.print_exc()
with open('/Users/donjayamanne/Desktop/Development/vscode/ptvsd/log.log', 'a') as fs:
    fs.write('\n3\n')
    fs.write(str(sys.argv))
    fs.write('\n2\n')
