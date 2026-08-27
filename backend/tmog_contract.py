from __future__ import annotations

import os
import pwd
import socket
import time
from pathlib import Path
from typing import Any


SCHEMA = "gg.ai-desktop.tmog-snapshot.v2"
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


def _temps() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    hwmon = Path("/sys/class/hwmon")
    try:
        chips = sorted(hwmon.glob("hwmon*"))
    except OSError:
        chips = []
    for chip in chips:
        label = _read_text(chip / "name", 64).strip() or chip.name
        for temp_file in sorted(chip.glob("temp*_input")):
            raw = _read_text(temp_file, 32).strip()
            try:
                celsius = int(raw) / 1000.0
            except ValueError:
                continue
            if celsius < 20 or celsius > 110:
                continue
            tag = label
            sibling = temp_file.name.replace("_input", "_label")
            named = _read_text(chip / sibling, 64).strip()
            if named:
                tag = named
            rows.append({"name": tag[:24], "c": round(celsius, 1), "chip": label[:16]})
            if len(rows) >= 10:
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
    if prev[0] <= 0 or now - prev[0] < 0.05:
        return (now, a, b), 0, 0
    dt = now - prev[0]
    ra = max(0, int((a - prev[1]) / dt))
    rb = max(0, int((b - prev[2]) / dt))
    return (now, a, b), ra, rb


def _pid_dirs() -> list[Path]:
    root = Path("/proc")
    found: list[Path] = []
    try:
        names = os.listdir(root)
    except OSError:
        return []
    for name in names:
        if not name.isdigit():
            continue
        path = root / name
        if path.is_symlink() or not path.is_dir():
            continue
        found.append(path)
        if len(found) >= MAX_SCAN:
            break
    return found


def _user_name(uid: int) -> str:
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def _processes(now: float, dt: float, clk: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
    global _prev_times
    rows: list[dict[str, Any]] = []
    next_times: dict[int, tuple[float, int]] = {}
    users: dict[str, int] = {}
    running = 0
    page = _page_kb()
    for proc_dir in _pid_dirs():
        try:
            pid = int(proc_dir.name)
        except ValueError:
            continue
        stat = _read_text(proc_dir / "stat", 2048)
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
        comm = _read_text(proc_dir / "comm", 64).strip() or "?"
        cmdline = _read_text(proc_dir / "cmdline", 512).replace("\x00", " ").strip()
        if len(cmdline) > MAX_CMDLINE:
            cmdline = cmdline[: MAX_CMDLINE - 1] + "…"
        try:
            uid = proc_dir.stat().st_uid
        except OSError:
            uid = os.getuid()
        user = _user_name(uid)
        users[user] = users.get(user, 0) + 1
        if state == "R":
            running += 1
        rows.append(
            {
                "pid": pid,
                "ppid": ppid,
                "comm": comm[:32],
                "state": state[:1],
                "status": PROC_STATES.get(state[:1], state[:1]),
                "user": user[:24],
                "rss_kb": max(0, rss_pages * page),
                "virt_kb": max(0, vsize // 1024),
                "cpu_pct": round(cpu_pct, 1),
                "threads": max(1, threads),
                "cmdline": cmdline,
            }
        )
    _prev_times = next_times
    rows.sort(key=lambda item: (float(item["cpu_pct"]), int(item["rss_kb"])), reverse=True)
    counts = {
        "running": running,
        "total": len(next_times),
        "shown": min(len(rows), MAX_PROCESSES),
    }
    return rows[:MAX_PROCESSES], counts, users


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


def snapshot() -> dict[str, Any]:
    global _prev_mono, _prev_net, _prev_disk
    now = time.monotonic()
    dt = now - _prev_mono if _prev_mono else 0.0
    clk = _clk()
    mem = _meminfo()
    load1, load5, load15 = _loadavg()
    cpu_rows = _cpu_times()
    cpu_pcts = _cpu_pcts(cpu_rows)
    overall = cpu_pcts[0] if cpu_pcts else 0.0
    mhz = _cpu_mhz()
    cores: list[dict[str, Any]] = []
    for index, pct in enumerate(cpu_pcts[1:]):
        cores.append(
            {
                "id": index,
                "pct": pct,
                "mhz": mhz[index] if index < len(mhz) else 0,
            }
        )
    temps = _temps()
    temp_c = temps[0]["c"] if temps else 0.0
    while len(_core_hist) < len(cores):
        _core_hist.append([])
    core_hist = []
    for index, core in enumerate(cores):
        core_hist.append(_push(_core_hist[index], float(core["pct"])))
    energy = _energy()
    rx, tx, iface = _net_bytes()
    _prev_net, rx_bps, tx_bps = _rate(_prev_net, now, rx, tx)
    dread, dwrite = _disk_bytes()
    _prev_disk, read_bps, write_bps = _rate(_prev_disk, now, dread, dwrite)
    procs, tasks, users = _processes(now, dt, clk)
    _prev_mono = now
    user_rows = [
        {"name": name, "procs": count}
        for name, count in sorted(users.items(), key=lambda item: item[1], reverse=True)[:16]
    ]
    app = resolve_appimage()
    return {
        "schema": SCHEMA,
        "cpu_busy": overall,
        "cpu_model": _cpu_model(),
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
        "hostname": socket.gethostname()[:48],
        "kernel": os.uname().release[:48],
        "process_count": tasks["total"],
        "tasks_running": tasks["running"],
        "net_iface": iface,
        "net_rx_bps": rx_bps,
        "net_tx_bps": tx_bps,
        "disk_read_bps": read_bps,
        "disk_write_bps": write_bps,
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
        "mounts": _mounts(),
        "connections": _connections(),
        "startup": _names_from_dir(Path.home() / ".config/autostart", ".desktop"),
        "apps": _names_from_dir(
            Path.home() / ".local/share/applications", ".desktop"
        ),
        "services": _names_from_dir(Path("/etc/systemd/system"), ".service"),
        "appimage": str(app) if app is not None else "",
        "appimage_found": app is not None,
    }


def format_kib(value: int) -> str:
    amount = max(0, int(value))
    if amount >= 1024 * 1024:
        return str(round(amount / 1024 / 1024, 1)) + " GiB"
    if amount >= 1024:
        return str(round(amount / 1024, 1)) + " MiB"
    return str(amount) + " KiB"
