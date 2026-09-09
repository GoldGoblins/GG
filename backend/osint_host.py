"""Qt bridge for the bounded native OSIRIS collector."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import json
import threading
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from backend import osint_contract


class OsintHost(QObject):
    """Keep public-feed I/O off the Qt GUI thread."""

    updated = Signal(str)
    stateChanged = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="gg-osiris-refresh",
        )
        self._future: Future[Any] | None = None
        self._raw = json.dumps(
            osint_contract.empty_snapshot(), separators=(",", ":")
        )
        self._closed = False

    @Slot(str, result=str)
    def snapshot(self, page: str = "OVERVIEW") -> str:
        with self._lock:
            if self._closed:
                return self._raw
        try:
            return json.dumps(
                osint_contract.snapshot(page), separators=(",", ":")
            )
        except Exception as exc:
            return json.dumps(
                {
                    "schema": osint_contract.SCHEMA,
                    "scope": osint_contract.SAFE_SCOPE,
                    "page": str(page or "OVERVIEW").upper(),
                    "status": "ERROR",
                    "error": type(exc).__name__,
                },
                separators=(",", ":"),
            )

    @Slot(str, result=str)
    def planRoute(self, spec_json: str = "{}") -> str:
        try:
            spec = json.loads(spec_json or "{}")
        except json.JSONDecodeError:
            spec = {}
        if not isinstance(spec, dict):
            spec = {}
        places = spec.get("places") or []
        if not isinstance(places, list):
            places = []
        gps = spec.get("gps") if isinstance(spec.get("gps"), dict) else None
        result = osint_contract.plan_driving_route(
            [str(item) for item in places],
            gps,
        )
        return json.dumps(result, separators=(",", ":"))

    @Slot(str, result=bool)
    def refresh(self, page: str = "OVERVIEW") -> bool:
        with self._lock:
            if self._closed:
                return False
            if self._future is not None:
                return False
            self.stateChanged.emit("FETCHING")
            self._future = self._executor.submit(
                osint_contract.collect_snapshot,
                str(page or "OVERVIEW"),
                True,
            )
            self._future.add_done_callback(self._finished)
        return True

    def _finished(self, future: Future[Any]) -> None:
        try:
            payload = future.result()
            raw = json.dumps(payload, separators=(",", ":"))
            state = str(payload.get("status") or "READY")
        except Exception as exc:
            raw = json.dumps(
                {
                    "schema": osint_contract.SCHEMA,
                    "scope": osint_contract.SAFE_SCOPE,
                    "status": "ERROR",
                    "error": type(exc).__name__,
                },
                separators=(",", ":"),
            )
            state = "ERROR"
        with self._lock:
            if self._closed:
                return
            self._raw = raw
            if self._future is future:
                self._future = None
        # PySide queues this signal when a QML receiver lives on the GUI
        # thread.  The worker never touches QML objects directly.
        self.updated.emit(raw)
        self.stateChanged.emit(state)

    def shutdown(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            future = self._future
            self._future = None
        if future is not None:
            future.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)
