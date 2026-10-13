import importlib.util
import gzip
import tempfile
import sys
import types
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HANDLERS = ROOT / "AbletonBridge_Remote_Script" / "handlers"
PACKAGE = "abletonbridge_test_handlers"

package = types.ModuleType(PACKAGE)
package.__path__ = [str(HANDLERS)]
sys.modules.setdefault(PACKAGE, package)

for module_name in ("diagnostics", "persistence"):
    qualified_name = "{0}.{1}".format(PACKAGE, module_name)
    spec = importlib.util.spec_from_file_location(
        qualified_name,
        HANDLERS / (module_name + ".py"),
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified_name] = module
    spec.loader.exec_module(module)

persistence = sys.modules[PACKAGE + ".persistence"]


class _Song:
    def __init__(self, file_path):
        self.file_path = file_path
        self.is_playing = False
        self.record_mode = False


class _NativeSave:
    def __init__(self):
        self.calls = []

    def document_state(self):
        return {"has_unsaved_changes": True}

    def save_as(self, path, overwrite=False):
        raise ValueError("Legacy native Save is unavailable under desktop noninterference")

    def open_set(self, path, replace_confirmed=False):
        self.calls.append(("open_set", path, replace_confirmed))
        return {
            "backend": "live_native_document_request",
            "path": path,
            "open_requested": True,
            "ui_used": False,
        }

    def new_set(self, replace_confirmed=False):
        self.calls.append(("new_set", replace_confirmed))
        return {
            "backend": "live_native_document_new",
            "new_requested": True,
            "ui_used": False,
        }

    def prepare(self):
        return {"supported": True, "ui_used": False}

    def save_copy(self, path, overwrite=False):
        self.calls.append(("save_copy", path, overwrite))
        return {"path": path, "copy_requested": True, "experimental": True}


