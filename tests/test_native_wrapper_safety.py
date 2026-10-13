"""Test fixed refusal without loading a macOS library outside Live."""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock


WRAPPER = Path(__file__).parents[1] / "AbletonBridge_Remote_Script" / "_ableton_native_save.py"


class NativeWrapperSafetyTests(unittest.TestCase):
    def test_document_exchange_refuses_before_native_call(self):
        tree = ast.parse(WRAPPER.read_text())
        for name, kwargs in (("open_set", {"path": "/tmp/unused.als", "replace_confirmed": True}),
                             ("new_set", {"replace_confirmed": True})):
            with self.subTest(name=name):
                function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == name)
                module = ast.Module(body=[function], type_ignores=[])
                library = Mock()
                scope = {"_lib": library}
                exec(compile(module, str(WRAPPER), "exec"), scope)
                with self.assertRaisesRegex(ValueError, "document exchange changes cursor state"):
                    scope[name](**kwargs)
                self.assertEqual(library.mock_calls, [])

    def test_legacy_save_as_never_enters_native_view_route(self):
        tree = ast.parse(WRAPPER.read_text())
        function = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef) and node.name == "save_as")
        module = ast.Module(body=[function], type_ignores=[])
        library = Mock()
        scope = {"_lib": library}
        exec(compile(module, str(WRAPPER), "exec"), scope)
        with self.assertRaisesRegex(ValueError, "observed cursor effects"):
            scope["save_as"]("/tmp/unused.als", overwrite=True)
        self.assertEqual(library.mock_calls, [])


if __name__ == "__main__":
    unittest.main()
