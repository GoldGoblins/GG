"""Application resources and per-user data, independent of the install path."""
from __future__ import annotations

import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()
STATE_HOME = Path(os.environ.get("XDG_STATE_HOME", HOME / ".local/state"))
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share"))
CACHE_HOME = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache"))
STATE_ROOT = Path(os.environ.get("GG_DESKTOP_STATE_ROOT", STATE_HOME / "goldgoblins/gg-ai-desktop"))
DATA_ROOT = Path(os.environ.get("GG_DESKTOP_DATA_ROOT", DATA_HOME / "goldgoblins/gg-ai-desktop"))
TOOLS_ROOT = DATA_HOME / "goldgoblins/tools"
SUPPORT_ROOT = PROJECT_ROOT / "support"
SKILLS_ROOT = PROJECT_ROOT / "skills"
GPT_KNOWLEDGE_ROOT = Path(os.environ.get("GG_GPT_KNOWLEDGE_ROOT", PROJECT_ROOT / "knowledge/web-gpts"))
USER_CODEX_HOME = Path(os.environ.get("GG_USER_CODEX_HOME", HOME / ".codex"))


def _default_workspace() -> Path:
    # Retain the shared development workspace when running in its projects/ tree.
    if PROJECT_ROOT.parent.name == "projects" and (PROJECT_ROOT.parent.parent / "AGENTS.md").is_file():
        return PROJECT_ROOT.parent.parent
    return PROJECT_ROOT


WORKSPACE_ROOT = Path(os.environ.get("GG_WORKSPACE", _default_workspace()))


def private_runtime_path(name: str, default: Path) -> Path:
    """Keep migration pointers in private state, outside distributed sources."""
    try:
        value = json.loads((STATE_ROOT / "runtime-paths.json").read_text()).get(name)
        if isinstance(value, str) and "\x00" not in value and Path(value).is_absolute():
            return Path(value)
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return default


def resource_path(relative: str, *, workspace: Path | None = None) -> Path:
    """Resolve a canonical source name without weakening its caller's checks."""
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("RESOURCE_PATH_OUTSIDE_APPLICATION")
    prefix = Path("projects/gg-ai-desktop")
    if path.parts[:2] == prefix.parts:
        return PROJECT_ROOT / Path(*path.parts[2:])
    packaged = SUPPORT_ROOT / path
    if packaged.exists() or packaged.is_symlink():
        return packaged
    # Compatibility for an older development checkout before support is bundled.
    return (workspace or WORKSPACE_ROOT) / path


def bundled_skills() -> tuple[Path, ...]:
    if not SKILLS_ROOT.is_dir():
        return ()
    return tuple(sorted(p.parent for p in SKILLS_ROOT.glob("*/SKILL.md")))


def prepare_codex_skills(codex_home: Path) -> None:
    """Expose GG skills while retaining each user's own skills and settings."""
    root = codex_home / "skills"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    for source in bundled_skills():
        target = root / source.name
        if target.is_symlink():
            if target.resolve() == source.resolve():
                continue
            # An installed GG skill may point at an older app installation.
            if source.name.startswith("gg-") and not target.exists():
                target.unlink()
            else:
                continue
        elif target.exists():
            continue
        target.symlink_to(source, target_is_directory=True)