class PersistenceTests(unittest.TestCase):
    def test_named_save_forwards_explicit_experimental_consent(self):
        native = _NativeSave()
        with patch.object(persistence, "save_set_as", return_value={}) as save:
            result = persistence.save_current_set(_Song("/tmp/source.als"),
                native_module=native, experimental=True)
        self.assertEqual(result["file_path"], "/tmp/source.als")
        self.assertTrue(save.call_args.kwargs["overwrite"])
        self.assertTrue(save.call_args.kwargs["experimental"])

    def test_open_clean_named_set_does_not_invoke_save(self):
        native = _NativeSave()
        native.document_state = lambda: {"has_unsaved_changes": False}
        result = persistence.open_set(_Song("/tmp/source.als"), "/tmp/next.als",
                                      native_module=native)
        self.assertEqual(native.calls, [("open_set", "/tmp/next.als", True)])
        self.assertEqual(result["current_set_action"], "already_clean")

    def test_dirty_save_refusal_prevents_open_and_new(self):
        def blocked(*args, **kwargs):
            raise ValueError("Full Save/Save As is unavailable under desktop noninterference")
        for operation, params in ((persistence.open_set, {"path": "/tmp/next.als"}),
                                  (persistence.new_set, {})):
            native = _NativeSave()
            native.save_as = blocked
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(ValueError, "desktop noninterference"):
                    operation(_Song("/tmp/source.als"), native_module=native, **params)
            self.assertEqual(native.calls, [])

    def test_document_state_reports_dirty_without_mutation(self):
        native = _NativeSave()
        native.document_state = lambda: {"has_unsaved_changes": True}
        result = persistence.get_document_persistence_state(_Song("/tmp/source.als"), native)
        self.assertTrue(result["dirty_exchange_refused"])
        self.assertFalse(result["native_discard_supported"])
        self.assertEqual(result["file_path"], "/tmp/source.als")
        self.assertEqual(native.calls, [])

    def test_document_state_reports_clean_untitled(self):
        native = _NativeSave()
        native.document_state = lambda: {"has_unsaved_changes": False}
        result = persistence.get_document_persistence_state(_Song(None), native)
        self.assertFalse(result["dirty_exchange_refused"])
        self.assertIsNone(result["file_path"])

    def test_dirty_document_refusal_is_client_safe_validation_error(self):
        message = (
            "Current Set has unsaved changes; native discard is not implemented; "
            "refusing document exchange because Live would open a dialog"
        )
        def denied(**params):
            raise PermissionError(message)
        native = _NativeSave()
        native.open_set = denied
        native.new_set = denied
        for operation, params in (
            (persistence.open_set, {"path": "/tmp/next.als"}),
            (persistence.new_set, {}),
        ):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(ValueError, "native discard is not implemented"):
                    operation(_Song("/tmp/source.als"), discard_current=True,
                              native_module=native, **params)

    def test_other_permission_errors_remain_private(self):
        def denied(**params):
            raise PermissionError("Private runtime or filesystem details")
        with self.assertRaises(PermissionError):
            persistence._request_document_exchange(denied)

    def test_save_copy_requires_explicit_experimental_flag(self):
        native = _NativeSave()
        with self.assertRaisesRegex(ValueError, "experimental=true"):
            persistence.save_set_copy(_Song(None), "/tmp/copy.als", native_module=native)
        self.assertEqual(native.calls, [])

    def test_save_copy_rejects_truthy_nonboolean_flags_before_mutation(self):
        native = _NativeSave()
        for flags in ({"experimental": "false"},
                      {"experimental": True, "overwrite": "false"}):
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                persistence.save_set_copy(_Song(None), "/tmp/copy.als",
                                         native_module=native, **flags)
        self.assertEqual(native.calls, [])

    def test_save_copy_retains_active_path(self):
        native = _NativeSave()
        result = persistence.save_set_copy(
            _Song("/tmp/original.als"), "/tmp/copy.als",
            experimental=True, native_module=native,
        )
        self.assertEqual(native.calls, [("save_copy", "/tmp/copy.als", False)])
        self.assertTrue(result["active_path_unchanged"])
        self.assertEqual(result["active_file_path"], "/tmp/original.als")

    def test_save_copy_reports_unexpected_path_change(self):
        native = _NativeSave()
        song = _Song("/tmp/original.als")
        original_copy = native.save_copy
        def changed(path, overwrite=False):
            song.file_path = path
            return original_copy(path, overwrite)
        native.save_copy = changed
        with self.assertRaisesRegex(RuntimeError, "changed active"):
            persistence.save_set_copy(song, "/tmp/copy.als",
                                      experimental=True, native_module=native)

    def test_save_copy_rejects_empty_path_before_native_call(self):
        native = _NativeSave()
        with self.assertRaisesRegex(ValueError, "path is required"):
            persistence.save_set_copy(_Song(None), "", experimental=True,
                                      native_module=native)
        self.assertEqual(native.calls, [])

    def test_save_current_set_refuses_legacy_route(self):
        native = _NativeSave()
        with self.assertRaisesRegex(ValueError, "desktop noninterference"):
            persistence.save_current_set(_Song("/tmp/ABKB-3/disposable.als"),
                                         native_module=native)
        self.assertEqual(native.calls, [])

    def test_save_current_set_refuses_untitled_before_native_call(self):
        native = _NativeSave()
        with self.assertRaisesRegex(ValueError, "Untitled"):
            persistence.save_current_set(_Song(None), native_module=native)
        self.assertEqual(native.calls, [])

    def test_save_current_set_propagates_native_failure(self):
        native = _NativeSave()
        def fail(*args, **kwargs):
            raise RuntimeError("save failed")
        native.save_as = fail
        with self.assertRaisesRegex(RuntimeError, "save failed"):
            persistence.save_current_set(_Song("/tmp/ABKB-3/disposable.als"),
                                         native_module=native)

    def test_save_set_as_without_experiment_refuses_legacy_route(self):
        native = _NativeSave()
        with self.assertRaisesRegex(ValueError, "desktop noninterference"):
            persistence.save_set_as(_Song(None), "/tmp/ABKB-3/disposable.als",
                                    overwrite=True, native_module=native)
        self.assertEqual(native.calls, [])

    def test_save_set_as_requires_path_before_import(self):
        with self.assertRaisesRegex(ValueError, "path is required"):
            persistence.save_set_as(_Song(None), "")

    def test_prepare_native_save_as_requires_supported_identity(self):
        native = _NativeSave()
        self.assertTrue(
            persistence.prepare_native_save_as(native_module=native)["supported"]
        )

        native.prepare = lambda: {"supported": False, "ui_used": False}
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            persistence.prepare_native_save_as(native_module=native)

    def test_open_dirty_named_set_refuses_legacy_save_first(self):
        native = _NativeSave()
        with self.assertRaisesRegex(ValueError, "desktop noninterference"):
            persistence.open_set(_Song("/tmp/ABKB-3/current.als"), "/tmp/ABKB-3/next.als",
                                 native_module=native)
        self.assertEqual(native.calls, [])

    def test_open_set_refuses_untitled_without_explicit_policy(self):
        native = _NativeSave()

        with self.assertRaisesRegex(ValueError, "Untitled"):
            persistence.open_set(
                _Song(None),
                "/tmp/ABKB-3/next.als",
                native_module=native,
            )

        self.assertEqual(native.calls, [])

    def test_open_set_allows_explicit_discard_without_save_or_ui(self):
        native = _NativeSave()

        result = persistence.open_set(
            _Song(None),
            "/tmp/ABKB-3/next.als",
            discard_current=True,
            native_module=native,
        )

        self.assertEqual(
            native.calls, [("open_set", "/tmp/ABKB-3/next.als", True)]
        )
        self.assertEqual(result["current_set_action"], "explicit_discard")

    def test_new_dirty_named_set_refuses_legacy_save_first(self):
        native = _NativeSave()
        song = _Song("/tmp/ABKB-3/current.als")
        with self.assertRaisesRegex(ValueError, "desktop noninterference"):
            persistence.new_set(song, native_module=native)
        self.assertEqual(native.calls, [])

    def test_new_set_refuses_untitled_without_explicit_policy(self):
        native = _NativeSave()

        with self.assertRaisesRegex(ValueError, "Untitled"):
            persistence.new_set(_Song(None), native_module=native)

        self.assertEqual(native.calls, [])


