"""C ABI wrapper for Live's embedded Python, which hides Python C symbols."""

try:
    import _ctypes
except ImportError:
    # Live registers the low-level built-in under this public name.
    import ctypes as _ctypes
import os


class _Int(_ctypes._SimpleCData):
    _type_ = "i"


class _CharPointer(_ctypes._SimpleCData):
    _type_ = "z"


class _Function(_ctypes.CFuncPtr):
    # CDECL | PYTHONAPI: retain GIL while Live callbacks invoke Python.
    _flags_ = _ctypes.FUNCFLAG_CDECL | _ctypes.FUNCFLAG_PYTHONAPI
    _restype_ = _Int


class _Library:
    def __init__(self, path):
        self._handle = _ctypes.dlopen(path)

    def __getattr__(self, name):
        function = _Function((name, self))
        setattr(self, name, function)
        return function


_lib = _Library(os.path.join(os.path.dirname(__file__), "libableton_native_save.dylib"))
for _name in ("ab_hash", "ab_uuid", "ab_error"):
    _function = getattr(_lib, _name)
    _function.argtypes = []
    _function.restype = _CharPointer
for _name in ("ab_prepare", "ab_main_thread", "ab_error_type", "ab_commit_document"):
    _function = getattr(_lib, _name)
    _function.argtypes = []
    _function.restype = _Int
_lib.ab_cancel_document.argtypes = []
_lib.ab_cancel_document.restype = None
_lib.ab_save_as.argtypes = [_CharPointer, _Int]
_lib.ab_open_set.argtypes = [_CharPointer, _Int]
_lib.ab_new_set.argtypes = [_Int]
for _name in ("ab_save_as", "ab_open_set", "ab_new_set"):
    getattr(_lib, _name).restype = _Int


def prepare():
    supported = bool(_lib.ab_prepare())
    return {
        "supported_version": "12.4.6",
        "actual_sha256": _lib.ab_hash().decode("ascii"),
        "actual_arm64_uuid": _lib.ab_uuid().decode("ascii"),
        "supported": supported,
        "main_thread": bool(_lib.ab_main_thread()),
        "ui_used": False,
    }


probe = prepare


def _path_bytes(path):
    if not isinstance(path, str) or "\x00" in path:
        raise ValueError("Path must be a string without NUL bytes")
    return path.encode("utf-8")


def _check(accepted):
    if not accepted:
        errors = (ValueError, PermissionError, FileExistsError, FileNotFoundError, RuntimeError)
        code = _lib.ab_error_type()
        error_type = errors[code] if 0 <= code < len(errors) else RuntimeError
        raise error_type(_lib.ab_error().decode("utf-8"))


def save_as(path, overwrite=False):
    _check(_lib.ab_save_as(_path_bytes(path), bool(overwrite)))
    return {"backend": "live_native_lfile", "path": path, "save_requested": True, "ui_used": False}


def open_set(path, replace_confirmed=False):
    _check(_lib.ab_open_set(_path_bytes(path), bool(replace_confirmed)))
    return {"backend": "live_native_document_request", "path": os.path.realpath(path), "open_requested": True, "ui_used": False}


def new_set(replace_confirmed=False):
    _check(_lib.ab_new_set(bool(replace_confirmed)))
    return {"backend": "live_native_document_new", "new_requested": True, "ui_used": False}


def commit_document():
    _check(_lib.ab_commit_document())


def cancel_document():
    _lib.ab_cancel_document()
