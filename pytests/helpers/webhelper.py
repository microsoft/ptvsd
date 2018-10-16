# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from contextlib import contextmanager
import threading
import requests
import re

def get_web_string(path, obj):
    r = requests.get(path)
    content = r.text
    if obj is not None:
        obj['content'] = content
    return content


def get_web_string_no_error(path, obj):
    try:
        return get_web_string(path, obj)
    except Exception:
        pass


re_link = r"(http(s|)\:\/\/[\w\.]*\:[0-9]{4,6}(\/|))"
def get_url_from_str(s):
    matches = re.findall(re_link, s)
    if matches and matches[0]and matches[0][0].strip():
        return matches[0][0]
    return None


@contextmanager
def get_web_content(link, web_result=None, timeout=1):
    web_client_thread = threading.Thread(
        target=get_web_string_no_error,
        args=(link, web_result),
        name='test.webClient'
    )
    web_client_thread.start()
    yield web_result
    web_client_thread.join(timeout=timeout)
