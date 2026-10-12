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


class _Bridge:
    __module__ = "Live.Licensing"

    def __init__(self):
        self.calls = 0

    def save_current_set(self):
        self.calls += 1


class _Owner:
    __module__ = "abl.live.licensing"

    def __init__(self, bridge):
        self.licensing_bridge = bridge


_Owner.__name__ = "PythonLicensing"


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

    def prepare(self):
        return {"supported": True, "ui_used": False}


class PersistenceTests(unittest.TestCase):
    def test_save_current_set_uses_existing_bridge_without_ui(self):
        bridge = _Bridge()

        result = persistence.save_current_set(
            _Song("/tmp/ABKB-3/disposable.als"),
            objects=[_Owner(bridge)],
        )

        self.assertEqual(bridge.calls, 1)
        self.assertEqual(
            result,
            {
                "backend": "live_owned_python_licensing",
                "file_path": "/tmp/ABKB-3/disposable.als",
                "save_requested": True,
                "ui_used": False,
            },
        )

    def test_save_current_set_refuses_untitled_before_resolving_bridge(self):
        bridge = _Bridge()

        with self.assertRaisesRegex(ValueError, "Untitled"):
            persistence.save_current_set(_Song(None), objects=[_Owner(bridge)])

        self.assertEqual(bridge.calls, 0)

    def test_save_current_set_requires_exactly_one_live_owned_owner(self):
        with self.assertRaisesRegex(RuntimeError, "found 0"):
            persistence.save_current_set(
                _Song("/tmp/ABKB-3/disposable.als"),
                objects=[],
            )

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
        bridge = _Bridge()
        native = _NativeSave()

        result = persistence.open_set(
            _Song("/tmp/ABKB-3/current.als"),
            "/tmp/ABKB-3/next.als",
            native_module=native,
            objects=[_Owner(bridge)],
        )

        self.assertEqual(bridge.calls, 1)
        self.assertEqual(
            native.calls, [("open_set", "/tmp/ABKB-3/next.als", True)]
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


if __name__ == "__main__":
    unittest.main()
