from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SCHEMA = "gg.ai-desktop.media-status.v1"
STATE_DIR = Path("/home/GG/.local/state/goldgoblins/gg-ai-desktop/media")
MODES = ("MUSIC", "RADIO", "TV", "GAME", "FETCH")
DEFAULT_MODE = "MUSIC"
MAX_ITEMS = 400
MAX_SCAN_DEPTH = 4
MAX_TITLE = 96
VOLUME_DEFAULT = 70

AUDIO_EXT = frozenset(
    {".mp3", ".flac", ".ogg", ".opus", ".m4a", ".wav", ".aac", ".wma", ".aiff"}
)
VIDEO_EXT = frozenset(
    {".mp4", ".mkv", ".avi", ".webm", ".mov", ".m4v", ".mpg", ".mpeg", ".ts"}
)
DENIED_TOKENS = (
    "ps3",
    "ps4",
    "ps5",
    "switch",
    "xbox360",
    "xboxone",
    "seriesx",
    "series-x",
)

SYSTEMS: dict[str, dict[str, Any]] = {
    "nes": {
        "label": "NES",
        "ext": {".nes", ".fds"},
        "bins": ("fceux", "nestopia", "mednafen", "retroarch"),
        "tokens": ("fceux", "nestopia", "mednafen", "retroarch"),
    },
    "snes": {
        "label": "SNES",
        "ext": {".smc", ".sfc"},
        "bins": ("snes9x", "snes9x-gtk", "zsnes", "mednafen", "retroarch"),
        "tokens": ("snes9x", "zsnes", "mednafen", "retroarch"),
    },
    "n64": {
        "label": "N64",
        "ext": {".n64", ".z64", ".v64"},
        "bins": ("mupen64plus", "retroarch"),
        "tokens": ("mupen64plus", "retroarch"),
    },
    "gb": {
        "label": "GAME BOY",
        "ext": {".gb", ".gbc"},
        "bins": ("mgba", "vbam", "sameboy", "retroarch"),
        "tokens": ("mgba", "vbam", "sameboy", "retroarch"),
    },
    "gba": {
        "label": "GBA",
        "ext": {".gba"},
        "bins": ("mgba", "vbam", "retroarch"),
        "tokens": ("mgba", "vbam", "retroarch"),
    },
    "nds": {
        "label": "NDS",
        "ext": {".nds"},
        "bins": ("melonds", "desmume", "retroarch"),
        "tokens": ("melonds", "desmume", "retroarch"),
    },
    "genesis": {
        "label": "GENESIS",
        "ext": {".md", ".gen", ".smd"},
        "bins": ("genesis_plus_gx", "mednafen", "retroarch"),
        "tokens": ("mednafen", "retroarch"),
    },
    "ps1": {
        "label": "PS1",
        "ext": {".cue", ".chd", ".pbp", ".ccd"},
        "folders": ("ps1", "psx", "playstation"),
        "bins": ("duckstation", "duckstation-qt", "pcsxr", "mednafen", "retroarch"),
        "tokens": ("duckstation", "pcsxr", "mednafen", "retroarch"),
    },
    "ps2": {
        "label": "PS2",
        "ext": {".iso", ".chd", ".cso", ".bin"},
        "folders": ("ps2", "playstation2"),
        "bins": ("pcsx2", "pcsx2-qt", "retroarch"),
        "tokens": ("pcsx2", "retroarch"),
    },
    "psp": {
        "label": "PSP",
        "ext": {".iso", ".cso", ".pbp"},
        "folders": ("psp",),
        "bins": ("ppsspp", "PPSSPPSDL", "retroarch"),
        "tokens": ("ppsspp", "retroarch"),
    },
    "gc": {
        "label": "GAMECUBE",
        "ext": {".gcm", ".gcz", ".rvz", ".iso"},
        "folders": ("gc", "gamecube", "gcn"),
        "bins": ("dolphin-emu", "retroarch"),
        "tokens": ("dolphin-emu", "dolphin", "retroarch"),
    },
    "wii": {
        "label": "WII",
        "ext": {".wbfs", ".wad", ".rvz", ".iso"},
        "folders": ("wii",),
        "bins": ("dolphin-emu", "retroarch"),
        "tokens": ("dolphin-emu", "dolphin", "retroarch"),
    },
    "xbox": {
        "label": "XBOX",
        "ext": {".xiso", ".iso"},
        "folders": ("xbox", "ogxbox"),
        "bins": ("xemu",),
        "tokens": ("xemu",),
    },
    "dreamcast": {
        "label": "DREAMCAST",
        "ext": {".gdi", ".cdi", ".chd"},
        "bins": ("flycast", "redream", "retroarch"),
        "tokens": ("flycast", "redream", "retroarch"),
    },
}

