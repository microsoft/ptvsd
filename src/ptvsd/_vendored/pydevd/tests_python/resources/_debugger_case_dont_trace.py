def call_me_back(callback):
    if callback is not None and callable(callback):
        callback()