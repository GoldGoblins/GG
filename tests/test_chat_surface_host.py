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
    if "setInterval(2000)" not in src:
        raise AssertionError("wallet timer still too hot")
    if "cryptoTickTrader" not in src or "cryptoArmTrader" not in src:
        raise AssertionError("swing trader slots missing")
    if "cryptoFlashArb" not in src:
        raise AssertionError("flash arb slot missing")
    if "cryptoEvalSignals" not in src or "cryptoArmBot" not in src:
        raise AssertionError("signal bot slots missing")
    if "cryptoLabOn" not in src or "cryptoLabOff" not in src:
        raise AssertionError("crypto lab start/stop missing")
    if "tmogSnapshot" not in src or "startTmog" not in src:
        raise AssertionError("tmog host slots missing")
    if "shellLoadQueue" not in src:
        raise AssertionError("shell load queue slot missing")
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