TOOL_BINS = {
    "cliamp": ("cliamp",),
    "vlc": ("cvlc", "vlc"),
    "ffplay": ("ffplay",),
    "torlink": ("torlnk", "torlink"),
    "yt-dlp": ("yt-dlp",),
    "retroarch": ("retroarch",),
}

TOOL_DIRS = (
    Path("/home/GG/.local/bin"),
    Path.home() / ".local/bin",
    Path("/home/GG/.local/share/goldgoblins/tools"),
    Path("/home/GG/.local/share/goldgoblins/tools/node/bin"),
    Path("/home/GG/.local/share/pnpm"),
    Path("/home/GG/.local/share/pnpm/bin"),
)

RADIO_API = "https://de1.api.radio-browser.info/json/stations/search"
IPTV_PLAYLISTS = (
    "https://iptv-org.github.io/iptv/countries/se.m3u",
    "https://iptv-org.github.io/iptv/countries/uk.m3u",
    "https://iptv-org.github.io/iptv/countries/no.m3u",
    "https://iptv-org.github.io/iptv/countries/dk.m3u",
    "https://iptv-org.github.io/iptv/categories/news.m3u",
)
IPTV_PER_SOURCE = 80
HTTP_UA = "gg-ai-desktop/media"
CACHE_TTL = 6 * 3600

RADIO_PRESETS = (
    {
        "title": "SR P1",
        "url": "https://http-live.sr.se/p1-mp3-192",
    },
    {
        "title": "SR P2",
        "url": "https://http-live.sr.se/p2-mp3-192",
    },
    {
        "title": "SR P3",
        "url": "https://http-live.sr.se/p3-mp3-192",
    },
    {
        "title": "SR P4 Stockholm",
        "url": "https://http-live.sr.se/p4stockholm-mp3-192",
    },
    {
        "title": "BBC World Service",
        "url": "https://stream.live.vc.bbcmedia.co.uk/bbc_world_service",
    },
)

LIBRARY_DIRS = (
    Path("/home/GG/Musik"),
    Path.home() / "Musik",
    Path.home() / "Music",
    Path("/home/GG/Videor"),
    Path.home() / "Videor",
    Path.home() / "Videos",
    Path("/home/GG/ROMs"),
    Path.home() / "ROMs",
    Path("/home/GG/Spel"),
    Path.home() / "Spel",
    Path.home() / "Games",
    STATE_DIR / "library",
)


def ensure_state_dir() -> Path:
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    return STATE_DIR


def which_first(names: tuple[str, ...]) -> str:
    parts = [str(path) for path in TOOL_DIRS if path.is_dir()]
    inherited = str(os.environ.get("PATH") or "")
    if inherited:
        parts.append(inherited)
    search = os.pathsep.join(parts)
    for name in names:
        found = shutil.which(name, path=search)
        if found:
            return found
    return ""


def probe_tools() -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for key, names in TOOL_BINS.items():
        path = which_first(names)
        rows[key] = {
            "present": bool(path),
            "path": path,
            "names": list(names),
        }
    cores: dict[str, dict[str, Any]] = {}
    for system, spec in SYSTEMS.items():
        path = which_first(tuple(spec["bins"]))
        cores[system] = {
            "label": spec["label"],
            "present": bool(path),
            "path": path,
        }
    rows["cores"] = cores
    return rows


def _library_roots() -> list[Path]:
    roots: list[Path] = []
    seen: set[Path] = set()
    for folder in LIBRARY_DIRS + (ensure_state_dir() / "library",):
        try:
            resolved = folder.expanduser()
            if not resolved.exists() or not resolved.is_dir():
                continue
            resolved = resolved.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        roots.append(resolved)
    return roots


def library_roots() -> list[Path]:
    return _library_roots()


def _denied_path(path: Path) -> bool:
    parts = [part.lower() for part in path.parts]
    return any(token in parts for token in DENIED_TOKENS)


def item_id(kind: str, source: str) -> str:
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
    return kind.lower() + ":" + digest


def _title_of(path: Path) -> str:
    name = path.stem.replace("_", " ").replace("-", " ").strip()
    return (name or path.name)[:MAX_TITLE]


