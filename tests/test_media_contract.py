#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from backend import media_contract, media_host
from backend.surface_intent import parse_surface_intent


def main() -> int:
    src = (PROJECT / "backend" / "media_contract.py").read_text(encoding="utf-8")
    host_src = (PROJECT / "backend" / "media_host.py").read_text(encoding="utf-8")
    if "ps3" not in src or "ps4" not in src:
        raise AssertionError("denied new consoles missing")
    if "RADIO_PRESETS" not in src:
        raise AssertionError("radio presets missing")
    if "cliamp" not in src or "torlink" not in src:
        raise AssertionError("cliamp/torlink probe missing")
    if "RADIO_API" not in src or "IPTV_PLAYLISTS" not in src:
        raise AssertionError("live radio/tv catalogs missing")
    if "/bin/sh" in host_src or "bash -c" in host_src:
        raise AssertionError("generic shell in media host")
    if "magnet:" in src:
        raise AssertionError("magnet catalog is not a local media source")
    tmp = Path(tempfile.mkdtemp(prefix="gg-media-"))
    media_contract.STATE_DIR = tmp
    media_host.STATE_DIR = tmp
    music = tmp / "Musik"
    roms = tmp / "ROMs" / "snes"
    denied = tmp / "ROMs" / "ps3"
    music.mkdir(parents=True)
    roms.mkdir(parents=True)
    denied.mkdir(parents=True)
    (music / "track one.mp3").write_bytes(b"ID3")
    (roms / "adventure.sfc").write_bytes(b"ROM")
    (denied / "forbidden.iso").write_bytes(b"ISO")
    media_contract.LIBRARY_DIRS = (music, tmp / "ROMs")
    try:
        media_contract.stream_allowed("magnet:xyz")
        raise AssertionError("magnet allowed")
    except ValueError:
        pass
    url = media_contract.stream_allowed("https://http-live.sr.se/p1-mp3-192")
    if not url.startswith("https://"):
        raise AssertionError("radio stream")
    songs = media_contract.music_catalog()
    if not songs or songs[0]["kind"] != "MUSIC":
        raise AssertionError("music catalog " + json.dumps(songs))
    games = media_contract.game_catalog()
    if not any(row["system"] == "snes" for row in games):
        raise AssertionError("snes rom missing")
    if any("forbidden" in row["source"] for row in games):
        raise AssertionError("ps3 rom leaked")
    if media_contract.system_for(denied / "forbidden.iso"):
        raise AssertionError("denied system classified")
    if media_contract.system_for(music / "movie.iso"):
        raise AssertionError("bare iso classified as a console")
    playlist = tmp / "radio.m3u"
    playlist.write_text(
        "#EXTM3U\n#EXTINF:-1,Test FM\nhttps://example.com/live.mp3\nmagnet:nope\n",
        encoding="utf-8",
    )
    parsed = media_contract.parse_m3u(playlist, "RADIO")
    if len(parsed) != 1 or parsed[0]["title"] != "Test FM":
        raise AssertionError("m3u " + json.dumps(parsed))
    prefs = media_contract.save_prefs({"mode": "RADIO", "volume": 40})
    if prefs["mode"] != "RADIO" or prefs["volume"] != 40:
        raise AssertionError("prefs")
    payload = media_host.set_mode("GAME")
    if payload["mode"] != "GAME" or payload["schema"] != media_contract.SCHEMA:
        raise AssertionError("status schema")
    tools = media_contract.probe_tools()
    if "vlc" not in tools or "cliamp" not in tools:
        raise AssertionError("tool probe")
    if parse_surface_intent("musik") != "MEDIA":
        raise AssertionError("musik intent")
    if parse_surface_intent("öppna radion") != "MEDIA":
        raise AssertionError("radio intent")
    if parse_surface_intent("öppna emulatorn") != "MEDIA":
        raise AssertionError("emulator intent")
    if parse_surface_intent("tv") != "MEDIA":
        raise AssertionError("tv intent")
    if not media_contract.which_first(("cliamp",)):
        raise AssertionError("cliamp binary missing")
    if not media_contract.which_first(("torlnk", "torlink")):
        raise AssertionError("torlnk binary missing")
    if not media_contract.which_first(("yt-dlp",)):
        raise AssertionError("yt-dlp binary missing")
    if not media_contract.looks_like_url("https://live1.sr.se/p3-mp3-96"):
        raise AssertionError("stream url")
    direct = media_contract.query_item("RADIO", "https://live1.sr.se/p3-mp3-96")
    if not direct or direct["player"] != "cliamp":
        raise AssertionError("radio url item")
    host_src = (PROJECT / "backend" / "media_host.py").read_text(encoding="utf-8")
    if '"url.load"' not in host_src or '"queue.play"' not in host_src:
        raise AssertionError("cliamp IPC play path missing")
    qml = (PROJECT / "qml" / "components" / "MediaSurface.qml").read_text(
        encoding="utf-8"
    )
    if 'objectName: "workspaceMediaHole"' not in qml:
        raise AssertionError("workspace display hole missing")
    if "showDisplay" not in qml:
        raise AssertionError("workspace screen pane missing")
    if "--drawable-xid" not in host_src:
        raise AssertionError("VLC workspace drawable missing")
    if "torlnk" not in host_src or "9160" not in host_src:
        raise AssertionError("torlink files stream missing")
    if "duckstation" not in src or "pcsx2" not in src or "xemu" not in src:
        raise AssertionError("old-console bins missing")
    print("MEDIA_CONTRACT_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
