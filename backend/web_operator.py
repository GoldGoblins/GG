from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from backend import web_surface


SCHEMA_COMMAND = "gg.web-operator-command.v1"
SCHEMA_RESULT = "gg.web-operator-result.v1"
GENERAL_ACTION_AUTHORITY = "NONE"
ROOT = Path("/home/GG/.local/state/goldgoblins/gg-ai-desktop/web-operator")
COMMAND_NAME = "command.json"
ACTIVE_NAME = "command.active.json"
RESULT_NAME = "result.json"

ACTIONS = ("OPEN", "SNAPSHOT", "CLICK", "TYPE", "RELOAD", "BACK")
RED_HOSTS = (
    "one.com",
    "www.one.com",
    "login.one.com",
    "www.login.one.com",
)
_PASSWORD_RE = re.compile(
    r"password|passwd|\bpwd\b|type\s*=\s*['\"]password['\"]",
    re.IGNORECASE,
)
_SHA_LIKE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class WebOperatorError(ValueError):
    pass


def ensure_root() -> Path:
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    return ROOT


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _write_exclusive(path: Path, data: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise WebOperatorError("FILE_EXISTS:" + path.name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _host(url: str) -> str:
    return str(urlparse(url).hostname or "").lower()


def risk_class_for(action: str, url: str) -> str:
    host = _host(url)
    path = str(urlparse(url).path or "").lower()
    if host.endswith("one.com") or host in RED_HOSTS:
        return "RED"
    if "wp-login.php" in path or "/wp-admin" in path:
        return "RED"
    if action in {"CLICK", "TYPE"}:
        return "YELLOW"
    if action == "OPEN" and host in {"goldgoblins.se", "www.goldgoblins.se"}:
        return "YELLOW"
    if action == "OPEN":
        return "YELLOW"
    return "GREEN"


def password_selector(selector: str) -> bool:
    return bool(_PASSWORD_RE.search(str(selector or "")))


def validate_command(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WebOperatorError("COMMAND_NOT_OBJECT")
    if value.get("schema") != SCHEMA_COMMAND:
        raise WebOperatorError("COMMAND_SCHEMA_INVALID")
    action = str(value.get("action") or "")
    if action not in ACTIONS:
        raise WebOperatorError("ACTION_INVALID")
    command_id = str(value.get("command_id") or "")
    if not command_id.startswith("webop-") or not _SHA_LIKE.fullmatch(command_id):
        raise WebOperatorError("COMMAND_ID_INVALID")
    url = str(value.get("url") or "")
    selector = str(value.get("selector") or "")
    text = value.get("text")
    if text is None:
        text = ""
    if not isinstance(text, str):
        raise WebOperatorError("TEXT_INVALID")
    if len(text) > 4000:
        raise WebOperatorError("TEXT_TOO_LONG")
    if len(selector) > 240:
        raise WebOperatorError("SELECTOR_TOO_LONG")
    if "javascript:" in selector.lower() or "<" in selector:
        raise WebOperatorError("SELECTOR_FORBIDDEN")
    if action == "OPEN":
        normalized = web_surface.normalize_browse_url(url)
        if not normalized:
            raise WebOperatorError("URL_NOT_ALLOWED")
        url = normalized
    elif url and not web_surface.browse_url_allowed(url) and url != "about:blank":
        raise WebOperatorError("URL_NOT_ALLOWED")
    if action in {"CLICK", "TYPE"} and not selector.strip():
        raise WebOperatorError("SELECTOR_REQUIRED")
    if action == "TYPE" and password_selector(selector):
        raise WebOperatorError("PASSWORD_FIELD_FORBIDDEN")
    if action == "TYPE" and not text:
        raise WebOperatorError("TEXT_REQUIRED")
    risk = risk_class_for(action, url)
    return {
        "schema": SCHEMA_COMMAND,
        "command_id": command_id,
        "action": action,
        "url": url,
        "selector": selector.strip(),
        "text": text,
        "risk_class": risk,
        "general_action_authority": GENERAL_ACTION_AUTHORITY,
    }


def make_command(
    action: str,
    *,
    url: str = "",
    selector: str = "",
    text: str = "",
) -> dict[str, Any]:
    return validate_command(
        {
            "schema": SCHEMA_COMMAND,
            "command_id": "webop-" + uuid.uuid4().hex[:24],
            "action": action,
            "url": url,
            "selector": selector,
            "text": text,
        }
    )


def make_result(
    command: dict[str, Any],
    *,
    ok: bool,
    reason_code: str,
    url: str = "",
    title: str = "",
    text: str = "",
    links: list[Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_RESULT,
        "command_id": command.get("command_id"),
        "ok": bool(ok),
        "reason_code": str(reason_code),
        "risk_class": command.get("risk_class") or "GREEN",
        "action": command.get("action"),
        "url": url,
        "title": title,
        "text": text[:8000],
        "links": list(links or [])[:40],
        "general_action_authority": GENERAL_ACTION_AUTHORITY,
        "visible_web_tab": True,
    }


def take_command() -> dict[str, Any] | None:
    ensure_root()
    path = ROOT / COMMAND_NAME
    active = ROOT / ACTIVE_NAME
    if active.is_file():
        try:
            return validate_command(json.loads(active.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, WebOperatorError):
            try:
                active.unlink()
            except OSError:
                pass
            return None
    if not path.is_file() or path.is_symlink():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        command = validate_command(json.loads(raw))
    except (OSError, json.JSONDecodeError, WebOperatorError):
        try:
            path.unlink()
        except OSError:
            pass
        return None
    try:
        os.replace(path, active)
    except OSError:
        return None
    return command


def write_result(result: dict[str, Any]) -> None:
    ensure_root()
    payload = _canonical(result)
    target = ROOT / RESULT_NAME
    if target.exists() or target.is_symlink():
        target.unlink()
    _write_exclusive(target, payload)
    active = ROOT / ACTIVE_NAME
    if active.exists():
        try:
            active.unlink()
        except OSError:
            pass


def submit(command: dict[str, Any], *, timeout: float = 25.0) -> dict[str, Any]:
    validated = validate_command(command)
    ensure_root()
    command_path = ROOT / COMMAND_NAME
    result_path = ROOT / RESULT_NAME
    if command_path.exists() or (ROOT / ACTIVE_NAME).exists():
        raise WebOperatorError("OPERATOR_BUSY")
    if result_path.exists():
        result_path.unlink()
    _write_exclusive(command_path, _canonical(validated))
    deadline = time.monotonic() + max(1.0, timeout)
    while time.monotonic() < deadline:
        if result_path.is_file():
            try:
                value = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                time.sleep(0.05)
                continue
            if value.get("command_id") == validated["command_id"]:
                return value
        time.sleep(0.05)
    raise WebOperatorError("OPERATOR_TIMEOUT")


def open_url(url: str, *, timeout: float = 25.0) -> dict[str, Any]:
    return submit(make_command("OPEN", url=url), timeout=timeout)


def snapshot(*, timeout: float = 25.0) -> dict[str, Any]:
    return submit(make_command("SNAPSHOT"), timeout=timeout)


def click(selector: str, *, timeout: float = 25.0) -> dict[str, Any]:
    return submit(make_command("CLICK", selector=selector), timeout=timeout)


def type_text(selector: str, text: str, *, timeout: float = 25.0) -> dict[str, Any]:
    return submit(
        make_command("TYPE", selector=selector, text=text),
        timeout=timeout,
    )


def reload_page(*, timeout: float = 25.0) -> dict[str, Any]:
    return submit(make_command("RELOAD"), timeout=timeout)


def go_back(*, timeout: float = 25.0) -> dict[str, Any]:
    return submit(make_command("BACK"), timeout=timeout)
