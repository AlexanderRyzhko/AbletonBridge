import asyncio
import json
import importlib.util
import pathlib
import sys
import types
from unittest.mock import MagicMock

import pytest

from MCP_Server.tools.clips import register_tools


class _FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func
        return decorator


def _load_clip_handlers():
    handlers_dir = pathlib.Path(__file__).resolve().parents[1] / "AbletonBridge_Remote_Script" / "handlers"
    package_name = "_test_remote_handlers"
    package = types.ModuleType(package_name)
    package.__path__ = [str(handlers_dir)]
    sys.modules[package_name] = package

    helpers_spec = importlib.util.spec_from_file_location(
        package_name + "._helpers",
        handlers_dir / "_helpers.py",
    )
    helpers_module = importlib.util.module_from_spec(helpers_spec)
    sys.modules[helpers_spec.name] = helpers_module
    helpers_spec.loader.exec_module(helpers_module)

    clips_spec = importlib.util.spec_from_file_location(
        package_name + ".clips",
        handlers_dir / "clips.py",
    )
    clips_module = importlib.util.module_from_spec(clips_spec)
    sys.modules[clips_spec.name] = clips_module
    clips_spec.loader.exec_module(clips_module)
    return clips_module


def test_create_session_audio_clip_handler_calls_clip_slot():
    clip_handlers = _load_clip_handlers()

    class FakeClipSlot:
        def __init__(self):
            self.has_clip = False
            self.clip = None
            self.called_with = None

        def create_audio_clip(self, file_path):
            self.called_with = file_path
            self.has_clip = True
            self.clip = type("Clip", (), {"name": "Imported clip"})()

    slot = FakeClipSlot()

    track = MagicMock()
    track.has_audio_input = True
    track.clip_slots = [slot]

    song = MagicMock()
    song.tracks = [track]

    result = clip_handlers.create_session_audio_clip(song, 0, 0, "/tmp/example.wav")

    assert slot.called_with == "/tmp/example.wav"
    assert result["created"] is True
    assert result["clip_name"] == "Imported clip"


def test_create_session_audio_clip_handler_requires_absolute_path():
    clip_handlers = _load_clip_handlers()
    slot = MagicMock()
    slot.has_clip = False
    track = MagicMock()
    track.has_audio_input = True
    track.clip_slots = [slot]
    song = MagicMock()
    song.tracks = [track]

    with pytest.raises(ValueError, match="absolute path"):
        clip_handlers.create_session_audio_clip(song, 0, 0, "relative.wav")


def test_create_session_audio_clip_tool_dispatches_command(patch_ableton):
    mcp = _FakeMCP()
    register_tools(mcp)

    result = asyncio.run(mcp.tools["create_session_audio_clip"](None, 2, 3, "/tmp/sample.wav"))
    parsed = json.loads(result)

    assert parsed["status"] == "ok"
    patch_ableton.send_command.assert_called_once_with("create_session_audio_clip", {
        "track_index": 2,
        "clip_index": 3,
        "file_path": "/tmp/sample.wav",
    })
