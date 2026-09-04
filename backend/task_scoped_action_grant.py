from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

from backend import live_mandate_store


SCHEMA = "gg.task-scoped-action-grant.v1"
GENERAL_ACTION_AUTHORITY = "NONE"
ACTION_AUTHORITY = "TASK_SCOPED"

THIS_TASK = {
    "task_id": "task-live-mandate-store-task-scoped-action",
    "owner": "GG",
    "goal": (
        "After explicit human approval of a new YELLOW or RED task, grant "
        "TASK_SCOPED action inside the hash-bound Idékompass scope so work "
        "can proceed. GENERAL_ACTION_AUTHORITY stays NONE."
    ),
    "expected_value": (
        "A durable single-use mandate store plus a task-scoped grant that "
        "lets approved local work continue without flipping global action "
        "authority or opening one.com, credentials, production, or network."
    ),
    "scope": [
        "live mandate store for EXPLICIT_REQUIRED YELLOW/RED tasks",
        "task-scoped grant after MANDATE_VALID",
        "local workspace source bound by sha256",
        "existing limited-write and safe-tool paths",
    ],
    "forbidden_scope": [
        "network",
        "production",
        "one.com",
        "credentials",
        "sudo",
        "rights expansion",
        "automatic action authority",
        "GENERAL_ACTION_AUTHORITY other than NONE",
    ],
    "risk_class": "RED",
    "stop_conditions": [
        "approval_scope_revision drift",
        "target source sha256 drift",
        "replay of a consumed or approved request_capture",
        "attempt to inherit a previous mandate",
        "attempt to list a hard-forbidden effect in scope",
    ],
    "expected_artifacts": [
        "backend/live_mandate_store.py",
        "backend/task_scoped_action_grant.py",
        "tests proving GREEN needs no grant",
        "tests proving YELLOW/RED require explicit mandate",
        "tests proving GENERAL_ACTION_AUTHORITY remains NONE",
    ],
    "acceptance_criteria": [
        "GREEN continues without extra approval",
        "YELLOW and RED stay EXPLICIT_REQUIRED",
        "MANDATE_VALID issues TASK_SCOPED not ALL",
        "replay and hash drift fail closed",
        "one.com credentials production network sudo remain forbidden",
        "K7-K ACTION_AUTHORITY remains NONE",
    ],
}

ONE_COM_MANDATE = {
    "task_id": "task-one-com-named-red",
    "owner": "GG",
    "goal": (
        "Named RED mandate for goldgoblins.se on one.com: local SITE "
        "inventory, export, and a deploy step the user authenticates. "
        "No autonomous login and no agent-held credentials."
    ),
    "expected_value": (
        "After explicit /approve-mandate, only the listed local and "
        "user-authenticated steps may run. Production login stays with GG."
    ),
    "scope": [
        "local SITE copy under gg-ai-desktop/site",
        "local snippets, mu-plugins, and theme files",
        "read-only public goldgoblins.se",
        "user-authenticated export or deploy that GG performs",
    ],
    "forbidden_scope": [
        "autonomous one.com login",
        "agent-held credentials",
        "password in chat",
        "production write without a user-authenticated step",
        "sudo",
        "rights expansion",
        "automatic action authority",
        "GENERAL_ACTION_AUTHORITY other than NONE",
    ],
    "risk_class": "RED",
    "stop_conditions": [
        "credentials appear in chat or files",
        "attempted autonomous login or SFTP with stored secrets",
        "approval_scope_revision drift",
        "mandate inherited from another task",
    ],
    "expected_artifacts": [
        "named RED ready_core for one.com",
        "rail still TOOLS GREEN TYPED and WRITE YELLOW CURRENT",
        "no one.com session from this process",
    ],
    "acceptance_criteria": [
        "ONE_COM_MANDATE.risk_class is RED",
        "YELLOW/RED still require /approve-mandate",
        "GENERAL_ACTION_AUTHORITY remains NONE",
        "autonomous login remains forbidden",
    ],
}

HARD_FORBIDDEN = live_mandate_store.HARD_FORBIDDEN

GRANT_STATUSES = ("ACTIVE", "CONSUMED", "DEAD")

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

_GRANT_FIELDS = frozenset(
    {
        "schema",
        "general_action_authority",
        "action_authority",
        "grant_status",
        "task_id",
        "pending_id",
        "request_capture_sha256",
        "approval_scope_revision",
        "mandate_assertion_sha256",
        "risk_class",
        "capability_human_id",
        "target_object_id",
        "target_source_revision",
        "forbidden_scope",
        "store_record_sha256",
        "grant_sha256",
    }
)


class TaskScopedActionGrantError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise TaskScopedActionGrantError("CANONICAL_JSON_INVALID") from exc
    return (rendered + "\n").encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise TaskScopedActionGrantError(label + "_INVALID")
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise TaskScopedActionGrantError(label + "_INVALID")
    return value


