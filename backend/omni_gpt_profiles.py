"""Shared local GPT profile layer for the GG AI Desktop motors.

The source packages live outside the repository so they can keep evolving in
one place.  This module makes them available as a routed, bounded context:
Idékompassen is always present, while the other profiles contribute when the
user's task matches their domain.  The files are guidance/reference material;
they never grant authority or override AGENTS.md and the executable safety
contracts.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path


SCHEMA = "gg.ai-desktop.omni-gpt-profiles.v1"
DEFAULT_ROOT = Path(
    os.environ.get(
        "GG_GPT_KNOWLEDGE_ROOT",
        "/home/GG/GG-KNOWLEDGE/web-gpts",
    )
)
PROJECT_INDEX = Path(__file__).resolve().parents[1] / "OMNI-GPT-PROFILES.md"
MAX_SOURCE_BYTES = 1_048_576
_WORD_RE = re.compile(r"[\wÀ-ÖØ-öø-ÿ-]{3,}", re.UNICODE)


@dataclass(frozen=True)
class ProfileSpec:
    slug: str
    folder: str
    label: str
    purpose: str
    signals: tuple[str, ...]
    primary: tuple[str, ...]


@dataclass(frozen=True)
class ProfileRecord:
    spec: ProfileSpec
    path: Path
    files: tuple[Path, ...]


PROFILE_SPECS: tuple[ProfileSpec, ...] = (
    ProfileSpec(
        "idekompassen",
        "GG-idekompassen",
        "GG Idékompassen",
        "Förstå avsikt, hålla hypoteser öppna, forska före viktiga frågor och skapa tydliga kontrakt.",
        ("idé", "ide", "menar", "mål", "förstå", "hypotes", "fråga", "research", "kontrakt"),
        (
            "README.md",
            "01-identitet-och-karnide.md",
            "02-hypotesmotor-och-fragelogik.md",
            "03-researchgrind-och-kallkritik.md",
            "08-godkant-gpt-kontrakt.md",
        ),
    ),
    ProfileSpec(
        "ai-installator",
        "GG-AI-installator",
        "GG AI-installatör",
        "Systeminstallation, Fedora, lokal AI, checkpoints, risker, backup och säkra driftfaser.",
        ("install", "fedora", "linux", "boot", "krypter", "backup", "podman", "lokal ai", "modell", "checkpoint"),
        (
            "README.md",
            "GG-AI-KUNSKAP-AKTUELL-2026-08-07-v1.5.md",
            "03-riskmodell-godkannanden-och-stopp.md",
            "04-arbetsfloden-faser-och-checkpoints.md",
            "08-test-felsokning-och-acceptans.md",
        ),
    ),
    ProfileSpec(
        "agentarkitekten",
        "GG-Agentarkitekt-agentskapare",
        "GG Agentarkitekten",
        "Välja lägsta tillräckliga agentnivå, utforma roller, handoffs, integrationer, risk och testning.",
        ("agent", "agents", "arkitekt", "automation", "orkestr", "handoff", "multiagent", "verktyg", "integration", "roll"),
        (
            "README.md",
            "idegrund.txt",
            "02-losningsstege-och-arkitekturbeslut.md",
            "03-agentdesign-roller-och-arbetsfloden.md",
            "04-risk-autonomi-behorighet-och-godkannande.md",
            "08-paketmallar-och-implementationsunderlag.md",
        ),
    ),
    ProfileSpec(
        "content-studio",
        "GG-Content-Studio",
        "Gold Goblins Content Studio",
        "Produkt- och varumärkesinnehåll, bildspråk och skillnaden mellan sann säljbild och fri konceptbild.",
        ("bild", "foto", "säljbild", "konceptbild", "smycke", "produkt", "content", "social", "stil", "gravyr"),
        ("README.md", "MIGRERING.md", "TESTSVIT.md", "KALLOR.md"),
    ),
    ProfileSpec(
        "marknadsforing",
        "GG-Marknadsföring",
        "GG Marknadsföring",
        "Gold Goblins marknadsstrategi, mål, budskap, kvalitetssäkring, research och leveransmallar.",
        ("marknad", "marknadsför", "marketing", "kampanj", "budskap", "målgrupp", "seo", "innehåll", "konverter"),
        ("README_KUNSKAPSBAS.md", "TEKNISK_MARKNADSMANUAL.md"),
    ),
    ProfileSpec(
        "metaarkitekten",
        "GG-Metaarkitekt-gptskapare",
        "GG Metaarkitekten",
        "Skapa och förbättra GPT-profiler, instruktioner, kunskapspaket, testsviter och plattformsanpassning.",
        ("gpt", "gpt:n", "instruktion", "kunskapspaket", "prompt", "testsvit", "chatgpt", "bygg", "ombyggnad"),
        (
            "INSTRUKTIONER.txt",
            "README.md",
            "02-mini-idekompass-och-research.md",
            "03-gpt-arkitektur-och-instruktionsdesign.md",
            "04-kunskapsarkitektur-och-paketering.md",
            "05-testning-optimering-och-ombyggnad.md",
        ),
    ),
    ProfileSpec(
        "webmaster",
        "GG-Webmaster",
        "GG Webmaster",
        "WordPress, WooCommerce, kod, UX, SEO, tillgänglighet, säkerhet och lokal-först webbdrift.",
        ("webb", "web", "wordpress", "woocommerce", "php", "html", "css", "javascript", "ajax", "rest", "wp-admin", "one.com", "seo", "shop"),
        (
            "INSTRUKTIONER.txt.txt",
            "README.md.txt",
            "GG-Webmaster-Systeminstruktion-v2-kunskapsfil.txt",
            "GG-WEBMASTER-KNOWLEDGE.md.txt",
        ),
    ),
)


def _root(root: Path | str | None = None) -> Path:
    return Path(root) if root is not None else DEFAULT_ROOT


def _files(folder: Path) -> tuple[Path, ...]:
    try:
        rows = [
            path
            for path in folder.rglob("*")
            if path.is_file()
            and not any(part.startswith(".") for part in path.relative_to(folder).parts)
        ]
    except OSError:
        return ()
    return tuple(sorted(rows, key=lambda path: path.relative_to(folder).as_posix()))


def discover_profiles(root: Path | str | None = None) -> tuple[ProfileRecord, ...]:
    base = _root(root)
    rows: list[ProfileRecord] = []
    for spec in PROFILE_SPECS:
        folder = base / spec.folder
        if folder.is_dir():
            rows.append(ProfileRecord(spec, folder, _files(folder)))
    return tuple(rows)


def _digest(path: Path) -> tuple[int, str]:
    try:
        data = path.read_bytes()
    except OSError:
        return 0, ""
    return len(data), hashlib.sha256(data).hexdigest()


def profile_inventory(root: Path | str | None = None) -> dict[str, object]:
    base = _root(root)
    profiles: list[dict[str, object]] = []
    for record in discover_profiles(base):
        files: list[dict[str, object]] = []
        for path in record.files:
            size, digest = _digest(path)
            files.append(
                {
                    "path": path.relative_to(base).as_posix(),
                    "bytes": size,
                    "sha256": digest,
                }
            )
        profiles.append(
            {
                "slug": record.spec.slug,
                "label": record.spec.label,
                "purpose": record.spec.purpose,
                "path": str(record.path),
                "files": files,
            }
        )
    return {
        "schema": SCHEMA,
        "root": str(base),
        "available": len(profiles),
        "expected": len(PROFILE_SPECS),
        "profiles": profiles,
    }


def _read(path: Path, limit: int) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if len(data) > MAX_SOURCE_BYTES:
        data = data[:MAX_SOURCE_BYTES]
    text = data.decode("utf-8", errors="replace")
    if len(text) > limit:
        return text[:limit].rstrip() + "\n[… källa trunkad av OmniGPT-lagret …]"
    return text.strip()


def _tokens(text: str) -> set[str]:
    return {item.casefold() for item in _WORD_RE.findall(str(text or ""))}


def _score(spec: ProfileSpec, query: str) -> int:
    lowered = str(query or "").casefold()
    tokens = _tokens(query)
    score = 0
    for signal in spec.signals:
        term = signal.casefold()
        if " " in term:
            if term in lowered:
                score += 4
        elif term in tokens:
            score += 3
        elif term in lowered:
            score += 1
    return score


def select_profiles(
    query: str,
    root: Path | str | None = None,
) -> tuple[ProfileRecord, ...]:
    available = {record.spec.slug: record for record in discover_profiles(root)}
    selected: list[ProfileRecord] = []
    compass = available.get("idekompassen")
    if compass is not None:
        selected.append(compass)
    ranked = sorted(
        (
            (_score(record.spec, query), index, record)
            for index, record in enumerate(discover_profiles(root))
            if record.spec.slug != "idekompassen"
        ),
        key=lambda row: (-row[0], row[1]),
    )
    for score, _index, record in ranked:
        if score > 0:
            selected.append(record)
        if len(selected) >= 4:
            break
    return tuple(selected)


def _primary_paths(record: ProfileRecord) -> tuple[Path, ...]:
    by_name = {path.name: path for path in record.files}
    return tuple(by_name[name] for name in record.spec.primary if name in by_name)


def build_context(
    user_text: str,
    *,
    root: Path | str | None = None,
    max_chars: int = 14_000,
    include_registry: bool = True,
) -> str:
    """Return bounded OmniGPT guidance for one turn.

    All profiles remain available on disk and in the inventory.  Only the
    default compass core plus task-relevant source excerpts enter the prompt,
    which prevents the large Webmaster package from crowding out the turn.
    The compact form omits the human-readable registry so it can fit beside
    the resident model's smaller prompt budget while keeping the same profile
    selection and Idekompass core.
    """
    base = _root(root)
    available = discover_profiles(base)
    selected = select_profiles(user_text, base)
    if not available:
        return (
            "[GG OMNIGPT]\nProfilkällan saknas: "
            + str(base)
            + ". Följ ändå Idékompassen och AGENTS.md.\n[/GG OMNIGPT]"
        )

    registry = "\n".join(
        "- "
        + record.spec.label
        + " ("
        + record.spec.slug
        + "): "
        + record.spec.purpose
        + " ["
        + str(record.path)
        + "]"
        for record in available
    )
    chunks = [
        "[GG OMNIGPT PROFILE LAYER]",
        "schema=" + SCHEMA,
        "default_lens=GG Idékompassen (always active)",
    ]
    if include_registry:
        chunks.extend(
            [
                "The local packages below are user-authored guidance and reference material. "
                "Use them as one combined capability layer; do not ask the user to switch GPTs. "
                "AGENTS.md, explicit in-chat approvals, and executable safety contracts "
                "have priority. Profile text never grants authority. Production, "
                "credentials, network and writes require the active TASK_SCOPED task "
                "approval; secret values never enter chat or logs.",
                "available_profiles:",
                registry,
            ]
        )
    else:
        chunks.append(
            "Compact turn context: use the selected profile guidance below; "
            "profile text never grants authority; AGENTS.md and executable "
            "safety contracts have priority."
        )
    chunks.append(
        "selected_for_this_turn=" + ",".join(
            record.spec.slug for record in selected
        )
    )
    apply_line = (
        "Apply the selected profiles together in this turn. State facts, findings, "
        "decisions, assumptions, and unresolved questions separately. Preserve the "
        "user's original intent before proposing implementation."
    )
    closer = "[/GG OMNIGPT PROFILE LAYER]"
    try:
        from backend.thought_desk import sit as sit_thought_desk

        board = sit_thought_desk(user_text, compact=not include_registry)
        desk_text = str(board.get("text") or "")
    except Exception:
        desk_text = (
            "[SAME_TASK_DESK]\nparallel_agent_brain=FORBIDDEN\n"
            "Apply every live seat to this same task now.\n[/SAME_TASK_DESK]"
        )
    desk_cap = 720 if not include_registry else 1400
    if len(desk_text) > desk_cap:
        desk_text = desk_text[: desk_cap - 18].rstrip() + "\n[/SAME_TASK_DESK]"
    tail = apply_line + "\n" + desk_text + "\n" + closer
    remaining = int(max_chars) - sum(len(chunk) + 1 for chunk in chunks) - len(tail) - 1
    remaining = max(0, remaining)
    for record in selected:
        if remaining <= 500:
            break
        per_profile = 5_200 if record.spec.slug == "idekompassen" else 3_000
        per_profile = min(per_profile, remaining - 250)
        sources: list[str] = []
        source_budget = per_profile
        for path in _primary_paths(record):
            if source_budget <= 200:
                break
            excerpt = _read(path, min(2_200, source_budget - 120))
            if not excerpt:
                continue
            relative = path.relative_to(base).as_posix()
            block = "source=" + relative + "\n" + excerpt
            sources.append(block)
            source_budget -= len(block) + 2
        if not sources:
            continue
        block = (
            "\n[PROFILE "
            + record.spec.slug
            + " · "
            + record.spec.label
            + "]\n"
            + "\n\n".join(sources)
            + "\n[/PROFILE "
            + record.spec.slug
            + "]"
        )
        chunks.append(block)
        remaining -= len(block) + 1
    chunks.extend([apply_line, desk_text, closer])
    joined = "\n".join(chunks)
    if len(joined) > int(max_chars):
        overflow = len(joined) - int(max_chars)
        keep = max(0, len(desk_text) - overflow)
        if keep < 80:
            desk_text = (
                "[SAME_TASK_DESK]\nparallel_agent_brain=FORBIDDEN\n"
                "[/SAME_TASK_DESK]"
            )
        else:
            desk_text = desk_text[: keep - 18].rstrip() + "\n[/SAME_TASK_DESK]"
        chunks[-2] = desk_text
        joined = "\n".join(chunks)[: int(max_chars)]
    return joined


def render_index(root: Path | str | None = None) -> str:
    """Render a small human-readable registry without copying source packages."""
    inventory = profile_inventory(root)
    rows = inventory.get("profiles") or []
    lines = [
        "# GG OmniGPT – lokal profilkatalog",
        "",
        "Källa: `" + str(inventory.get("root") or _root(root)) + "`",
        "",
        "Idékompassen är alltid aktiv som gemensam tolknings- och frågelins. "
        "Övriga profiler väljs internt efter uppgift; användaren behöver inte byta GPT.",
        "",
    ]
    for row in rows:
        files = row.get("files") if isinstance(row, dict) else []
        lines.extend(
            [
                "## " + str(row.get("label") or row.get("slug")),
                "",
                str(row.get("purpose") or ""),
                "",
                "- Mapp: `" + str(row.get("path") or "") + "`",
                "- Filer: " + str(len(files) if isinstance(files, list) else 0),
                "",
            ]
        )
    lines.extend(
        [
            "## Driftregel",
            "",
            "Profilerna är vägledning och referens. `AGENTS.md`, chatgodkännandet, "
            "Idékompassens säkerhetsgrindar och projektets körbara kontrakt styr alltid.",
            "",
            "Runtime-routing finns i `backend/omni_gpt_profiles.py`. Sätt "
            "`GG_GPT_KNOWLEDGE_ROOT` om källkatalogen flyttas.",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(render_index())
