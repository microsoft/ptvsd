try:
    import urllib.request as url_lib
except ImportError:
    import urllib2 as url_lib


def get_web_string(path):
    req = url_lib.urlopen(path)
    data = req.read()
    if not isinstance(data, str):
        data = data.decode('utf-8')
    return data
