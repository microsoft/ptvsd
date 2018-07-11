import threading, atexit

try:
    from thread import start_new_thread
except:
    from _thread import start_new_thread

    
def _atexit():
    print('TEST SUCEEDED')


# Register the TEST SUCEEDED msg to the exit of the process.
atexit.register(_atexit)


def thread_func(n):
    raise Exception('argh')


th = threading.Thread(target=lambda: thread_func(1))
th.setDaemon(True)
th.start()

event = threading.Event()


def thread_func2():
    event.set()
    raise Exception('argh')
    

start_new_thread(thread_func2, ())

event.wait()
th.join()

# This is a bit tricky: although we waited on the event, there's a slight chance
# that we didn't get the notification because the thread could've stopped executing,
# so, sleep a bit so that the test does not become flaky.
import time
time.sleep(.3) 

raise Exception('argh')
