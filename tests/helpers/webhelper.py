try:
    import urllib.request as url_lib
except ImportError:
    import urllib2 as url_lib


def get_web_string(path, obj):
    req = url_lib.urlopen(path)
    data = req.read()
    if not isinstance(data, str):
        data = data.decode('utf-8')
    if obj is not None:
        obj['content'] = data
    return data


def get_web_string_no_error(path, obj):
    try:
        return get_web_string(path, obj)
    except Exception:
        pass
