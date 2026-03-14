#!/usr/bin/env python3
"""Safely import an audio file into a Session View clip slot on a named track.

This helper avoids touching unrelated tracks:
- it finds a target track by exact name match
- if no exact match exists, it creates one new audio track and renames it
- it refuses to proceed if multiple tracks share the same target name
- it refuses to overwrite an occupied clip slot
"""

from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path


HOST = "127.0.0.1"
PORT = 9877


def send_command(command_type: str, params: dict | None = None, timeout: float = 20.0) -> dict:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect((HOST, PORT))
    payload = json.dumps({"type": command_type, "params": params or {}}) + "\n"
    sock.sendall(payload.encode("utf-8"))
    data = b""
    while b"\n" not in data:
        chunk = sock.recv(65536)
        if not chunk:
            break
        data += chunk
    sock.close()
    if not data:
        raise RuntimeError(f"No response for command {command_type}")
    response = json.loads(data.decode("utf-8").strip())
    if response.get("status") != "success":
        raise RuntimeError(response.get("message", f"{command_type} failed"))
    return response["result"]


def get_tracks() -> list[dict]:
    return send_command("get_all_tracks_info").get("tracks", [])


def find_track_by_name(tracks: list[dict], track_name: str) -> dict | None:
    matches = [track for track in tracks if track.get("name") == track_name]
    if len(matches) > 1:
        raise RuntimeError(
            f"Refusing to continue because {len(matches)} tracks share the exact name {track_name!r}"
        )
    return matches[0] if matches else None


def ensure_named_audio_track(track_name: str) -> dict:
    tracks = get_tracks()
    existing = find_track_by_name(tracks, track_name)
    if existing:
        if not existing.get("is_audio"):
            raise RuntimeError(f"Track {track_name!r} exists but is not an audio track")
        return existing

    created = send_command("create_audio_track", {"index": -1})
    send_command("set_track_name", {"track_index": created["index"], "name": track_name})

    refreshed = get_tracks()
    created_track = find_track_by_name(refreshed, track_name)
    if not created_track:
        raise RuntimeError(f"Created track {track_name!r} but could not resolve it afterward")
    if not created_track.get("is_audio"):
        raise RuntimeError(f"Created track {track_name!r} is not an audio track")
    return created_track


def ensure_empty_slot(track_index: int, clip_index: int) -> None:
    track = send_command("get_track_info", {"track_index": track_index})
    clip_slots = track.get("clip_slots", [])
    if clip_index < 0 or clip_index >= len(clip_slots):
        raise RuntimeError(
            f"Clip slot {clip_index} is out of range for track {track.get('name', track_index)!r}"
        )
    if clip_slots[clip_index].get("has_clip"):
        raise RuntimeError(
            f"Clip slot {clip_index} on track {track.get('name', track_index)!r} already has a clip"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--track-name", required=True, help="Exact track name to match or create")
    parser.add_argument("--file-path", required=True, help="Absolute path to the source audio file")
    parser.add_argument("--clip-index", type=int, default=0, help="Session clip slot index")
    args = parser.parse_args()

    file_path = Path(args.file_path).expanduser().resolve()
    if not file_path.is_file():
        raise SystemExit(f"Audio file not found: {file_path}")

    target_track = ensure_named_audio_track(args.track_name)
    ensure_empty_slot(target_track["index"], args.clip_index)
    result = send_command(
        "create_session_audio_clip",
        {
            "track_index": target_track["index"],
            "clip_index": args.clip_index,
            "file_path": str(file_path),
        },
        timeout=30.0,
    )

    print(
        json.dumps(
            {
                "track_index": target_track["index"],
                "track_name": args.track_name,
                "clip_index": args.clip_index,
                "file_path": str(file_path),
                "result": result,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
