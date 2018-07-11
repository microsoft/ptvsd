import subprocess
import time


with open('one.txt', 'r') as fs:
    lines = fs.readlines()
    for hash in (l.strip() for l in lines):
        proc = subprocess.Popen(['git', 'revert', '--no-edit', hash])
        proc.wait()

