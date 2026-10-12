"""Non-UI Live Set persistence through Live-owned in-process objects."""

from __future__ import absolute_import, print_function, unicode_literals

from .diagnostics import _find_licensing_owners


def _resolve_save_bridge(objects=None):
    owners = _find_licensing_owners(objects)
    if len(owners) != 1:
        raise RuntimeError(
            "Expected one Live-owned PythonLicensing instance; found {0}".format(
                len(owners)
            )
        )

    bridge = getattr(owners[0], "licensing_bridge", None)
    save = getattr(bridge, "save_current_set", None)
    if not callable(save):
        raise RuntimeError(
            "Live-owned PythonLicensing bridge has no callable save_current_set"
        )
    return bridge


def save_current_set(song, ctrl=None, objects=None):
    """Save a named Set without focus changes, keystrokes, or UI fallback."""
    file_path = str(getattr(song, "file_path", "") or "")
    if not file_path:
        raise ValueError(
            "Current Live Set is Untitled; refusing Save because Live would open UI"
        )

    bridge = _resolve_save_bridge(objects)
    bridge.save_current_set()
    if ctrl:
        ctrl.log_message("Saved current Live Set through Live-owned licensing bridge")
    return {
        "backend": "live_owned_python_licensing",
        "file_path": file_path,
        "save_requested": True,
        "ui_used": False,
    }
