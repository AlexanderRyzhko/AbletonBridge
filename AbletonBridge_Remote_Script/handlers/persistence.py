"""Non-UI Live Set persistence through Live-owned in-process objects."""

from __future__ import absolute_import, print_function, unicode_literals



def _load_native_save_module():
    try:
        from .. import _ableton_native_save
    except ImportError as exc:
        raise RuntimeError(
            "Native document adapter is not installed for this Stable build"
        ) from exc
    return _ableton_native_save


def prepare_native_save_as(native_module=None):
    """Hash/cache native document-adapter identity from the TCP worker."""
    if native_module is None:
        native_module = _load_native_save_module()
    result = native_module.prepare()
    if not result.get("supported"):
        raise RuntimeError(
            "Native document adapter does not match loaded Stable Live binary"
        )
    return result


def prepare_native_document_adapter(native_module=None):
    """Prepare the shared Save As/Open Set adapter on the TCP worker."""
    return prepare_native_save_as(native_module=native_module)


def commit_document_request():
    _load_native_save_module().commit_document()


def cancel_document_request():
    _load_native_save_module().cancel_document()


def save_current_set(song, ctrl=None, native_module=None):
    """Save a named Set without focus changes, keystrokes, or UI fallback."""
    file_path = str(getattr(song, "file_path", "") or "")
    if not file_path:
        raise ValueError(
            "Current Live Set is Untitled; refusing Save because Live would open UI"
        )

    result = save_set_as(song, file_path, overwrite=True, ctrl=ctrl,
                         native_module=native_module)
    result["file_path"] = file_path
    return result


def save_set_as(song, path, overwrite=False, ctrl=None, native_module=None):
    """Save current Set to an absolute path through version-locked native adapter."""
    del song
    path = str(path or "")
    if not path:
        raise ValueError("Save As path is required")
    if native_module is None:
        native_module = _load_native_save_module()

    result = native_module.save_as(path=path, overwrite=bool(overwrite))
    if ctrl:
        ctrl.log_message("Requested non-UI Save As through native LFile adapter")
    return result


def _protect_current_set(
    song,
    discard_current,
    save_as_path,
    overwrite_save_as,
    ctrl,
    native_module,
):
    current_path = str(getattr(song, "file_path", "") or "")
    if discard_current:
        return "explicit_discard"
    if current_path:
        save_current_set(song, ctrl=ctrl, native_module=native_module)
        return "saved_named_set"
    if save_as_path:
        save_set_as(
            song,
            save_as_path,
            overwrite=overwrite_save_as,
            ctrl=ctrl,
            native_module=native_module,
        )
        return "saved_untitled_set_as"
    raise ValueError(
        "Current Live Set is Untitled; provide save_as_path or explicitly "
        "set discard_current=true"
    )


def open_set(
    song,
    path,
    discard_current=False,
    save_as_path="",
    overwrite_save_as=False,
    ctrl=None,
    native_module=None,
):
    """Open an explicit .als path without UI and with fail-closed data policy."""
    path = str(path or "")
    if not path:
        raise ValueError("Open Set path is required")
    if native_module is None:
        native_module = _load_native_save_module()

    current_action = _protect_current_set(
        song,
        discard_current,
        save_as_path,
        overwrite_save_as,
        ctrl,
        native_module,
    )

    result = native_module.open_set(path=path, replace_confirmed=True)
    result["current_set_action"] = current_action
    result["source_document_id"] = ctrl.document_id if ctrl else None
    if ctrl:
        ctrl.log_message("Requested non-UI Open Set through native document adapter")
    return result


def new_set(
    song,
    discard_current=False,
    save_as_path="",
    overwrite_save_as=False,
    ctrl=None,
    native_module=None,
):
    """Create a new Set without UI and with fail-closed data policy."""
    if native_module is None:
        native_module = _load_native_save_module()
    current_action = _protect_current_set(
        song,
        discard_current,
        save_as_path,
        overwrite_save_as,
        ctrl,
        native_module,
    )
    result = native_module.new_set(replace_confirmed=True)
    result["current_set_action"] = current_action
    result["source_document_id"] = ctrl.document_id if ctrl else None
    if ctrl:
        ctrl.log_message("Requested non-UI New Set through native document adapter")
    return result
