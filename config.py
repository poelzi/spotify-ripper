import json

_RV = None
def config_get(key, default=None):
    global _RV
    if not _RV:
        with open('config.json', 'r') as fp:
            _RV = json.load(fp)

    try:
        return _RV[key]
    except AttributeError:
        return default
