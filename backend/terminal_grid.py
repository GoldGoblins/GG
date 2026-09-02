from __future__ import annotations

import base64
import codecs

from PySide6.QtCore import (
    QObject,
    QRectF,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QGuiApplication
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QKeyEvent,
    QPainter,
)
from PySide6.QtQuick import QQuickItem, QQuickPaintedItem

from backend.mini_vt import (
    BOLD,
    DEFAULT_BG_RGB,
    DEFAULT_FG_RGB,
    DIM,
    HIDDEN,
    INVERSE,
    ITALIC,
    MiniVt,
    STRIKE,
    UNDERLINE,
    rgb_of,
)


def _color(rgb: tuple[int, int, int]) -> QColor:
    return QColor(rgb[0], rgb[1], rgb[2])


_VT_SNAP_MS = 33


class _VtHost(QObject):
    snapshotReady = Signal(object)
    repliesReady = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._vt = MiniVt(24, 80)
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._pulse: QTimer | None = None
        self._dirty = False

    @Slot()
    def start(self) -> None:
        pulse = QTimer(self)
        pulse.setInterval(_VT_SNAP_MS)
        pulse.timeout.connect(self._emit_snapshot)
        self._pulse = pulse

    @Slot(object)
    def feed(self, raw: object) -> None:
        blob = raw if isinstance(raw, (bytes, bytearray)) else b""
        if blob:
            text = self._decoder.decode(bytes(blob))
            if text:
                self._vt.feed(text)
            if self._vt.out:
                reply = "".join(self._vt.out)
                self._vt.out.clear()
                if reply:
                    self.repliesReady.emit(reply)
        self._dirty = True
        pulse = self._pulse
        if pulse is not None and not pulse.isActive():
            pulse.start()

    @Slot(int, int)
    def resize(self, rows: int, cols: int) -> None:
        self._vt.resize(int(rows), int(cols))
        self._dirty = True
        pulse = self._pulse
        if pulse is not None and not pulse.isActive():
            pulse.start()

    @Slot()
    def _emit_snapshot(self) -> None:
        if not self._dirty:
            pulse = self._pulse
            if pulse is not None:
                pulse.stop()
            return
        self._dirty = False
        vt = self._vt
        self.snapshotReady.emit(
            {
                "buf": [row[:] for row in vt.buf],
                "r": vt.r,
                "c": vt.c,
                "rows": vt.rows,
                "cols": vt.cols,
                "cursor_visible": vt.cursor_visible,
                "app_cursor": vt.app_cursor,
                "mouse_mode": vt.mouse_mode,
                "mouse_sgr": vt.mouse_sgr,
                "bracket_paste": vt.bracket_paste,
            }
        )

    @Slot()
    def shutdown(self) -> None:
        pulse = self._pulse
        self._pulse = None
        if pulse is not None:
            pulse.stop()
        thread = self.thread()
        if thread is not None:
            thread.quit()


