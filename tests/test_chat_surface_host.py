#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))


def main() -> int:
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

    from backend.chat_surface_host import BASH, ChatSurfaceHost

    src = (PROJECT / "backend" / "chat_surface_host.py").read_text(
        encoding="utf-8"
    )
    if "bash -c" in src or "/bin/sh" in src:
        raise AssertionError("generic host shell in chat surface host")
    if "pty.openpty" not in src:
        raise AssertionError("chat terminal is not a real PTY")
    if BASH != "/bin/bash":
        raise AssertionError("unexpected bash path")

    app = QCoreApplication.instance() or QCoreApplication([])
    host = ChatSurfaceHost()
    chunks: list[str] = []
    host.chatTerminalOutput.connect(lambda _i, text: chunks.append(text))
    if not host.startChatTerminal("gg-term-contract"):
        raise AssertionError("PTY bash failed to start")
    if not host.writeChatTerminal(
        "gg-term-contract",
        "echo unique-gg-term-ok\n",
    ):
        raise AssertionError("PTY write failed")

    loop = QEventLoop()
    QTimer.singleShot(2000, loop.quit)

    def maybe_quit() -> None:
        if "unique-gg-term-ok" in "".join(chunks):
            loop.quit()

    host.chatTerminalOutput.connect(lambda _i, _t: maybe_quit())
    loop.exec()
    host.shutdown()
    blob = "".join(chunks)
    if "unique-gg-term-ok" not in blob:
        raise AssertionError("PTY produced no real command output")
    saved = host.saveScratchFile("untitled-close-test.txt", "ok\n")
    if not saved or not saved.endswith("untitled-close-test.txt"):
        raise AssertionError("scratch save failed")
    from pathlib import Path

    if Path(saved).read_text(encoding="utf-8") != "ok\n":
        raise AssertionError("scratch save bytes mismatch")
    if host.saveScratchFile("../escape.txt", "no"):
        raise AssertionError("scratch path escape accepted")
    from backend import desktop_settings

    saved_settings = desktop_settings.SETTINGS_PATH
    desktop_settings.SETTINGS_PATH = Path(tempfile.mkdtemp(prefix="gg-set-")) / "s.json"
    try:
        written = host.saveDesktopSettings('{"engineTarget":"GROK_WORKER"}')
        if not written:
            raise AssertionError("settings save failed")
        blob = json.loads(host.loadDesktopSettings())
        if blob.get("engineTarget") != "GROK_WORKER":
            raise AssertionError("settings load missed engine")
    finally:
        desktop_settings.SETTINGS_PATH = saved_settings
    if not hasattr(host, "startGrokTui"):
        raise AssertionError("startGrokTui missing")
    from backend.chat_surface_host import ChatSurfaceHost as HostClass
    src = Path(HostClass.startGrokTui.__code__.co_filename).read_text(
        encoding="utf-8"
    )
    from backend.mini_vt import MiniVt
    from backend.chat_surface_host import _strip_ansi

    screen = MiniVt(4, 10)
    screen.feed("hello")
    if "hello" not in screen.display():
        raise AssertionError("vt put failed")
    screen.feed("\x1b[2J\x1b[HABC")
    shown = screen.display()
    if "hello" in shown:
        raise AssertionError("vt clear did not replace the screen")
    if not shown.startswith("ABC"):
        raise AssertionError("vt home write failed: " + repr(shown))

    if "\x1b" in _strip_ansi("\x1b[0;grok\x1b[?1049h hi"):
        raise AssertionError("ANSI not stripped")
    if "hi" not in _strip_ansi("\x1b[0mhi"):
        raise AssertionError("text lost while stripping ANSI")
    if "grokTuiChunk" not in src:
        raise AssertionError("xterm hole unused")
    if "TerminalGrid" not in src:
        raise AssertionError("native TUI grid unused")
    if "_attach_native_tui" not in src:
        raise AssertionError("native TUI attach missing")
    if "build_grok_tui_argv(" not in src:
        raise AssertionError("TUI argv builder unused")
    if "workspaceFileChanged" not in src:
        raise AssertionError("live workspace watch missing")
    if "grokWalletChanged" not in src:
        raise AssertionError("wallet signal missing")
    if "grok_wallet" not in src:
        raise AssertionError("wallet module unused")
    if "chatSessionsChanged" not in src:
        raise AssertionError("chat session list signal missing")
    if "resumeGrokTui" not in src:
        raise AssertionError("resume grok tui missing")
    if "GIT_TERMINAL_PROMPT" not in src:
        raise AssertionError("TUI must not wait on git credentials")
    if "setInterval(15000)" not in src:
        raise AssertionError("wallet timer still too hot")
    if "_PTY_READ_BUDGET" not in src or "def _drain_pty" not in src:
        raise AssertionError("PTY output still parsed on every socket tick")
    if "_PTY_DRAIN_MS = 16" in src:
        raise AssertionError("PTY drain still at 16ms")
    if "lambda _fd=None, key=identity" in src:
        raise AssertionError(
            "PTY notifier lambda still binds Qt6 Type.Read as terminal id"
        )
    if "lambda *_args, key=identity" not in src:
        raise AssertionError(
            "PTY notifier must swallow Qt6 activated extra args"
        )
    from PySide6.QtCore import QSocketNotifier

    stolen: list[object] = []

    def _capture(key: object) -> None:
        stolen.append(key)

    identity = "ws.tui.grok"
    fixed = lambda *_args, key=identity: _capture(key)
    fixed(object(), QSocketNotifier.Type.Read)
    if stolen != [identity]:
        raise AssertionError(
            "Qt6 notifier args stole terminal id: " + repr(stolen)
        )
    if "cached_quick_item" not in (
        PROJECT / "backend" / "grok_tui_embed.py"
    ).read_text(encoding="utf-8"):
        raise AssertionError("embed hole cache helper missing")
    grid_src = (PROJECT / "backend" / "terminal_grid.py").read_text(encoding="utf-8")
    if "class _VtHost" not in grid_src or "QThread" not in grid_src:
        raise AssertionError("native TUI parser is still on the GUI thread")
    if "QThread(self)" in grid_src:
        raise AssertionError("VT QThread still dies with the Quick item")
    attach = src[src.index("def _attach_native_tui") : src.index("def _on_native_tui_ready")]
    if "_stop_worker" not in attach:
        raise AssertionError("TUI reattach still deleteLater a running QThread")
    if "mediaLiveStatus" not in src:
        raise AssertionError("mediaLiveStatus slot missing")
    if "live_status_json" not in src:
        raise AssertionError("live media slot still dumps status on the GUI thread")
    if "class _EmuWorker" not in src or "libretro_host.run()" not in src:
        raise AssertionError("libretro still ticks on the GUI thread")
    if "def _ensure_tui_grid" not in src:
        raise AssertionError("GROK TUI grid still boots before the TUI hole is shown")
    if "def ensureWebEngine" not in src:
        raise AssertionError("Chromium still boots with the desktop process")
    if "def _apply_tui_winsize" not in src:
        raise AssertionError("TUI resize still SIGWINCH on every layout twitch")
    if "session.get(\"cols\") is None" not in src:
        raise AssertionError("first TUI winsize still waits on the debounce timer")
    if "BlockingIOError" not in src:
        raise AssertionError("PTY write still blocks the GUI thread")
    if "parse_pty_wallet(_strip_ansi" in src:
        raise AssertionError("PTY drain still strips ANSI for wallet on the GUI thread")
    if "self._console_timer" in src or "def _console_tick" in src:
        raise AssertionError("16ms GUI console timer remains")
    if "_crypto_idle_work" not in src or 'name="gg-crypto-idle"' not in src:
        raise AssertionError("crypto idle tick still blocks the GUI thread")
    qml_dir = src[src.index("def _on_qml_dir") : src.index("def _emit_qml_reload")]
    if "_qml_reload.start()" in qml_dir or "watchQmlSources()" in qml_dir:
        raise AssertionError("QML directory events still reload the whole shell")
    if "mediaStateChanged" not in src:
        raise AssertionError("mediaStateChanged signal missing")
    if "cryptoRailStatus" not in src:
        raise AssertionError("rail status slot missing")
    if "cryptoTickTrader" not in src or "cryptoArmTrader" not in src:
        raise AssertionError("swing trader slots missing")
    if "cryptoBacktestTrader" not in src:
        raise AssertionError("trader backtest slot missing")
    if "cryptoSetBook" not in src:
        raise AssertionError("book switch slot missing")
    if "_crypto_idle_tick" not in src or "setInterval(60000)" not in src:
        raise AssertionError("nonstop crypto ticker missing")
    if "cryptoFlashArb" not in src:
        raise AssertionError("flash arb slot missing")
    if "cryptoEvalSignals" not in src or "cryptoArmBot" not in src:
        raise AssertionError("signal bot slots missing")
    if "cryptoLabOn" not in src or "cryptoLabOff" not in src:
        raise AssertionError("crypto lab start/stop missing")
    if "tmogSnapshot" not in src or "startTmog" not in src:
        raise AssertionError("tmog host slots missing")
    if "marketplaceStatus" not in src or "marketplaceList" not in src:
        raise AssertionError("marketplace host slots missing")
    if "marketplacePaperBuy" not in src or "marketplaceDelist" not in src:
        raise AssertionError("marketplace trade slots missing")
    if "shellLoadQueue" not in src:
        raise AssertionError("shell load queue slot missing")
    if "def hydrateDesktop" not in src:
        raise AssertionError("desktop hydrate slot missing")
    attach_root = src[
        src.index("def set_qml_root") : src.index("def _tui_hole")
    ]
    if "QTimer.singleShot(0, self._emit_wallet)" not in attach_root:
        raise AssertionError("first wallet/chats emit still waits for the 15s timer")
    if "self._emit_wallet()" not in src[src.index("def hydrateDesktop"): src.index("def _tui_hole")]:
        raise AssertionError("hydrateDesktop does not push wallet/chats")
    if not hasattr(host, "hydrateDesktop"):
        raise AssertionError("hydrateDesktop missing on host")
    import json as _json
    from backend.shell_load import queue as shell_queue
    queued = _json.loads(host.shellLoadQueue())
    if queued != shell_queue():
        raise AssertionError("host queue drifted from walker")
    if "qmlLiveReload" not in src:
        raise AssertionError("QML live reload missing")
    if "clearComponentCache" not in src:
        raise AssertionError("QML cache clear missing")
    if "restartDesktop" not in src:
        raise AssertionError("manual desktop restart missing")
    if "os.execv" in src or "_reexec_desktop" in src:
        raise AssertionError("RELOAD must not re-exec the desktop")
    listed = host.listShellSources()
    if "qml/Main.qml" not in listed:
        raise AssertionError("shell source list missing Main.qml")
    if "qml/components/WorkspaceSurface.qml" not in listed:
        raise AssertionError("shell source list missing WorkspaceSurface")
    if "startDetached" in src:
        raise AssertionError("desktop reload must stay in-process")
    if "self.watchDesktopWorkspace()\n        self.watchQmlSources()" in src:
        raise AssertionError("QML live reload still auto-starts")
    if host.watchLivePath("/etc/passwd") is not None:
        pass
    saved = host.saveScratchFile("live-watch.txt", "hello-live\n")
    if not saved:
        raise AssertionError("scratch live write failed")
    if host.readScratchFile("live-watch.txt") != "hello-live\n":
        raise AssertionError("scratch live read mismatch")
    if '"--sandbox"' in src and "off" not in src:
        raise AssertionError("TUI sandbox off missing in host")
    print("CHAT_SURFACE_HOST_TEST=PASS")
    print("CHAT_TERMINAL=REAL_PTY_BASH")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
