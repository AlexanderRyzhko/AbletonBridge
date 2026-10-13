import asyncio
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

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
        with gzip.open(params["path"], "wb") as stream:
            stream.write(b"<Ableton><LiveSet/></Ableton>")
        return {
            "backend": "live_native_document_serializer_and_bookkeeping",
            "path": params["path"],
            "save_requested": True,
            "ui_automation_used": False,
            "active_file_path": params["path"],
            "active_path_verified": True,
            "has_unsaved_changes": False,
        }


class SaveSetAsToolTests(unittest.TestCase):
    def test_named_save_requires_consent_before_connection(self):
        mcp = _FakeMCP()
        register_tools(mcp)
        with patch("MCP_Server.tools.session.get_ableton_connection") as connection:
            response = asyncio.run(mcp.tools["save_current_set"](None))
        self.assertIn("experimental=true", response)
        connection.assert_not_called()

    def test_named_save_checks_real_xml_and_clean_state(self):
        mcp = _FakeMCP()
        register_tools(mcp)
        connection = Mock()
        with tempfile.TemporaryDirectory(prefix="ABKB-3-named-tool-") as directory:
            target = str(Path(directory) / "named.als")
            with gzip.open(target, "wb") as stream:
                stream.write(b"<Ableton><LiveSet/></Ableton>")
            connection.send_command.return_value = {
                "file_path": target, "active_path_verified": True,
                "has_unsaved_changes": False,
            }
            with patch("MCP_Server.tools.session.get_ableton_connection", return_value=connection):
                response = asyncio.run(mcp.tools["save_current_set"](None, experimental=True))
        self.assertTrue(json.loads(response)["gzip_xml_verified"])
        connection.send_command.assert_called_once_with("save_current_set", {"experimental": True})

    def test_experimental_flag_required_before_connection(self):
        mcp = _FakeMCP()
        register_tools(mcp)
        with patch("MCP_Server.tools.session.get_ableton_connection") as connection:
            result = asyncio.run(mcp.tools["save_set_as"](None, "/tmp/unused.als"))
        self.assertIn("experimental=true", result)
        connection.assert_not_called()

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
                    mcp.tools["save_set_as"](None, target, overwrite=False, experimental=True)
                )

        result = json.loads(response)
        self.assertTrue(result["copy_file_verified"])
        self.assertTrue(result["gzip_xml_verified"])
        self.assertGreater(result["file_size"], 0)
        self.assertFalse(result["ui_automation_used"])
        self.assertEqual(
            connection.calls,
            [("save_set_as", {"path": target, "overwrite": False, "experimental": True})],
        )


if __name__ == "__main__":
    unittest.main()
