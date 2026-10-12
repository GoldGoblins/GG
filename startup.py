#!/usr/bin/env python3
"""Show the real desktop window before loading its backend modules."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# EXT hosts Blender as a native child of this window, so the desktop uses
# X11/XWayland rather than a Tool overlay.
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--disable-extensions --disable-background-networking --disable-sync "
    "--ignore-gpu-blocklist --enable-webgl --enable-webgl2 "
    "--enable-unsafe-swiftshader --renderer-process-limit=4",
)

try:
    from PySide6.QtCore import QObject, QTimer, QUrl, Qt
    from PySide6.QtGui import QFont, QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWidgets import QApplication
except Exception:
    print(
        "FAIL: PySide6/Qt missing. Fedora: dnf install python3-pyside6 "
        "qt6-qtwebengine",
        file=sys.stderr,
    )
    raise SystemExit(2)

PROJECT = Path(__file__).resolve().parent
QML_PATH = PROJECT / "qml" / "Main.qml"


class FirstFrameBootstrap(QObject):
    """Import backend code only after the integrated loading screen paints."""

    def __init__(
        self,
        root: QObject,
        app: QApplication,
        engine: QQmlApplicationEngine,
    ) -> None:
        super().__init__(app)
        self._root = root
        self._app = app
        self._engine = engine
        self._frame_swapped = None
        self._started = False

    def start(self) -> None:
        frame_swapped = getattr(self._root, "frameSwapped", None)
        if frame_swapped is None:
            self._show_failure("Qt did not expose the desktop render signal")
            return
        try:
            frame_swapped.connect(
                self._on_first_frame,
                Qt.ConnectionType.QueuedConnection,
            )
            self._frame_swapped = frame_swapped
        except (AttributeError, TypeError, RuntimeError) as exc:
            self._show_failure(
                "Could not connect the desktop render signal: " + str(exc)
            )
            return

        self._root.showMaximized()

    def _on_first_frame(self) -> None:
        if self._started:
            return
        self._started = True
        if self._frame_swapped is not None:
            try:
                self._frame_swapped.disconnect(self._on_first_frame)
            except (AttributeError, TypeError, RuntimeError):
                pass
            self._frame_swapped = None
        QTimer.singleShot(0, self._load_backend)

    def _load_backend(self) -> None:
        try:
            project_path = str(PROJECT)
            if project_path not in sys.path:
                sys.path.insert(0, project_path)
            import main as desktop_main

            desktop_main.initialize_loaded_window(self._root, self._app)
        except Exception as exc:
            self._show_failure(type(exc).__name__ + ": " + str(exc))

    def _show_failure(self, reason: str) -> None:
        self._root.setProperty("shellLoadLabel", "STARTUP FAILED")
        self._root.setProperty("shellLoadCurrent", reason)
        self._root.setProperty("shellLoading", True)
        append_log = getattr(self._root, "appendShellLog", None)
        if callable(append_log):
            append_log("startup · " + reason)
        print("GG AI Desktop startup failed: " + reason, file=sys.stderr)


def launch(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv if argv is None else argv)
    QGuiApplication.setDesktopFileName("org.goldgoblins.gg-ai-desktop")
    QGuiApplication.setApplicationName("GG AI Desktop")
    QGuiApplication.setApplicationDisplayName("GG AI Desktop")

    app = QApplication(arguments)
    desk_font = QFont("monospace")
    desk_font.setStyleHint(QFont.StyleHint.Monospace)
    app.setFont(desk_font)

    engine = QQmlApplicationEngine()
    engine.load(QUrl.fromLocalFile(str(QML_PATH)))
    roots = engine.rootObjects()
    if not roots:
        print(
            "GG AI Desktop startup failed: Main.qml did not create a window",
            file=sys.stderr,
        )
        return 2

    root = roots[0]
    bootstrap = FirstFrameBootstrap(root, app, engine)
    app._gg_qml_engine = engine  # type: ignore[attr-defined]
    app._gg_startup_bootstrap = bootstrap  # type: ignore[attr-defined]
    bootstrap.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(launch())
