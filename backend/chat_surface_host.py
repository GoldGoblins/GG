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
import threading
import time
from pathlib import Path
from typing import Any

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

from backend.chat_sessions import list_for_ui
from backend import crypto_host
from backend import libretro_host
from backend import media_host
from backend import tmog_contract
from backend.grok_wallet import snapshot as grok_wallet_snapshot
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

BASH = "/bin/bash"
_PTY_READ_BUDGET = 48 * 1024
_PTY_DRAIN_MS = 32
_PTY_BACKUP_MS = 500
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
    grokTuiChunk = Signal(str)
    grokWalletChanged = Signal(str)
    chatSessionsChanged = Signal(str)
    qmlLiveReload = Signal()
    workspaceFileChanged = Signal(str, str, str)
    siteImportProgress = Signal(str, int, int, str)
    mediaFrameSeqChanged = Signal()
    mediaStateChanged = Signal()
    mediaSeekChanged = Signal(float)

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
        self._sessions_json = ""
        self._pending_resume = ""
        self._wallet_timer = QTimer(self)
        self._wallet_timer.setInterval(15000)
        self._wallet_timer.timeout.connect(self._emit_wallet)
        self._wallet_timer.start()
        self._qml_watch: QFileSystemWatcher | None = None
        self._qml_reload = QTimer(self)
        self._qml_reload.setSingleShot(True)
        self._qml_reload.setInterval(250)
        self._qml_reload.timeout.connect(self._emit_qml_reload)
        self._emu: _EmuWorker | None = None
        self._crypto_timer = QTimer(self)
        self._crypto_timer.setInterval(60000)
        self._crypto_timer.timeout.connect(self._crypto_idle_tick)
        self._crypto_timer.start()
        self._console_provider = None
        self._console_provider_added = False
        self._console_sink = None
        self._console_io = None
        self._frame_seq = 0
        self._winch = QTimer(self)
        self._winch.setSingleShot(True)
        self._winch.setInterval(80)
        self._winch.timeout.connect(self._apply_tui_winsize)
        self._webengine_ready = False

    def set_qml_root(self, root: QObject | None) -> None:
        self._qml_root = root
        self.watchDesktopWorkspace()
        self._attach_native_tui()
        self._ensure_console_provider()

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
        try:
            hole.visibleChanged.connect(self._on_tui_hole_visible)
        except Exception:
            pass
        if hole.isVisible():
            self._ensure_tui_grid()

    def _ensure_tui_grid(self) -> None:
        hole = self._tui_hole()
        if hole is None:
            return
        grid = self._tui_grid
        if grid is not None and getattr(grid, "parentItem", lambda: None)() is hole:
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
        grid.resized.connect(self.grokTuiResize)
        grid.ready.connect(self._on_native_tui_ready)
        self._tui_grid = grid
        if hole.isVisible():
            grid.forceActiveFocus()

    def _on_native_tui_ready(self) -> None:
        hole = self._tui_hole()
        if hole is not None and hole.isVisible():
            self.startGrokTui("ws.tui.grok")

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
        drain = QTimer(self)
        drain.setSingleShot(True)
        drain.setInterval(_PTY_DRAIN_MS)
        backup = QTimer(self)
        backup.setInterval(_PTY_BACKUP_MS)
        session = {
            "proc": proc,
            "master": master,
            "notifier": notifier,
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
        drain.timeout.connect(lambda key=identity: self._drain_pty(key))
        backup.timeout.connect(lambda key=identity: self._pty_readable(key))
        self._sessions[identity] = session
        backup.start()
        drain.start()

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
        from PySide6.QtQml import QQmlEngine

        root = self._qml_root
        if root is not None:
            ctx = QQmlEngine.contextForObject(root)
            if ctx is not None:
                ctx.engine().clearComponentCache()
        self.qmlLiveReload.emit()

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
        if self._pending_tui_size == pending and self._winch.isActive():
            return
        self._pending_tui_size = pending
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
        session = self._sessions.get(str(terminal_id or "").strip())
        if session is None:
            return False
        payload = data if isinstance(data, str) else str(data)
        if payload == "":
            return True
        key = str(terminal_id or "").strip()
        try:
            os.write(session["master"], payload.encode("utf-8"))
        except BlockingIOError:
            return False
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
        grid = self._tui_grid
        self._tui_grid = None
        if grid is not None:
            grid.setParentItem(None)
            grid.deleteLater()
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
        for key in list(self._sessions):
            self._close(key)

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
            raw = b"".join(chunks)
            if terminal_id == GROK_TUI_TERMINAL_ID:
                grid = self._tui_grid
                if grid is not None:
                    grid.feed_bytes(raw)
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
