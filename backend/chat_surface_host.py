from __future__ import annotations

import fcntl
import json
import os
import pty
import re
import signal
import shutil
import struct
import subprocess
import termios
import threading
import time
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import (
    Property,
    QFileSystemWatcher,
    QObject,
    QProcess,
    QSocketNotifier,
    QThread,
    QTimer,
    Signal,
    Slot,
)

from backend.chat_sessions import forget_session, list_for_ui, sync_owned
from backend import crypto_host
from backend import libretro_host
from backend import marketplace_host
from backend import media_host
from backend import tmog_contract
from backend.grok_wallet import snapshot as grok_wallet_snapshot
from backend.codex_wallet import (
    CODEX_SESSIONS,
    DESKTOP_CODEX_HOME,
    DESKTOP_CODEX_SESSION_STATE,
    DESKTOP_CODEX_SESSIONS,
    clear_session_id,
    load_session_id as load_codex_session_id,
    save_session_id as save_codex_session_id,
    session_path as codex_session_path,
    session_id_from_file,
    snapshot as codex_wallet_snapshot,
)
from backend.grok_worker_contract import (
    DEV_GROK_HOME,
    GROK_BIN,
    GROK_CWD,
    GROK_TUI_TERMINAL_ID,
    build_grok_tui_argv,
)
from backend.mini_vt import MiniVt
from backend.surface_intent import parse_surface_intent
from backend import shell_load
from backend import web_surface
from backend import gpt_memory_commands

BASH = "/bin/bash"
_PTY_READ_BUDGET = 48 * 1024
_PTY_DRAIN_MS = 32
_PTY_BACKUP_MS = 500
_PTY_WRITE_CHUNK = 16 * 1024
_GPT_CAPTURE_WINDOW_S = 30.0
_GPTUI_DEVELOPER_INSTRUCTIONS_MAX_CHARS = 14_000
_GAME_KEYS = {
    0x01000012: 6,
    0x01000014: 7,
    0x01000013: 4,
    0x01000015: 5,
    0x01000004: 3,
    0x01000005: 3,
    32: 2,
    90: 0,
    88: 8,
    65: 8,
    83: 0,
    81: 10,
    87: 11,
}
SCRATCH_ROOT = (
    Path("/home/GG/.local/state/goldgoblins/gg-ai-desktop/scratch")
)
_SCRATCH_NAME = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
_ANSI = re.compile(
    r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))"
)
_GPT_SHARED_COMMANDS = (
    "/flush",
    "/dream",
    "/memory",
    "/remember",
    "/skills",
    "/plugins",
    "/hooks-list",
    "/hooks-trust",
    "/hooks-add",
)
_UNRECOGNIZED_GPT_COMMAND = re.compile(
    r"Unrecognized command ['\"](/(?:flush|dream|memory|remember|skills|plugins|hooks-list|hooks-trust|hooks-add)(?: [^'\"\r\n]*)?)['\"]",
    re.IGNORECASE,
)


def _strip_ansi(text: str) -> str:
    cleaned = _ANSI.sub("", text)
    cleaned = cleaned.replace("\x00", "")
    return cleaned.replace("\r\n", "\n").replace("\r", "\n")


class _EmuWorker(QThread):
    framed = Signal(bytes, int, int, int, int, bytes)

    def __init__(self) -> None:
        super().__init__()
        self._keep = True
        self.setObjectName("gg-libretro")

    def stop(self) -> None:
        self._keep = False

    def run(self) -> None:
        while self._keep:
            started = time.monotonic()
            if libretro_host.loaded() and not media_host._paused:
                libretro_host.run()
                raw, width, height, pitch, pixel = libretro_host.frame()
                pcm = bytes(libretro_host.audio_bytes())
                if raw:
                    self.framed.emit(
                        raw,
                        int(width),
                        int(height),
                        int(pitch),
                        int(pixel),
                        pcm,
                    )
            fps = max(1.0, float(libretro_host.fps() or 60.0))
            remain = (1.0 / fps) - (time.monotonic() - started)
            if remain > 0.0:
                time.sleep(min(remain, 0.05))
            elif self._keep:
                time.sleep(0.001)


