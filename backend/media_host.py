from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from backend.media_contract import (
    MODES,
    SCHEMA,
    STATE_DIR,
    SYSTEMS,
    VIDEO_EXT,
    catalog_for,
    confined,
    ensure_state_dir,
    library_roots,
    load_prefs,
    looks_like_url,
    player_bin,
    probe_tools,
    save_prefs,
    search_items,
    stream_allowed,
    which_first,
)


_proc: subprocess.Popen[bytes] | None = None
_cliamp_proc: subprocess.Popen[bytes] | None = None
_files_proc: subprocess.Popen[bytes] | None = None
_kind = "audio"
_item: dict[str, Any] | None = None
_paused = False
_embed_tokens: tuple[str, ...] = ()
_rc_sock: Path | None = None
_extra_items: list[dict[str, Any]] = []
_backend = ""


def _rc_path() -> Path:
    return ensure_state_dir() / "vlc.sock"


def _cliamp_sock() -> Path:
    return Path.home() / ".config/cliamp/cliamp.sock"


def _clear_socket() -> None:
    path = _rc_path()
    try:
        path.unlink()
    except OSError:
        pass


def _running() -> bool:
    if _backend == "cliamp":
        return _cliamp_alive()
    return _proc is not None and _proc.poll() is None


def player_pid() -> int:
    if _backend == "cliamp" and _cliamp_proc is not None and _cliamp_proc.poll() is None:
        return int(_cliamp_proc.pid)
    if not _running() or _proc is None:
        return 0
    return int(_proc.pid)


def embed_tokens() -> tuple[str, ...]:
    return _embed_tokens


def _stop_proc() -> None:
    global _proc, _paused, _embed_tokens, _rc_sock
    proc = _proc
    _proc = None
    _paused = False
    _embed_tokens = ()
    _rc_sock = None
    if proc is None:
        return
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
    _clear_socket()


def _spawn_env() -> dict[str, str]:
    env = os.environ.copy()
    extra = [
        "/home/GG/.local/bin",
        str(Path.home() / ".local/bin"),
        "/home/GG/.local/share/goldgoblins/tools/node/bin",
        "/home/GG/.local/share/pnpm",
        "/home/GG/.local/share/pnpm/bin",
    ]
    path = str(env.get("PATH") or "")
    env["PATH"] = os.pathsep.join(extra + ([path] if path else []))
    env["QT_QPA_PLATFORM"] = env.get("QT_QPA_PLATFORM") or "xcb"
    return env


def _rc_send(command: str) -> str:
    path = _rc_path()
    if not path.exists():
        return ""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(0.4)
        sock.connect(str(path))
        sock.sendall((command.strip() + "\n").encode("utf-8"))
        chunks: list[bytes] = []
        while True:
            try:
                data = sock.recv(4096)
            except socket.timeout:
                break
            if not data:
                break
            chunks.append(data)
            if len(b"".join(chunks)) > 8192:
                break
        sock.close()
        return b"".join(chunks).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _volume_vlc(volume: int) -> int:
    return max(0, min(512, int(round(int(volume) * 5.12))))


def _volume_db(volume: int) -> float:
    return round(-30.0 + 36.0 * (max(0, min(100, int(volume))) / 100.0), 2)


def _cliamp_alive() -> bool:
    path = _cliamp_sock()
    if not path.exists():
        return False
    try:
        payload = _cliamp_call({"cmd": "status"}, timeout=0.6)
    except OSError:
        return False
    return bool(payload.get("ok"))


