import importlib.util
import sys
import types
import unittest
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


class _NativeSave:
    def __init__(self):
        self.calls = []

    def save_as(self, path, overwrite=False):
        self.calls.append((path, overwrite))
        return {
            "backend": "live_native_lfile",
            "path": path,
            "save_requested": True,
            "ui_used": False,
        }

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

    def test_save_current_set_uses_explicit_path_without_licensing_menu(self):
        native = _NativeSave()

        result = persistence.save_current_set(
            _Song("/tmp/ABKB-3/disposable.als"),
            native_module=native,
        )

        self.assertEqual(native.calls, [("/tmp/ABKB-3/disposable.als", True)])
        self.assertEqual(
            result,
            {
                "backend": "live_native_lfile",
                "path": "/tmp/ABKB-3/disposable.als",
                "file_path": "/tmp/ABKB-3/disposable.als",
                "save_requested": True,
                "ui_used": False,
            },
        )

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

    def test_save_set_as_uses_native_adapter_without_ui(self):
        native = _NativeSave()

        result = persistence.save_set_as(
            _Song(None),
            "/tmp/ABKB-3/disposable.als",
            overwrite=True,
            native_module=native,
        )

        self.assertEqual(native.calls, [("/tmp/ABKB-3/disposable.als", True)])
        self.assertEqual(result["backend"], "live_native_lfile")
        self.assertFalse(result["ui_used"])

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

    def test_open_set_saves_named_current_set_before_native_request(self):
        native = _NativeSave()

        result = persistence.open_set(
            _Song("/tmp/ABKB-3/current.als"),
            "/tmp/ABKB-3/next.als",
            native_module=native,
        )

        self.assertEqual(
            native.calls, [("/tmp/ABKB-3/current.als", True),
                           ("open_set", "/tmp/ABKB-3/next.als", True)]
        )
        self.assertEqual(result["current_set_action"], "saved_named_set")
        self.assertFalse(result["ui_used"])

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

    def test_new_set_saves_named_current_set_before_native_request(self):
        native = _NativeSave()
        song = _Song("/tmp/ABKB-3/current.als")

        result = persistence.new_set(
            song,
            native_module=native,
        )

        self.assertEqual(native.calls, [("/tmp/ABKB-3/current.als", True), ("new_set", True)])
        self.assertEqual(result["current_set_action"], "saved_named_set")
        self.assertFalse(result["ui_used"])

    def test_new_set_refuses_untitled_without_explicit_policy(self):
        native = _NativeSave()

        with self.assertRaisesRegex(ValueError, "Untitled"):
            persistence.new_set(_Song(None), native_module=native)

        self.assertEqual(native.calls, [])


if __name__ == "__main__":
    unittest.main()
