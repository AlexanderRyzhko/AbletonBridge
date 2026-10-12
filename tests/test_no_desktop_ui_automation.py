import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = [ROOT / "AbletonBridge_Remote_Script", ROOT / "MCP_Server"]
FORBIDDEN = (
    "osascript",
    "pyautogui",
    "cliclick",
    "system events",
    "cgevent",
    "activateignoringotherapps",
    "nsworkspace",
)


class NoDesktopUiAutomationTests(unittest.TestCase):
    def test_runtime_contains_no_desktop_ui_automation(self):
        violations = []
        for runtime_root in RUNTIME_ROOTS:
            for source in runtime_root.rglob("*"):
                if source.suffix.lower() not in (".py", ".js"):
                    continue
                text = source.read_text(encoding="utf-8").lower()
                for token in FORBIDDEN:
                    if token in text:
                        violations.append("{0}: {1}".format(source, token))
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
