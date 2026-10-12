import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from MCP_Server.tools.session import register_tools


class _FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(function):
            self.tools[function.__name__] = function
            return function

        return decorator


class _SavingConnection:
    def __init__(self):
        self.calls = []

    def send_command(self, command, params):
        self.calls.append((command, params))
        Path(params["path"]).write_bytes(b"saved Live Set")
        return {
            "backend": "live_native_lfile",
            "path": params["path"],
            "save_requested": True,
            "ui_used": False,
        }


class SaveSetAsToolTests(unittest.TestCase):
    def test_tool_waits_for_changed_nonempty_file(self):
        mcp = _FakeMCP()
        register_tools(mcp)
        connection = _SavingConnection()

        with tempfile.TemporaryDirectory(prefix="ABKB-3-save-tool-") as directory:
            target = str(Path(directory) / "agent-set.als")
            with patch(
                "MCP_Server.tools.session.get_ableton_connection",
                return_value=connection,
            ):
                response = asyncio.run(
                    mcp.tools["save_set_as"](None, target, overwrite=False)
                )

        result = json.loads(response)
        self.assertTrue(result["durable_file_verified"])
        self.assertGreater(result["file_size"], 0)
        self.assertFalse(result["ui_used"])
        self.assertEqual(
            connection.calls,
            [("save_set_as", {"path": target, "overwrite": False})],
        )


if __name__ == "__main__":
    unittest.main()
