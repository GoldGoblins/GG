from __future__ import annotations

import fcntl
import json
import os
import pty
import re
import signal
import struct
import subprocess
import termios
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QFileSystemWatcher,
    QObject,
    QProcess,
    QSocketNotifier,
    QTimer,
    Signal,
    Slot,
)

from backend.chat_sessions import list_for_ui
from backend.grok_wallet import parse_pty_wallet, snapshot as grok_wallet_snapshot
from backend.grok_worker_contract import (
    DEV_GROK_HOME,
    GROK_BIN,
    GROK_CWD,
    GROK_TUI_TERMINAL_ID,
    build_grok_tui_argv,
)
from backend.mini_vt import MiniVt
from backend.surface_intent import parse_surface_intent
from backend import web_surface

BASH = "/bin/bash"
SCRATCH_ROOT = (
    Path("/home/GG/.local/state/goldgoblins/gg-ai-desktop/scratch")
)
_SCRATCH_NAME = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
_ANSI = re.compile(
    r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))"
)


def _strip_ansi(text: str) -> str:
    cleaned = _ANSI.sub("", text)
    cleaned = cleaned.replace("\x00", "")
    return cleaned.replace("\r\n", "\n").replace("\r", "\n")


class ChatSurfaceHost(QObject):
    chatTerminalOutput = Signal(str, str)
    chatTerminalExit = Signal(str, int)
    grokTuiChunk = Signal(str)
    grokWalletChanged = Signal(str)
    chatSessionsChanged = Signal(str)
    workspaceFileChanged = Signal(str, str, str)
    siteImportProgress = Signal(str, int, int, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sessions: dict[str, dict[str, Any]] = {}
        self._preview: QProcess | None = None
        self._preview_origin = ""
        self._qml_root: QObject | None = None
        self._tui_embed: object | None = None
        self._pending_tui_size: tuple[int, int] | None = None
        self._fs: QFileSystemWatcher | None = None
        self._fs_suppress: set[str] = set()
        self._wallet_pty: dict[str, Any] = {}
        self._wallet_live_base: int | None = None
        self._wallet_last_turn: int | None = None
        self._wallet_json = ""
        self._sessions_json = ""
        self._pending_resume = ""
        self._wallet_timer = QTimer(self)
        self._wallet_timer.setInterval(400)
        self._wallet_timer.timeout.connect(self._emit_wallet)
        self._wallet_timer.start()

    def set_qml_root(self, root: QObject | None) -> None:
        self._qml_root = root
        self.watchDesktopWorkspace()

    @Slot(str, result=str)
    def parseSurfaceIntent(self, text: str) -> str:
        return parse_surface_intent(text)

    @Slot(str, result=bool)
    def urlAllowed(self, url: str) -> bool:
        return web_surface.url_allowed(url)

    @Slot(str, result=bool)
    def browseUrlAllowed(self, url: str) -> bool:
        return web_surface.browse_url_allowed(url)

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
            self.grokTuiResize(*self._pending_tui_size)
        return True

    def _watch_pty(
        self,
        identity: str,
        proc: subprocess.Popen,
        master: int,
        screen: MiniVt | None = None,
    ) -> None:
        notifier = QSocketNotifier(master, QSocketNotifier.Type.Read, self)
        timer = QTimer(self)
        timer.setInterval(50)
        session = {
            "proc": proc,
            "master": master,
            "notifier": notifier,
            "timer": timer,
            "screen": screen,
        }
        notifier.activated.connect(
            lambda _fd=None, key=identity: self._read(key)
        )
        timer.timeout.connect(lambda key=identity: self._read(key))
        self._sessions[identity] = session
        timer.start()

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
        watcher.directoryChanged.connect(self._on_live_dir)
        watcher.fileChanged.connect(self._on_live_file)
        self._fs = watcher

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

    def _on_live_dir(self, directory: str) -> None:
        folder = Path(directory)
        if not self._live_allowed(folder):
            return
        kind = self._kind_for(folder)
        self.workspaceFileChanged.emit(str(folder.resolve()), "", kind + "-dir")
        if folder.resolve() == SCRATCH_ROOT.resolve():
            untitled = SCRATCH_ROOT / "untitled.txt"
            self._emit_live_file(untitled)

    @Slot(str)
    def grokTuiWrite(self, data: str) -> None:
        self.writeChatTerminal(GROK_TUI_TERMINAL_ID, str(data or ""))

    @Slot(int, int)
    def grokTuiResize(self, cols: int, rows: int) -> None:
        width = max(8, min(240, int(cols)))
        height = max(4, min(80, int(rows)))
        self._pending_tui_size = (width, height)
        session = self._sessions.get(GROK_TUI_TERMINAL_ID)
        if session is None:
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
        session = self._sessions.get(str(terminal_id or "").strip())
        if session is None:
            return False
        payload = data if isinstance(data, str) else str(data)
        if payload == "":
            return True
        key = str(terminal_id or "").strip()
        try:
            os.write(session["master"], payload.encode("utf-8"))
        except OSError:
            return False
        return True

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

    def _emit_wallet(self) -> None:
        peek = grok_wallet_snapshot(
            pty_overlay=self._wallet_pty,
            live_base=self._wallet_live_base,
            tui_pid=self._tui_pid(),
        )
        used = peek.get("context_used")
        turn = peek.get("turn_tokens")
        if used is not None:
            if self._wallet_live_base is None or used < self._wallet_live_base:
                self._wallet_live_base = int(used)
            if turn is not None and turn != self._wallet_last_turn:
                self._wallet_last_turn = int(turn)
                self._wallet_live_base = int(used)
        payload = grok_wallet_snapshot(
            pty_overlay=self._wallet_pty,
            live_base=self._wallet_live_base,
            tui_pid=self._tui_pid(),
        )
        text = json.dumps(payload, separators=(",", ":"))
        if text == self._wallet_json:
            return
        self._wallet_json = text
        self.grokWalletChanged.emit(text)
        current = ""
        if isinstance(payload, dict):
            session_path = str(payload.get("session") or "")
            if session_path:
                current = Path(session_path).name
        listing = json.dumps(
            list_for_ui(current_id=current),
            separators=(",", ":"),
        )
        if listing != self._sessions_json:
            self._sessions_json = listing
            self.chatSessionsChanged.emit(listing)

    def shutdown(self) -> None:
        self.stopSitePreview()
        embed = self._tui_embed
        self._tui_embed = None
        if embed is not None:
            embed.stop()
        for key in list(self._sessions):
            self._close(key)

    def _read(self, terminal_id: str) -> None:
        session = self._sessions.get(terminal_id)
        if session is None:
            return
        master = session["master"]
        chunks: list[bytes] = []
        try:
            while True:
                piece = os.read(master, 4096)
                if not piece:
                    break
                chunks.append(piece)
        except BlockingIOError:
            pass
        except OSError:
            self._close(terminal_id)
            return
        if chunks:
            raw = b"".join(chunks)
            if terminal_id == GROK_TUI_TERMINAL_ID:
                import base64

                self.grokTuiChunk.emit(base64.b64encode(raw).decode("ascii"))
                decoded = raw.decode("utf-8", errors="replace")
                overlay = parse_pty_wallet(_strip_ansi(decoded))
                if overlay:
                    self._wallet_pty.update(overlay)
                    self._emit_wallet()
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

    def _close(self, terminal_id: str) -> None:
        session = self._sessions.pop(terminal_id, None)
        if session is None:
            return
        timer = session.get("timer")
        if timer is not None:
            timer.stop()
            timer.deleteLater()
        notifier = session.get("notifier")
        if notifier is not None:
            notifier.setEnabled(False)
            notifier.deleteLater()
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