def _forbidden(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TaskScopedActionGrantError("FORBIDDEN_SCOPE_INVALID")
    items: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise TaskScopedActionGrantError("FORBIDDEN_SCOPE_ITEM_INVALID")
        text = item.strip()
        if text in seen:
            raise TaskScopedActionGrantError("FORBIDDEN_SCOPE_DUPLICATE")
        seen.add(text)
        items.append(text)
    for required in HARD_FORBIDDEN:
        if required not in seen:
            raise TaskScopedActionGrantError(
                "HARD_FORBIDDEN_MISSING:" + required
            )
    return tuple(items)


def validate_grant(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _GRANT_FIELDS:
        raise TaskScopedActionGrantError("GRANT_SURFACE_INVALID")
    grant = copy.deepcopy(value)
    if grant["schema"] != SCHEMA:
        raise TaskScopedActionGrantError("GRANT_SCHEMA_INVALID")
    if grant["general_action_authority"] != GENERAL_ACTION_AUTHORITY:
        raise TaskScopedActionGrantError("GENERAL_ACTION_AUTHORITY_DRIFT")
    if grant["action_authority"] != ACTION_AUTHORITY:
        raise TaskScopedActionGrantError("ACTION_AUTHORITY_NOT_TASK_SCOPED")
    if grant["grant_status"] not in GRANT_STATUSES:
        raise TaskScopedActionGrantError("GRANT_STATUS_INVALID")
    _identifier(grant["task_id"], "TASK_ID")
    _identifier(grant["pending_id"], "PENDING_ID")
    _sha_text(grant["request_capture_sha256"], "REQUEST_CAPTURE_SHA256")
    _sha_text(grant["approval_scope_revision"], "APPROVAL_SCOPE_REVISION")
    _sha_text(grant["mandate_assertion_sha256"], "MANDATE_ASSERTION_SHA256")
    if grant["risk_class"] not in {"YELLOW", "RED"}:
        raise TaskScopedActionGrantError("RISK_CLASS_NOT_RED_OR_YELLOW")
    _identifier(grant["capability_human_id"], "CAPABILITY_HUMAN_ID")
    _identifier(grant["target_object_id"], "TARGET_OBJECT_ID")
    _sha_text(grant["target_source_revision"], "TARGET_SOURCE_REVISION")
    grant["forbidden_scope"] = list(_forbidden(grant["forbidden_scope"]))
    _sha_text(grant["store_record_sha256"], "STORE_RECORD_SHA256")
    without_hash = {
        key: copy.deepcopy(item)
        for key, item in grant.items()
        if key != "grant_sha256"
    }
    expected = _sha(without_hash)
    if grant["grant_sha256"] != expected:
        raise TaskScopedActionGrantError("GRANT_SHA256_MISMATCH")
    return grant


def green_path_no_grant() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "general_action_authority": GENERAL_ACTION_AUTHORITY,
        "action_authority": "NONE",
        "grant_status": "DEAD",
        "reason_code": "GREEN_RISK_CLASS",
        "mandate_requirement": "NOT_REQUIRED",
    }


def issue_from_approved_record(record: dict[str, Any]) -> dict[str, Any]:
    stored = live_mandate_store.validate_record(record)
    if stored["status"] != "APPROVED":
        raise TaskScopedActionGrantError(
            "GRANT_REQUIRES_APPROVED_RECORD:" + stored["status"]
        )
    grant = {
        "schema": SCHEMA,
        "general_action_authority": GENERAL_ACTION_AUTHORITY,
        "action_authority": ACTION_AUTHORITY,
        "grant_status": "ACTIVE",
        "task_id": stored["task_id"],
        "pending_id": stored["pending_id"],
        "request_capture_sha256": stored["request_capture_sha256"],
        "approval_scope_revision": stored["approval_scope_revision"],
        "mandate_assertion_sha256": stored["mandate_assertion_sha256"],
        "risk_class": stored["risk_class"],
        "capability_human_id": stored["capability_human_id"],
        "target_object_id": stored["target_object_id"],
        "target_source_revision": stored["target_source_revision"],
        "forbidden_scope": list(HARD_FORBIDDEN),
        "store_record_sha256": stored["record_sha256"],
    }
    grant["grant_sha256"] = _sha(
        {
            key: copy.deepcopy(item)
            for key, item in grant.items()
            if key != "grant_sha256"
        }
    )
    return validate_grant(grant)


def bind_current_target(
    grant: dict[str, Any],
    *,
    current_target_object_id: str,
    current_target_source_revision: str,
) -> dict[str, Any]:
    validated = validate_grant(grant)
    if validated["grant_status"] != "ACTIVE":
        raise TaskScopedActionGrantError(
            "GRANT_NOT_ACTIVE:" + validated["grant_status"]
        )
    if validated["target_object_id"] != current_target_object_id:
        raise TaskScopedActionGrantError("TARGET_OBJECT_DRIFT")
    if validated["target_source_revision"] != current_target_source_revision:
        raise TaskScopedActionGrantError("TARGET_SOURCE_DRIFT")
    return validated
