import asyncio
import json
import unittest
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


class _NewSetConnection:
    def __init__(self):
        self.calls = []

    def send_command(self, command, params):
        self.calls.append((command, params))
        if command == "get_song_file_path":
            return {"file_path": None}
        return {
            "backend": "live_native_document_new",
            "new_requested": True,
            "ui_used": False,
            "current_set_action": "saved_named_set",
        }


class NewSetToolTests(unittest.TestCase):
    def test_tool_verifies_untitled_state_without_ui(self):
        mcp = _FakeMCP()
        register_tools(mcp)
        connection = _NewSetConnection()

        with patch(
            "MCP_Server.tools.session.get_ableton_connection",
            return_value=connection,
        ):
            response = asyncio.run(mcp.tools["new_set"](None))

        result = json.loads(response)
        self.assertTrue(result["untitled_state_verified"])
        self.assertFalse(result["ui_used"])
        self.assertEqual(connection.calls[0][0], "new_set")
        self.assertEqual(connection.calls[1], ("get_song_file_path", {}))


if __name__ == "__main__":
    unittest.main()
