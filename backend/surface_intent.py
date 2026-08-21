from __future__ import annotations

import re

_OPEN = re.compile(
    r"\b(öppna|visa|gå till|byt till|switch(?:a)?(?:\s+to)?|open|show)\b",
    re.IGNORECASE,
)
_TERMINAL = re.compile(r"\b(terminal(?:en)?|term|konsol(?:en)?|pty)\b", re.IGNORECASE)
_WEB = re.compile(
    r"\b(webb(?:en)?|web(?:ben)?|browser|webbläsare)\b",
    re.IGNORECASE,
)
_EXTERNAL = re.compile(
    r"\b(external|extern(?:t)?|program(?:met)?|app(?:en)?)\b",
    re.IGNORECASE,
)
_CODE = re.compile(
    r"\b(kod(?:en)?|filen|code|coden|qml|editorn)\b",
    re.IGNORECASE,
)
_SITE = re.compile(
    r"\b(sajt(?:en)?|site|hemsida(?:n)?|wordpress|dreamweaver|webbplats(?:en)?)\b",
    re.IGNORECASE,
)
_BARE = {
    "terminal": "TERMINAL",
    "term": "TERMINAL",
    "web": "WEB",
    "webb": "WEB",
    "external": "EXTERNAL",
    "kod": "CODE",
    "code": "CODE",
    "site": "SITE",
    "sajt": "SITE",
    "hemsida": "SITE",
}


def parse_surface_intent(text: str) -> str:
    value = " ".join(str(text or "").strip().split())
    if not value or len(value) > 80:
        return ""
    bare = _BARE.get(value.lower(), "")
    if bare:
        return bare
    if not _OPEN.search(value):
        return ""
    if _TERMINAL.search(value):
        return "TERMINAL"
    if _SITE.search(value):
        return "SITE"
    if _WEB.search(value):
        return "WEB"
    if _EXTERNAL.search(value):
        return "EXTERNAL"
    if _CODE.search(value):
        return "CODE"
    return ""
