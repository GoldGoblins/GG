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
    if "http-live.sr.se" in src:
        raise AssertionError("dead SR host still in presets")
    if "live1.sr.se" not in src:
        raise AssertionError("live SR stream missing")
    if "track.play" not in host_src:
        raise AssertionError("cliamp track.play missing")
    if "set_eq_band" not in host_src or "set_eq_preset" not in host_src:
        raise AssertionError("eq control missing")
    if "EQ_PRESETS" not in src:
        raise AssertionError("eq presets missing")
    if "cliamp" not in src or "torlink" not in src:
        raise AssertionError("cliamp/torlink probe missing")
    if "RADIO_API" not in src or "IPTV_PLAYLISTS" not in src:
        raise AssertionError("live radio/tv catalogs missing")
    if "HOMEBREW_API" not in src or "hackrom" not in src:
        raise AssertionError("homebrew hub missing")
    if "materialize_homebrew" not in src or "materialize_homebrew" not in host_src:
        raise AssertionError("homebrew download path missing")
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
    if media_contract.format_clock(65) != "01:05":
        raise AssertionError("clock")
    spec = media_contract.normalize_spectrum([0, 5, 10, 2], 4)
    if spec[2] != 1.0 or spec[0] != 0.0:
        raise AssertionError("spectrum " + str(spec))
    stretched = media_contract.normalize_spectrum([1.0, 0.2], 5)
    if len(stretched) != 5 or stretched[0] != 1.0 or stretched[-1] != 0.2:
        raise AssertionError("log resample " + str(stretched))
    if stretched[2] == 0.0:
        raise AssertionError("hz padded with zeros " + str(stretched))
    if media_contract.SPECTRUM_BARS != 120:
        raise AssertionError("spectrum bar count")
    eq = media_contract.normalize_eq([3, -6], 10)
    if eq[0] != 3.0 or eq[1] != -6.0 or len(eq) != 10:
        raise AssertionError("eq " + str(eq))
    if '"cmd": "bands"' not in host_src and "'cmd': 'bands'" not in host_src:
        raise AssertionError("cliamp spectrum ipc missing")
    if "status_payload(live" not in host_src and "live: bool = False" not in host_src:
        raise AssertionError("live media status path missing")
    if "_CLIAMP_POLL_TIMEOUT" not in host_src or "_catalog_memo" not in host_src:
        raise AssertionError("media live poll still rebuilds catalog / blocks on ipc")
    if "start_live_pump" not in host_src or "live_status_json" not in host_src:
        raise AssertionError("cliamp live ipc still runs on the GUI thread")
    if "_live_pump_loop" not in host_src or "_cached_cliamp" not in host_src:
        raise AssertionError("gui live status still waits on the cliamp socket")
    if "--buffer-ms" not in host_src:
        raise AssertionError("cliamp radio buffer missing")
    if "_maybe_resume_stream" not in host_src or "_cliamp_buffered" not in host_src:
        raise AssertionError("radio stream watchdog / buffered daemon missing")
    if "_CLIAMP_RESUME_GAP" not in host_src:
        raise AssertionError("radio resume backoff missing")
    live = media_host.status_payload(live=True)
    if live.get("items") is not None:
        raise AssertionError("live status still ships the catalog")
    if live.get("live") is not True:
        raise AssertionError("live status marker missing " + json.dumps(live))
    if "library_roots" in live or "eq_presets" in live:
        raise AssertionError("live status still ships heavy fields")
    if not media_contract.which_first(("cliamp",)):
        raise AssertionError("cliamp binary missing")
    if not media_contract.which_first(("mednafen",)):
        raise AssertionError("mednafen binary missing")
    if not media_contract.which_first(("mupen64plus",)):
        raise AssertionError("mupen64plus binary missing")
    hacked = media_contract.homebrew_entry_item(
        {
            "typetag": "hackrom",
            "platform": "GB",
            "slug": "mario-hack",
            "title": "hack",
            "files": [{"playable": True, "filename": "hack.gb", "default": True}],
        }
    )
    if hacked is not None:
        raise AssertionError("hackrom leaked into game catalog")
    hb = media_contract.homebrew_entry_item(
        {
            "typetag": "game",
            "platform": "GB",
            "slug": "2048gb",
            "title": "2048gb",
            "files": [{"playable": True, "filename": "2048.gb", "default": True}],
        }
    )
    if not hb or hb["system"] != "gb" or hb["media"] != "homebrew":
        raise AssertionError("homebrew entry " + json.dumps(hb))
    if "raw.githubusercontent.com/gbdev/database" not in str(hb["source"]):
        raise AssertionError("homebrew url " + str(hb["source"]))
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
    if "function refreshLive(" not in qml or "catalogItems" not in qml:
        raise AssertionError("media catalog is rebuilt on every live poll")
    if "mediaLiveStatus" not in qml:
        raise AssertionError("media pane does not use live status")
    if "qmlVideo ? 250" in qml:
        raise AssertionError("qml video still live-polls at 250ms")
    if "playbackState" not in qml:
        raise AssertionError("MediaPlayer play() retriggered while already playing")
    if "onMediaStateChanged" not in qml:
        raise AssertionError("media pane still polls instead of following mediaStateChanged")
    if 'leftLegend: "MEDIA"' in qml:
        raise AssertionError("media pane still nests a MEDIA GgFrame inside the workspace frame")
    utility = (PROJECT / "qml" / "components" / "UtilitySurface.qml").read_text(
        encoding="utf-8"
    )
    if "mediaLiveStatus" not in utility:
        raise AssertionError("utility strip still polls full media catalog")
    if "liveMeters" not in utility:
        raise AssertionError("utility strip still paints spectrum during TV")
    if "playing ? 220" in utility:
        raise AssertionError("utility strip still 220ms-polls any playing backend")
    if "running: root.liveMeters" not in utility:
        raise AssertionError("utility strip still polls while idle")
    if "function applyChrome(" not in utility:
        raise AssertionError("utility strip cannot follow RADIO play from the workspace")
    if "running: !root.liveMeters" not in utility:
        raise AssertionError("utility strip never resyncs mode after a missed mediaStateChanged")
    if "function refreshMeters(" not in utility:
        raise AssertionError("meter paint still rewrites chrome statusJson")
    if "interval: 33" in utility:
        raise AssertionError("utility meters still fight the GUI thread at 33ms")
    if "interval: 125" in utility:
        raise AssertionError("spectrum meters still lag at 125ms")
    if "spectrumSegs: 18" not in utility:
        raise AssertionError("spectrum lost the stacked LED dots")
    if "for (s = 0; s < segs; s++)" not in utility:
        raise AssertionError("spectrum paints solid bars instead of LED dots")
    if "root.ledColor(level)" in utility:
        raise AssertionError("spectrum recolors whole bars instead of per-LED height")
    if "playing ? 1" in utility:
        raise AssertionError("live streams still paint a full gold progress bar")
    if 'objectName: "utilityTimeline"' not in utility:
        raise AssertionError("utility timeline missing")
    if "function seekAt(" not in utility:
        raise AssertionError("timeline is not seekable")
    if 'backend || "") === "cliamp" && root.playing' in utility:
        raise AssertionError("spectrum/timeline still gated on cliamp only")
    play_src = (PROJECT / "backend" / "chat_surface_host.py").read_text(
        encoding="utf-8"
    )
    if "def mediaLiveStatus" not in play_src:
        raise AssertionError("mediaLiveStatus slot missing")
    if "mediaStateChanged" not in play_src:
        raise AssertionError("mediaStateChanged signal missing")
    if "def mediaSeek" not in play_src or "def mediaReportClock" not in play_src:
        raise AssertionError("qml clock/seek slots missing")
    if "def seek(" not in host_src or "def report_clock(" not in host_src:
        raise AssertionError("media host seek/clock missing")
    if "_CLIAMP_BUFFER_MS = 750" in host_src:
        raise AssertionError("cliamp stream buffer still 750ms")
    if "_CLIAMP_BUFFER_MS = 3000" in host_src:
        raise AssertionError("cliamp stream buffer still 3000ms")
    if "_LIVE_TTL" not in host_src:
        raise AssertionError("cliamp live status still uncached")
    if "def publish_live" not in host_src:
        raise AssertionError("play/mode still does not publish live meter JSON")
    if "media_host.publish_live" not in play_src:
        raise AssertionError("mediaStateChanged still fires before live JSON exists")
    embed_src = (PROJECT / "backend" / "media_embed.py").read_text(encoding="utf-8")
    if "self._geo" not in embed_src:
        raise AssertionError("media embed resizes the foreign window every tick")
    if "cached_quick_item" not in embed_src:
        raise AssertionError("media embed still findChild on every geometry tick")
    if "_PTY_READ_BUDGET" not in play_src or "def _drain_pty" not in play_src:
        raise AssertionError("PTY drain coalesce missing")
    if 'objectName: "workspaceMediaHole"' not in qml:
        raise AssertionError("workspace display hole missing")
    if "showDisplay" not in qml:
        raise AssertionError("workspace screen pane missing")
    if "import QtMultimedia" not in qml:
        raise AssertionError("QtMultimedia missing from screen")
    if 'objectName: "workspaceMediaVideo"' not in qml:
        raise AssertionError("in-hole VideoOutput missing")
    if 'objectName: "workspaceMediaFrame"' not in qml:
        raise AssertionError("in-hole console frame missing")
    if "_play_qml" not in host_src or '_backend = "qml"' not in host_src:
        raise AssertionError("in-process TV player missing")
    if "_play_libretro" not in host_src:
        raise AssertionError("in-process console missing")
    if "--drawable-xid" not in host_src:
        raise AssertionError("VLC workspace drawable missing")
    play_fn = play_src[
        play_src.index("def mediaPlay") : play_src.index("def mediaPause")
    ]
    if "holder_xid" in play_fn:
        raise AssertionError("TV play still opens an extra X11 holder window")
    media_host._extra_items = [
        {
            "id": "tv:qml-test",
            "kind": "TV",
            "title": "QML TV",
            "source": "https://example.com/live.ts",
            "media": "stream",
            "system": "",
            "player": "qml",
        }
    ]
    tv = media_host.play_item("tv:qml-test")
    if tv.get("backend") != "qml":
        raise AssertionError("tv backend " + json.dumps(tv))
    if tv.get("now", {}).get("source") != "https://example.com/live.ts":
        raise AssertionError("tv source " + json.dumps(tv))
    if media_host.player_pid() != 0 or media_host._proc is not None:
        raise AssertionError("tv spawned an extra player process")
    paused = media_host.pause()
    if paused.get("paused") is not True:
        raise AssertionError("qml pause " + json.dumps(paused))
    stopped = media_host.stop()
    if stopped.get("backend") == "qml" or stopped.get("playing"):
        raise AssertionError("qml stop " + json.dumps(stopped))
    from backend import libretro_host
    if libretro_host.core_path("gb") is None:
        raise AssertionError("gambatte core missing")
    gb_src = Path("/home/GG/ROMs/gb/2048.gb")
    if gb_src.is_file():
        gb_dir = tmp / "ROMs" / "gb"
        gb_dir.mkdir(parents=True, exist_ok=True)
        local_gb = gb_dir / "2048.gb"
        local_gb.write_bytes(gb_src.read_bytes())
        media_host._extra_items = [
            {
                "id": "game:2048",
                "kind": "GAME",
                "title": "2048gb",
                "source": str(local_gb),
                "media": "rom",
                "system": "gb",
                "system_label": "GAME BOY",
            }
        ]
        game = media_host.play_item("game:2048")
        if game.get("backend") != "libretro":
            raise AssertionError("game backend " + json.dumps(game))
        if media_host._proc is not None:
            raise AssertionError("game spawned an extra emulator window")
        libretro_host.run()
        frame, width, height, pitch, fmt = libretro_host.frame()
        if width < 160 or height < 144 or len(frame) < 1000:
            raise AssertionError("console frame " + str((width, height, len(frame))))
        media_host.stop()
        if libretro_host.loaded():
            raise AssertionError("libretro still loaded after stop")
    media_host._extra_items = []
    if "torlnk" not in host_src or "9160" not in host_src:
        raise AssertionError("torlink files stream missing")
    argv = media_host.fetch_argv()
    if "konsole" not in argv[0] or "-e" not in argv or "--hide-menubar" not in argv:
        raise AssertionError("torlink TUI must launch inside konsole " + json.dumps(argv))
    if media_contract.FETCH_TUI_TITLE not in " ".join(argv):
        raise AssertionError("torlink konsole title missing " + json.dumps(argv))
    if "--separate" in argv:
        raise AssertionError("torlink konsole must match grok TUI argv, not --separate")
    if argv[-1].rstrip("/").split("/")[-1] not in ("torlnk", "torlink"):
        raise AssertionError("konsole -e target " + json.dumps(argv))
    if any(part in ("/bin/sh", "bash") for part in argv):
        raise AssertionError("shell in fetch argv")
    embed_src = (PROJECT / "backend" / "torlink_embed.py").read_text(encoding="utf-8")
    if "konsole_xids" not in embed_src or "workspaceMediaHole" not in embed_src:
        raise AssertionError("torlink embed is not the grok TUI hole pattern")
    if "DEVNULL" in embed_src:
        raise AssertionError("torlink TUI stdout discarded")
    if "TorlinkEmbed" not in play_src or "def _torlink_embedder" not in play_src:
        raise AssertionError("FETCH does not own a Konsole embedder")
    grok_embed = (PROJECT / "backend" / "grok_tui_embed.py").read_text(encoding="utf-8")
    if "def drop_qt_wrap" not in grok_embed or "Shiboken.delete" not in grok_embed:
        raise AssertionError("foreign window wrappers are not dropped before Qt teardown")
    if "release_embed_windows" not in embed_src:
        raise AssertionError("torlink embed does not drop foreign Qt wrappers on stop")
    fetch_dir = tmp / "Downloads" / "torlink"
    fetch_dir.mkdir(parents=True)
    (fetch_dir / "clip.mp4").write_bytes(b"0" * 32)
    (fetch_dir / "tune.mp3").write_bytes(b"ID3")
    (fetch_dir / "notes.txt").write_text("nope", encoding="utf-8")
    media_contract.FETCH_DIR = fetch_dir
    fetched = media_contract.fetch_catalog()
    titles = {row["title"] for row in fetched}
    if "clip" not in titles or "tune" not in titles or "notes" in titles:
        raise AssertionError("fetch catalog " + json.dumps(fetched))
    if any(row["kind"] != "FETCH" for row in fetched):
        raise AssertionError("fetch kind " + json.dumps(fetched))
    payload = media_host.set_mode("FETCH")
    if payload["mode"] != "FETCH":
        raise AssertionError("fetch mode " + json.dumps(payload))
    names = {row["title"] for row in payload.get("items") or []}
    if "clip" not in names:
        raise AssertionError("fetch status items " + json.dumps(payload.get("items")))
    qml = (PROJECT / "qml" / "components" / "MediaSurface.qml").read_text(
        encoding="utf-8"
    )
    if "OPEN TORLINK" not in qml or "REATTACH TORLINK" not in qml:
        raise AssertionError("FETCH open control missing")
    if "search finished downloads" not in qml:
        raise AssertionError("FETCH file search missing")
    collapsed = qml[qml.index("listCollapsed:") : qml.index("function refresh(")]
    if "FETCH" in collapsed:
        raise AssertionError("FETCH still collapses the finished-file list")
    if "duckstation" not in src or "pcsx2" not in src or "xemu" not in src:
        raise AssertionError("old-console bins missing")
    print("MEDIA_CONTRACT_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