def _cliamp_call(payload: dict[str, Any], timeout: float = 8.0) -> dict[str, Any]:
    path = _cliamp_sock()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(str(path))
    sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
    chunks = b""
    try:
        while True:
            data = sock.recv(16384)
            if not data:
                break
            chunks += data
            if b"\n" in chunks:
                break
    except socket.timeout:
        pass
    sock.close()
    text = chunks.decode("utf-8", errors="replace").splitlines()
    if not text:
        return {}
    try:
        parsed = json.loads(text[0])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _ensure_cliamp() -> str:
    global _cliamp_proc
    binary = which_first(("cliamp",))
    if not binary:
        raise RuntimeError("MEDIA_CLIAMP_MISSING")
    if _cliamp_alive():
        return binary
    if _cliamp_proc is not None and _cliamp_proc.poll() is None:
        time.sleep(0.3)
        if _cliamp_alive():
            return binary
    _cliamp_sock().parent.mkdir(parents=True, exist_ok=True)
    _cliamp_proc = subprocess.Popen(
        [binary, "--daemon", "--provider", "radio"],
        cwd=str(Path.home()),
        env=_spawn_env(),
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(20):
        time.sleep(0.15)
        if _cliamp_alive():
            return binary
    raise RuntimeError("MEDIA_CLIAMP_DAEMON")


def _play_cliamp(source: str) -> None:
    global _backend, _paused, _kind
    _ensure_cliamp()
    loaded = _cliamp_call({"cmd": "url.load", "path": source}, timeout=20.0)
    if not loaded.get("ok"):
        queued = _cliamp_call({"cmd": "queue", "path": source})
        if not queued.get("ok"):
            raise RuntimeError("MEDIA_CLIAMP_LOAD")
    status = _cliamp_call({"cmd": "status"})
    total = int(status.get("total") or 0)
    index = max(0, total - 1)
    played = _cliamp_call({"cmd": "queue.play", "index": index})
    if not played.get("ok"):
        _cliamp_call({"cmd": "play"})
    _backend = "cliamp"
    _paused = False
    _kind = "audio"
    prefs = load_prefs()
    _cliamp_call({"cmd": "volume", "value": _volume_db(int(prefs["volume"]))})


def _spawn(argv: list[str], tokens: tuple[str, ...]) -> None:
    global _proc, _paused, _embed_tokens, _rc_sock, _backend
    _stop_proc()
    try:
        _proc = subprocess.Popen(
            argv,
            cwd=str(STATE_DIR),
            env=_spawn_env(),
            start_new_session=True,
            close_fds=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        _proc = None
        raise RuntimeError("MEDIA_SPAWN_FAILED:" + type(exc).__name__) from exc
    _paused = False
    _embed_tokens = tokens
    _rc_sock = _rc_path() if "--rc-unix" in argv else None
    _backend = "vlc" if any("vlc" in part for part in argv) else "proc"


def _player_argv(source: str, video: bool, drawable_xid: int) -> list[str]:
    binary = player_bin()
    if not binary:
        raise RuntimeError("MEDIA_PLAYER_MISSING")
    name = Path(binary).name
    if video:
        gui = which_first(("vlc", "cvlc"))
        if not gui:
            raise RuntimeError("MEDIA_PLAYER_MISSING")
        argv = [
            gui,
            "--extraintf",
            "rc",
            "--rc-unix",
            str(_rc_path()),
            "--rc-fake-tty",
            "--no-video-title-show",
            "--no-qt-privacy-ask",
            "--no-video-deco",
            "--play-and-stop",
        ]
        if drawable_xid > 0:
            argv.extend(["--drawable-xid", str(int(drawable_xid))])
        argv.append(source)
        return argv
    if name in ("cvlc", "vlc"):
        argv = [
            binary,
            "--intf",
            "rc",
            "--rc-unix",
            str(_rc_path()),
            "--rc-fake-tty",
            "--no-video-title-show",
            "--play-and-stop",
            "--no-video",
            source,
        ]
        return argv
    if name == "ffplay":
        if video:
            return [binary, "-autoexit", "-loglevel", "quiet", source]
        return [binary, "-nodisp", "-autoexit", "-loglevel", "quiet", source]
    return [binary, source]


def _emulator_argv(item: dict[str, Any]) -> tuple[list[str], tuple[str, ...]]:
    system = str(item.get("system") or "")
    spec = SYSTEMS.get(system)
    if spec is None:
        raise RuntimeError("MEDIA_SYSTEM_UNKNOWN")
    binary = which_first(tuple(spec["bins"]))
    if not binary:
        raise RuntimeError("MEDIA_EMULATOR_MISSING:" + system)
    name = Path(binary).name
    source = str(item["source"])
    tokens = tuple(str(token) for token in spec["tokens"])
    if name == "retroarch":
        return [binary, source], tokens
    if name == "dolphin-emu":
        return [binary, "-b", "-e", source], tokens
    if name in ("pcsx2", "pcsx2-qt"):
        return [binary, source], tokens
    return [binary, source], tokens


def ytdlp_resolve(url: str) -> str:
    binary = which_first(("yt-dlp",))
    if not binary:
        return url
    try:
        raw = subprocess.check_output(
            [binary, "-g", "--no-playlist", "--format", "b/best", url],
            timeout=25,
            env=_spawn_env(),
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return url
    line = raw.decode("utf-8", errors="replace").splitlines()
    if not line:
        return url
    try:
        return stream_allowed(line[0].strip())
    except ValueError:
        return url


def set_mode(mode: str) -> dict[str, Any]:
    global _extra_items
    kind = str(mode or "").strip().upper()
    if kind not in MODES:
        raise ValueError("MEDIA_MODE_INVALID")
    save_prefs({"mode": kind})
    _extra_items = []
    return status_payload()


def set_volume(volume: int) -> dict[str, Any]:
    prefs = save_prefs({"volume": int(volume)})
    if _backend == "cliamp" and _cliamp_alive():
        _cliamp_call({"cmd": "volume", "value": _volume_db(int(prefs["volume"]))})
    elif _running() and _rc_sock is not None:
        _rc_send("volume " + str(_volume_vlc(int(prefs["volume"]))))
    return status_payload()


def item_by_id(item_id_value: str) -> dict[str, Any] | None:
    wanted = str(item_id_value or "").strip()
    if not wanted:
        return None
    for item in _extra_items:
        if item.get("id") == wanted:
            return item
    prefs = load_prefs()
    for mode in (prefs["mode"],) + MODES:
        for item in catalog_for(mode):
            if item["id"] == wanted:
                return item
    return None


def _resolve_item(item: dict[str, Any]) -> dict[str, Any]:
    media = str(item.get("media") or "")
    source = str(item.get("source") or "")
    if media in ("stream", "tool") or looks_like_url(source):
        item = dict(item)
        if media != "tool":
            item["source"] = stream_allowed(source)
        return item
    item = dict(item)
    item["source"] = str(confined(Path(source)))
    return item


def play_item(item_id_value: str, drawable_xid: int = 0) -> dict[str, Any]:
    global _item, _kind, _backend
    item = item_by_id(item_id_value)
    if item is None:
        raise ValueError("MEDIA_ITEM_UNKNOWN")
    item = _resolve_item(item)
    kind = str(item["kind"])
    if kind == "GAME":
        argv, tokens = _emulator_argv(item)
        _spawn(argv, tokens)
        _kind = "game"
        _backend = "emu"
        _item = item
        save_prefs({"mode": "GAME", "last_id": item["id"]})
        payload = status_payload()
        payload["screen"] = "EMBED"
        return payload
    source = str(item["source"])
    host = (urlparse(source).hostname or "").lower()
    if kind == "TV" and (
        "youtube." in host
        or host.endswith("youtu.be")
        or host.endswith("twitch.tv")
    ):
        source = ytdlp_resolve(source)
        item["source"] = source
    use_cliamp = kind in ("MUSIC", "RADIO") and bool(which_first(("cliamp",)))
    if use_cliamp:
        _stop_proc()
        _play_cliamp(source)
        _item = item
        save_prefs({"mode": kind, "last_id": item["id"]})
        return status_payload()
    video = kind == "TV" or Path(source).suffix.lower() in VIDEO_EXT
    _clear_socket()
    argv = _player_argv(source, video=video, drawable_xid=drawable_xid)
    tokens = ("vlc", "VLC", "ffplay") if video else ()
    _spawn(argv, tokens)
    time.sleep(0.15)
    prefs = save_prefs({"mode": kind, "last_id": item["id"]})
    if _rc_sock is not None:
        _rc_send("volume " + str(_volume_vlc(int(prefs["volume"]))))
    _kind = "video" if video else "audio"
    _item = item
    payload = status_payload()
    if video:
        payload["screen"] = "EMBED"
        payload["drawable"] = bool(drawable_xid > 0)
    return payload


def pause() -> dict[str, Any]:
    global _paused
    if _backend == "cliamp" and _cliamp_alive():
        _cliamp_call({"cmd": "toggle"})
        status = _cliamp_call({"cmd": "status"})
        _paused = str(status.get("state") or "") == "paused"
        return status_payload()
    if not _running():
        return status_payload()
    if _rc_sock is not None:
        _rc_send("pause")
        _paused = not _paused
    elif _proc is not None:
        if _paused:
            os.kill(_proc.pid, 18)
            _paused = False
        else:
            os.kill(_proc.pid, 19)
            _paused = True
    return status_payload()


def stop() -> dict[str, Any]:
    global _item, _kind, _backend, _paused
    if _backend == "cliamp" and _cliamp_alive():
        _cliamp_call({"cmd": "stop"})
    _stop_proc()
    _item = None
    _kind = "audio"
    _backend = ""
    _paused = False
    return status_payload()


def search(query: str) -> dict[str, Any]:
    global _extra_items
    prefs = load_prefs()
    cleaned = str(query or "").strip()
    if not cleaned:
        _extra_items = []
        return status_payload()
    rows = search_items(prefs["mode"], cleaned)
    _extra_items = rows
    payload = status_payload()
    payload["items"] = rows
    payload["query"] = str(query or "")[:80]
    return payload


def next_item_id(delta: int) -> str:
    prefs = load_prefs()
    rows = _extra_items or catalog_for(prefs["mode"])
    if not rows:
        return ""
    current = str((_item or {}).get("id") or prefs.get("last_id") or "")
    index = 0
    for i, item in enumerate(rows):
        if item["id"] == current:
            index = i
            break
    return str(rows[(index + int(delta)) % len(rows)]["id"])


def skip(delta: int) -> dict[str, Any]:
    if _backend == "cliamp" and _cliamp_alive() and int(delta) in (-1, 1):
        _cliamp_call({"cmd": "next" if int(delta) > 0 else "prev"})
        return status_payload()
    nxt = next_item_id(delta)
    if not nxt:
        return status_payload()
    return play_item(nxt)


def fetch_status() -> dict[str, Any]:
    tools = probe_tools()
    path = tools["torlink"]["path"]
    if not path:
        return {
            "present": False,
            "label": "TORLINK · MISSING",
            "detail": "torlnk is not on PATH.",
            "bin": "",
            "files": "http://127.0.0.1:9160/",
        }
    return {
        "present": True,
        "label": "TORLINK · READY",
        "detail": "Workspace opens torlink. Finished files stream at 127.0.0.1:9160.",
        "bin": path,
        "files": "http://127.0.0.1:9160/",
    }


def fetch_argv() -> list[str]:
    tools = probe_tools()
    path = tools["torlink"]["path"]
    if not path:
        raise RuntimeError("MEDIA_TORLINK_MISSING")
    return [path]


def start_cliamp() -> dict[str, Any]:
    global _item, _kind, _backend, _cliamp_proc
    binary = which_first(("cliamp",))
    if not binary:
        raise RuntimeError("MEDIA_CLIAMP_MISSING")
    owned = _cliamp_proc
    _cliamp_proc = None
    if owned is not None and owned.poll() is None:
        owned.terminate()
        try:
            owned.wait(timeout=2)
        except subprocess.TimeoutExpired:
            owned.kill()
    argv = [binary, "--provider", "radio"]
    _spawn(argv, ("cliamp",))
    _kind = "fetch"
    _backend = "cliamp"
    _item = {
        "id": "music:cliamp",
        "kind": "MUSIC",
        "title": "cliamp",
        "source": binary,
        "media": "tool",
        "system": "",
    }
    save_prefs({"mode": "RADIO", "last_id": "music:cliamp"})
    payload = status_payload()
    payload["screen"] = "EMBED"
    return payload


def _ensure_torlink_files() -> None:
    global _files_proc
    if _files_proc is not None and _files_proc.poll() is None:
        return
    binary = which_first(("torlnk", "torlink"))
    if not binary:
        return
    _files_proc = subprocess.Popen(
        [binary, "files", "--host", "127.0.0.1", "--port", "9160"],
        cwd=str(Path.home()),
        env=_spawn_env(),
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def start_fetch() -> dict[str, Any]:
    global _item, _kind, _backend
    argv = fetch_argv()
    _spawn(argv, ("torlnk", "torlink"))
    _ensure_torlink_files()
    _kind = "fetch"
    _backend = "torlink"
    _item = {
        "id": "fetch:torlink",
        "kind": "FETCH",
        "title": "torlink",
        "source": argv[0],
        "media": "tool",
        "system": "",
    }
    save_prefs({"mode": "FETCH", "last_id": "fetch:torlink"})
    payload = status_payload()
    payload["screen"] = "EMBED"
    return payload


def status_payload() -> dict[str, Any]:
    prefs = load_prefs()
    tools = probe_tools()
    mode = prefs["mode"]
    rows = _extra_items if _extra_items else (
        catalog_for(mode) if mode != "FETCH" else []
    )
    now = dict(_item) if _item else {}
    playing = False
    paused = False
    if _backend == "cliamp" and _cliamp_alive():
        live = _cliamp_call({"cmd": "status"}, timeout=0.8)
        state = str(live.get("state") or "")
        playing = state == "playing"
        paused = state == "paused"
        track = live.get("track") if isinstance(live.get("track"), dict) else {}
        if track:
            now = {
                "id": now.get("id") or "",
                "kind": now.get("kind") or mode,
                "title": str(track.get("title") or now.get("title") or mode),
                "source": str(track.get("path") or now.get("source") or ""),
                "media": "stream" if track.get("stream") else now.get("media") or "file",
                "system": "",
                "player": "cliamp",
            }
    else:
        playing = _running() and not _paused
        paused = _paused and _running()
    player = "CLIAMP" if _backend == "cliamp" else (
        Path(player_bin()).name.upper() if player_bin() else "NONE"
    )
    legend = mode
    if now:
        legend = str(now.get("title") or mode)
    if mode == "FETCH":
        fetch = fetch_status()
        legend = str(fetch["label"])
    screen = ""
    if _running() and _kind in ("video", "game", "fetch"):
        screen = "EMBED"
    return {
        "schema": SCHEMA,
        "mode": mode,
        "modes": list(MODES),
        "volume": int(prefs["volume"]),
        "playing": playing,
        "paused": paused,
        "running": playing or paused or _running(),
        "player": player,
        "backend": _backend or player.lower(),
        "pid": player_pid(),
        "screen": screen,
        "kind": _kind,
        "legend": legend[:80],
        "now": now,
        "items": rows,
        "tools": {
            "cliamp": tools["cliamp"],
            "vlc": tools["vlc"],
            "ffplay": tools["ffplay"],
            "torlink": tools["torlink"],
            "yt-dlp": tools.get("yt-dlp") or {"present": False, "path": ""},
            "retroarch": tools["retroarch"],
        },
        "cores": tools["cores"],
        "fetch": fetch_status(),
        "library_roots": [str(path) for path in library_roots()],
        "last_id": str(prefs.get("last_id") or ""),
    }


def tool_line(payload: dict[str, Any] | None = None) -> str:
    data = payload if payload is not None else status_payload()
    tools = data.get("tools") or {}
    parts = []
    for key in ("vlc", "cliamp", "torlink", "yt-dlp", "retroarch"):
        row = tools.get(key) or {}
        mark = "ON" if row.get("present") else "OFF"
        parts.append(key.upper() + " " + mark)
    return " · ".join(parts)