class ChatSurfaceHost(QObject):
    chatTerminalOutput = Signal(str, str)
    chatTerminalExit = Signal(str, int)
    chatTerminalNotice = Signal(str, str)
    chatTerminalFocusRequested = Signal(str)
    grokTuiChunk = Signal(str)
    grokWalletChanged = Signal(str)
    gptWalletChanged = Signal(str)
    webOperatorCommand = Signal(str)
    chatSessionsChanged = Signal(str)
    qmlLiveReload = Signal()
    workspaceFileChanged = Signal(str, str, str)
    siteImportProgress = Signal(str, int, int, str)
    mediaFrameSeqChanged = Signal()
    mediaStateChanged = Signal()
    mediaSeekChanged = Signal(float)
    terminalScrollChanged = Signal(str, int, int, int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sessions: dict[str, dict[str, Any]] = {}
        self._preview: QProcess | None = None
        self._preview_origin = ""
        self._qml_root: QObject | None = None
        self._tui_embed: object | None = None
        self._tui_grid: object | None = None
        self._tmog_embed: object | None = None
        self._media_embed: object | None = None
        self._torlink_embed: object | None = None
        self._draw_embed: object | None = None
        self._pending_tui_size: tuple[int, int] | None = None
        self._fs: QFileSystemWatcher | None = None
        self._fs_suppress: set[str] = set()
        self._wallet_pty: dict[str, Any] = {}
        self._wallet_live_base: int | None = None
        self._wallet_last_turn: int | None = None
        self._wallet_json = ""
        self._gpt_wallet_json = ""
        # The old state file was written by a host-wide mtime scan and can
        # point at the parent Codex conversation.  GPTUI keeps its active
        # pointer and new rollout root separate; legacy sessions remain
        # resumable when selected explicitly.
        self._legacy_gpt_session_id = load_codex_session_id()
        self._gpt_session_id = load_codex_session_id(
            DESKTOP_CODEX_SESSION_STATE
        )
        if self._legacy_gpt_session_id and not self._gpt_session_id:
            # This pointer was produced by the old host-wide mtime scan. It
            # commonly identifies the parent Codex conversation, not GPTUI.
            # Remove only its catalog row; the JSONL session remains intact.
            forget_session(self._legacy_gpt_session_id)
        self._gpt_started_at = 0.0
        self._gpt_capture_attempts = 0
        self._gpt_capture_root: Path | None = None
        self._gpt_capture_roots: tuple[Path, ...] = ()
        self._gpt_capture_before: set[Path] = set()
        self._gpt_capture_deadline = 0.0
        self._gpt_capture_timer = QTimer(self)
        self._gpt_capture_timer.setSingleShot(True)
        self._gpt_capture_timer.timeout.connect(self._capture_gpt_session)
        self._gpt_codex_home = CODEX_SESSIONS.parent
        self._gpt_sessions_root = CODEX_SESSIONS
        self._gpt_input_line = ""
        self._gpt_pending_local_commands: list[str] = []
        self._gpt_output_tail = ""
        # Native GPT/Grok TUI input normally goes straight to the child PTY.
        # The Workbench installs this callback so an ordinary chat task, or a
        # bare ja/nej response to a pending task, can enter the same
        # task-scoped mandate path as the QML composer.  The callback is
        # intentionally optional: shell-like terminal surfaces remain raw.
        self._tui_chat_line_handler: Callable[[str, str], bool] | None = None
        self._tui_input_lines: dict[str, str] = {}
        self._sessions_json = ""
        self._pending_resume = ""
        self._wallet_timer = QTimer(self)
        self._wallet_timer.setInterval(15000)
        self._wallet_timer.timeout.connect(self._emit_wallet)
        self._wallet_timer.start()
        self._qml_watch: QFileSystemWatcher | None = None
        self._web_op_watch: QFileSystemWatcher | None = None
        self._desk_op_watch: QFileSystemWatcher | None = None
        self._desk_job: dict[str, Any] | None = None
        self._desk_observation_seq = 0
        self._desk_timer = QTimer(self)
        self._desk_timer.setInterval(16)
        self._desk_timer.timeout.connect(self._desk_tick)
        self._imported_zips: set[str] = set()
        self._qml_reload = QTimer(self)
        self._qml_reload.setSingleShot(True)
        self._qml_reload.setInterval(250)
        self._qml_reload.timeout.connect(self._emit_qml_reload)
        self._emu: _EmuWorker | None = None
        self._crypto_timer = QTimer(self)
        self._crypto_timer.setInterval(60000)
        self._crypto_timer.timeout.connect(self._crypto_idle_tick)
        self._crypto_timer.start()
        self._tmog_pulse_at = 0.0
        self._tmog_pulse_raw = ""
        self._chat_io_at = 0.0
        self._console_provider = None
        self._console_provider_added = False
        self._console_sink = None
        self._console_io = None
        self._frame_seq = 0
        self._winch = QTimer(self)
        self._winch.setSingleShot(True)
        self._winch.setInterval(80)
        self._winch.timeout.connect(self._apply_tui_winsize)
        # A PTY response can make Qt move focus to the surrounding shell while
        # the native TUI is still visible.  Debounce a focus handoff until the
        # output has gone quiet so the next prompt is immediately typeable,
        # without stealing focus continuously while the user is working in a
        # different part of the desktop.
        self._tui_focus_terminal = ""
        self._tui_focus_timer = QTimer(self)
        self._tui_focus_timer.setSingleShot(True)
        self._tui_focus_timer.setInterval(180)
        self._tui_focus_timer.timeout.connect(self._emit_tui_focus_request)
        self._webengine_ready = False
        # QML shell reloads replace the items that host the embedded terminal
        # grids.  Keep the current host objects explicit so an old signal or
        # grid can never survive into the new scene.
        self._gpt_hole = None
        self._native_hole = None
        self._gpt_connected_hole = None
        self._native_connected_hole = None
        self._qml_rebind_timer = QTimer(self)
        self._qml_rebind_timer.setSingleShot(True)
        self._qml_rebind_timer.setInterval(120)
        self._qml_rebind_timer.timeout.connect(self._rebind_qml_surfaces)
        self._qml_rebind_attempts = 0

    def set_qml_root(self, root: QObject | None) -> None:
        self._qml_root = root
        self._attach_gpt_tui()
        self.watchDesktopWorkspace()
        self._attach_native_tui()
        self._ensure_console_provider()
        QTimer.singleShot(0, self._emit_wallet)

    def _attach_gpt_tui(self) -> None:
        from PySide6.QtQuick import QQuickItem
        hole = self._qml_root.findChild(QQuickItem, "gptTuiHost") if self._qml_root else None
        if hole is None:
            return
        old_hole = getattr(self, "_gpt_hole", None)
        if old_hole is not None and old_hole is not hole:
            try:
                old_hole.visibleChanged.disconnect(self._show_gpt_tui)
            except (AttributeError, TypeError, RuntimeError):
                pass
        grid = getattr(self, "_gpt_grid", None)
        if grid is not None and self._grid_parent(grid) is not hole:
            self._dispose_terminal_grid("_gpt_grid")
        self._gpt_hole = hole
        if self._gpt_connected_hole is not hole:
            try:
                hole.visibleChanged.connect(self._show_gpt_tui)
                self._gpt_connected_hole = hole
            except (AttributeError, TypeError, RuntimeError):
                self._gpt_hole = None
                return
        self._show_gpt_tui()

    def _show_gpt_tui(self) -> None:
        hole = self._gpt_hole
        if hole is None:
            return
        try:
            if not hole.isVisible():
                return
        except RuntimeError:
            self._gpt_hole = None
            return
        grid = getattr(self, "_gpt_grid", None)
        if grid is not None and self._grid_parent(grid) is not hole:
            self._dispose_terminal_grid("_gpt_grid")
            grid = None
        if grid is None or getattr(grid, "_thread", None) is None:
            from backend.terminal_grid import TerminalGrid
            grid = TerminalGrid(hole)
            self._gpt_grid = grid
            grid.dataProduced.connect(self.gptTuiWrite)
            grid.terminalReplyProduced.connect(self.gptTuiTerminalReply)
            grid.scrollMetricsChanged.connect(
                lambda offset, maximum, page: self.terminalScrollChanged.emit(
                    "ws.tui.gpt", offset, maximum, page))
            grid.resized.connect(self._resize_gpt_tui)
            grid.ready.connect(self._start_gpt_tui)
        else:
            self._start_gpt_tui()
        try:
            grid.forceActiveFocus()
        except (AttributeError, RuntimeError):
            self._dispose_terminal_grid("_gpt_grid")

    @staticmethod
    def _grid_parent(grid: object):
        try:
            parent = getattr(grid, "parentItem", None)
            return parent() if callable(parent) else None
        except (AttributeError, RuntimeError):
            return None

    def _dispose_terminal_grid(self, attr: str) -> None:
        grid = getattr(self, attr, None)
        if grid is None:
            return
        setattr(self, attr, None)
        stop = getattr(grid, "_stop_worker", None)
        if callable(stop):
            stop()
        try:
            grid.setParentItem(None)
        except (AttributeError, RuntimeError):
            pass
        try:
            grid.deleteLater()
        except (AttributeError, RuntimeError):
            pass

    def _rebind_qml_surfaces(self) -> None:
        """Reconnect native terminal items after an asynchronous QML reload."""
        root = self._qml_root
        if root is None:
            return
        self._attach_gpt_tui()
        self._attach_native_tui()
        from PySide6.QtQuick import QQuickItem
        if root.findChild(QQuickItem, "gptTuiHost") is None and self._qml_rebind_attempts < 20:
            self._qml_rebind_attempts += 1
            self._qml_rebind_timer.start()
        else:
            self._qml_rebind_attempts = 0

    def _resize_gpt_tui(self, cols: int, rows: int) -> None:
        self._gpt_size = (max(8, min(240, cols)), max(4, min(80, rows)))
        session = self._sessions.get("ws.tui.gpt")
        if session is not None:
            width, height = self._gpt_size
            try:
                fcntl.ioctl(session["master"], termios.TIOCSWINSZ,
                            struct.pack("HHHH", height, width, 0, 0))
                os.kill(session["proc"].pid, signal.SIGWINCH)
            except OSError:
                pass

    @staticmethod
    def _ensure_gpt_codex_home() -> bool:
        """Prepare an isolated Codex home for GPTUI-created sessions.

        Authentication and configuration stay in the user's normal Codex
        home through read-only symlinks. GPTUI state and rollout JSONL stay
        isolated when Codex honors CODEX_HOME; the shared home is only a
        last-resort fallback when this directory cannot be prepared.
        """
        try:
            DESKTOP_CODEX_HOME.mkdir(mode=0o700, parents=True, exist_ok=True)
            for name in ("auth.json", "config.toml", "rules", "skills"):
                source = CODEX_SESSIONS.parent / name
                target = DESKTOP_CODEX_HOME / name
                if target.exists() or target.is_symlink() or not source.exists():
                    continue
                target.symlink_to(
                    source,
                    target_is_directory=source.is_dir(),
                )
            return True
        except OSError:
            return False

    @staticmethod
    def _gpt_session_location(
        session_id: str,
    ) -> tuple[Path, Path] | None:
        sid = str(session_id or "").strip()
        if not sid:
            return None
        desktop_path = codex_session_path(
            sid,
            sessions_root=DESKTOP_CODEX_SESSIONS,
        )
        if desktop_path is not None:
            return DESKTOP_CODEX_HOME, DESKTOP_CODEX_SESSIONS
        shared_path = codex_session_path(
            sid,
            sessions_root=CODEX_SESSIONS,
        )
        if shared_path is not None:
            return CODEX_SESSIONS.parent, CODEX_SESSIONS
        return None

    @staticmethod
    def _session_files(sessions_root: Path) -> set[Path]:
        try:
            return set(sessions_root.rglob("*.jsonl"))
        except OSError:
            return set()

    @staticmethod
    def _gpt_session_capture_roots(
        preferred_root: Path,
    ) -> tuple[Path, ...]:
        """Return roots that belong to this GPTUI launch.

        Codex normally writes a TUI's rollout below the CODEX_HOME used to
        launch that TUI. Some CLI versions still write rollout JSONL to the
        shared home, however, even when CODEX_HOME points at GPTUI's isolated
        state directory. Watch the matching canonical fallback as well, while
        keeping arbitrary test/custom roots isolated.
        """
        roots = [preferred_root]
        fallback = None
        if preferred_root == DESKTOP_CODEX_SESSIONS:
            fallback = CODEX_SESSIONS
        elif preferred_root == CODEX_SESSIONS:
            fallback = DESKTOP_CODEX_SESSIONS
        if fallback is not None and fallback not in roots:
            roots.append(fallback)
        return tuple(roots)

    @staticmethod
    def _gptui_developer_instructions() -> str:
        """Build Codex's hidden shared profile layer for the GPTUI session.

        GPTUI receives ordinary user turns through its PTY. The profile layer
        therefore belongs in Codex's developer-instruction channel, which is
        injected into model context without becoming a visible user message
        or part of the rendered TUI transcript.
        """
        try:
            from backend.omni_gpt_profiles import build_context

            context = build_context(
                "",
                max_chars=_GPTUI_DEVELOPER_INSTRUCTIONS_MAX_CHARS,
                include_registry=True,
            )
        except Exception:
            context = (
                "[GG OMNIGPT PROFILE LAYER]\n"
                "Profile source unavailable; follow AGENTS.md and "
                "Idékompassen.\n"
                "[/GG OMNIGPT PROFILE LAYER]"
            )
        return (
            context
            + "\n"
            + "This is hidden shared developer guidance. Apply it internally "
            + "and never repeat or expose the profile layer in the user-facing "
            + "conversation. Keep GG Idékompassen as the default lens and "
            + "consult the relevant local profile package internally when a "
            + "turn needs domain expertise."
        )

    def _start_gpt_tui(self) -> bool:
        if "ws.tui.gpt" in self._sessions:
            return True
        grid = getattr(self, "_gpt_grid", None)
        if grid is None:
            return False
        binary = shutil.which("codex")
        if not binary:
            grid.feed_bytes(b"\r\nCodex CLI saknas. Installera Codex och starta om GG AI Desktop.\r\n")
            return False
        width, height = getattr(self, "_gpt_size", (
            getattr(grid, "_last_cols", 72) or 72,
            getattr(grid, "_last_rows", 36) or 36))
        master, slave = pty.openpty()
        resume_id = self._gpt_session_id
        if resume_id:
            location = self._gpt_session_location(resume_id)
            if location is None:
                resume_id = ""
                self._gpt_session_id = ""
            else:
                self._gpt_codex_home, self._gpt_sessions_root = location
        if not resume_id:
            # Keep newly-created GPTUI sessions away from the parent Codex
            # motor.  Fall back to the canonical home only if the isolated
            # state directory cannot be prepared.
            if self._ensure_gpt_codex_home():
                self._gpt_codex_home = DESKTOP_CODEX_HOME
                self._gpt_sessions_root = DESKTOP_CODEX_SESSIONS
            else:
                self._gpt_codex_home = CODEX_SESSIONS.parent
                self._gpt_sessions_root = CODEX_SESSIONS
        # Keep watching after startup too: a rollout may be created lazily,
        # after the PTY has rendered its first prompt. The baseline prevents
        # the current/resumed rollout from being mistaken for that new
        # session.
        self._gpt_capture_root = self._gpt_sessions_root
        self._gpt_capture_roots = self._gpt_session_capture_roots(
            self._gpt_capture_root
        )
        self._gpt_capture_before = set()
        for root in self._gpt_capture_roots:
            self._gpt_capture_before.update(self._session_files(root))
        # Keep GPTUI on the model's paid priority/"Fast" tier while
        # preserving the configured reasoning effort (currently Max for
        # gpt-5.6-luna).
        argv = [
            binary,
            "-c",
            'service_tier="priority"',
            "-c",
            "developer_instructions="
            + json.dumps(
                self._gptui_developer_instructions(),
                ensure_ascii=True,
            ),
            "--no-alt-screen",
        ]
        if resume_id:
            argv.extend(["resume", resume_id])
        self._gpt_started_at = time.time()
        self._gpt_capture_attempts = 0
        try:
            fcntl.ioctl(slave, termios.TIOCSWINSZ,
                        struct.pack("HHHH", height, width, 0, 0))
            os.set_blocking(master, False)
            env = os.environ.copy()
            env.update(TERM="xterm-256color", COLORTERM="truecolor",
                       LANG="C.UTF-8", LC_ALL="C.UTF-8",
                       LINES=str(height), COLUMNS=str(width),
                       CODEX_HOME=str(self._gpt_codex_home))
            proc = subprocess.Popen(
                argv + [
                    "--sandbox", "workspace-write",
                    "--ask-for-approval", "on-request",
                ],
                stdin=slave, stdout=slave, stderr=slave, cwd=str(GROK_CWD),
                env=env, start_new_session=True, close_fds=True)
        except OSError as exc:
            os.close(master)
            if getattr(self, "_gpt_grid", None) is grid:
                grid.feed_bytes(
                    ("\r\nCodex kunde inte starta: " + str(exc) + "\r\n")
                    .encode()
                )
            return False
        finally:
            os.close(slave)
        self._watch_pty("ws.tui.gpt", proc, master)
        # Do not scan both Codex session trees merely because the terminal
        # started.  A rollout is captured when GPTUI actually submits input;
        # keeping a timer alive while the terminal is idle caused needless
        # recursive filesystem scans at startup.
        return True

    @Slot(result=bool)
    def startGptTui(self) -> bool:
        """Start GPTUI when a Workbench task must resume in the visible TUI."""
        existing = self._sessions.get("ws.tui.gpt")
        if existing is not None:
            proc = existing.get("proc")
            if proc is None or proc.poll() is None:
                return True
        return self._start_gpt_tui()

    def _capture_gpt_session(self) -> None:
        if "ws.tui.gpt" not in self._sessions:
            return
        if self._gpt_capture_root is None or not self._gpt_capture_roots:
            return
        newest = ""
        newest_root: Path | None = None
        newest_path: Path | None = None
        newest_mtime = self._gpt_started_at - 1
        try:
            for root in self._gpt_capture_roots:
                for path in root.rglob("*.jsonl"):
                    if path in self._gpt_capture_before:
                        continue
                    try:
                        mtime = path.stat().st_mtime
                    except OSError:
                        continue
                    if mtime < self._gpt_started_at - 2 or mtime < newest_mtime:
                        continue
                    sid = session_id_from_file(path)
                    if sid:
                        newest = sid
                        newest_mtime = mtime
                        newest_root = root
                        newest_path = path
        except OSError:
            return
        if newest:
            self._adopt_gpt_session(newest, sessions_root=newest_root)
            if newest_path is not None:
                self._gpt_capture_before.add(newest_path)
            self._gpt_capture_attempts = 0
            self._gpt_capture_deadline = 0.0
            self._gpt_capture_timer.stop()
        else:
            session = self._sessions.get("ws.tui.gpt")
            process = session.get("proc") if session is not None else None
            # A fresh Codex rollout may not be written until the user's first
            # prompt completes. Give that one rollout a bounded window, then
            # wait for the next explicit GPTUI submission to re-arm capture.
            # This prevents an idle READY terminal from scanning forever.
            now = time.monotonic()
            if (
                process is not None
                and process.poll() is None
                and self._gpt_capture_deadline > now
            ):
                self._gpt_capture_attempts += 1
                delay = 500 if self._gpt_capture_attempts <= 10 else 2000
                self._gpt_capture_timer.start(delay)
            else:
                self._gpt_capture_attempts = 0
                self._gpt_capture_deadline = 0.0
                self._gpt_capture_timer.stop()

    def _arm_gpt_session_capture(self) -> None:
        """Retry capture for a rollout created inside the live GPTUI PTY."""
        if "ws.tui.gpt" not in self._sessions:
            return
        if self._gpt_capture_root is None or not self._gpt_capture_roots:
            return
        self._gpt_capture_attempts = 0
        self._gpt_capture_deadline = (
            time.monotonic() + _GPT_CAPTURE_WINDOW_S
        )
        self._gpt_capture_timer.start(250)

    def _reset_gpt_terminal(self) -> None:
        grid = getattr(self, "_gpt_grid", None)
        reset = getattr(grid, "reset_terminal", None)
        if callable(reset):
            reset()

    def _start_fresh_gpt_session(self) -> bool:
        """Switch GPTUI to a new Codex rollout before the next prompt.

        `/new` is a navigation command for the desktop shell. Letting the
        old PTY receive its final Enter means the old Codex process can handle
        the command and keep the next answer attached to the wrong session.
        Close that PTY first, clear only GPTUI's active pointer, and launch a
        fresh Codex process so its next rollout can be adopted into CHATS.
        """
        old_id = self._gpt_session_id
        old_home = self._gpt_codex_home
        old_root = self._gpt_sessions_root
        had_session = "ws.tui.gpt" in self._sessions
        if had_session:
            self._close("ws.tui.gpt")
        self._reset_gpt_terminal()

        self._gpt_session_id = ""
        self._pending_resume = ""
        self._gpt_input_line = ""
        self._gpt_pending_local_commands.clear()
        self._gpt_output_tail = ""
        clear_session_id(DESKTOP_CODEX_SESSION_STATE)
        # Remove the old current marker immediately. The new rollout may not
        # be written until Codex has rendered its first prompt.
        self._emit_wallet()

        if self._start_gpt_tui():
            return True

        # Starting the fresh process can fail transiently (for example while
        # the binary is being replaced). Restore the previous resumable chat
        # so a failed `/new` does not strand the user without GPTUI.
        self._gpt_session_id = old_id
        self._gpt_codex_home = old_home
        self._gpt_sessions_root = old_root
        if old_id:
            save_codex_session_id(old_id, DESKTOP_CODEX_SESSION_STATE)
        else:
            clear_session_id(DESKTOP_CODEX_SESSION_STATE)
        if old_id and getattr(self, "_gpt_grid", None) is not None:
            self._start_gpt_tui()
        self._emit_wallet()
        return False

    def _adopt_gpt_session(
        self,
        session_id: str,
        sessions_root: Path | None = None,
    ) -> None:
        """Make a real Codex session the active shared-chat session."""
        sid = str(session_id or "").strip()
        if not sid:
            return
        if sessions_root is not None:
            self._gpt_sessions_root = sessions_root
            self._gpt_codex_home = (
                DESKTOP_CODEX_HOME
                if sessions_root == DESKTOP_CODEX_SESSIONS
                else CODEX_SESSIONS.parent
            )
        self._gpt_session_id = save_codex_session_id(
            sid,
            DESKTOP_CODEX_SESSION_STATE,
        ) or sid
        sync_owned([sid], engine="GPT_TUI")
        self._emit_wallet()

    @Slot(str, result=bool)
    def activateGptTui(self, session_id: str) -> bool:
        """Bring the persistent GPT TUI session back into view and focus."""
        sid = str(session_id or "").strip()
        hole = getattr(self, "_gpt_hole", None)
        if hole is None or not hole.isVisible():
            return False
        if sid:
            location = self._gpt_session_location(sid)
            if location is None:
                return False
        if sid and sid != self._gpt_session_id:
            old_id = self._gpt_session_id
            old_home = self._gpt_codex_home
            old_root = self._gpt_sessions_root
            if "ws.tui.gpt" in self._sessions:
                self._close("ws.tui.gpt")
            self._reset_gpt_terminal()
            self._gpt_session_id = save_codex_session_id(
                sid,
                DESKTOP_CODEX_SESSION_STATE,
            ) or sid
            self._gpt_codex_home, self._gpt_sessions_root = location
            sync_owned([sid], engine="GPT_TUI")
            self._show_gpt_tui()
            if "ws.tui.gpt" not in self._sessions:
                grid = getattr(self, "_gpt_grid", None)
                if grid is not None and getattr(grid, "_thread", None) is None:
                    # TerminalGrid has not emitted ready yet. Keep the
                    # selected id; its ready callback will start this exact
                    # session after the visibility switch settles.
                    return True
                # A bad resume must not leave the user with a dead chat. Put
                # the previous selection back and only restore it on a
                # subsequent explicit activation.
                self._gpt_session_id = old_id
                self._gpt_codex_home = old_home
                self._gpt_sessions_root = old_root
                if old_id:
                    save_codex_session_id(
                        old_id,
                        DESKTOP_CODEX_SESSION_STATE,
                    )
                return False
            return True
        self._show_gpt_tui()
        return getattr(self, "_gpt_grid", None) is not None

    @Slot(result=str)
    def hydrateDesktop(self) -> str:
        self._attach_native_tui()
        # Wallet/session telemetry can scan a growing JSONL rollout. Queue it
        # after the QML shell has returned to the event loop so reload never
        # leaves the full-window hydration overlay visible while that scan
        # runs.
        QTimer.singleShot(0, lambda: self._emit_wallet())
        return self.cryptoRailStatus()

    def _tui_hole(self):
        root = self._qml_root
        if root is None:
            return None
        from PySide6.QtQuick import QQuickItem

        item = root.findChild(QQuickItem, "grokTuiHost")
        return item

    def _attach_native_tui(self) -> None:
        hole = self._tui_hole()
        if hole is None:
            return
        old_hole = getattr(self, "_native_hole", None)
        if old_hole is not None and old_hole is not hole:
            try:
                old_hole.visibleChanged.disconnect(self._on_tui_hole_visible)
            except (AttributeError, TypeError, RuntimeError):
                pass
        self._native_hole = hole
        if self._native_connected_hole is not hole:
            try:
                hole.visibleChanged.connect(self._on_tui_hole_visible)
                self._native_connected_hole = hole
            except (AttributeError, TypeError, RuntimeError):
                pass
        if hole.isVisible():
            self._ensure_tui_grid()

    def _ensure_tui_grid(self) -> None:
        hole = self._tui_hole()
        if hole is None:
            return
        grid = self._tui_grid
        if grid is not None and self._grid_parent(grid) is hole:
            if hole.isVisible():
                grid.forceActiveFocus()
            return
        if grid is not None:
            stop = getattr(grid, "_stop_worker", None)
            if callable(stop):
                stop()
            grid.setParentItem(None)
            grid.deleteLater()
            self._tui_grid = None
        from backend.terminal_grid import TerminalGrid

        grid = TerminalGrid(hole)
        grid.dataProduced.connect(self.grokTuiWrite)
        grid.terminalReplyProduced.connect(self.grokTuiTerminalReply)
        grid.scrollMetricsChanged.connect(
            lambda offset, maximum, page: self.terminalScrollChanged.emit(
                GROK_TUI_TERMINAL_ID, offset, maximum, page))
        grid.resized.connect(self.grokTuiResize)
        grid.ready.connect(self._on_native_tui_ready)
        self._tui_grid = grid
        if hole.isVisible():
            grid.forceActiveFocus()

    def _on_native_tui_ready(self) -> None:
        hole = self._tui_hole()
        if hole is not None and hole.isVisible():
            self.startGrokTui("ws.tui.grok")

    def _run_gpt_shared_command(self, command: str) -> bool:
        command = str(command or "").strip()
        if not any(
            command == item or command.startswith(item + " ")
            for item in _GPT_SHARED_COMMANDS
        ):
            return False
        grid = getattr(self, "_gpt_grid", None)
        result = gpt_memory_commands.run(command)
        if grid is not None:
            grid.feed_bytes(("\r\n" + result + "\r\n").encode("utf-8"))
        elif result:
            self.chatTerminalOutput.emit("ws.tui.gpt", result + "\n")
        return True

    def _tui_grid_for_terminal(self, terminal_id: str) -> object | None:
        key = str(terminal_id or "").strip()
        if key == "ws.tui.gpt":
            return getattr(self, "_gpt_grid", None)
        if key == GROK_TUI_TERMINAL_ID:
            return self._tui_grid
        return None

    def _tui_focus_is_owned_by_terminal(
        self,
        terminal_id: str,
        grid: object,
    ) -> bool:
        """Return whether refocusing this terminal would preserve user input.

        PTY output is asynchronous.  By the time the debounced focus request
        fires, the user may already be typing in another control.  Walking
        the active Quick item back to the terminal host lets us restore focus
        after startup without stealing it from a field the user selected.
        """
        try:
            window_getter = getattr(grid, "window", None)
            window = window_getter() if callable(window_getter) else None
            active_getter = getattr(window, "activeFocusItem", None)
            active = active_getter() if callable(active_getter) else None
            # During startup/offscreen tests there may be no active item yet;
            # the normal activation path is allowed to establish focus then.
            if active is None:
                return True

            allowed: list[object] = [grid]
            hole = (
                getattr(self, "_gpt_hole", None)
                if str(terminal_id or "").strip() == "ws.tui.gpt"
                else getattr(self, "_native_hole", None)
            )
            if hole is not None:
                allowed.append(hole)

            item = active
            for _ in range(64):
                if any(item is candidate or item == candidate for candidate in allowed):
                    return True
                parent_getter = getattr(item, "parentItem", None)
                if not callable(parent_getter):
                    return False
                parent = parent_getter()
                if parent is None or parent is item:
                    return False
                item = parent
        except (AttributeError, RuntimeError, TypeError):
            return False
        return False

    def _arm_tui_focus(self, terminal_id: str) -> None:
        key = str(terminal_id or "").strip()
        if key not in {GROK_TUI_TERMINAL_ID, "ws.tui.gpt"}:
            return
        self._tui_focus_terminal = key
        self._tui_focus_timer.start()

    def _emit_tui_focus_request(self) -> None:
        key = self._tui_focus_terminal
        self._tui_focus_terminal = ""
        if key in self._sessions:
            grid = self._tui_grid_for_terminal(key)
            if grid is not None:
                try:
                    if not grid.isVisible():
                        return
                except (AttributeError, RuntimeError):
                    return
                if not self._tui_focus_is_owned_by_terminal(key, grid):
                    return
            self.chatTerminalFocusRequested.emit(key)

    def _commands_from_gpt_output(self, text: str) -> list[str]:
        """Find local commands even when Codex output crosses PTY reads."""
        combined = self._gpt_output_tail + str(text or "")
        matches = list(_UNRECOGNIZED_GPT_COMMAND.finditer(combined))
        if matches:
            self._gpt_output_tail = combined[matches[-1].end() :][-512:]
        else:
            self._gpt_output_tail = combined[-512:]
        commands: list[str] = []
        for match in matches:
            reported = match.group(1)
            reported_name = reported.partition(" ")[0].lower()
            queued = next(
                (
                    index
                    for index, command in enumerate(self._gpt_pending_local_commands)
                    if command.partition(" ")[0].lower() == reported_name
                ),
                None,
            )
            commands.append(
                self._gpt_pending_local_commands.pop(queued)
                if queued is not None
                else reported
            )
        return commands

    def _scan_gpt_input(self, payload: str) -> tuple[str, list[str]]:
        line = self._gpt_input_line
        submitted: list[str] = []
        # Strip terminal control sequences and bracketed-paste framing so
        # local slash-command detection only sees the user's text. Terminal
        # replies are kept off this path by TerminalGrid's separate signal.
        text = _ANSI.sub("", str(payload or ""))
        for char in text:
            if char in "\r\n":
                submitted.append(line.strip())
                line = ""
            elif char in "\b\x7f":
                line = line[:-1]
            elif char in "\x03\x15":
                line = ""
            elif char.isprintable():
                line += char
        return line, submitted

    def set_tui_chat_line_handler(
        self,
        handler: Callable[[str, str], bool] | None,
    ) -> None:
        """Install the Workbench ingress for submitted native TUI lines."""
        self._tui_chat_line_handler = handler

    def _scan_tui_input(
        self,
        terminal_id: str,
        payload: str,
    ) -> tuple[str, list[str]]:
        key = str(terminal_id or "").strip()
        line = self._tui_input_lines.get(key, "")
        submitted: list[str] = []
        text = _ANSI.sub("", str(payload or ""))
        for char in text:
            if char in "\r\n":
                submitted.append(line.strip())
                line = ""
            elif char in "\b\x7f":
                line = line[:-1]
            elif char in "\x03\x15":
                line = ""
            elif char.isprintable():
                line += char
        return line, submitted

    def _remember_tui_input(self, terminal_id: str, line: str) -> None:
        self._tui_input_lines[str(terminal_id or "").strip()] = line

    def _remember_gpt_input(
        self,
        line: str,
        submitted: list[str],
    ) -> None:
        self._gpt_input_line = line
        for command in submitted:
            if any(
                command == item or command.startswith(item + " ")
                for item in _GPT_SHARED_COMMANDS
            ):
                self._gpt_pending_local_commands.append(command)

    def _track_gpt_input(self, payload: str) -> None:
        """Remember submitted local commands without withholding any keys."""
        line, submitted = self._scan_gpt_input(payload)
        self._remember_gpt_input(line, submitted)

    def _on_tui_hole_visible(self, *_args) -> None:
        hole = self._tui_hole()
        if hole is None:
            return
        if not hole.isVisible():
            return
        self._ensure_tui_grid()
        grid = self._tui_grid
        if grid is not None:
            grid.forceActiveFocus()
        self.startGrokTui("ws.tui.grok")

    @Slot(result=str)
    def listShellSources(self) -> str:
        root = Path(__file__).resolve().parents[1]
        qml_root = root / "qml"
        rows: list[str] = []
        if qml_root.is_dir():
            for path in sorted(qml_root.rglob("*")):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in {".qml", ".js", ".html", ".css"}:
                    continue
                if any(part.startswith(".") for part in path.relative_to(root).parts):
                    continue
                rows.append(path.relative_to(root).as_posix())
        return json.dumps(rows)

    @Slot(result=str)
    def shellLoadQueue(self) -> str:
        return json.dumps(shell_load.queue())

    @Slot(str, result=str)
    def parseSurfaceIntent(self, text: str) -> str:
        return parse_surface_intent(text)

    @Slot(str, result=bool)
    def urlAllowed(self, url: str) -> bool:
        return web_surface.url_allowed(url)

    @Slot(str, result=bool)
    def browseUrlAllowed(self, url: str) -> bool:
        return web_surface.browse_url_allowed(url)

    @Slot(result=str)
    def webDownloadDirectory(self) -> str:
        """Return the user's existing visible-browser download directory."""
        for folder in (Path.home() / "Hämtningar", Path.home() / "Downloads"):
            try:
                if folder.is_dir() and not folder.is_symlink():
                    return str(folder)
            except OSError:
                continue
        return str(Path.home() / "Downloads")

    @Slot(str, result=str)
    def normalizeBrowseUrl(self, url: str) -> str:
        return web_surface.normalize_browse_url(url)

    @Slot(result=str)
    def defaultWebUrl(self) -> str:
        return web_surface.default_web_url()

    @Slot(result=str)
    def defaultBrowseUrl(self) -> str:
        return web_surface.default_browse_url()

    @Slot(result=str)
    @Slot(str, result=str)
    def tmogSnapshot(self, page: str = "") -> str:
        try:
            return json.dumps(
                tmog_contract.snapshot(page), separators=(",", ":")
            )
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__, "schema": tmog_contract.SCHEMA})

    @Slot(result=str)
    def tmogPulse(self) -> str:
        now = time.monotonic()
        if self._tmog_pulse_raw and now - self._tmog_pulse_at < 0.012:
            return self._tmog_pulse_raw
        try:
            raw = json.dumps(tmog_contract.pulse(), separators=(",", ":"))
        except Exception as exc:
            raw = json.dumps({"error": type(exc).__name__, "schema": tmog_contract.SCHEMA})
        self._tmog_pulse_raw = raw
        self._tmog_pulse_at = now
        return raw

    @Slot(result=bool)
    def chatIoActive(self) -> bool:
        return bool(self._chat_io_at) and (time.monotonic() - self._chat_io_at) < 0.28

    @Slot(str)
    def tmogCopy(self, text: str) -> None:
        from PySide6.QtGui import QGuiApplication

        clip = QGuiApplication.clipboard()
        if clip is None:
            return
        clip.setText(str(text or "")[:4000])

    @Slot(result=bool)
    def startTmog(self) -> bool:
        root = self._qml_root
        if root is None:
            return False
        embed = self._tmog_embed
        if embed is None:
            from backend.tmog_embed import TmogEmbed

            embed = TmogEmbed(root)
            self._tmog_embed = embed
        return bool(embed.start())

    @Slot(result=bool)
    def openTmog(self) -> bool:
        root = self._qml_root
        if root is None:
            return False
        embed = self._tmog_embed
        if embed is None:
            from backend.tmog_embed import TmogEmbed

            embed = TmogEmbed(root)
            self._tmog_embed = embed
        return bool(embed.open_full())

    @Slot()
    def hideTmog(self) -> None:
        embed = self._tmog_embed
        if embed is not None:
            embed.hide()

    @Slot(result=str)
    def drawStatus(self) -> str:
        from backend import draw_contract

        try:
            return json.dumps(draw_contract.status_payload(), separators=(",", ":"))
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__, "schema": draw_contract.SCHEMA})

    @Slot(str, result=bool)
    def drawStart(self, editor_id: str) -> bool:
        root = self._qml_root
        if root is None:
            return False
        embed = self._draw_embed
        if embed is None:
            from backend.draw_embed import DrawEmbed

            embed = DrawEmbed(root)
            self._draw_embed = embed
        return bool(embed.start(str(editor_id or "")))

    @Slot()
    def hideDraw(self) -> None:
        embed = self._draw_embed
        if embed is not None:
            embed.hide()

    def _media_embedder(self):
        root = self._qml_root
        if root is None:
            return None
        embed = self._media_embed
        if embed is None:
            from backend.media_embed import MediaEmbed

            embed = MediaEmbed(root)
            self._media_embed = embed
        return embed

    def _torlink_embedder(self):
        root = self._qml_root
        if root is None:
            return None
        embed = self._torlink_embed
        if embed is None:
            from backend.torlink_embed import TorlinkEmbed

            embed = TorlinkEmbed(root)
            self._torlink_embed = embed
        return embed

    def _hide_torlink(self) -> None:
        embed = self._torlink_embed
        if embed is not None:
            embed.hide()

    def _media_follow(self, payload: dict[str, Any]) -> dict[str, Any]:
        embed = self._media_embed
        backend = str(payload.get("backend") or "")
        kind = str(payload.get("kind") or "")
        if backend in ("qml", "libretro"):
            if embed is not None:
                embed.hide()
            self._hide_torlink()
            return payload
        if backend == "torlink":
            if embed is not None:
                embed.hide()
            return payload
        if payload.get("screen") != "EMBED":
            if embed is not None:
                embed.hide()
            self._hide_torlink()
            return payload
        self._hide_torlink()
        embed = self._media_embedder()
        if embed is None:
            return payload
        if kind == "game" or (kind == "video" and not payload.get("drawable")):
            embed.attach(media_host.player_pid(), media_host.embed_tokens())
        embed.show()
        return payload

    def _mediaFrameSeq(self) -> int:
        return int(self._frame_seq)

    mediaFrameSeq = Property(int, _mediaFrameSeq, notify=mediaFrameSeqChanged)

    def _ensure_console_provider(self) -> None:
        root = self._qml_root
        if root is None or self._console_provider_added:
            return
        from PySide6.QtGui import QImage
        from PySide6.QtQml import QQmlEngine
        from PySide6.QtQuick import QQuickImageProvider

        class _ConsoleFrames(QQuickImageProvider):
            def __init__(self) -> None:
                super().__init__(QQuickImageProvider.ImageType.Image)
                self.image = QImage()

            def requestImage(self, ident, size, requested_size):  # type: ignore[no-untyped-def]
                return self.image

        ctx = QQmlEngine.contextForObject(root)
        if ctx is None or ctx.engine() is None:
            return
        self._console_provider = _ConsoleFrames()
        ctx.engine().addImageProvider("console", self._console_provider)
        self._console_provider_added = True

    def _console_sync(self, payload: dict[str, Any]) -> None:
        if str(payload.get("backend") or "") == "libretro" and libretro_host.loaded():
            self._ensure_console_provider()
            self._console_start_audio()
            self._start_emu()
            return
        self._stop_emu()
        self._console_stop_audio()

    def _start_emu(self) -> None:
        worker = self._emu
        if worker is not None and worker.isRunning():
            return
        worker = _EmuWorker()
        worker.framed.connect(self._on_emu_frame)
        self._emu = worker
        worker.start()

    def _stop_emu(self) -> None:
        worker = self._emu
        self._emu = None
        if worker is None:
            return
        worker.stop()
        worker.wait(80)

    def _console_start_audio(self) -> None:
        if self._console_sink is not None:
            return
        try:
            from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices
        except Exception:
            return
        fmt = QAudioFormat()
        fmt.setSampleRate(int(libretro_host.sample_rate()))
        fmt.setChannelCount(2)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        try:
            device = QMediaDevices.defaultAudioOutput()
            sink = QAudioSink(device, fmt, self)
            payload = media_host.status_payload()
            sink.setVolume(max(0.0, min(1.0, int(payload.get("volume") or 70) / 100.0)))
            io = sink.start()
        except Exception:
            return
        self._console_sink = sink
        self._console_io = io

    def _console_stop_audio(self) -> None:
        sink = self._console_sink
        self._console_sink = None
        self._console_io = None
        if sink is not None:
            try:
                sink.stop()
            except Exception:
                pass

    def _on_emu_frame(
        self,
        raw: bytes,
        width: int,
        height: int,
        pitch: int,
        pixel: int,
        pcm: bytes,
    ) -> None:
        provider = self._console_provider
        if provider is not None and raw and width >= 8 and height >= 8:
            from PySide6.QtGui import QImage

            if pixel == 1:
                qfmt = QImage.Format.Format_RGB32
            elif pixel == 2:
                qfmt = QImage.Format.Format_RGB16
            else:
                qfmt = QImage.Format.Format_RGB555
            image = QImage(raw, int(width), int(height), int(pitch), qfmt)
            if not image.isNull():
                provider.image = image.copy()
                self._frame_seq += 1
                self.mediaFrameSeqChanged.emit()
        io = self._console_io
        if pcm and io is not None:
            try:
                io.write(pcm)
            except Exception:
                pass

    @Slot(int, bool)
    def mediaGameKey(self, key: int, down: bool) -> None:
        button = _GAME_KEYS.get(int(key))
        if button is None:
            return
        libretro_host.set_button(int(button), bool(down))

    def _media_status_json(self, live: bool) -> str:
        payload = media_host.status_payload(live=live)
        if live:
            return json.dumps(payload, separators=(",", ":"))
        embed = self._media_embed
        torlink = self._torlink_embed
        if torlink is not None and str(payload.get("kind") or "") == "fetch":
            payload["embed_error"] = torlink.error()
            payload["embed_attached"] = bool(torlink.attached())
        elif embed is not None:
            payload["embed_error"] = embed.error()
            payload["embed_attached"] = bool(embed.attached())
        return json.dumps(payload, separators=(",", ":"))

    @Slot(result=str)
    def mediaStatus(self) -> str:
        try:
            return self._media_status_json(False)
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__, "schema": media_host.SCHEMA})

    @Slot(result=str)
    def mediaLiveStatus(self) -> str:
        try:
            return media_host.live_status_json()
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__, "schema": media_host.SCHEMA})

    @Slot(float, result=str)
    def mediaTuneMhz(self, mhz: float) -> str:
        try:
            return self._media_changed(media_host.tune_mhz(mhz))
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__, "schema": media_host.SCHEMA})

    def _media_changed(self, payload: dict[str, Any]) -> str:
        media_host.publish_live(payload)
        self.mediaStateChanged.emit()
        return json.dumps(payload, separators=(",", ":"))

    @Slot(str, result=str)
    def mediaSetMode(self, mode: str) -> str:
        try:
            return self._media_changed(media_host.set_mode(mode))
        except ValueError as exc:
            return json.dumps({"error": str(exc)})

    @Slot(str, result=str)
    def mediaPlay(self, item_id: str) -> str:
        try:
            payload = self._media_follow(media_host.play_item(item_id))
            self._console_sync(payload)
            return self._media_changed(payload)
        except (ValueError, RuntimeError) as exc:
            return json.dumps({"error": str(exc)})

    @Slot(result=str)
    def mediaPause(self) -> str:
        return self._media_changed(media_host.pause())

    @Slot(result=str)
    def mediaStop(self) -> str:
        embed = self._media_embed
        if embed is not None:
            embed.stop()
        torlink = self._torlink_embed
        if torlink is not None:
            torlink.stop()
        payload = media_host.stop()
        self._console_sync(payload)
        return self._media_changed(payload)

    @Slot(float, float)
    def mediaReportClock(self, position: float, duration: float) -> None:
        media_host.report_clock(float(position), float(duration))

    @Slot(bool, bool)
    def mediaReportPlayerState(self, playing: bool, buffering: bool) -> None:
        changed = media_host.report_player_state(bool(playing), bool(buffering))
        if changed:
            self.mediaStateChanged.emit()

    @Slot(float, result=str)
    def mediaSeek(self, seconds: float) -> str:
        payload = media_host.seek(float(seconds))
        if str(payload.get("backend") or "") == "qml":
            self.mediaSeekChanged.emit(float(payload.get("position") or seconds))
        self.mediaStateChanged.emit()
        return json.dumps(payload, separators=(",", ":"))

    @Slot(int, result=str)
    def mediaSkip(self, delta: int) -> str:
        payload = media_host.status_payload()
        if str(payload.get("backend") or "") == "cliamp":
            return self._media_changed(media_host.skip(int(delta)))
        nxt = media_host.next_item_id(int(delta))
        if not nxt:
            return json.dumps(payload, separators=(",", ":"))
        return self.mediaPlay(nxt)

    @Slot(str, result=str)
    def mediaSearch(self, query: str) -> str:
        try:
            return self._media_changed(media_host.search(query))
        except (ValueError, RuntimeError) as exc:
            return json.dumps({"error": str(exc)})

    @Slot(int, result=str)
    def mediaSetVolume(self, volume: int) -> str:
        try:
            payload = media_host.set_volume(int(volume))
            sink = self._console_sink
            if sink is not None:
                sink.setVolume(max(0.0, min(1.0, int(payload.get("volume") or 70) / 100.0)))
            return self._media_changed(payload)
        except (TypeError, ValueError) as exc:
            return json.dumps({"error": str(exc)})

    @Slot(str, result=str)
    def mediaSetEqPreset(self, name: str) -> str:
        try:
            return self._media_changed(media_host.set_eq_preset(name))
        except (TypeError, ValueError, RuntimeError) as exc:
            return json.dumps({"error": str(exc)})

    @Slot(int, float, result=str)
    def mediaSetEqBand(self, band: int, db: float) -> str:
        try:
            return self._media_changed(media_host.set_eq_band(int(band), float(db)))
        except (TypeError, ValueError, RuntimeError) as exc:
            return json.dumps({"error": str(exc)})

    @Slot(result=str)
    def mediaStartCliamp(self) -> str:
        try:
            payload = self._media_follow(media_host.start_cliamp())
            return self._media_changed(payload)
        except RuntimeError as exc:
            return json.dumps({"error": str(exc)})

    @Slot(result=str)
    def mediaStartFetch(self) -> str:
        try:
            payload = media_host.start_fetch()
            media = self._media_embed
            if media is not None:
                media.hide()
            embed = self._torlink_embedder()
            if embed is None:
                return json.dumps({"error": "MEDIA_TORLINK_EMBED"})
            if not embed.start():
                return json.dumps({"error": embed.error() or "MEDIA_TORLINK_EMBED"})
            payload = media_host.status_payload()
            payload["screen"] = "EMBED"
            payload["embed_error"] = embed.error()
            payload["embed_attached"] = bool(embed.attached())
            return self._media_changed(payload)
        except RuntimeError as exc:
            return json.dumps({"error": str(exc)})

    @Slot()
    def hideMedia(self) -> None:
        embed = self._media_embed
        if embed is not None:
            embed.hide()
        self._hide_torlink()

    @Slot(result=str)
    def cryptoStatus(self) -> str:
        try:
            return json.dumps(crypto_host.status_payload(), separators=(",", ":"))
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__})

    @Slot(result=str)
    def cryptoRailStatus(self) -> str:
        try:
            return json.dumps(
                crypto_host.status_payload(rail=True), separators=(",", ":")
            )
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__})

    @Slot(result=str)
    def cryptoRefreshChart(self) -> str:
        try:
            crypto_host.cached_sol_chart()
            return json.dumps(crypto_host.status_payload(), separators=(",", ":"))
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__})

    @Slot(str, result=str)
    def cryptoConnectWatch(self, pubkey: str) -> str:
        try:
            return json.dumps(
                crypto_host.connect_watch(pubkey),
                separators=(",", ":"),
            )
        except ValueError as exc:
            return json.dumps({"error": str(exc)})

    @Slot(result=str)
    def cryptoCreateTestWallet(self) -> str:
        try:
            return json.dumps(
                crypto_host.create_test_wallet(),
                separators=(",", ":"),
            )
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__ + ":" + str(exc)})

    @Slot(str, result=str)
    def cryptoImportKeypair(self, path: str) -> str:
        try:
            raw = str(path or "").replace("file://", "")
            return json.dumps(
                crypto_host.import_keypair_file(raw),
                separators=(",", ":"),
            )
        except ValueError as exc:
            return json.dumps({"error": str(exc)})

    @Slot(result=str)
    def cryptoAirdrop(self) -> str:
        try:
            return json.dumps(crypto_host.airdrop_testnet(), separators=(",", ":"))
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__ + ":" + str(exc)})

    @Slot(result=str)
    def cryptoDisconnect(self) -> str:
        return json.dumps(crypto_host.disconnect(), separators=(",", ":"))

    @Slot(str, result=str)
    def cryptoSetNetwork(self, network: str) -> str:
        try:
            payload = crypto_host.set_network(network)
            if "wallet" in payload:
                return json.dumps(crypto_host.status_payload(), separators=(",", ":"))
            return json.dumps(payload, separators=(",", ":"))
        except ValueError as exc:
            return json.dumps({"error": str(exc)})

    @Slot(result=str)
    def cryptoLabOn(self) -> str:
        try:
            return json.dumps(crypto_host.lab_on(), separators=(",", ":"))
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__ + ":" + str(exc)})

    @Slot(result=str)
    def cryptoLabOff(self) -> str:
        try:
            return json.dumps(crypto_host.lab_off(), separators=(",", ":"))
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__ + ":" + str(exc)})

    @Slot(bool, result=str)
    def cryptoArmBot(self, armed: bool) -> str:
        try:
            return json.dumps(crypto_host.set_bot_armed(bool(armed)), separators=(",", ":"))
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__ + ":" + str(exc)})

    @Slot(result=str)
    def cryptoEvalSignals(self) -> str:
        try:
            return json.dumps(crypto_host.evaluate_signals(), separators=(",", ":"))
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__ + ":" + str(exc)})

    @Slot(bool, result=str)
    def cryptoArmTrader(self, armed: bool) -> str:
        try:
            return json.dumps(crypto_host.set_trader_armed(bool(armed)), separators=(",", ":"))
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__ + ":" + str(exc)})

    def _crypto_idle_tick(self) -> None:
        threading.Thread(
            target=self._crypto_idle_work,
            name="gg-crypto-idle",
            daemon=True,
        ).start()

    def _crypto_idle_work(self) -> None:
        try:
            from backend import crypto_trader

            if crypto_trader.load_state().get("armed"):
                crypto_host.tick_trader()
            bot = crypto_host.load_bot()
            if bot.get("armed"):
                crypto_host.tick_bot()
        except Exception:
            return

    @Slot(result=str)
    def cryptoTickTrader(self) -> str:
        try:
            return json.dumps(crypto_host.tick_trader(), separators=(",", ":"))
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__ + ":" + str(exc)})

    @Slot(result=str)
    def cryptoResetTrader(self) -> str:
        try:
            return json.dumps(crypto_host.reset_trader(), separators=(",", ":"))
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__ + ":" + str(exc)})

    @Slot(str, result=str)
    def cryptoSetBook(self, book_id: str) -> str:
        try:
            return json.dumps(
                crypto_host.set_trader_book(str(book_id or "")),
                separators=(",", ":"),
            )
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__ + ":" + str(exc)})

    @Slot(result=str)
    def cryptoBacktestTrader(self) -> str:
        try:
            return json.dumps(crypto_host.start_backtest_trader(), separators=(",", ":"))
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__ + ":" + str(exc)})

    @Slot(result=str)
    def cryptoTickBot(self) -> str:
        try:
            return json.dumps(crypto_host.tick_bot(), separators=(",", ":"))
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__ + ":" + str(exc)})

    @Slot(result=str)
    def cryptoFlashArb(self) -> str:
        try:
            return json.dumps(crypto_host.run_flash_arb(), separators=(",", ":"))
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__ + ":" + str(exc)})

    @Slot(result=str)
    def cryptoFlashArbReset(self) -> str:
        try:
            return json.dumps(crypto_host.reset_flash_arb(), separators=(",", ":"))
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__ + ":" + str(exc)})

    @Slot(str, result=str)
    def cryptoIngestSignal(self, raw: str) -> str:
        try:
            return json.dumps(
                crypto_host.ingest_paper_signal(raw),
                separators=(",", ":"),
            )
        except ValueError as exc:
            return json.dumps({"error": str(exc)})

    @Slot(result=str)
    def marketplaceStatus(self) -> str:
        try:
            return json.dumps(marketplace_host.status_payload(), separators=(",", ":"))
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__})

    @Slot(str, result=str)
    def marketplaceList(self, raw: str) -> str:
        try:
            return json.dumps(marketplace_host.list_item(raw), separators=(",", ":"))
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__})

    @Slot(str, result=str)
    def marketplaceDelist(self, listing_id: str) -> str:
        try:
            return json.dumps(
                marketplace_host.delist_item(listing_id), separators=(",", ":")
            )
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__})

    @Slot(str, result=str)
    def marketplacePaperBuy(self, listing_id: str) -> str:
        try:
            return json.dumps(
                marketplace_host.paper_buy(listing_id), separators=(",", ":")
            )
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__})

    @Slot(str, result=str)
    def marketplaceSelect(self, listing_id: str) -> str:
        try:
            return json.dumps(
                marketplace_host.select_listing(listing_id), separators=(",", ":")
            )
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__})

    @Slot(str, result=str)
    def marketplaceSetFilter(self, category: str) -> str:
        try:
            return json.dumps(
                marketplace_host.set_filter(category), separators=(",", ":")
            )
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__})

    @Slot(str, result=str)
    def marketplaceListElement(self, symbol: str) -> str:
        try:
            return json.dumps(
                marketplace_host.list_element(symbol), separators=(",", ":")
            )
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__})

    @Slot(str, result=str)
    def marketplaceRebirth(self, raw: str) -> str:
        try:
            return json.dumps(
                marketplace_host.rebirth_item(raw), separators=(",", ":")
            )
        except Exception as exc:
            return json.dumps({"error": type(exc).__name__})

    @Slot(result=str)
    def listSiteFiles(self) -> str:
        return web_surface.list_site_files()

    @Slot(result=str)
    def preferredSiteFile(self) -> str:
        return web_surface.preferred_site_file()

    @Slot(str, result=str)
    def siteFileUrl(self, relative: str) -> str:
        return web_surface.site_file_url(relative)

    @Slot(str, result=str)
    def readSiteFile(self, relative: str) -> str:
        return web_surface.read_site_file(relative)

    @Slot(result=str)
    def siteRoot(self) -> str:
        return str(web_surface.SITE_ROOT)

    @Slot(result=str)
    def scratchRoot(self) -> str:
        return str(SCRATCH_ROOT)

    @Slot(str, str, result=str)
    def writeSiteFile(self, relative: str, text: str) -> str:
        written = web_surface.write_site_file(relative, text)
        if written:
            self._fs_suppress.add(str(Path(written).resolve()))
        return written

    @Slot(result=str)
    def startSitePreview(self) -> str:
        import socket
        import time

        from PySide6.QtCore import QCoreApplication

        existing = str(self._preview_origin or "").strip()
        if existing.startswith("http://127.0.0.1:"):
            hostport = existing.split("://", 1)[-1].rstrip("/").split("/", 1)[0]
            port_s = hostport.split(":")[-1]
            try:
                port_n = int(port_s)
            except ValueError:
                port_n = 0
            if port_n:
                import socket as _socket

                try:
                    with _socket.create_connection(("127.0.0.1", port_n), 0.2):
                        from backend.site_database import rewrite_preview_origin

                        rewrite_preview_origin(existing)
                        return existing.rstrip("/") + "/\n" + web_surface.preview_kind()
                except OSError:
                    pass
        self.stopSitePreview()
        web_surface.ensure_site_root()
        kind = web_surface.preview_kind()
        if kind == "PHP":
            from backend.site_database import start_mysqld

            started = start_mysqld()
            if not started.startswith("PASS"):
                return ""
        port = web_surface.pick_preview_port()
        argv = web_surface.preview_argv(port)
        process = QProcess(self)
        process.setProgram(argv[0])
        process.setArguments(argv[1:])
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.start()
        if not process.waitForStarted(8000 if kind == "PHP" else 2000):
            process.deleteLater()
            return ""
        deadline = time.time() + (
            8.0 if web_surface.preview_kind() == "PHP" else 3.0
        )
        listening = False
        while time.time() < deadline:
            if process.state() != QProcess.ProcessState.Running:
                break
            try:
                with socket.create_connection(
                    (web_surface.preview_bind_host(), port),
                    0.15,
                ):
                    listening = True
                    break
            except OSError:
                app = QCoreApplication.instance()
                if app is not None:
                    app.processEvents()
                time.sleep(0.05)
        if not listening:
            process.kill()
            process.waitForFinished(400)
            process.deleteLater()
            return ""
        origin = web_surface.preview_origin(port)
        if web_surface.preview_kind() == "PHP":
            from backend.site_database import rewrite_preview_origin

            rewrite_preview_origin(origin)
        self._preview = process
        self._preview_origin = origin
        return origin + "\n" + web_surface.preview_kind()

    @Slot(result=bool)
    def stopSitePreview(self) -> bool:
        process = self._preview
        self._preview = None
        self._preview_origin = ""
        if process is None:
            return True
        process.terminate()
        if not process.waitForFinished(800):
            process.kill()
            process.waitForFinished(400)
        process.deleteLater()
        return True

    @Slot(result=str)
    def sitePreviewOrigin(self) -> str:
        return self._preview_origin

    @Slot(str, result=str)
    def importSiteSql(self, path: str) -> str:
        from PySide6.QtCore import QCoreApplication

        from backend.site_database import import_sql_dump

        def progress(phase: str, current: int, total: int, extra: str) -> None:
            self.siteImportProgress.emit(phase, current, total, extra)
            app = QCoreApplication.instance()
            if app is not None:
                app.processEvents()

        return import_sql_dump(path, progress=progress)

    @Slot(str, result=str)
    def importSite(self, path: str) -> str:
        from PySide6.QtCore import QCoreApplication

        def progress(phase: str, current: int, total: int, extra: str) -> None:
            self.siteImportProgress.emit(phase, current, total, extra)
            app = QCoreApplication.instance()
            if app is not None:
                app.processEvents()

        return web_surface.import_site_tree(path, progress=progress)

    @Slot(result=str)
    def loadDesktopSettings(self) -> str:
        from backend.desktop_settings import load_settings

        return json.dumps(load_settings(), separators=(",", ":"))

    @Slot(str, result=str)
    def saveDesktopSettings(self, blob: str) -> str:
        from backend.desktop_settings import save_settings

        try:
            payload = json.loads(blob) if blob else {}
        except json.JSONDecodeError:
            return ""
        return save_settings(payload)

    @Slot(bool)
    def applyDesktopShell(self, enabled: bool) -> None:
        from backend.desktop_shell import apply_desktop_shell_window

        root = self._qml_root
        if root is None:
            return
        window = None
        getter = getattr(root, "window", None)
        if callable(getter):
            try:
                window = getter()
            except RuntimeError:
                window = None
        if window is None:
            from PySide6.QtGui import QWindow

            if isinstance(root, QWindow):
                window = root
        apply_desktop_shell_window(window, bool(enabled))

    @Slot(str, result=bool)
    def startChatTerminal(self, terminal_id: str) -> bool:
        identity = str(terminal_id or "").strip()
        if not identity:
            return False
        if identity in self._sessions:
            return True
        if not os.path.isfile(BASH) or not os.access(BASH, os.X_OK):
            return False
        master, slave = pty.openpty()
        flags = fcntl.fcntl(master, fcntl.F_GETFL)
        fcntl.fcntl(master, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        env = os.environ.copy()
        env["TERM"] = "dumb"
        env["PS1"] = "$ "
        try:
            proc = subprocess.Popen(
                [BASH, "--noprofile", "--norc"],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=str(GROK_CWD),
                env=env,
                start_new_session=True,
                close_fds=True,
            )
        except OSError:
            os.close(master)
            os.close(slave)
            return False
        os.close(slave)
        self._watch_pty(identity, proc, master)
        return True

    @Slot(str, result=bool)
    def startGrokTui(self, terminal_id: str) -> bool:
        identity = str(terminal_id or "").strip() or GROK_TUI_TERMINAL_ID
        existing = self._sessions.get(identity)
        if existing is not None:
            proc = existing.get("proc")
            if proc is not None and proc.poll() is None:
                return True
        return self._start_grok_tui_pty(
            identity,
            resume=self._pending_resume,
        )

    @Slot(str, result=bool)
    def resumeGrokTui(self, session_id: str) -> bool:
        sid = str(session_id or "").strip()
        if not sid:
            return False
        self._pending_resume = sid
        return self._start_grok_tui_pty(GROK_TUI_TERMINAL_ID, resume=sid)

    def _start_grok_tui_pty(
        self,
        identity: str,
        resume: str = "",
    ) -> bool:
        existing = self._sessions.get(identity)
        if existing is not None:
            self._close(identity)
        if not GROK_BIN.is_file() or not os.access(GROK_BIN, os.X_OK):
            return False
        argv = build_grok_tui_argv(
            full_screen_tui=True,
            resume=resume or None,
        )
        master, slave = pty.openpty()
        rows, cols = 36, 72
        if self._pending_tui_size is not None:
            cols, rows = self._pending_tui_size
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        try:
            fcntl.ioctl(master, termios.TIOCSWINSZ, winsize)
            fcntl.ioctl(slave, termios.TIOCSWINSZ, winsize)
        except OSError:
            pass
        flags = fcntl.fcntl(master, fcntl.F_GETFL)
        fcntl.fcntl(master, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"
        env["LANG"] = "C.UTF-8"
        env["LC_ALL"] = "C.UTF-8"
        env["GROK_HOME"] = str(DEV_GROK_HOME)
        env["LINES"] = str(rows)
        env["COLUMNS"] = str(cols)
        env["GIT_TERMINAL_PROMPT"] = "0"
        env.pop("GIT_ASKPASS", None)
        env.pop("SSH_ASKPASS", None)
        try:
            proc = subprocess.Popen(
                argv,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=str(GROK_CWD),
                env=env,
                start_new_session=True,
                close_fds=True,
            )
        except OSError:
            os.close(master)
            os.close(slave)
            return False
        os.close(slave)
        self._watch_pty(identity, proc, master)
        if self._pending_tui_size is not None:
            self._apply_tui_winsize()
        QTimer.singleShot(0, self._emit_wallet)
        return True

    def _watch_pty(
        self,
        identity: str,
        proc: subprocess.Popen,
        master: int,
        screen: MiniVt | None = None,
    ) -> None:
        notifier = QSocketNotifier(master, QSocketNotifier.Type.Read, self)
        write_notifier = QSocketNotifier(master, QSocketNotifier.Type.Write, self)
        write_notifier.setEnabled(False)
        drain = QTimer(self)
        drain.setSingleShot(True)
        drain.setInterval(_PTY_DRAIN_MS)
        backup = QTimer(self)
        backup.setInterval(_PTY_BACKUP_MS)
        session = {
            "proc": proc,
            "master": master,
            "notifier": notifier,
            "write_notifier": write_notifier,
            "write_queue": bytearray(),
            "drain": drain,
            "timer": backup,
            "screen": screen,
        }
        # Qt6 activated(QSocketDescriptor, Type) is 2-arg. A default
        # `key=identity` after `_fd` is overwritten by Type.Read, the
        # session lookup misses, and the notifier never disables — 80% GUI.
        notifier.activated.connect(
            lambda *_args, key=identity: self._pty_readable(key)
        )
        write_notifier.activated.connect(
            lambda *_args, key=identity: self._flush_pty_write(key)
        )
        drain.timeout.connect(lambda key=identity: self._drain_pty(key))
        backup.timeout.connect(lambda key=identity: self._pty_readable(key))
        self._sessions[identity] = session
        backup.start()
        drain.start()

    def _flush_pty_write(self, terminal_id: str) -> bool:
        """Flush queued terminal input without losing partial nonblocking writes."""
        session = self._sessions.get(terminal_id)
        if session is None:
            return False
        queue = session.get("write_queue")
        if not isinstance(queue, bytearray):
            queue = bytearray(queue or b"")
            session["write_queue"] = queue
        notifier = session.get("write_notifier")
        master = session.get("master")
        while queue:
            chunk = bytes(queue[:_PTY_WRITE_CHUNK])
            try:
                written = os.write(master, chunk)
            except BlockingIOError:
                if notifier is not None:
                    notifier.setEnabled(True)
                return False
            except OSError:
                if notifier is not None:
                    notifier.setEnabled(False)
                self._close(terminal_id)
                return False
            # Real os.write always returns an int. Treat a non-int result as a
            # complete write so lightweight test doubles remain compatible.
            if not isinstance(written, int):
                written = len(chunk)
            written = max(0, min(written, len(chunk)))
            if written == 0:
                if notifier is not None:
                    notifier.setEnabled(True)
                return False
            del queue[:written]
        if notifier is not None:
            notifier.setEnabled(False)
        return True

    @Slot(str, result=bool)
    def focusChatTerminal(self, terminal_id: str) -> bool:
        """Give the visible native chat terminal its keyboard focus."""
        key = str(terminal_id or "").strip()
        grid = (
            getattr(self, "_gpt_grid", None)
            if key == "ws.tui.gpt"
            else self._tui_grid
            if key == GROK_TUI_TERMINAL_ID
            else None
        )
        if grid is None:
            return False
        try:
            if not grid.isVisible():
                return False
            grid.forceActiveFocus()
            return bool(grid.hasActiveFocus())
        except (AttributeError, RuntimeError):
            return False

    @Slot(str, str, result=bool)
    def showChatTerminalNotice(self, terminal_id: str, text: str) -> bool:
        """Show host-generated feedback without writing it into the PTY.

        Approval replies are intentionally consumed before they reach Codex.
        The visible notice keeps that safe routing understandable to the
        operator without changing the child terminal's cursor state.
        """
        key = str(terminal_id or "").strip()
        if key not in {GROK_TUI_TERMINAL_ID, "ws.tui.gpt"}:
            return False
        message = " ".join(str(text or "").split()).strip()
        if not message:
            return False
        if key not in self._sessions:
            return False
        self.chatTerminalNotice.emit(key, message)
        self._arm_tui_focus(key)
        return True

    @Slot(str, result=bool)
    def stopChatTerminal(self, terminal_id: str) -> bool:
        identity = str(terminal_id or "").strip()
        if not identity:
            return False
        if identity not in self._sessions:
            return True
        self._close(identity)
        return True

    @Slot(str, str, result=str)
    def saveScratchFile(self, file_name: str, text: str) -> str:
        name = str(file_name or "").strip()
        if "/" in name or "\\" in name or name in {".", ".."}:
            return ""
        if not _SCRATCH_NAME.fullmatch(name):
            return ""
        body = text if isinstance(text, str) else str(text)
        data = body.encode("utf-8")
        if len(data) > 1_048_576:
            return ""
        SCRATCH_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = (SCRATCH_ROOT / name).resolve()
        if target.parent != SCRATCH_ROOT.resolve():
            return ""
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
        fd = os.open(target, flags, 0o600)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        self._fs_suppress.add(str(target))
        return str(target)

    def _live_allowed(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
        except OSError:
            return False
        roots = [
            SCRATCH_ROOT.resolve(),
            web_surface.SITE_ROOT.resolve(),
            GROK_CWD.resolve(),
        ]
        for root in roots:
            try:
                resolved.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    def _write_live_pointer(self) -> None:
        SCRATCH_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        untitled = SCRATCH_ROOT / "untitled.txt"
        if not untitled.is_file():
            untitled.write_text("", encoding="utf-8")
        body = (
            "GG AI Desktop live surfaces\n"
            "repo=" + str(GROK_CWD) + "\n"
            "scratch=" + str(SCRATCH_ROOT) + "\n"
            "untitled=" + str(untitled) + "\n"
            "site=" + str(web_surface.SITE_ROOT) + "\n"
        )
        pointer = GROK_CWD / ".gg-ai-desktop-live"
        try:
            pointer.write_text(body, encoding="utf-8")
        except OSError:
            return

    @Slot()
    def watchQmlSources(self) -> None:
        qml_root = Path(__file__).resolve().parents[1] / "qml"
        if not qml_root.is_dir():
            return
        if self._qml_watch is None:
            self._qml_watch = QFileSystemWatcher(self)
            self._qml_watch.fileChanged.connect(self._on_qml_file)
            self._qml_watch.directoryChanged.connect(self._on_qml_dir)
        watcher = self._qml_watch
        watcher.addPath(str(qml_root))
        components = qml_root / "components"
        if components.is_dir():
            watcher.addPath(str(components))
        for path in qml_root.rglob("*.qml"):
            watcher.addPath(str(path))

    def _on_qml_file(self, path: str) -> None:
        target = Path(path)
        if self._qml_watch is not None and target.is_file():
            self._qml_watch.addPath(path)
        if target.suffix.lower() != ".qml":
            return
        self._qml_reload.start()

    def _on_qml_dir(self, directory: str) -> None:
        folder = Path(directory)
        watcher = self._qml_watch
        if watcher is None:
            return
        watcher.addPath(directory)
        if not folder.is_dir():
            return
        for child in folder.glob("*.qml"):
            watcher.addPath(str(child))

    def _emit_qml_reload(self) -> None:
        # The loaders below destroy the QML host items synchronously.  Tear
        # down PTYs and painted terminal items first so Qt's render thread
        # cannot paint an item whose parent is already being deleted.
        self._qml_reload_safety_barrier()
        # Main.qml appends a nonce to every shell URL during reload.  Avoid
        # clearing the global QQml component cache here: doing that from a
        # QFileSystemWatcher callback can race the scene's render pass.
        self._qml_rebind_attempts = 0
        self.qmlLiveReload.emit()
        self._qml_rebind_timer.start()

    def _qml_reload_safety_barrier(self) -> None:
        for identity in list(self._sessions):
            self._close(identity)
        self._dispose_terminal_grid("_gpt_grid")
        self._dispose_terminal_grid("_tui_grid")
        self._gpt_hole = None
        self._native_hole = None
        self._gpt_connected_hole = None
        self._native_connected_hole = None

    @Slot()
    def reloadQml(self) -> None:
        self._emit_qml_reload()

    @Slot(result=bool)
    def restartDesktop(self) -> bool:
        self._emit_qml_reload()
        return True

    def watchDesktopWorkspace(self) -> None:
        if self._fs is not None:
            return
        self._write_live_pointer()
        watcher = QFileSystemWatcher(self)
        SCRATCH_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        watcher.addPath(str(SCRATCH_ROOT))
        untitled = SCRATCH_ROOT / "untitled.txt"
        if untitled.is_file():
            watcher.addPath(str(untitled))
        site = web_surface.SITE_ROOT
        if site.is_dir():
            watcher.addPath(str(site))
        drop = web_surface.ensure_import_drop()
        watcher.addPath(str(drop))
        watcher.directoryChanged.connect(self._on_live_dir)
        watcher.fileChanged.connect(self._on_live_file)
        self._fs = watcher
        self._arm_web_operator()
        self._arm_desktop_operator()
        self._poll_import_drop()

    @Slot(str)
    def watchLivePath(self, path: str) -> None:
        raw = str(path or "").strip()
        if not raw:
            return
        target = Path(raw)
        if not self._live_allowed(target):
            return
        if self._fs is None:
            self.watchDesktopWorkspace()
        if self._fs is None:
            return
        if target.exists():
            self._fs.addPath(str(target.resolve()))

    @Slot(str, result=str)
    def readScratchFile(self, file_name: str) -> str:
        name = str(file_name or "").strip()
        if not _SCRATCH_NAME.fullmatch(name):
            return ""
        target = (SCRATCH_ROOT / name).resolve()
        if target.parent != SCRATCH_ROOT.resolve() or not target.is_file():
            return ""
        try:
            data = target.read_bytes()
        except OSError:
            return ""
        if len(data) > 1_048_576:
            return ""
        return data.decode("utf-8", errors="replace")

    def _kind_for(self, path: Path) -> str:
        try:
            resolved = path.resolve()
            if resolved.is_relative_to(SCRATCH_ROOT.resolve()):
                return "scratch"
            if resolved.is_relative_to(web_surface.SITE_ROOT.resolve()):
                return "site"
        except (OSError, ValueError):
            return "repo"
        return "repo"

    def _emit_live_file(self, path: Path) -> None:
        if not self._live_allowed(path) or not path.is_file():
            return
        key = str(path.resolve())
        if key in self._fs_suppress:
            self._fs_suppress.discard(key)
            return
        try:
            data = path.read_bytes()
        except OSError:
            return
        if len(data) > 1_048_576:
            return
        text = data.decode("utf-8", errors="replace")
        self.workspaceFileChanged.emit(key, text, self._kind_for(path))

    def _on_live_file(self, path: str) -> None:
        target = Path(path)
        self._emit_live_file(target)
        if self._fs is not None and target.is_file():
            self._fs.addPath(str(target))

    def _poll_import_drop(self) -> None:
        from backend import web_surface

        for path in web_surface.pending_import_zips():
            try:
                key = path.name + ":" + str(path.stat().st_mtime_ns)
            except OSError:
                continue
            if key in self._imported_zips:
                continue
            result = self.importSite(str(path))
            self._imported_zips.add(key)
            self.siteImportProgress.emit("DROP", 1, 1, result)

    def _on_live_dir(self, directory: str) -> None:
        folder = Path(directory)
        try:
            if folder.resolve() == web_surface.IMPORT_DROP.resolve():
                self._poll_import_drop()
                return
            # The operator roots share the workspace watcher.  Keeping these
            # paths on the same QFileSystemWatcher avoids opening one inotify
            # instance per small IPC directory.
            from backend import desktop_operator, web_operator

            resolved = folder.resolve()
            if resolved == web_operator.ROOT.resolve():
                self._poll_web_operator()
                return
            if resolved == desktop_operator.ROOT.resolve():
                self._poll_desktop_operator()
                return
        except (OSError, ValueError):
            pass
        if not self._live_allowed(folder):
            return
        kind = self._kind_for(folder)
        self.workspaceFileChanged.emit(str(folder.resolve()), "", kind + "-dir")
        if folder.resolve() == SCRATCH_ROOT.resolve():
            untitled = SCRATCH_ROOT / "untitled.txt"
            self._emit_live_file(untitled)

    @Slot(str)
    def grokTuiWrite(self, data: str) -> None:
        self._write_chat_terminal(
            GROK_TUI_TERMINAL_ID,
            str(data or ""),
            user_input=True,
        )

    @Slot(str)
    def gptTuiWrite(self, data: str) -> None:
        """Forward GPTUI keystrokes exactly like the native GROK TUI path."""
        self._write_chat_terminal(
            "ws.tui.gpt",
            str(data or ""),
            user_input=True,
        )

    @Slot(str)
    def grokTuiTerminalReply(self, data: str) -> None:
        """Return VT device/status replies to the native GROK PTY."""
        self._write_chat_terminal(
            GROK_TUI_TERMINAL_ID,
            str(data or ""),
            user_input=False,
            terminal_reply=True,
        )

    @Slot(str)
    def gptTuiTerminalReply(self, data: str) -> None:
        """Return VT device/status replies to the GPTUI PTY."""
        self._write_chat_terminal(
            "ws.tui.gpt",
            str(data or ""),
            user_input=False,
            terminal_reply=True,
        )

    @Slot()
    def ensureWebEngine(self) -> bool:
        if self._webengine_ready:
            return True
        from backend.web_surface import ensure_webengine

        self._webengine_ready = bool(ensure_webengine())
        return self._webengine_ready

    @Slot(int, int)
    def grokTuiResize(self, cols: int, rows: int) -> None:
        width = max(8, min(240, int(cols)))
        height = max(4, min(80, int(rows)))
        pending = (width, height)
        session = self._sessions.get(GROK_TUI_TERMINAL_ID)
        if session is not None and session.get("cols") is None:
            self._pending_tui_size = pending
            self._apply_tui_winsize()
            return
        if self._pending_tui_size == pending and self._winch.isActive():
            return
        self._pending_tui_size = pending
        if session is None:
            return
        self._winch.start()

    def _apply_tui_winsize(self) -> None:
        if self._pending_tui_size is None:
            return
        width, height = self._pending_tui_size
        session = self._sessions.get(GROK_TUI_TERMINAL_ID)
        if session is None:
            return
        if session.get("cols") == width and session.get("rows") == height:
            return
        winsize = struct.pack("HHHH", height, width, 0, 0)
        session["cols"] = width
        session["rows"] = height
        try:
            fcntl.ioctl(session["master"], termios.TIOCSWINSZ, winsize)
        except OSError:
            return
        proc = session.get("proc")
        if proc is not None and proc.poll() is None:
            try:
                os.kill(int(proc.pid), signal.SIGWINCH)
            except OSError:
                return

    @Slot(str, str, result=bool)
    def writeChatTerminal(self, terminal_id: str, data: str) -> bool:
        # Calls from WorkObject and ResidentChatTransport are programmatic
        # writes.  Only the TerminalGrid keystroke slots above are user
        # ingress, so an internally dispatched approved prompt cannot be
        # mistaken for a new user mandate.
        return self._write_chat_terminal(
            terminal_id,
            data,
            user_input=False,
        )

    def _write_chat_terminal(
        self,
        terminal_id: str,
        data: str,
        *,
        user_input: bool,
        terminal_reply: bool = False,
    ) -> bool:
        key = str(terminal_id or "").strip()
        session = self._sessions.get(key)
        if session is None:
            return False
        payload = data if isinstance(data, str) else str(data)
        if payload == "":
            return True

        if user_input and key in {GROK_TUI_TERMINAL_ID, "ws.tui.gpt"}:
            line, submitted = self._scan_tui_input(key, payload)
            self._remember_tui_input(key, line)
            handler = self._tui_chat_line_handler
            # A single submitted line is the normal Enter/paste path.  Do
            # not partially consume multi-line pastes; they remain ordinary
            # terminal input and cannot accidentally mix task boundaries.
            if (
                len(submitted) == 1
                and not line
                and submitted[0]
                and callable(handler)
            ):
                try:
                    handled = bool(handler(key, submitted[0]))
                except Exception:
                    handled = False
                if handled:
                    # The visible characters may already have been echoed by
                    # the PTY in earlier key events.  Clear that native line
                    # first; the callback schedules the Workbench action
                    # after the clear has been written. Ctrl-C cancels the
                    # Codex TUI prompt itself and can make the next first
                    # input disappear, so use the standard terminal
                    # line-kill control instead.
                    cancel_queue = session.get("write_queue")
                    if not isinstance(cancel_queue, bytearray):
                        cancel_queue = bytearray(cancel_queue or b"")
                        session["write_queue"] = cancel_queue
                    cancel_queue.extend(b"\x15")
                    if not self._flush_pty_write(key) and key not in self._sessions:
                        return False
                    self._remember_tui_input(key, "")
                    if key == "ws.tui.gpt":
                        self._gpt_input_line = ""
                    return True
        if key == "ws.tui.gpt" and not terminal_reply:
            # Handle `/new` before forwarding its terminating Enter. If the
            # old Codex PTY receives Enter first, it owns the session switch
            # and the desktop cannot reliably make the new rollout current.
            line, submitted = self._scan_gpt_input(payload)
            if "/new" in submitted:
                self._remember_gpt_input(line, submitted)
                return self._start_fresh_gpt_session()
        queue = session.get("write_queue")
        if not isinstance(queue, bytearray):
            queue = bytearray(queue or b"")
            session["write_queue"] = queue
        queue.extend(payload.encode("utf-8"))
        if not self._flush_pty_write(key) and key not in self._sessions:
            return False
        if key == "ws.tui.gpt" and not terminal_reply:
            line, submitted = self._scan_gpt_input(payload)
            self._remember_gpt_input(line, submitted)
            if submitted:
                self._arm_gpt_session_capture()
        return True

    @Slot(str, int, result=bool)
    def scrollChatTerminal(self, terminal_id: str, delta: int) -> bool:
        """Scroll a rendered TUI without turning the wheel into prompt input.

        The native TerminalGrid handles wheel events when Qt delivers them to
        the painted item.  QML can also receive the event first, however, so
        expose the same operation as a small explicit slot for the transparent
        wheel proxy in GrokTuiHole.
        """
        key = str(terminal_id or "").strip()
        grid = (
            getattr(self, "_gpt_grid", None)
            if key == "ws.tui.gpt"
            else self._tui_grid
        )
        scroll = getattr(grid, "scrollWheel", None)
        if not callable(scroll):
            return False
        try:
            return bool(scroll(int(delta)))
        except (RuntimeError, TypeError, ValueError):
            return False

    @Slot(str, int, result=bool)
    def scrollChatTerminalTo(self, terminal_id: str, offset: int) -> bool:
        """Set a terminal's inline scrollback position from its scrollbar."""
        key = str(terminal_id or "").strip()
        grid = (
            getattr(self, "_gpt_grid", None)
            if key == "ws.tui.gpt"
            else self._tui_grid
        )
        scroll = getattr(grid, "scrollToOffset", None)
        if not callable(scroll):
            return False
        try:
            return bool(scroll(int(offset)))
        except (RuntimeError, TypeError, ValueError):
            return False

    @Slot(str, result=bool)
    def pasteChatTerminal(self, terminal_id: str) -> bool:
        from PySide6.QtGui import QGuiApplication

        clip = QGuiApplication.clipboard()
        text = clip.text() if clip is not None else ""
        if not text and clip is not None:
            mime = clip.mimeData()
            if mime is not None and mime.hasImage():
                # Codex handles image paste itself when it receives Ctrl+V.
                return self._write_chat_terminal(
                    terminal_id,
                    "\x16",
                    user_input=True,
                )
        if not text:
            return False
        return self._write_chat_terminal(
            terminal_id,
            str(text).replace("\n", "\r"),
            user_input=True,
        )

    def _tui_pid(self) -> int | None:
        session = self._sessions.get(GROK_TUI_TERMINAL_ID)
        if session is None:
            return None
        proc = session.get("proc")
        if proc is None:
            return None
        if proc.poll() is not None:
            return None
        try:
            return int(proc.pid)
        except (TypeError, ValueError):
            return None

    def _arm_web_operator(self) -> None:
        from backend import web_operator

        web_operator.ensure_root()
        if self._fs is None:
            self.watchDesktopWorkspace()
        watcher = self._fs
        if watcher is None:
            return
        if self._web_op_watch is not None:
            self._poll_web_operator()
            return
        watcher.addPath(str(web_operator.ROOT))
        self._web_op_watch = watcher
        self._poll_web_operator()

    def _on_web_operator_dir(self, _directory: str) -> None:
        self._poll_web_operator()

    def _reload_web_operator(self):
        import importlib

        from backend import web_operator

        path = Path(web_operator.__file__)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return web_operator
        previous = getattr(self, "_web_op_mtime", 0.0)
        if mtime != previous:
            module = importlib.reload(web_operator)
            self._web_op_mtime = mtime
            return module
        return web_operator

    def _poll_web_operator(self) -> None:
        web_operator = self._reload_web_operator()

        command = web_operator.take_command()
        if command is None:
            return
        self.webOperatorCommand.emit(
            json.dumps(command, ensure_ascii=False, separators=(",", ":"))
        )

    def _arm_desktop_operator(self) -> None:
        from backend import desktop_operator

        desktop_operator.ensure_root()
        if self._fs is None:
            self.watchDesktopWorkspace()
        watcher = self._fs
        if watcher is None:
            return
        if self._desk_op_watch is not None:
            self._poll_desktop_operator()
            return
        watcher.addPath(str(desktop_operator.ROOT))
        self._desk_op_watch = watcher
        self._poll_desktop_operator()

    def _on_desktop_operator_dir(self, _directory: str) -> None:
        self._poll_desktop_operator()

    def _poll_desktop_operator(self) -> None:
        from backend import desktop_operator

        if self._desk_job is not None:
            return
        command = desktop_operator.take_command()
        if command is None:
            return
        self._desk_start(command)

    def _desk_window(self):
        hole = self._tui_hole()
        if hole is not None:
            win = hole.window()
            if win is not None:
                return win
        root = self._qml_root
        if root is not None and hasattr(root, "window"):
            try:
                win = root.window()
            except Exception:
                win = None
            if win is not None:
                return win
        from PySide6.QtGui import QGuiApplication

        wins = QGuiApplication.topLevelWindows()
        return wins[0] if wins else None

    def _desk_find(self, name: str):
        if not name:
            return None
        for item in self._desk_visible_items():
            if self._desk_item_name(item) == name:
                return item
        return None

    def _desk_class_name(self, item) -> str:
        try:
            meta = item.metaObject()
            if meta is not None:
                return str(meta.className() or "")
        except Exception:
            pass
        return type(item).__name__

    def _desk_is_web_surface(self, item) -> bool:
        cls = self._desk_class_name(item)
        return any(
            token in cls
            for token in ("WebEngine", "WebView", "Chromium", "RenderWidget")
        )

    def _desk_item_name(self, item) -> str:
        obj = str(item.objectName() or "")
        if obj:
            return obj
        value = item.property("objectName")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return ""

    def _desk_is_heavy_surface(self, item) -> bool:
        if self._desk_is_web_surface(item):
            return True
        name = self._desk_item_name(item)
        if name in {
            "grokTuiHost",
            "webPane",
            "webPaneLoader",
            "webAgentCursor",
            "chatActivityStream",
            "chatArtifactPane",
            "workspaceCodeEditor",
            "workspaceCodeScroll",
            "workspaceCryptoPane",
            "workspaceTmogPane",
            "workspaceMediaPane",
            "workspaceDrawPane",
            "workspaceMarketplacePane",
        }:
            return True
        cls = self._desk_class_name(item)
        return any(
            token in cls for token in ("TerminalGrid", "TuiHole", "VtHost")
        )

    def _desk_child_items(self, item) -> list:
        if item is None:
            return []
        kids = None
        attr = getattr(item, "childItems", None)
        if callable(attr):
            try:
                kids = attr()
            except Exception:
                kids = None
        elif attr is not None:
            kids = attr
        if kids is None:
            try:
                kids = item.property("childItems")
            except Exception:
                kids = None
        out: list = []
        if kids:
            try:
                out = list(kids)
            except Exception:
                out = []
        loaded = self._desk_loader_item(item)
        if loaded is not None and loaded not in out:
            out.append(loaded)
        return out

    def _desk_loader_item(self, item):
        if item is None:
            return None
        loaded = None
        try:
            loaded = item.property("item")
        except Exception:
            loaded = None
        if loaded is None:
            getter = getattr(item, "item", None)
            if callable(getter):
                try:
                    loaded = getter()
                except Exception:
                    loaded = None
        if loaded is None or loaded is item:
            return None
        return loaded

    def _desk_walk_visible(self, item, depth: int, acc: list) -> None:
        if item is None or depth > 32 or len(acc) >= 200:
            return
        vis = item.property("visible")
        if vis is False:
            return
        named = bool(self._desk_item_name(item) or self._desk_item_label(item))
        if named and item not in acc:
            acc.append(item)
        if self._desk_is_heavy_surface(item):
            if self._desk_item_name(item) == "grokTuiHost":
                for child in self._desk_child_items(item):
                    child_name = self._desk_item_name(child)
                    child_label = self._desk_item_label(child)
                    if (child_name or child_label) and child not in acc:
                        acc.append(child)
            return
        for child in self._desk_child_items(item):
            self._desk_walk_visible(child, depth + 1, acc)

    def _desk_content_item(self):
        win = self._desk_window()
        for source in (win, self._qml_root):
            if source is None:
                continue
            attr = getattr(source, "contentItem", None)
            content = None
            if callable(attr):
                try:
                    content = attr()
                except Exception:
                    content = None
            elif attr is not None:
                content = attr
            if content is None:
                try:
                    content = source.property("contentItem")
                except Exception:
                    content = None
            if content is not None:
                return content
        return None

    def _desk_visible_items(self) -> list:
        acc: list = []
        root = self._qml_root
        workspace = None
        if root is not None:
            try:
                workspace = root.property("workspace")
            except Exception:
                workspace = None
        if workspace is not None:
            self._desk_walk_visible(workspace, 0, acc)
        content = self._desk_content_item()
        if content is not None:
            self._desk_walk_visible(content, 0, acc)
        if root is not None and root is not content:
            self._desk_walk_visible(root, 0, acc)
        return acc

    def _desk_item_shown(self, item) -> bool:
        if item is None or self._desk_is_web_surface(item):
            return False
        vis = item.property("visible")
        if vis is False:
            return False
        try:
            if float(item.property("width") or 0) <= 0:
                return False
            if float(item.property("height") or 0) <= 0:
                return False
        except (TypeError, ValueError):
            pass
        return True

    def _desk_item_label(self, item) -> str:
        for key in ("text", "placeholderText", "title"):
            value = item.property(key)
            if isinstance(value, str):
                label = value.strip()
                if label and label != "|":
                    return label
        return ""

    def _desk_list_names(self, query: str) -> list[str]:
        needle = query.lower()
        names: list[str] = []
        seen: set[str] = set()
        for item in self._desk_visible_items():
            if not self._desk_item_shown(item):
                continue
            obj = self._desk_item_name(item)
            label = self._desk_item_label(item)
            hay = (obj + " " + label).lower()
            if needle and needle not in hay:
                continue
            try:
                x, y = self._desk_point(item)
            except Exception:
                continue
            if label:
                row = label.replace("\n", " ")[:60] + " @" + str(x) + "," + str(y)
                if obj:
                    row += " [" + obj + "]"
            elif obj:
                row = obj + " @" + str(x) + "," + str(y)
            else:
                continue
            if row in seen:
                continue
            seen.add(row)
            names.append(row)
            if len(names) >= 120:
                break
        return names

    def _desk_find_label(self, query: str):
        if not query:
            return None
        needle = query.strip().lower()
        exact = None
        partial = None
        for item in self._desk_visible_items():
            if not self._desk_item_shown(item):
                continue
            label = self._desk_item_label(item)
            if not label:
                continue
            low = label.strip().lower()
            if low == needle:
                exact = item
                break
            if partial is None and needle in low and len(label) < 80:
                partial = item
        return exact or partial

    def _desk_point(self, item) -> tuple[int, int]:
        from PySide6.QtCore import QPoint, QPointF

        width = float(item.property("width") or 0)
        height = float(item.property("height") or 0)
        if width <= 0:
            width = 1.0
        if height <= 0:
            height = 1.0
        local = QPointF(width / 2.0, height / 2.0)
        content = self._desk_content_item()
        if content is not None and hasattr(item, "mapToItem"):
            try:
                point = item.mapToItem(content, local)
                if hasattr(point, "x"):
                    return int(point.x()), int(point.y())
            except Exception:
                pass
        win = item.window() if hasattr(item, "window") else None
        if win is not None and hasattr(item, "mapToGlobal"):
            glob = item.mapToGlobal(local)
            if hasattr(glob, "toPoint"):
                glob = glob.toPoint()
            elif not isinstance(glob, QPoint):
                glob = QPoint(int(glob.x()), int(glob.y()))
            if hasattr(win, "mapFromGlobal"):
                loc = win.mapFromGlobal(glob)
                return int(loc.x()), int(loc.y())
        raise RuntimeError("MAP_FAIL")

    def _desk_set_cursor(self, x: int, y: int, shape: str) -> None:
        root = self._qml_root
        if root is None:
            return
        root.setProperty("deskX", float(x))
        root.setProperty("deskY", float(y))
        if shape:
            root.setProperty("deskShape", shape)
        root.setProperty("deskFromChrome", False)

    def _desk_current_cursor(self) -> tuple[int, int]:
        root = self._qml_root
        if root is None:
            return 420, 240
        try:
            return int(root.property("deskX") or 420), int(
                root.property("deskY") or 240
            )
        except (TypeError, ValueError):
            return 420, 240

    def _gpt_tui_busy(self) -> bool:
        """Return True while Codex is rendering an active turn."""
        grid = getattr(self, "_gpt_grid", None)
        if grid is None:
            return False
        try:
            text = str(grid.vt().display() or "").lower()
        except (AttributeError, RuntimeError):
            return False
        return "working" in text and "interrupt" in text

    def _desk_finish(self, cmd: dict[str, Any], **fields: Any) -> None:
        from backend import desktop_operator

        self._desk_job = None
        self._desk_timer.stop()
        fields.setdefault("observation_seq", self._desk_observation_seq)
        fields.setdefault(
            "stable_frames",
            2 if cmd.get("action") in {"CLICK", "TYPE", "KEY"} else 0,
        )
        desktop_operator.write_result(desktop_operator.make_result(cmd, **fields))

    def _desk_start(self, cmd: dict[str, Any]) -> None:
        from backend import desktop_operator

        action = str(cmd.get("action") or "")
        if action == "FIND":
            query = str(cmd.get("text") or cmd.get("name") or "")
            names = self._desk_list_names(query)
            self._desk_finish(
                cmd,
                ok=True,
                reason_code="FOUND",
                text=query,
                names=names,
            )
            return
        if action == "SNAPSHOT":
            path = str(desktop_operator.ROOT / desktop_operator.VIEW_NAME)
            visual = bool(cmd.get("visual"))
            ok = False
            if visual:
                ok = self._desk_grab(path)
                if not ok:
                    ok = self._desk_grab_screen(path)
            x, y = self._desk_current_cursor()
            names = self._desk_list_names("")
            self._desk_finish(
                cmd,
                ok=True,
                reason_code="SNAPSHOT" if ok else "OBSERVED",
                text="" if ok else "semantic-observation",
                x=x,
                y=y,
                names=names,
                image=path if ok else "",
            )
            return
        busy = self._gpt_tui_busy()
        cancel_key = action == "KEY" and str(cmd.get("text") or "").lower() in {
            "esc",
            "escape",
        }
        if busy and not cancel_key:
            x, y = self._desk_current_cursor()
            self._desk_finish(
                cmd,
                ok=False,
                reason_code="BUSY",
                text="GPTUI is working; observe again after the turn finishes.",
                x=x,
                y=y,
            )
            return
        if action == "KEY" and not cmd.get("name"):
            self._desk_send_key(str(cmd.get("text") or ""))
            x, y = self._desk_current_cursor()
            self._desk_finish(
                cmd,
                ok=True,
                reason_code="KEYED",
                text=str(cmd.get("text") or ""),
                x=x,
                y=y,
            )
            return
        name = str(cmd.get("name") or "")
        label = str(cmd.get("text") or "") if action != "TYPE" else ""
        x = int(cmd.get("x") or 0)
        y = int(cmd.get("y") or 0)
        item = None
        if name:
            item = self._desk_find(name)
        elif label:
            item = self._desk_find_label(label)
        if name or label:
            if item is None:
                self._desk_finish(
                    cmd,
                    ok=False,
                    reason_code="MISS",
                    text=name or label,
                    names=self._desk_list_names(name or label),
                )
                return
            try:
                x, y = self._desk_point(item)
            except Exception:
                self._desk_finish(
                    cmd,
                    ok=False,
                    reason_code="MAP_FAIL",
                    text=name or label,
                )
                return
        if action == "TYPE" and not name and not label and x == 0 and y == 0:
            x, y = self._desk_current_cursor()
        start = self._desk_current_cursor()
        shape = "text" if action == "TYPE" else "pointer"
        if action == "MOVE":
            shape = "default"
        self._desk_job = {
            "cmd": cmd,
            "sx": float(start[0]),
            "sy": float(start[1]),
            "tx": float(x),
            "ty": float(y),
            "step": 0,
            "steps": 22,
            "shape": shape,
            # Two 60 Hz frames of settling gives the observer a stable target
            # before any click/key/type side effect is emitted.
            "settle": 2,
        }
        self._desk_set_cursor(start[0], start[1], shape)
        self._desk_timer.start()

    def _desk_tick(self) -> None:
        self._desk_observation_seq += 1
        job = self._desk_job
        if job is None:
            self._desk_timer.stop()
            return
        if job.get("typing"):
            text = str(job.get("type_text") or "")
            index = int(job.get("type_index") or 0)
            if index >= len(text):
                self._desk_timer.setInterval(16)
                cmd = job["cmd"]
                x, y = self._desk_current_cursor()
                self._desk_finish(
                    cmd,
                    ok=True,
                    reason_code="TYPED",
                    text=text,
                    x=x,
                    y=y,
                )
                return
            self._desk_send_char(text[index])
            job["type_index"] = index + 1
            return
        job["step"] = int(job["step"]) + 1
        steps = max(1, int(job["steps"]))
        t = min(1.0, float(job["step"]) / float(steps))
        ease = t * t * (3.0 - 2.0 * t)
        x = int(job["sx"] + (job["tx"] - job["sx"]) * ease)
        y = int(job["sy"] + (job["ty"] - job["sy"]) * ease)
        self._desk_set_cursor(x, y, str(job["shape"]))
        if t < 1.0:
            return
        settle = int(job.get("settle") or 0)
        if settle > 0:
            job["settle"] = settle - 1
            self._desk_timer.start()
            return
        self._desk_timer.stop()
        cmd = job["cmd"]
        action = str(cmd.get("action") or "")
        if action == "CLICK":
            self._desk_send_click(x, y, str(cmd.get("button") or "left"))
            self._desk_finish(
                cmd,
                ok=True,
                reason_code="CLICKED",
                text=str(cmd.get("name") or ""),
                x=x,
                y=y,
            )
            return
        if action == "HOVER":
            self._desk_send_move(x, y)
            self._desk_finish(
                cmd,
                ok=True,
                reason_code="HOVERED",
                text=str(cmd.get("name") or ""),
                x=x,
                y=y,
            )
            return
        if action == "TYPE":
            self._desk_send_click(x, y, "left")
            self._desk_job = {
                "cmd": cmd,
                "typing": True,
                "type_text": str(cmd.get("text") or ""),
                "type_index": 0,
                "shape": "text",
            }
            self._desk_set_cursor(x, y, "text")
            self._desk_timer.setInterval(28)
            self._desk_timer.start()
            return
        if action == "KEY":
            if cmd.get("name"):
                self._desk_send_click(x, y, "left")
            self._desk_send_key(str(cmd.get("text") or ""))
            self._desk_finish(
                cmd,
                ok=True,
                reason_code="KEYED",
                text=str(cmd.get("text") or ""),
                x=x,
                y=y,
            )
            return
        self._desk_finish(
            cmd,
            ok=True,
            reason_code="MOVED",
            text=str(cmd.get("name") or ""),
            x=x,
            y=y,
        )

    def _desk_grab_screen(self, path: str) -> bool:
        from PySide6.QtGui import QGuiApplication

        from backend import desktop_operator

        win = self._desk_window()
        screen = None
        if win is not None:
            screen = win.screen()
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return False
        desktop_operator.ensure_root()
        try:
            wid = int(win.winId()) if win is not None else 0
            pix = screen.grabWindow(wid)
            if pix is None or pix.isNull() or pix.width() < 2:
                pix = screen.grabWindow(0)
            return bool(pix.save(path, "PNG")) and Path(path).stat().st_size > 200
        except Exception:
            return False

    def _desk_grab_qml(self, path: str) -> bool:
        from PySide6.QtCore import Q_ARG, QEventLoop, QMetaObject, QTimer, Qt

        from backend import desktop_operator

        root = self._qml_root
        if root is None:
            return False
        desktop_operator.ensure_root()
        target = Path(path)
        if target.exists():
            try:
                target.unlink()
            except OSError:
                pass
        root.setProperty("deskGrabReady", False)
        invoked = False
        for arg in (path,):
            try:
                invoked = bool(
                    QMetaObject.invokeMethod(
                        root,
                        "grabDesk",
                        Qt.ConnectionType.DirectConnection,
                        Q_ARG(str, arg),
                    )
                )
            except Exception:
                invoked = False
            if invoked:
                break
            try:
                invoked = bool(
                    QMetaObject.invokeMethod(
                        root,
                        "grabDesk",
                        Qt.ConnectionType.QueuedConnection,
                        Q_ARG("QString", arg),
                    )
                )
            except Exception:
                invoked = False
            if invoked:
                break
        if not invoked:
            content = self._desk_content_item()
            if content is not None and hasattr(content, "grabToImage"):
                try:
                    content.grabToImage(
                        lambda result: root.setProperty(
                            "deskGrabReady",
                            bool(result.saveToFile(path)),
                        )
                    )
                    invoked = True
                except Exception:
                    invoked = False
        if not invoked:
            return False
        loop = QEventLoop()
        ticks = {"n": 0}

        def tick() -> None:
            ticks["n"] += 1
            ready = bool(root.property("deskGrabReady"))
            if ready or ticks["n"] > 25:
                loop.quit()

        timer = QTimer(self)
        timer.setInterval(40)
        timer.timeout.connect(tick)
        timer.start()
        loop.exec()
        timer.stop()
        try:
            return target.is_file() and target.stat().st_size > 200
        except OSError:
            return False

    def _desk_grab(self, path: str) -> bool:
        from backend import desktop_operator

        desktop_operator.ensure_root()
        win = self._desk_window()
        if win is not None:
            grab = getattr(win, "grabWindow", None)
            if callable(grab):
                try:
                    img = grab()
                    if img is not None and not img.isNull():
                        ok = bool(img.save(path, "PNG"))
                        if ok and Path(path).is_file() and Path(path).stat().st_size > 200:
                            return True
                except Exception:
                    pass
        if self._desk_grab_qml(path):
            return True
        return False

    def _desk_send_move(self, x: int, y: int) -> None:
        from PySide6.QtCore import QCoreApplication, QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        win = self._desk_window()
        if win is None:
            return
        point = QPointF(float(x), float(y))
        QCoreApplication.postEvent(
            win,
            QMouseEvent(
                QEvent.Type.MouseMove,
                point,
                point,
                Qt.MouseButton.NoButton,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            ),
        )

    def _desk_send_click(self, x: int, y: int, button: str) -> None:
        from PySide6.QtCore import QCoreApplication, QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        win = self._desk_window()
        if win is None:
            return
        mapping = {
            "left": Qt.MouseButton.LeftButton,
            "middle": Qt.MouseButton.MiddleButton,
            "right": Qt.MouseButton.RightButton,
        }
        qt_button = mapping.get(button, Qt.MouseButton.LeftButton)
        point = QPointF(float(x), float(y))
        modifiers = Qt.KeyboardModifier.NoModifier
        for event_type, event_button in (
            (QEvent.Type.MouseButtonPress, qt_button),
            (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton),
        ):
            QCoreApplication.postEvent(
                win,
                QMouseEvent(
                    event_type,
                    point,
                    point,
                    event_button,
                    qt_button,
                    modifiers,
                ),
            )

    def _desk_send_key(self, key: str) -> None:
        from PySide6.QtCore import QCoreApplication, QEvent, Qt
        from PySide6.QtGui import QKeyEvent

        win = self._desk_window()
        if win is None:
            return
        keys = {
            "Enter": Qt.Key.Key_Return,
            "Tab": Qt.Key.Key_Tab,
            "Escape": Qt.Key.Key_Escape,
            "Space": Qt.Key.Key_Space,
            "Backspace": Qt.Key.Key_Backspace,
            "Delete": Qt.Key.Key_Delete,
            "Home": Qt.Key.Key_Home,
            "End": Qt.Key.Key_End,
            "ArrowUp": Qt.Key.Key_Up,
            "ArrowDown": Qt.Key.Key_Down,
            "ArrowLeft": Qt.Key.Key_Left,
            "ArrowRight": Qt.Key.Key_Right,
        }
        modifiers = Qt.KeyboardModifier.NoModifier
        if key == "Ctrl+V":
            qt_key = Qt.Key.Key_V
            modifiers = Qt.KeyboardModifier.ControlModifier
        elif key == "Shift+Insert":
            qt_key = Qt.Key.Key_Insert
            modifiers = Qt.KeyboardModifier.ShiftModifier
        else:
            qt_key = keys.get(key)
            if qt_key is None:
                return
        for event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QCoreApplication.postEvent(
                win,
                QKeyEvent(event_type, qt_key, modifiers),
            )

    def _desk_send_char(self, ch: str) -> None:
        from PySide6.QtCore import QCoreApplication, QEvent, Qt
        from PySide6.QtGui import QKeyEvent, QKeySequence

        win = self._desk_window()
        if win is None or not ch:
            return
        if ch == "\n":
            key = Qt.Key.Key_Return
            text = "\r"
        elif ch == " ":
            key = Qt.Key.Key_Space
            text = " "
        else:
            seq = QKeySequence(ch)
            key = seq[0].key() if seq.count() > 0 else Qt.Key.Key_unknown
            text = ch
        mods = Qt.KeyboardModifier.NoModifier
        QCoreApplication.postEvent(
            win, QKeyEvent(QEvent.Type.KeyPress, key, mods, text)
        )
        QCoreApplication.postEvent(
            win, QKeyEvent(QEvent.Type.KeyRelease, key, mods, text)
        )

    def _desk_send_type(self, text: str) -> None:
        for ch in str(text or ""):
            self._desk_send_char(ch)

    @Slot(str)
    def webOperatorReport(self, payload: str) -> None:
        web_operator = self._reload_web_operator()

        try:
            value = json.loads(str(payload or ""))
        except json.JSONDecodeError:
            return
        if not isinstance(value, dict):
            return
        web_operator.write_result(value)

    def _emit_wallet(self) -> None:
        payload = grok_wallet_snapshot(
            pty_overlay=self._wallet_pty,
            live_base=self._wallet_live_base,
            tui_pid=self._tui_pid(),
        )
        used = payload.get("context_used")
        turn = payload.get("turn_tokens")
        if used is not None:
            if self._wallet_live_base is None or used < self._wallet_live_base:
                self._wallet_live_base = int(used)
            if turn is not None and turn != self._wallet_last_turn:
                self._wallet_last_turn = int(turn)
                self._wallet_live_base = int(used)
        gpt_root = self._gpt_sessions_root
        if "ws.tui.gpt" not in self._sessions and not self._gpt_session_id:
            gpt_root = DESKTOP_CODEX_SESSIONS
        gpt_path = None
        if self._gpt_session_id:
            gpt_path = codex_session_path(
                self._gpt_session_id,
                sessions_root=gpt_root,
            )
        gpt_text = json.dumps(
            codex_wallet_snapshot(
                session=gpt_path,
                sessions_root=gpt_root,
            ),
            separators=(",", ":"),
        )
        if gpt_text != self._gpt_wallet_json:
            self._gpt_wallet_json = gpt_text
            self.gptWalletChanged.emit(gpt_text)
        text = json.dumps(payload, separators=(",", ":"))
        if text != self._wallet_json:
            self._wallet_json = text
            self.grokWalletChanged.emit(text)
        current = ""
        if isinstance(payload, dict):
            session_path = str(payload.get("session") or "")
            if session_path:
                current = Path(session_path).name
        if self._gpt_session_id and "ws.tui.gpt" in self._sessions:
            current = self._gpt_session_id
        rows = list_for_ui(current_id=current)
        if self._legacy_gpt_session_id:
            # Keep the row hidden even if an older read-only catalog cannot be
            # rewritten. It is the id captured by the old host-wide scan.
            rows = [
                row
                for row in rows
                if row.get("session_id") != self._legacy_gpt_session_id
            ]
        listing = json.dumps(rows, separators=(",", ":"))
        if listing != self._sessions_json:
            self._sessions_json = listing
            self.chatSessionsChanged.emit(listing)

    def shutdown(self) -> None:
        self._tui_focus_timer.stop()
        self._tui_focus_terminal = ""
        self._gpt_capture_timer.stop()
        for identity in list(self._sessions):
            self._close(identity)
        self._qml_rebind_timer.stop()
        self._qml_reload_safety_barrier()
        self.stopSitePreview()
        embed = self._tui_embed
        self._tui_embed = None
        if embed is not None:
            embed.stop()
        tmog = self._tmog_embed
        self._tmog_embed = None
        if tmog is not None:
            tmog.stop()
        media = self._media_embed
        self._media_embed = None
        if media is not None:
            media.stop()
        torlink = self._torlink_embed
        self._torlink_embed = None
        if torlink is not None:
            torlink.stop()
        draw = self._draw_embed
        self._draw_embed = None
        if draw is not None:
            draw.stop()
        media_host.stop()

    def _pty_readable(self, terminal_id: str) -> None:
        if not isinstance(terminal_id, str):
            return
        session = self._sessions.get(terminal_id)
        if session is None:
            return
        notifier = session.get("notifier")
        if notifier is not None:
            notifier.setEnabled(False)
        self._drain_pty(terminal_id)

    def _drain_pty(self, terminal_id: str) -> None:
        more = False
        try:
            more = self._read(terminal_id)
        except Exception:
            more = False
        session = self._sessions.get(terminal_id)
        if session is None:
            return
        if more:
            drain = session.get("drain")
            if drain is not None:
                drain.start()
            return
        notifier = session.get("notifier")
        if notifier is not None:
            notifier.setEnabled(True)

    def _read(self, terminal_id: str) -> bool:
        session = self._sessions.get(terminal_id)
        if session is None:
            return False
        master = session["master"]
        chunks: list[bytes] = []
        hit_budget = False
        total = 0
        try:
            while True:
                if total >= _PTY_READ_BUDGET:
                    hit_budget = True
                    break
                piece = os.read(master, min(4096, _PTY_READ_BUDGET - total))
                if not piece:
                    break
                chunks.append(piece)
                total += len(piece)
        except BlockingIOError:
            pass
        except OSError:
            self._close(terminal_id)
            return False
        if chunks:
            self._chat_io_at = time.monotonic()
            raw = b"".join(chunks)
            commands: list[str] = []
            if terminal_id == "ws.tui.gpt":
                visible = _strip_ansi(raw.decode("utf-8", errors="replace"))
                commands = self._commands_from_gpt_output(visible)
            if terminal_id in (GROK_TUI_TERMINAL_ID, "ws.tui.gpt"):
                grid = getattr(self, "_gpt_grid", None) if terminal_id == "ws.tui.gpt" else self._tui_grid
                if grid is not None:
                    grid.feed_bytes(raw)
                self._arm_tui_focus(terminal_id)
                for command in commands:
                    self._run_gpt_shared_command(command)
            else:
                text = raw.decode("utf-8", errors="replace")
                screen = session.get("screen")
                if isinstance(screen, MiniVt):
                    screen.feed(text)
                    self.chatTerminalOutput.emit(terminal_id, screen.display())
                else:
                    text = _strip_ansi(text)
                    if text:
                        self.chatTerminalOutput.emit(terminal_id, text)
        proc = session["proc"]
        if proc.poll() is not None:
            self.chatTerminalExit.emit(terminal_id, int(proc.returncode or 0))
            self._close(terminal_id)
            return False
        return hit_budget

    def _close(self, terminal_id: str) -> None:
        session = self._sessions.pop(terminal_id, None)
        if session is None:
            return
        self._tui_input_lines.pop(terminal_id, None)
        if terminal_id == "ws.tui.gpt":
            self._gpt_capture_timer.stop()
            self._gpt_capture_attempts = 0
            self._gpt_capture_deadline = 0.0
            self._gpt_input_line = ""
        drain = session.get("drain")
        if drain is not None:
            drain.stop()
            drain.deleteLater()
        timer = session.get("timer")
        if timer is not None:
            timer.stop()
            timer.deleteLater()
        notifier = session.get("notifier")
        if notifier is not None:
            notifier.setEnabled(False)
            notifier.deleteLater()
        write_notifier = session.get("write_notifier")
        if write_notifier is not None:
            write_notifier.setEnabled(False)
            write_notifier.deleteLater()
        write_queue = session.get("write_queue")
        if isinstance(write_queue, bytearray):
            write_queue.clear()
        master = session.get("master")
        if isinstance(master, int):
            try:
                os.close(master)
            except OSError:
                pass
        proc = session.get("proc")
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except OSError:
                proc.terminate()
            try:
                proc.wait(timeout=0.4)
            except Exception:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except OSError:
                    proc.kill()
                try:
                    proc.wait(timeout=0.4)
                except Exception:
                    pass