class DocumentSaveAsTests(unittest.TestCase):
    def make_native(self, song, payload=b"<Ableton><LiveSet/></Ableton>"):
        native = _NativeSave()
        native.dirty = True
        def copy(path, overwrite=False):
            native.calls.append(("copy", path))
            with gzip.open(path, "wb") as stream:
                stream.write(payload)
            return {"backend": "live_native_document_serializer"}
        def adopt(path):
            native.calls.append(("adopt", path))
            song.file_path = path
            native.dirty = False
        native.save_copy = copy
        native.adopt_saved_copy = adopt
        native.document_state = lambda: {"has_unsaved_changes": native.dirty}
        return native

    def test_verified_copy_then_owned_bookkeeping(self):
        song = _Song(None)
        native = self.make_native(song)
        with tempfile.TemporaryDirectory() as directory:
            target = str(Path(directory) / "named.als")
            result = persistence.save_set_as(song, target, native_module=native,
                                             experimental=True)
        self.assertEqual(native.calls, [("copy", target), ("adopt", target)])
        self.assertTrue(result["active_path_verified"])
        self.assertFalse(result["has_unsaved_changes"])
        self.assertTrue(result["experimental"])
        self.assertFalse(result["desktop_noninterference_verified"])

    def test_playback_or_recording_refuses_before_copy(self):
        for playing, recording in ((True, False), (False, True)):
            song = _Song(None)
            song.is_playing, song.record_mode = playing, recording
            native = self.make_native(song)
            with self.assertRaisesRegex(ValueError, "requires stopped"):
                persistence.save_set_as(song, "/tmp/unused.als", native_module=native,
                                        experimental=True)
            self.assertEqual(native.calls, [])

    def test_invalid_set_structure_refuses_before_adoption(self):
        song = _Song("/tmp/original.als")
        native = self.make_native(song, b"<not_a_set/>")
        with tempfile.TemporaryDirectory() as directory:
            target = str(Path(directory) / "copy.als")
            with self.assertRaisesRegex(ValueError, "refusing adoption"):
                persistence.save_set_as(song, target, native_module=native,
                                        experimental=True)
        self.assertEqual(native.calls, [("copy", target)])
        self.assertEqual(song.file_path, "/tmp/original.als")

    def test_xml_declarations_refuse_before_adoption(self):
        song = _Song(None)
        native = self.make_native(song, b'<!DOCTYPE Ableton><Ableton><LiveSet/></Ableton>')
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "XML declarations"):
                persistence.save_set_as(song, str(Path(directory) / "copy.als"),
                                        native_module=native, experimental=True)
        self.assertEqual(len(native.calls), 1)

    def test_adoption_error_reports_partial_persistence_without_retry(self):
        song = _Song(None)
        native = self.make_native(song)
        def fail(path):
            native.calls.append(("adopt_failed", path))
            raise RuntimeError("private native failure")
        native.adopt_saved_copy = fail
        with tempfile.TemporaryDirectory() as directory:
            target = str(Path(directory) / "copy.als")
            with self.assertRaisesRegex(ValueError, "Set copy written.*do not retry"):
                persistence.save_set_as(song, target, native_module=native,
                                        experimental=True)
        self.assertEqual(native.calls, [("copy", target), ("adopt_failed", target)])

    def test_failed_path_readback_is_not_success(self):
        song = _Song("/tmp/original.als")
        native = self.make_native(song)
        native.adopt_saved_copy = lambda path: setattr(native, "dirty", False)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "failed path/dirty readback"):
                persistence.save_set_as(song, str(Path(directory) / "copy.als"),
                                        native_module=native, experimental=True)


if __name__ == "__main__":
    unittest.main()