class TerminalGrid(QQuickPaintedItem):
    dataProduced = Signal(str)
    resized = Signal(int, int)
    ready = Signal()
    _bytesIn = Signal(object)
    _resizeTo = Signal(int, int)

    def __init__(self, parent: QQuickItem | None = None) -> None:
        super().__init__(parent)
        self._vt = MiniVt(24, 80)
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._font = QFont("monospace")
        self._font.setPixelSize(13)
        self._font.setStyleHint(QFont.StyleHint.Monospace)
        self._font.setFixedPitch(True)
        self._cell_w = 8
        self._cell_h = 16
        self._ascent = 12
        self._cursor_on = True
        self._last_cols = 0
        self._last_rows = 0
        self._ready_emitted = False
        self._snap: dict | None = None
        self.setFillColor(_color(DEFAULT_BG_RGB))
        self.setAntialiasing(False)
        self.setOpaquePainting(True)
        self.setRenderTarget(QQuickPaintedItem.RenderTarget.Image)
        self.setAcceptedMouseButtons(
            Qt.MouseButton.LeftButton
            | Qt.MouseButton.RightButton
            | Qt.MouseButton.MiddleButton
        )
        self.setAcceptHoverEvents(True)
        self.setFlag(QQuickItem.Flag.ItemAcceptsInputMethod, True)
        self.setFlag(QQuickItem.Flag.ItemHasContents, True)
        self.setKeepMouseGrab(False)
        self.setFocus(True)
        self._blink = QTimer(self)
        self._blink.setInterval(530)
        self._blink.timeout.connect(self._toggle_cursor)
        self._blink.start()
        self._coalesce = QTimer(self)
        self._coalesce.setSingleShot(True)
        self._coalesce.setInterval(_VT_SNAP_MS)
        self._coalesce.timeout.connect(self.update)
        self.widthChanged.connect(self._refit)
        self.heightChanged.connect(self._refit)
        self._host = _VtHost()
        self._thread = QThread()
        self._thread.setObjectName("gg-vt-host")
        self._host.moveToThread(self._thread)
        self._bytesIn.connect(self._host.feed, Qt.ConnectionType.QueuedConnection)
        self._resizeTo.connect(self._host.resize, Qt.ConnectionType.QueuedConnection)
        self._host.snapshotReady.connect(self._apply_snapshot)
        self._host.repliesReady.connect(self.dataProduced.emit)
        self._thread.started.connect(self._host.start)
        app = QGuiApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_worker)
        self._thread.start()
        if parent is not None:
            self.setParentItem(parent)
            parent.widthChanged.connect(self._fill_parent)
            parent.heightChanged.connect(self._fill_parent)
            self._fill_parent()
        self._measure()
        QTimer.singleShot(0, self._emit_ready)

    def vt(self) -> MiniVt:
        return self._vt

    def _stop_worker(self) -> None:
        thread = self._thread
        if thread is None:
            return
        self._thread = None
        if thread.isRunning():
            thread.quit()
            if not thread.wait(1500):
                thread.terminate()
                thread.wait(400)
        self._host = None

    def itemChange(self, change, value):  # type: ignore[no-untyped-def]
        if change == QQuickItem.ItemChange.ItemSceneChange:
            window = getattr(value, "window", None)
            if window is None:
                self._stop_worker()
        return super().itemChange(change, value)

    def _fill_parent(self) -> None:
        parent = self.parentItem()
        if parent is None:
            return
        self.setX(2)
        self.setY(2)
        self.setWidth(max(0.0, float(parent.width()) - 4.0))
        self.setHeight(max(0.0, float(parent.height()) - 4.0))

    def _measure(self) -> None:
        metrics = QFontMetrics(self._font)
        self._cell_w = max(6, metrics.horizontalAdvance("M"))
        self._cell_h = max(10, metrics.height())
        self._ascent = metrics.ascent()

    def _emit_ready(self) -> None:
        if self._ready_emitted:
            return
        self._ready_emitted = True
        self._refit()
        self.ready.emit()

    def _toggle_cursor(self) -> None:
        if not self.hasActiveFocus():
            if not self._cursor_on:
                self._cursor_on = True
                self.update()
            return
        self._cursor_on = not self._cursor_on
        self.update()

    def _schedule(self) -> None:
        if not self._coalesce.isActive():
            self._coalesce.start()

    def _flush_replies(self) -> None:
        if not self._vt.out:
            return
        blob = "".join(self._vt.out)
        self._vt.out.clear()
        self.dataProduced.emit(blob)

    def _refit(self) -> None:
        width = int(self.width())
        height = int(self.height())
        if width <= 0 or height <= 0:
            return
        cols = max(16, min(240, width // self._cell_w))
        rows = max(8, min(80, height // self._cell_h))
        if cols != self._last_cols or rows != self._last_rows:
            self._vt.resize(rows, cols)
            self._last_cols = cols
            self._last_rows = rows
            self._resizeTo.emit(rows, cols)
            self.resized.emit(cols, rows)
            self.update()

    @Slot(str)
    def feedB64(self, blob: str) -> None:
        try:
            raw = base64.b64decode(blob.encode("ascii"), validate=False)
        except Exception:
            return
        self.feed_bytes(raw)

    def feed_bytes(self, raw: bytes) -> None:
        if not raw:
            return
        if self._thread is not None and self._thread.isRunning():
            self._bytesIn.emit(bytes(raw))
            return
        text = self._decoder.decode(raw)
        if not text:
            return
        self._vt.feed(text)
        self._flush_replies()
        self._schedule()

    @Slot(object)
    def _apply_snapshot(self, snap: object) -> None:
        if not isinstance(snap, dict):
            return
        self._snap = snap
        vt = self._vt
        vt.app_cursor = bool(snap.get("app_cursor"))
        vt.mouse_mode = int(snap.get("mouse_mode") or 0)
        vt.mouse_sgr = bool(snap.get("mouse_sgr"))
        vt.bracket_paste = bool(snap.get("bracket_paste"))
        self._schedule()

    def feed_text(self, text: str) -> None:
        if not text:
            return
        self._vt.feed(text)
        self._flush_replies()
        self._schedule()

    def paint(self, painter: QPainter) -> None:
        painter.setFont(self._font)
        painter.fillRect(self.contentsBoundingRect(), _color(DEFAULT_BG_RGB))
        cell_w = self._cell_w
        cell_h = self._cell_h
        snap = self._snap
        if snap is not None:
            buf = snap.get("buf") or []
            cursor_r = int(snap.get("r") or 0)
            cursor_c = int(snap.get("c") or 0)
            cursor_visible = bool(snap.get("cursor_visible"))
        else:
            buf = self._vt.buf
            cursor_r = self._vt.r
            cursor_c = self._vt.c
            cursor_visible = self._vt.cursor_visible
        for y, row in enumerate(buf):
            x = 0
            while x < len(row):
                ch, fg, bg, flags = row[x]
                if ch == "":
                    x += 1
                    continue
                run_fg, run_bg, run_flags = fg, bg, flags
                text = ch
                nx = x + 1
                while nx < len(row):
                    nch, nfg, nbg, nflags = row[nx]
                    if nch == "":
                        nx += 1
                        continue
                    if nfg != run_fg or nbg != run_bg or nflags != run_flags:
                        break
                    text += nch
                    nx += 1
                span = nx - x
                paint_fg, paint_bg = run_fg, run_bg
                if run_flags & INVERSE:
                    paint_fg, paint_bg = paint_bg, paint_fg
                if run_flags & BOLD and 0 <= paint_fg <= 7:
                    paint_fg += 8
                bg_rgb = rgb_of(paint_bg, False)
                fg_rgb = rgb_of(paint_fg, True)
                if run_flags & DIM:
                    fg_rgb = (fg_rgb[0] // 2, fg_rgb[1] // 2, fg_rgb[2] // 2)
                rect = QRectF(x * cell_w, y * cell_h, span * cell_w, cell_h)
                if bg_rgb != DEFAULT_BG_RGB:
                    painter.fillRect(rect, _color(bg_rgb))
                visible = "".join(part for part in text if part)
                if visible and not (run_flags & HIDDEN) and visible.strip() != "":
                    font = QFont(self._font)
                    font.setBold(bool(run_flags & BOLD))
                    font.setItalic(bool(run_flags & ITALIC))
                    font.setStrikeOut(bool(run_flags & STRIKE))
                    painter.setFont(font)
                    painter.setPen(_color(fg_rgb))
                    painter.drawText(
                        int(rect.x()),
                        int(y * cell_h + self._ascent),
                        visible,
                    )
                    if run_flags & UNDERLINE:
                        painter.drawLine(
                            int(rect.x()),
                            int((y + 1) * cell_h - 2),
                            int(rect.x() + rect.width()),
                            int((y + 1) * cell_h - 2),
                        )
                x = nx
        rows = len(buf)
        cols = len(buf[0]) if buf else 0
        if (
            cursor_visible
            and self._cursor_on
            and 0 <= cursor_r < rows
            and 0 <= cursor_c < cols
        ):
            cx = cursor_c * cell_w
            cy = cursor_r * cell_h
            painter.fillRect(QRectF(cx, cy, cell_w, cell_h), _color(DEFAULT_FG_RGB))
            ch = buf[cursor_r][cursor_c][0]
            if ch:
                painter.setPen(_color(DEFAULT_BG_RGB))
                painter.setFont(self._font)
                painter.drawText(cx, int(cy + self._ascent), ch)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        mapped = self._map_key(event)
        if mapped is None:
            super().keyPressEvent(event)
            return
        if mapped:
            self.dataProduced.emit(mapped)
        event.accept()

    def inputMethodEvent(self, event) -> None:
        commit = event.commitString()
        if commit:
            self.dataProduced.emit(commit)
            event.accept()
            return
        super().inputMethodEvent(event)

    def mousePressEvent(self, event) -> None:
        self.forceActiveFocus()
        report = self._mouse(event, pressed=True)
        if report:
            self.dataProduced.emit(report)
            event.accept()
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            paste = self._clipboard_text()
            if paste:
                self._emit_paste(paste)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        report = self._mouse(event, pressed=False)
        if report:
            self.dataProduced.emit(report)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._vt.mouse_mode >= 1002 and event.buttons():
            report = self._mouse(event, pressed=True, motion=True)
            if report:
                self.dataProduced.emit(report)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        if self._vt.mouse_mode:
            button = 64 if delta > 0 else 65
            col, row = self._cell_at(event.position().x(), event.position().y())
            report = self._vt.mouse_report(col, row, button, True)
            if report:
                self.dataProduced.emit(report)
            event.accept()
            return
        steps = max(1, abs(int(delta / 120)))
        seq = "\x1b[A" if delta > 0 else "\x1b[B"
        self.dataProduced.emit(seq * steps)
        event.accept()

    def _cell_at(self, px: float, py: float) -> tuple[int, int]:
        cols = int((self._snap or {}).get("cols") or self._vt.cols)
        rows = int((self._snap or {}).get("rows") or self._vt.rows)
        col = max(0, min(cols - 1, int(px // self._cell_w)))
        row = max(0, min(rows - 1, int(py // self._cell_h)))
        return col, row

    def _mouse(self, event, pressed: bool, motion: bool = False) -> str:
        if self._vt.mouse_mode == 0:
            return ""
        button = 0
        if event.button() == Qt.MouseButton.RightButton:
            button = 2
        elif event.button() == Qt.MouseButton.MiddleButton:
            button = 1
        elif motion:
            button = 0
        col, row = self._cell_at(event.position().x(), event.position().y())
        return self._vt.mouse_report(col, row, button, pressed, motion)

    def _clipboard_text(self) -> str:
        clip = QGuiApplication.clipboard()
        if clip is None:
            return ""
        return clip.text() or ""

    def _emit_paste(self, text: str) -> None:
        payload = text.replace("\n", "\r")
        if self._vt.bracket_paste:
            payload = "\x1b[200~" + payload + "\x1b[201~"
        self.dataProduced.emit(payload)

    def _map_key(self, event: QKeyEvent) -> str | None:
        key = event.key()
        mods = event.modifiers()
        text = event.text()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        if key == Qt.Key.Key_Shift or key == Qt.Key.Key_Control or key == Qt.Key.Key_Alt:
            return ""
        if key == Qt.Key.Key_Insert and shift:
            paste = self._clipboard_text()
            if paste:
                self._emit_paste(paste)
            return ""
        if ctrl and shift and key == Qt.Key.Key_V:
            paste = self._clipboard_text()
            if paste:
                self._emit_paste(paste)
            return ""
        if ctrl and shift and key == Qt.Key.Key_C:
            return ""
        arrows = {
            Qt.Key.Key_Up: ("A", "OA"),
            Qt.Key.Key_Down: ("B", "OB"),
            Qt.Key.Key_Right: ("C", "OC"),
            Qt.Key.Key_Left: ("D", "OD"),
        }
        if key in arrows:
            normal, app = arrows[key]
            if self._vt.app_cursor:
                return "\x1b" + app
            return "\x1b[" + normal
        extras = {
            Qt.Key.Key_Home: "\x1b[H",
            Qt.Key.Key_End: "\x1b[F",
            Qt.Key.Key_PageUp: "\x1b[5~",
            Qt.Key.Key_PageDown: "\x1b[6~",
            Qt.Key.Key_Insert: "\x1b[2~",
            Qt.Key.Key_Delete: "\x1b[3~",
            Qt.Key.Key_F1: "\x1bOP",
            Qt.Key.Key_F2: "\x1bOQ",
            Qt.Key.Key_F3: "\x1bOR",
            Qt.Key.Key_F4: "\x1bOS",
            Qt.Key.Key_F5: "\x1b[15~",
            Qt.Key.Key_F6: "\x1b[17~",
            Qt.Key.Key_F7: "\x1b[18~",
            Qt.Key.Key_F8: "\x1b[19~",
            Qt.Key.Key_F9: "\x1b[20~",
            Qt.Key.Key_F10: "\x1b[21~",
            Qt.Key.Key_F11: "\x1b[23~",
            Qt.Key.Key_F12: "\x1b[24~",
        }
        if key in extras:
            return extras[key]
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return "\r"
        if key == Qt.Key.Key_Backspace:
            return "\x7f"
        if key == Qt.Key.Key_Tab:
            return "\x1b[Z" if shift else "\t"
        if key == Qt.Key.Key_Escape:
            return "\x1b"
        if ctrl and text:
            return text
        if ctrl and Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            return chr(key - Qt.Key.Key_A + 1)
        if alt and text:
            return "\x1b" + text
        if text:
            return text
        return None
