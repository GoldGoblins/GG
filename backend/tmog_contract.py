from __future__ import annotations

import os
import pwd
import socket
import time
from pathlib import Path
from typing import Any


SCHEMA = "gg.ai-desktop.tmog-snapshot.v3"
APPIMAGE_NAMES = frozenset(
    {
        "TMOG-Task-Manager-Linux-x86_64.AppImage",
    }
)
SEARCH_DIRS = (
    Path("/home/GG/Hämtningar"),
    Path.home() / "Hämtningar",
    Path.home() / "Downloads",
    Path("/home/GG/.local/share/goldgoblins/tools/tmog"),
)
MIN_APPIMAGE_BYTES = 1_000_000
MAX_APPIMAGE_BYTES = 200_000_000
MAX_PROCESSES = 80
MAX_SCAN = 512
MAX_CMDLINE = 160
MAX_HISTORY = 48
MAX_CORES = 32
MAX_CONNS = 24
MAX_MOUNTS = 12
MAX_NAMES = 40
WINDOW_TOKENS = ("tmog", "task manager og")
TCP_STATES = {
    "01": "ESTABLISHED",
    "02": "SYN_SENT",
    "03": "SYN_RECV",
    "04": "FIN_WAIT1",
    "05": "FIN_WAIT2",
    "06": "TIME_WAIT",
    "07": "CLOSE",
    "08": "CLOSE_WAIT",
    "09": "LAST_ACK",
    "0A": "LISTEN",
    "0B": "CLOSING",
}
PROC_STATES = {
    "R": "Running",
    "S": "Sleeping",
    "D": "Disk sleep",
    "Z": "Zombie",
    "T": "Stopped",
    "t": "Tracing",
    "I": "Idle",
}

_prev_times: dict[int, tuple[float, int]] = {}
_prev_mono = 0.0
_prev_cpu: list[tuple[int, int]] = []
_prev_net: tuple[float, int, int] = (0.0, 0, 0)
_prev_disk: tuple[float, int, int] = (0.0, 0, 0)
_cpu_hist: list[float] = []
_mem_hist: list[float] = []
_net_hist: list[float] = []
_disk_hist: list[float] = []
_temp_hist: list[float] = []
_core_hist: list[list[float]] = []
_last_proc: dict[int, dict[str, Any]] = {}
_tombstones: dict[int, dict[str, Any]] = {}
_TOMBSTONE_TTL = 8.0


def resolve_appimage(
    search_dirs: tuple[Path, ...] | None = None,
) -> Path | None:
    dirs = search_dirs if search_dirs is not None else SEARCH_DIRS
    seen: set[Path] = set()
    for folder in dirs:
        try:
            folder = folder.resolve()
        except OSError:
            continue
        if folder in seen or not folder.is_dir() or folder.is_symlink():
            continue
        seen.add(folder)
        for name in sorted(APPIMAGE_NAMES):
            path = folder / name
            if _usable_appimage(path):
                return path
    return None


def _usable_appimage(path: Path) -> bool:
    try:
        if path.is_symlink() or not path.is_file():
            return False
        info = path.stat()
    except OSError:
        return False
    if info.st_uid != os.getuid():
        return False
    if not os.access(path, os.X_OK):
        return False
    if info.st_size < MIN_APPIMAGE_BYTES or info.st_size > MAX_APPIMAGE_BYTES:
        return False
    return path.name in APPIMAGE_NAMES


def _read_text(path: Path, limit: int = 4096) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _push(hist: list[float], value: float) -> list[float]:
    hist.append(round(float(value), 2))
    if len(hist) > MAX_HISTORY:
        del hist[: len(hist) - MAX_HISTORY]
    return list(hist)


def _clk() -> int:
    try:
        value = int(os.sysconf("SC_CLK_TCK"))
    except (OSError, ValueError, AttributeError):
        return 100
    return value if value > 0 else 100


