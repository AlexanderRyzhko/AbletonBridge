import asyncio
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from MCP_Server.tools.session import register_tools


class _MCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(function):
            self.tools[function.__name__] = function
            return function
        return register


class _Connection:
    def __init__(self, payload=b"<Ableton><LiveSet/></Ableton>", unchanged=True):
        self.calls = []
        self.payload = payload
        self.unchanged = unchanged

    def send_command(self, command, params):
        self.calls.append((command, params))
        with gzip.open(params["path"], "wb") as stream:
            stream.write(self.payload)
        return {"copy_requested": True, "active_path_unchanged": self.unchanged}


class SaveCopyToolTests(unittest.TestCase):
    def setUp(self):
        mcp = _MCP()
        register_tools(mcp)
        self.tool = mcp.tools["save_set_copy"]

    def test_experimental_flag_required_before_connection(self):
        with patch("MCP_Server.tools.session.get_ableton_connection") as connection:
            result = asyncio.run(self.tool(None, "/tmp/unused-copy.als"))
        self.assertIn("experimental=true", result)
        connection.assert_not_called()

    def test_valid_copy_checks_payload_and_path_preservation(self):
        connection = _Connection()
        with tempfile.TemporaryDirectory() as directory:
            target = str(Path(directory) / "copy.als")
            with patch("MCP_Server.tools.session.get_ableton_connection", return_value=connection):
                result = json.loads(asyncio.run(self.tool(None, target, experimental=True)))
        self.assertTrue(result["copy_file_verified"])
        self.assertTrue(result["gzip_xml_verified"])
        self.assertEqual(connection.calls, [("save_set_copy", {
            "path": target, "overwrite": False, "experimental": True,
        })])

    def test_non_set_xml_is_not_promoted(self):
        connection = _Connection(payload=b"<unrelated/>")
        with tempfile.TemporaryDirectory() as directory:
            target = str(Path(directory) / "copy.als")
            with patch("MCP_Server.tools.session.get_ableton_connection", return_value=connection):
                result = asyncio.run(self.tool(None, target, experimental=True))
        self.assertIn("lacks Ableton/LiveSet", result)

    def test_missing_path_readback_is_not_promoted(self):
        connection = _Connection(unchanged=False)
        with tempfile.TemporaryDirectory() as directory:
            target = str(Path(directory) / "copy.als")
            with patch("MCP_Server.tools.session.get_ableton_connection", return_value=connection):
                result = asyncio.run(self.tool(None, target, experimental=True))
        self.assertIn("unchanged active path", result)


class DocumentStateToolTests(unittest.TestCase):
    def setUp(self):
        mcp = _MCP()
        register_tools(mcp)
        self.tool = mcp.tools["get_document_persistence_state"]

    def test_state_read_sends_no_mutation(self):
        connection = Mock()
        connection.send_command.return_value = {"has_unsaved_changes": True}
        with patch("MCP_Server.tools.session.get_ableton_connection", return_value=connection):
            result = json.loads(asyncio.run(self.tool(None)))
        self.assertTrue(result["has_unsaved_changes"])
        connection.send_command.assert_called_once_with("get_document_persistence_state", {})

    def test_unknown_dirty_state_is_not_treated_as_clean(self):
        connection = Mock()
        connection.send_command.return_value = {}
        with patch("MCP_Server.tools.session.get_ableton_connection", return_value=connection):
            result = asyncio.run(self.tool(None))
        self.assertIn("dirty state was not verified", result)


if __name__ == "__main__":
    unittest.main()
