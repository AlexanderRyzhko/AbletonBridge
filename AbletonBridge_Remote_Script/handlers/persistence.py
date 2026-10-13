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


def _request_document_exchange(operation, **params):
    """Expose only the fixed, non-sensitive native dirty-state refusal."""
    try:
        return operation(**params)
    except PermissionError as exc:
        expected = (
            "Current Set has unsaved changes; native discard is not implemented; "
            "refusing document exchange because Live would open a dialog"
        )
        if str(exc) == expected:
            raise ValueError(expected) from exc
        raise


def get_document_persistence_state(song, native_module=None):
    """Read native dirty state without requesting Save or document exchange."""
    if native_module is None:
        native_module = _load_native_save_module()
    result = native_module.document_state()
    result["file_path"] = str(getattr(song, "file_path", "") or "") or None
    result["native_discard_supported"] = False
    result["document_exchange_supported"] = False
    result["document_exchange_reason"] = "cursor_side_effects"
    return result


def save_current_set(song, ctrl=None, native_module=None, experimental=False):
    """Experimental idle-only named Save; legacy application-view route refused."""
    file_path = str(getattr(song, "file_path", "") or "")
    if not file_path:
        raise ValueError(
            "Current Live Set is Untitled; refusing Save because Live would open UI"
        )

    result = save_set_as(song, file_path, overwrite=True, ctrl=ctrl,
                         native_module=native_module, experimental=experimental)
    result["file_path"] = file_path
    return result


def save_set_as(song, path, overwrite=False, ctrl=None, native_module=None, experimental=False):
    """Save current Set to an absolute path through version-locked native adapter."""
    path = str(path or "")
    if not path:
        raise ValueError("Save As path is required")
    if native_module is None:
        native_module = _load_native_save_module()

    if experimental is True:
        return _save_set_as_document(song, path, overwrite, native_module)

    result = native_module.save_as(path=path, overwrite=bool(overwrite))
    if ctrl:
        ctrl.log_message("Requested non-UI Save As through native LFile adapter")
    return result


def _save_set_as_document(song, path, overwrite, native_module):
    """Idle-only prototype: verify serialization before document bookkeeping."""
    import gzip
    import os
    import xml.etree.ElementTree as ET

    if getattr(song, "is_playing", True) or getattr(song, "record_mode", True):
        raise ValueError("Experimental Save As requires stopped playback and recording")
    copy = save_set_copy(song, path, overwrite=overwrite, experimental=True,
                         native_module=native_module)
    with gzip.open(path, "rb") as stream:
        xml = stream.read(32 * 1024 * 1024 + 1)
    if len(xml) > 32 * 1024 * 1024:
        raise ValueError("Serialized copy exceeds experimental Save As XML limit")
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise ValueError("Serialized copy contains XML declarations; refusing adoption")
    root = ET.fromstring(xml)
    if root.tag != "Ableton" or root.find("LiveSet") is None:
        raise ValueError("Serialized copy lacks Ableton/LiveSet XML; refusing adoption")
    try:
        native_module.adopt_saved_copy(path)
    except Exception as exc:
        raise ValueError(
            "Set copy written, but Save As finalization was not verified; "
            "read active path and dirty state before any further action; do not retry"
        ) from exc
    active = str(getattr(song, "file_path", "") or "")
    state = native_module.document_state()
    if os.path.realpath(active) != os.path.realpath(path) or state.get("has_unsaved_changes") is not False:
        raise ValueError(
            "Save As bookkeeping failed path/dirty readback; do not retry"
        )
    return {"backend": "live_native_document_serializer_and_bookkeeping",
            "path": path, "active_file_path": active, "save_requested": True,
            "copy_file_verified": True, "gzip_xml_verified": True,
            "has_unsaved_changes": False, "active_path_verified": True,
            "ui_automation_used": False, "desktop_noninterference_verified": False,
            "experimental": True, "snapshot_backend": copy["backend"]}


def save_set_copy(song, path, overwrite=False, experimental=False, native_module=None):
    """Experimental document serialization, not active-path Save As."""
    if experimental is not True:
        raise ValueError("Save Copy requires explicit experimental=true")
    if type(overwrite) is not bool:
        raise ValueError("overwrite must be a boolean")
    path = str(path or "")
    if not path:
        raise ValueError("Save Copy path is required")
    original_path = str(getattr(song, "file_path", "") or "")
    if native_module is None:
        native_module = _load_native_save_module()
    result = native_module.save_copy(path, overwrite=bool(overwrite))
    active_path = str(getattr(song, "file_path", "") or "")
    if active_path != original_path:
        raise RuntimeError("Save Copy unexpectedly changed active document path")
    result["active_path_unchanged"] = True
    result["active_file_path"] = active_path or None
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
        state = native_module.document_state()
        if state.get("has_unsaved_changes") is False:
            return "already_clean"
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

    result = _request_document_exchange(
        native_module.open_set, path=path, replace_confirmed=True
    )
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
    result = _request_document_exchange(native_module.new_set, replace_confirmed=True)
    result["current_set_action"] = current_action
    result["source_document_id"] = ctrl.document_id if ctrl else None
    if ctrl:
        ctrl.log_message("Requested non-UI New Set through native document adapter")
    return result
