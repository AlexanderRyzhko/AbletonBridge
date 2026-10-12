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


if __name__ == "__main__":
    unittest.main()