def system_for(path: Path) -> str:
    if _denied_path(path):
        return ""
    suffix = path.suffix.lower()
    folders = {part.lower() for part in path.parts}
    ranked: list[tuple[int, str]] = []
    ambiguous = {".iso", ".bin", ".chd", ".cue", ".cso"}
    for system, spec in SYSTEMS.items():
        score = 0
        folder_names = {str(name).lower() for name in spec.get("folders") or ()}
        if folder_names & folders:
            score += 2
        if suffix in spec["ext"]:
            score += 1
        if score:
            ranked.append((score, system))
    if not ranked:
        return ""
    ranked.sort(reverse=True)
    best_score, system = ranked[0]
    if suffix in ambiguous and best_score < 2:
        return ""
    return system


def confined(path: Path, roots: list[Path] | None = None) -> Path:
    resolved = path.expanduser().resolve()
    if _denied_path(resolved):
        raise ValueError("MEDIA_SYSTEM_DENIED")
    bases = roots if roots is not None else library_roots()
    for root in bases:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise ValueError("MEDIA_PATH_DENIED")


def stream_allowed(url: str) -> str:
    raw = str(url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("MEDIA_STREAM_DENIED")
    if not parsed.netloc:
        raise ValueError("MEDIA_STREAM_DENIED")
    if parsed.username or parsed.password:
        raise ValueError("MEDIA_STREAM_DENIED")
    return raw


def parse_m3u_text(text: str, kind: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    title = ""
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#EXTM3U"):
            continue
        if line.startswith("#EXTINF:"):
            title = line.split(",", 1)[-1].strip()[:MAX_TITLE]
            continue
        if line.startswith("#"):
            continue
        try:
            url = stream_allowed(line)
        except ValueError:
            title = ""
            continue
        rows.append(
            {
                "id": item_id(kind, url),
                "kind": kind,
                "title": title or urlparse(url).path.rsplit("/", 1)[-1] or kind,
                "source": url,
                "media": "stream",
                "system": "",
            }
        )
        title = ""
        if len(rows) >= MAX_ITEMS:
            break
    return rows


def parse_m3u(path: Path, kind: str) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return parse_m3u_text(text, kind)


def _http_get(url: str, timeout: float = 12.0) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": HTTP_UA, "Accept": "*/*"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _cache_path(name: str) -> Path:
    return ensure_state_dir() / name


def _cache_fresh(path: Path) -> bool:
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return False
    return age < CACHE_TTL


def _cached_bytes(name: str, url: str) -> bytes:
    path = _cache_path(name)
    if _cache_fresh(path):
        try:
            return path.read_bytes()
        except OSError:
            pass
    raw = _http_get(url)
    path.write_bytes(raw)
    path.chmod(0o600)
    return raw


def radio_browser_stations(
    query: str = "",
    country: str = "SE",
    limit: int = 80,
) -> list[dict[str, Any]]:
    params: dict[str, str] = {
        "hidebroken": "true",
        "order": "clickcount",
        "reverse": "true",
        "limit": str(max(1, min(int(limit), 120))),
    }
    cleaned = str(query or "").strip()
    if cleaned:
        params["name"] = cleaned[:80]
    elif country:
        params["countrycode"] = country
    url = RADIO_API + "?" + urllib.parse.urlencode(params)
    cache_name = "radio-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16] + ".json"
    try:
        raw = _cached_bytes(cache_name, url)
        payload = json.loads(raw.decode("utf-8"))
    except (
        OSError,
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
        UnicodeError,
    ):
        return []
    if not isinstance(payload, list):
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        source = str(item.get("url_resolved") or item.get("url") or "").strip()
        try:
            source = stream_allowed(source)
        except ValueError:
            continue
        if source in seen:
            continue
        seen.add(source)
        title = str(item.get("name") or "station").strip()[:MAX_TITLE]
        rows.append(
            {
                "id": item_id("RADIO", source),
                "kind": "RADIO",
                "title": title,
                "source": source,
                "media": "stream",
                "system": "",
                "player": "cliamp",
            }
        )
        if len(rows) >= MAX_ITEMS:
            break
    return rows


def _iptv_playlist(url: str) -> list[dict[str, Any]]:
    name = "tv-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16] + ".m3u"
    try:
        text = _cached_bytes(name, url).decode("utf-8", "replace")
    except (OSError, urllib.error.URLError, TimeoutError, UnicodeError):
        return []
    rows: list[dict[str, Any]] = []
    for item in parse_m3u_text(text, "TV"):
        item["player"] = "vlc"
        rows.append(item)
    return rows


def iptv_catalog() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for url in IPTV_PLAYLISTS:
        taken = 0
        for item in _iptv_playlist(url):
            if item["source"] in seen:
                continue
            seen.add(item["source"])
            rows.append(item)
            taken += 1
            if taken >= IPTV_PER_SOURCE or len(rows) >= MAX_ITEMS:
                break
        if len(rows) >= MAX_ITEMS:
            break
    return rows


def looks_like_url(value: str) -> bool:
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def query_item(kind: str, query: str) -> dict[str, Any] | None:
    raw = str(query or "").strip()
    if not looks_like_url(raw):
        return None
    source = stream_allowed(raw)
    title = urlparse(source).path.rsplit("/", 1)[-1] or source
    return {
        "id": item_id(kind, source),
        "kind": kind,
        "title": title[:MAX_TITLE],
        "source": source,
        "media": "stream",
        "system": "",
        "player": "cliamp" if kind == "RADIO" else "vlc",
    }


def _scan_files(kind: str, suffixes: frozenset[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root in library_roots():
        stack = [(root, 0)]
        while stack and len(rows) < MAX_ITEMS:
            folder, depth = stack.pop()
            if depth > MAX_SCAN_DEPTH:
                continue
            try:
                children = sorted(folder.iterdir(), key=lambda item: item.name.lower())
            except OSError:
                continue
            for child in children:
                if child.is_symlink() or child.name.startswith("."):
                    continue
                if child.is_dir():
                    if not _denied_path(child):
                        stack.append((child, depth + 1))
                    continue
                if child.suffix.lower() not in suffixes:
                    continue
                if _denied_path(child):
                    continue
                try:
                    source = str(confined(child))
                except ValueError:
                    continue
                if source in seen:
                    continue
                seen.add(source)
                rows.append(
                    {
                        "id": item_id(kind, source),
                        "kind": kind,
                        "title": _title_of(child),
                        "source": source,
                        "media": "file",
                        "system": "",
                    }
                )
                if len(rows) >= MAX_ITEMS:
                    break
    return rows


def music_catalog() -> list[dict[str, Any]]:
    return _scan_files("MUSIC", AUDIO_EXT)


def video_catalog() -> list[dict[str, Any]]:
    rows = _scan_files("TV", VIDEO_EXT)
    for item in rows:
        item["player"] = "vlc"
    playlist = ensure_state_dir() / "tv.m3u"
    if playlist.is_file():
        rows.extend(parse_m3u(playlist, "TV"))
    live = iptv_catalog()
    seen = {item["source"] for item in rows}
    for item in live:
        if item["source"] in seen:
            continue
        seen.add(item["source"])
        rows.append(item)
        if len(rows) >= MAX_ITEMS:
            break
    return rows[:MAX_ITEMS]


def radio_catalog() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for preset in RADIO_PRESETS:
        url = stream_allowed(str(preset["url"]))
        rows.append(
            {
                "id": item_id("RADIO", url),
                "title": str(preset["title"])[:MAX_TITLE],
                "kind": "RADIO",
                "source": url,
                "media": "stream",
                "system": "",
                "player": "cliamp",
            }
        )
        seen.add(url)
    playlist = ensure_state_dir() / "radio.m3u"
    if playlist.is_file():
        for item in parse_m3u(playlist, "RADIO"):
            if item["source"] in seen:
                continue
            item["player"] = "cliamp"
            rows.append(item)
            seen.add(item["source"])
    for item in radio_browser_stations(country="SE", limit=80):
        if item["source"] in seen:
            continue
        rows.append(item)
        seen.add(item["source"])
        if len(rows) >= MAX_ITEMS:
            break
    return rows[:MAX_ITEMS]


def search_items(mode: str, query: str) -> list[dict[str, Any]]:
    kind = str(mode or DEFAULT_MODE).strip().upper()
    cleaned = str(query or "").strip()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    direct = query_item("RADIO" if kind == "RADIO" else "TV", cleaned)
    if direct is not None:
        rows.append(direct)
        seen.add(direct["source"])
    if kind == "RADIO":
        for item in radio_browser_stations(query=cleaned, limit=60):
            if item["source"] in seen:
                continue
            rows.append(item)
            seen.add(item["source"])
        for item in radio_catalog():
            if cleaned.lower() not in str(item.get("title") or "").lower():
                continue
            if item["source"] in seen:
                continue
            rows.append(item)
            seen.add(item["source"])
        return rows[:MAX_ITEMS]
    if kind == "TV":
        needle = cleaned.lower()
        for url in IPTV_PLAYLISTS:
            for item in _iptv_playlist(url):
                hay = (str(item.get("title") or "") + " " + str(item.get("source") or "")).lower()
                if needle and needle not in hay:
                    continue
                if item["source"] in seen:
                    continue
                rows.append(item)
                seen.add(item["source"])
                if len(rows) >= MAX_ITEMS:
                    return rows
        for item in _scan_files("TV", VIDEO_EXT):
            if needle and needle not in str(item.get("title") or "").lower():
                continue
            if item["source"] in seen:
                continue
            item["player"] = "vlc"
            rows.append(item)
        return rows[:MAX_ITEMS]
    if kind == "MUSIC":
        needle = cleaned.lower()
        for item in music_catalog():
            if needle and needle not in str(item.get("title") or "").lower():
                continue
            rows.append(item)
        return rows[:MAX_ITEMS]
    if kind == "GAME":
        needle = cleaned.lower()
        for item in game_catalog():
            hay = (str(item.get("title") or "") + " " + str(item.get("system_label") or "")).lower()
            if needle and needle not in hay:
                continue
            rows.append(item)
        return rows[:MAX_ITEMS]
    return rows


def game_catalog() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    suffixes: set[str] = set()
    for spec in SYSTEMS.values():
        suffixes.update(spec["ext"])
    for root in library_roots():
        stack = [(root, 0)]
        while stack and len(rows) < MAX_ITEMS:
            folder, depth = stack.pop()
            if depth > MAX_SCAN_DEPTH:
                continue
            try:
                children = sorted(folder.iterdir(), key=lambda item: item.name.lower())
            except OSError:
                continue
            for child in children:
                if child.is_symlink() or child.name.startswith("."):
                    continue
                if child.is_dir():
                    if not _denied_path(child):
                        stack.append((child, depth + 1))
                    continue
                system = system_for(child)
                if not system:
                    continue
                if child.suffix.lower() not in suffixes:
                    continue
                try:
                    source = str(confined(child))
                except ValueError:
                    continue
                if source in seen:
                    continue
                seen.add(source)
                rows.append(
                    {
                        "id": item_id("GAME", source),
                        "kind": "GAME",
                        "title": _title_of(child),
                        "source": source,
                        "media": "rom",
                        "system": system,
                        "system_label": SYSTEMS[system]["label"],
                    }
                )
    return rows


def catalog_for(mode: str) -> list[dict[str, Any]]:
    kind = str(mode or DEFAULT_MODE).strip().upper()
    if kind == "MUSIC":
        return music_catalog()
    if kind == "RADIO":
        return radio_catalog()
    if kind == "TV":
        return video_catalog()
    if kind == "GAME":
        return game_catalog()
    return []


def load_prefs() -> dict[str, Any]:
    path = ensure_state_dir() / "prefs.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    mode = str(payload.get("mode") or DEFAULT_MODE).upper()
    if mode not in MODES:
        mode = DEFAULT_MODE
    try:
        volume = int(payload.get("volume", VOLUME_DEFAULT))
    except (TypeError, ValueError):
        volume = VOLUME_DEFAULT
    volume = max(0, min(100, volume))
    return {
        "mode": mode,
        "volume": volume,
        "last_id": str(payload.get("last_id") or ""),
    }


def save_prefs(prefs: dict[str, Any]) -> dict[str, Any]:
    current = load_prefs()
    current.update(prefs)
    mode = str(current.get("mode") or DEFAULT_MODE).upper()
    if mode not in MODES:
        mode = DEFAULT_MODE
    try:
        volume = int(current.get("volume", VOLUME_DEFAULT))
    except (TypeError, ValueError):
        volume = VOLUME_DEFAULT
    current["mode"] = mode
    current["volume"] = max(0, min(100, volume))
    current["last_id"] = str(current.get("last_id") or "")[:80]
    path = ensure_state_dir() / "prefs.json"
    path.write_text(json.dumps(current) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return current


def player_bin() -> str:
    tools = probe_tools()
    vlc = tools["vlc"]["path"]
    if vlc:
        return vlc
    return tools["ffplay"]["path"]


def format_clock(seconds: float | int | None) -> str:
    try:
        value = max(0, int(seconds or 0))
    except (TypeError, ValueError):
        return "00:00"
    minutes, rest = divmod(value, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{rest:02d}"
    return f"{minutes:02d}:{rest:02d}"
