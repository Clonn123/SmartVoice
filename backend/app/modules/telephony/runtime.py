_caller = None


def set_caller(caller):
    global _caller
    _caller = caller


def get_caller():
    if _caller is None:
        raise RuntimeError("AsteriskCaller is not initialized")

    return _caller