def _page_kb() -> int:
    try:
        page = int(os.sysconf("SC_PAGE_SIZE"))
    except (OSError, ValueError, AttributeError):
        page = 4096
    return max(1, page // 1024)


def _meminfo() -> dict[str, int]:
    data = {
        "total": 0,
        "available": 0,
        "cached": 0,
        "buffers": 0,
        "shared": 0,
        "slab": 0,
        "swap_total": 0,
        "swap_free": 0,
    }
    for line in _read_text(Path("/proc/meminfo"), 8192).splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        key = parts[0]
        try:
            value = int(parts[1])
        except ValueError:
            continue
        if key == "MemTotal:":
            data["total"] = value
        elif key == "MemAvailable:":
            data["available"] = value
        elif key == "Cached:":
            data["cached"] = value
        elif key == "Buffers:":
            data["buffers"] = value
        elif key == "Shmem:":
            data["shared"] = value
        elif key == "SReclaimable:" or key == "Slab:":
            if key == "Slab:":
                data["slab"] = value
        elif key == "SwapTotal:":
            data["swap_total"] = value
        elif key == "SwapFree:":
            data["swap_free"] = value
    used = data["total"] - data["available"] if data["total"] >= data["available"] else 0
    data["used"] = max(0, used)
    data["swap_used"] = max(0, data["swap_total"] - data["swap_free"])
    return data


def _loadavg() -> tuple[float, float, float]:
    parts = _read_text(Path("/proc/loadavg"), 128).split()
    if len(parts) < 3:
        return 0.0, 0.0, 0.0
    try:
        return (
            round(float(parts[0]), 2),
            round(float(parts[1]), 2),
            round(float(parts[2]), 2),
        )
    except ValueError:
        return 0.0, 0.0, 0.0


def _uptime() -> float:
    parts = _read_text(Path("/proc/uptime"), 64).split()
    if not parts:
        return 0.0
    try:
        return float(parts[0])
    except ValueError:
        return 0.0


def _cpu_times() -> list[tuple[int, int]]:
    rows: list[tuple[int, int]] = []
    for line in _read_text(Path("/proc/stat"), 8192).splitlines():
        if not line.startswith("cpu"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            nums = [int(item) for item in parts[1:8]]
        except ValueError:
            continue
        total = sum(nums)
        idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
        rows.append((total, idle))
        if len(rows) > MAX_CORES:
            break
    return rows


def _cpu_pcts(now_rows: list[tuple[int, int]]) -> list[float]:
    global _prev_cpu
    out: list[float] = []
    for index, current in enumerate(now_rows):
        total, idle = current
        if index < len(_prev_cpu):
            dt = total - _prev_cpu[index][0]
            di = idle - _prev_cpu[index][1]
            if dt > 0:
                busy = max(0.0, min(100.0, (1.0 - di / dt) * 100.0))
                out.append(round(busy, 1))
                continue
        out.append(0.0)
    _prev_cpu = now_rows
    return out


def _cpu_mhz() -> list[int]:
    mhz: list[int] = []
    cpu_root = Path("/sys/devices/system/cpu")
    try:
        names = sorted(
            cpu_root.iterdir(),
            key=lambda item: int(item.name[3:])
            if item.name.startswith("cpu") and item.name[3:].isdigit()
            else 10**6,
        )
    except OSError:
        names = []
    for entry in names:
        if not entry.name.startswith("cpu") or not entry.name[3:].isdigit():
            continue
        raw = _read_text(entry / "cpufreq/scaling_cur_freq", 64).strip()
        if not raw:
            raw = _read_text(entry / "cpufreq/cpuinfo_cur_freq", 64).strip()
        try:
            mhz.append(int(raw) // 1000)
        except ValueError:
            mhz.append(0)
        if len(mhz) >= MAX_CORES:
            break
    if mhz:
        return mhz
    for line in _read_text(Path("/proc/cpuinfo"), 65536).splitlines():
        if not line.lower().startswith("cpu mhz"):
            continue
        try:
            mhz.append(int(float(line.split(":")[-1].strip())))
        except ValueError:
            continue
        if len(mhz) >= MAX_CORES:
            break
    return mhz


def _cpu_model() -> str:
    for line in _read_text(Path("/proc/cpuinfo"), 8192).splitlines():
        if line.lower().startswith("model name"):
            return line.split(":", 1)[-1].strip()[:80]
    return ""


_TEMP_FILES: tuple[float, list[tuple[str, str, str]]] | None = None
_TEMP_DISC_TTL = 30.0
_SLOW_CHIPS = ("nvme", "pch", "bat", "hp", "acad", "iwlwifi", "amdgpu")


def _chip_slow(chip: str) -> bool:
    low = chip.lower()
    return any(low.startswith(prefix) for prefix in _SLOW_CHIPS)


def _discover_temp_files() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    hwmon = Path("/sys/class/hwmon")
    try:
        chips = sorted(hwmon.glob("hwmon*"))
    except OSError:
        chips = []
    for chip in chips:
        label = _read_text(chip / "name", 64).strip() or chip.name
        if _chip_slow(label):
            continue
        for temp_file in sorted(chip.glob("temp*_input")):
            sibling = temp_file.name.replace("_input", "_label")
            named = _read_text(chip / sibling, 64).strip()
            tag = named or label
            rows.append((str(temp_file), tag[:24], label[:16]))
            if len(rows) >= 12:
                break
        if len(rows) >= 12:
            break
    rows.sort(
        key=lambda item: (
            0
            if "pkg" in item[1].lower()
            or item[2] in {"coretemp", "k10temp", "zenpower"}
            else 1,
            item[2],
        )
    )
    return rows


def _temp_files() -> list[tuple[str, str, str]]:
    global _TEMP_FILES
    now = time.monotonic()
    hit = _TEMP_FILES
    if hit is not None and now - hit[0] < _TEMP_DISC_TTL:
        return hit[1]
    rows = _discover_temp_files()
    _TEMP_FILES = (now, rows)
    return rows


def _temps(limit: int = 3) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cap = max(1, min(10, int(limit)))
    for path, tag, chip in _temp_files():
        raw = _read_text(Path(path), 32).strip()
        try:
            celsius = int(raw) / 1000.0
        except ValueError:
            continue
        if celsius < 20 or celsius > 110:
            continue
        rows.append({"name": tag, "c": round(celsius, 1), "chip": chip})
        if len(rows) >= cap:
            break
    rows.sort(
        key=lambda item: (
            0 if "pkg" in item["name"].lower() or item.get("chip") == "coretemp" else 1,
            -float(item["c"]),
        )
    )
    return rows


def _net_bytes() -> tuple[int, int, str]:
    rx = 0
    tx = 0
    primary = ""
    best = 0
    for line in _read_text(Path("/proc/net/dev"), 8192).splitlines():
        if ":" not in line:
            continue
        name, _, rest = line.partition(":")
        iface = name.strip()
        if iface in {"lo", ""}:
            continue
        parts = rest.split()
        if len(parts) < 10:
            continue
        try:
            irx = int(parts[0])
            itx = int(parts[8])
        except ValueError:
            continue
        rx += irx
        tx += itx
        if irx + itx > best:
            best = irx + itx
            primary = iface
    return rx, tx, primary


def _disk_bytes() -> tuple[int, int]:
    read_s = 0
    write_s = 0
    for line in _read_text(Path("/proc/diskstats"), 16384).splitlines():
        parts = line.split()
        if len(parts) < 14:
            continue
        name = parts[2]
        if name.startswith("loop") or name.startswith("ram") or name.startswith("dm-"):
            continue
        if any(name.startswith(prefix) and name != prefix and name[-1].isdigit()
               for prefix in ("sd", "vd", "nvme", "hd")):
            if "nvme" in name and "p" in name:
                continue
            if name[-1].isdigit() and "nvme" not in name:
                continue
        try:
            read_s += int(parts[5])
            write_s += int(parts[9])
        except ValueError:
            continue
    return read_s * 512, write_s * 512


def _rate(prev: tuple[float, int, int], now: float, a: int, b: int) -> tuple[tuple[float, int, int], int, int]:
    if prev[0] <= 0:
        return (now, a, b), 0, 0
    dt = now - prev[0]
    if dt < 0.008:
        return prev, 0, 0
    ra = max(0, int((a - prev[1]) / dt))
    rb = max(0, int((b - prev[2]) / dt))
    return (now, a, b), ra, rb


_UID_NAMES: dict[int, str] = {}
_HOST_IDENTITY: dict[str, str] | None = None
_NAME_CACHE: dict[str, tuple[float, list[str]]] = {}
_APPIMAGE_CACHE: tuple[float, str] | None = None
_NAME_TTL = 20.0
_APPIMAGE_TTL = 30.0


def _user_name(uid: int) -> str:
    hit = _UID_NAMES.get(uid)
    if hit is not None:
        return hit
    try:
        name = pwd.getpwuid(uid).pw_name
    except KeyError:
        name = str(uid)
    _UID_NAMES[uid] = name
    return name


def _host_identity() -> dict[str, str]:
    global _HOST_IDENTITY
    if _HOST_IDENTITY is not None:
        return _HOST_IDENTITY
    _HOST_IDENTITY = {
        "hostname": socket.gethostname()[:48],
        "kernel": os.uname().release[:48],
        "cpu_model": _cpu_model(),
    }
    return _HOST_IDENTITY


def _cached_names(key: str, folder: Path, suffix: str) -> list[str]:
    now = time.monotonic()
    hit = _NAME_CACHE.get(key)
    if hit is not None and now - hit[0] < _NAME_TTL:
        return hit[1]
    rows = _names_from_dir(folder, suffix)
    _NAME_CACHE[key] = (now, rows)
    return rows


def _cached_appimage() -> str:
    global _APPIMAGE_CACHE
    now = time.monotonic()
    hit = _APPIMAGE_CACHE
    if hit is not None and now - hit[0] < _APPIMAGE_TTL:
        return hit[1]
    app = resolve_appimage()
    path = str(app) if app is not None else ""
    _APPIMAGE_CACHE = (now, path)
    return path


def _fill_proc(row: dict[str, Any]) -> dict[str, Any]:
    proc_dir = row.pop("_dir", None)
    if not isinstance(proc_dir, Path):
        return row
    comm = _read_text(proc_dir / "comm", 64).strip() or "?"
    cmdline = _read_text(proc_dir / "cmdline", 512).replace("\x00", " ").strip()
    if len(cmdline) > MAX_CMDLINE:
        cmdline = cmdline[: MAX_CMDLINE - 1] + "…"
    row["comm"] = comm[:32]
    row["cmdline"] = cmdline
    return row


def _task_hint() -> tuple[int, int]:
    parts = _read_text(Path("/proc/loadavg"), 64).split()
    if len(parts) < 4 or "/" not in parts[3]:
        return 0, 0
    run_s, total_s = parts[3].split("/", 1)
    try:
        return int(run_s), int(total_s)
    except ValueError:
        return 0, 0


def _processes(
    now: float,
    dt: float,
    clk: int,
    fill_limit: int = MAX_PROCESSES,
    need_users: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, int]]:
    global _prev_times, _last_proc, _tombstones
    scanned: list[tuple[float, int, int, Path, str, int, int, int]] = []
    next_times: dict[int, tuple[float, int]] = {}
    users: dict[str, int] = {}
    running = 0
    page = _page_kb()
    try:
        entries = os.scandir("/proc")
    except OSError:
        entries = None
    if entries is not None:
        with entries:
            for ent in entries:
                if not ent.name.isdigit():
                    continue
                try:
                    pid = int(ent.name)
                except ValueError:
                    continue
                try:
                    with open(ent.path + "/stat", "r", encoding="utf-8", errors="replace") as fh:
                        stat = fh.read(2048)
                except OSError:
                    continue
                if not stat:
                    continue
                rparen = stat.rfind(")")
                if rparen < 0:
                    continue
                rest = stat[rparen + 2 :].split()
                if len(rest) < 22:
                    continue
                state = rest[0]
                try:
                    ppid = int(rest[1])
                    utime = int(rest[11])
                    stime = int(rest[12])
                    threads = int(rest[17])
                    vsize = int(rest[20])
                    rss_pages = int(rest[21])
                except ValueError:
                    continue
                ticks = utime + stime
                next_times[pid] = (now, ticks)
                cpu_pct = 0.0
                prev = _prev_times.get(pid)
                if prev is not None and dt > 0.05:
                    cpu_pct = max(0.0, min(100.0, (ticks - prev[1]) / clk / dt * 100.0))
                if state == "R":
                    running += 1
                if need_users:
                    try:
                        uid = ent.stat().st_uid
                    except OSError:
                        uid = os.getuid()
                    user = _user_name(uid)
                    users[user] = users.get(user, 0) + 1
                scanned.append(
                    (
                        cpu_pct,
                        max(0, rss_pages * page),
                        pid,
                        Path(ent.path),
                        state[:1],
                        ppid,
                        max(1, threads),
                        max(0, vsize // 1024),
                    )
                )
                if len(next_times) >= MAX_SCAN:
                    break
    gone = set(_last_proc) - set(next_times)
    for pid in gone:
        marker = dict(_last_proc.pop(pid))
        marker.pop("_dir", None)
        marker["tombstone"] = True
        marker["status"] = "Tombstone"
        marker["state"] = "X"
        marker["cpu_pct"] = 0.0
        marker["gone_at"] = now
        _tombstones[pid] = marker
    for pid, marker in list(_tombstones.items()):
        if pid in next_times or now - float(marker.get("gone_at") or 0) > _TOMBSTONE_TTL:
            _tombstones.pop(pid, None)
    _prev_times = next_times
    scanned.sort(key=lambda item: (item[0], item[1]), reverse=True)
    stones = list(_tombstones.values())
    stones.sort(key=lambda item: float(item.get("gone_at") or 0), reverse=True)
    shown_cap = max(0, min(MAX_PROCESSES, int(fill_limit)))
    live_cap = max(0, shown_cap - len(stones))
    kept_src = scanned[:live_cap]
    kept: list[dict[str, Any]] = []
    fill_n = max(0, min(len(kept_src), int(fill_limit)))
    for index, item in enumerate(kept_src):
        cpu_pct, rss_kb, pid, proc_dir, state, ppid, threads, virt_kb = item
        row = {
            "pid": pid,
            "ppid": ppid,
            "comm": "",
            "state": state,
            "status": PROC_STATES.get(state, state),
            "user": "",
            "rss_kb": rss_kb,
            "virt_kb": virt_kb,
            "cpu_pct": round(cpu_pct, 1),
            "threads": threads,
            "cmdline": "",
            "tombstone": False,
            "_dir": proc_dir,
        }
        prev = _last_proc.get(pid)
        if prev:
            row["comm"] = str(prev.get("comm") or "")
            row["cmdline"] = str(prev.get("cmdline") or "")
            row["user"] = str(prev.get("user") or "")
        if index < fill_n:
            _fill_proc(row)
            if not row.get("user"):
                try:
                    row["user"] = _user_name(proc_dir.stat().st_uid)[:24]
                except OSError:
                    row["user"] = _user_name(os.getuid())[:24]
        row.pop("_dir", None)
        kept.append(row)
    _last_proc = {int(row["pid"]): dict(row) for row in kept}
    shown = stones + kept
    counts = {
        "running": running,
        "total": len(next_times),
        "shown": len(shown),
        "tombstones": len(stones),
    }
    return shown, counts, users


def _mounts() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in _read_text(Path("/proc/mounts"), 16384).splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        src, dest, fstype = parts[0], parts[1], parts[2]
        if fstype in {"proc", "sysfs", "devtmpfs", "devpts", "tmpfs", "cgroup2", "cgroup", "overlay", "squashfs"}:
            continue
        if not dest.startswith("/") or dest in seen:
            continue
        seen.add(dest)
        try:
            st = os.statvfs(dest)
        except OSError:
            continue
        total = st.f_frsize * st.f_blocks
        free = st.f_frsize * st.f_bavail
        used = max(0, total - free)
        if total <= 0:
            continue
        rows.append(
            {
                "path": dest[:48],
                "src": src[:32],
                "fstype": fstype[:12],
                "used": used,
                "total": total,
            }
        )
        if len(rows) >= MAX_MOUNTS:
            break
    rows.sort(key=lambda item: int(item["total"]), reverse=True)
    return rows


def _hex_ip(value: str) -> str:
    if len(value) != 8:
        return value
    try:
        parts = [str(int(value[i : i + 2], 16)) for i in (6, 4, 2, 0)]
        return ".".join(parts)
    except ValueError:
        return value


def _connections() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        lines = _read_text(path, 65536).splitlines()[1:]
        for line in lines:
            parts = line.split()
            if len(parts) < 4:
                continue
            local = parts[1]
            remote = parts[2]
            state = TCP_STATES.get(parts[3].upper(), parts[3])
            lip, _, lport = local.partition(":")
            rip, _, rport = remote.partition(":")
            try:
                lp = str(int(lport, 16))
                rp = str(int(rport, 16))
            except ValueError:
                lp, rp = lport, rport
            rows.append(
                {
                    "local": _hex_ip(lip) + ":" + lp,
                    "remote": _hex_ip(rip) + ":" + rp,
                    "state": state,
                }
            )
            if len(rows) >= MAX_CONNS:
                return rows
    return rows


def _energy() -> dict[str, Any]:
    supply = Path("/sys/class/power_supply")
    payload = {
        "source": "",
        "watts": None,
        "battery_pct": None,
        "charging": False,
    }
    try:
        nodes = sorted(supply.iterdir())
    except OSError:
        return payload
    for node in nodes:
        kind = _read_text(node / "type", 32).strip().upper()
        if kind == "MAINS" or kind == "ADP":
            online = _read_text(node / "online", 16).strip() == "1"
            if online:
                payload["source"] = "AC"
        if kind == "BAT":
            cap = _read_text(node / "capacity", 16).strip()
            try:
                payload["battery_pct"] = int(cap)
            except ValueError:
                pass
            status = _read_text(node / "status", 32).strip().lower()
            payload["charging"] = status == "charging"
            if not payload["source"]:
                payload["source"] = "BATTERY"
        micro = _read_text(node / "power_now", 32).strip()
        if not micro:
            continue
        try:
            payload["watts"] = round(int(micro) / 1_000_000.0, 1)
        except ValueError:
            continue
    if not payload["source"]:
        payload["source"] = "AC"
    return payload


def _names_from_dir(folder: Path, suffix: str) -> list[str]:
    names: list[str] = []
    try:
        entries = sorted(folder.iterdir())
    except OSError:
        return []
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            continue
        if suffix and not entry.name.endswith(suffix):
            continue
        names.append(entry.stem[:40] if suffix == ".desktop" else entry.name[:40])
        if len(names) >= MAX_NAMES:
            break
    return names


_last_snap: tuple[float, str, dict[str, Any]] | None = None
_SNAP_DEBOUNCE = 0.18
_last_mhz_val = 0
_last_mhz_max = 0
_last_mhz_at = 0.0
_last_temp_c = 0.0


def _refresh_slow_meters(now: float, force: bool = False) -> None:
    global _last_mhz_val, _last_mhz_max, _last_mhz_at, _last_temp_c
    if not force and _last_mhz_at and now - _last_mhz_at < 0.75:
        return
    mhz = _cpu_mhz()
    _last_mhz_val = mhz[0] if mhz else 0
    _last_mhz_max = max(mhz) if mhz else 0
    _last_mhz_at = now
    temps = _temps(1)
    if temps:
        _last_temp_c = float(temps[0]["c"])


def pulse() -> dict[str, Any]:
    global _prev_mono, _prev_net, _prev_disk
    now = time.monotonic()
    dt = now - _prev_mono if _prev_mono else 0.0
    mem = _meminfo()
    load1, load5, load15 = _loadavg()
    cpu_pcts = _cpu_pcts(_cpu_times())
    overall = cpu_pcts[0] if cpu_pcts else 0.0
    _refresh_slow_meters(now)
    rx, tx, iface = _net_bytes()
    _prev_net, rx_bps, tx_bps = _rate(_prev_net, now, rx, tx)
    dread, dwrite = _disk_bytes()
    _prev_disk, read_bps, write_bps = _rate(_prev_disk, now, dread, dwrite)
    _prev_mono = now
    mem_pct = (mem["used"] / mem["total"] * 100.0) if mem["total"] else 0.0
    return {
        "schema": SCHEMA,
        "cpu_busy": overall,
        "cores": [float(pct) for pct in cpu_pcts[1:MAX_CORES + 1]],
        "mhz": _last_mhz_val,
        "mhz_max": _last_mhz_max,
        "temp_c": _last_temp_c,
        "mem_used_kb": mem["used"],
        "mem_total_kb": mem["total"],
        "mem_pct": round(mem_pct, 2),
        "load1": load1,
        "load5": load5,
        "load15": load15,
        "net_iface": iface,
        "net_rx_bps": rx_bps,
        "net_tx_bps": tx_bps,
        "disk_read_bps": read_bps,
        "disk_write_bps": write_bps,
        "dt": round(dt, 4),
    }


def snapshot(page: str = "") -> dict[str, Any]:
    global _prev_mono, _prev_net, _prev_disk, _last_snap
    kind = str(page or "").strip().upper()
    full = kind == ""
    now = time.monotonic()
    hit = _last_snap
    if hit is not None and hit[1] == kind and now - hit[0] < _SNAP_DEBOUNCE:
        return hit[2]
    want_procs = full or kind in {"SUMMARY", "PROCESSES", "USERS"}
    want_conns = full or kind == "CONNECTIONS"
    want_mounts = full or kind == "DISK"
    want_names = full or kind in {"STARTUP", "APPS", "SERVICES"}
    want_cores = full or kind in {"PERFORMANCE", "FREQ"}
    want_core_hist = full or kind == "PERFORMANCE"
    dt = now - _prev_mono if _prev_mono else 0.0
    clk = _clk()
    mem = _meminfo()
    load1, load5, load15 = _loadavg()
    cpu_rows = _cpu_times()
    cpu_pcts = _cpu_pcts(cpu_rows)
    overall = cpu_pcts[0] if cpu_pcts else 0.0
    mhz = _cpu_mhz()
    _refresh_slow_meters(now, force=True)
    per_core = cpu_pcts[1:]
    while len(_core_hist) < len(per_core):
        _core_hist.append([])
    cores: list[dict[str, Any]] = []
    core_hist: list[list[float]] = []
    for index, pct in enumerate(per_core):
        _push(_core_hist[index], float(pct))
        if want_cores:
            cores.append(
                {
                    "id": index,
                    "pct": pct,
                    "mhz": mhz[index] if index < len(mhz) else 0,
                }
            )
        if want_core_hist:
            core_hist.append(list(_core_hist[index]))
    temps = _temps(1 if kind == "SUMMARY" else 3)
    temp_c = temps[0]["c"] if temps else 0.0
    energy = _energy()
    rx, tx, iface = _net_bytes()
    _prev_net, rx_bps, tx_bps = _rate(_prev_net, now, rx, tx)
    dread, dwrite = _disk_bytes()
    _prev_disk, read_bps, write_bps = _rate(_prev_disk, now, dread, dwrite)
    procs: list[dict[str, Any]] = []
    users: dict[str, int] = {}
    if want_procs:
        fill_limit = 8 if kind == "SUMMARY" else MAX_PROCESSES
        procs, tasks, users = _processes(
            now,
            dt,
            clk,
            fill_limit=fill_limit,
            need_users=full or kind == "USERS",
        )
    else:
        run, total = _task_hint()
        tasks = {"running": run, "total": total, "tombstones": 0}
    _prev_mono = now
    user_rows = [
        {"name": name, "procs": count}
        for name, count in sorted(users.items(), key=lambda item: item[1], reverse=True)[:16]
    ]
    ident = _host_identity()
    app = _cached_appimage()
    payload = {
        "schema": SCHEMA,
        "cpu_busy": overall,
        "cpu_model": ident["cpu_model"],
        "cores": cores,
        "mhz": mhz[0] if mhz else 0,
        "mhz_max": max(mhz) if mhz else 0,
        "temps": temps,
        "temp_c": temp_c,
        "mem_used_kb": mem["used"],
        "mem_total_kb": mem["total"],
        "mem_cached_kb": mem["cached"],
        "mem_avail_kb": mem["available"],
        "mem_buffers_kb": mem["buffers"],
        "mem_shared_kb": mem["shared"],
        "mem_slab_kb": mem["slab"],
        "swap_used_kb": mem["swap_used"],
        "swap_total_kb": mem["swap_total"],
        "energy": energy,
        "load1": load1,
        "load5": load5,
        "load15": load15,
        "uptime_s": int(_uptime()),
        "hostname": ident["hostname"],
        "kernel": ident["kernel"],
        "process_count": tasks["total"],
        "tasks_running": tasks["running"],
        "net_iface": iface,
        "net_rx_bps": rx_bps,
        "net_tx_bps": tx_bps,
        "disk_read_bps": read_bps,
        "disk_write_bps": write_bps,
        "disk_led": round(min(1.0, (read_bps + write_bps) / float(8 * 1024 * 1024)), 3),
        "tombstones": int(tasks.get("tombstones") or 0),
        "cpu_hist": _push(_cpu_hist, overall),
        "core_hist": core_hist,
        "mem_hist": _push(
            _mem_hist,
            (mem["used"] / mem["total"] * 100.0) if mem["total"] else 0.0,
        ),
        "net_hist": _push(_net_hist, (rx_bps + tx_bps) / 1024.0),
        "disk_hist": _push(_disk_hist, (read_bps + write_bps) / 1024.0),
        "temp_hist": _push(_temp_hist, temp_c),
        "processes": procs,
        "users": user_rows,
        "mounts": _mounts() if want_mounts else [],
        "connections": _connections() if want_conns else [],
        "startup": _cached_names(
            "startup", Path.home() / ".config/autostart", ".desktop"
        )
        if want_names
        else [],
        "apps": _cached_names(
            "apps", Path.home() / ".local/share/applications", ".desktop"
        )
        if want_names
        else [],
        "services": _cached_names(
            "services", Path("/etc/systemd/system"), ".service"
        )
        if want_names
        else [],
        "appimage": app,
        "appimage_found": bool(app),
        "page": kind or "FULL",
    }
    _last_snap = (now, kind, payload)
    return payload


def format_kib(value: int) -> str:
    amount = max(0, int(value))
    if amount >= 1024 * 1024:
        return str(round(amount / 1024 / 1024, 1)) + " GiB"
    if amount >= 1024:
        return str(round(amount / 1024, 1)) + " MiB"
    return str(amount) + " KiB"
