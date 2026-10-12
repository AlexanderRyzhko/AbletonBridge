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


class _OpeningConnection:
    def __init__(self, target):
        self.target = target
        self.calls = []

    def send_command(self, command, params):
        self.calls.append((command, params))
        if command == "get_song_file_path":
            return {"file_path": self.target, "document_id": "new-document"}
        return {
            "backend": "live_native_document_request",
            "path": params["path"],
            "open_requested": True,
            "ui_used": False,
            "current_set_action": "saved_named_set",
            "source_document_id": "old-document",
        }


class OpenSetToolTests(unittest.TestCase):
    def test_tool_verifies_active_path_without_ui(self):
        mcp = _FakeMCP()
        register_tools(mcp)

        with tempfile.TemporaryDirectory(prefix="ABKB-3-open-tool-") as directory:
            target = Path(directory) / "agent-set.als"
            target.write_bytes(b"existing Live Set")
            connection = _OpeningConnection(str(target))
            with patch(
                "MCP_Server.tools.session.get_ableton_connection",
                return_value=connection,
            ):
                response = asyncio.run(mcp.tools["open_set"](None, str(target)))

        result = json.loads(response)
        self.assertTrue(result["active_path_verified"])
        self.assertFalse(result["ui_used"])
        self.assertEqual(connection.calls[0][0], "open_set")
        self.assertEqual(connection.calls[1], ("get_song_file_path", {}))


if __name__ == "__main__":
    unittest.main()
