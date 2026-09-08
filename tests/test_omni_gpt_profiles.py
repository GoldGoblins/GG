#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))


def main() -> int:
    from backend.omni_gpt_profiles import (
        PROFILE_SPECS,
        build_context,
        profile_inventory,
        select_profiles,
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for spec in PROFILE_SPECS:
            folder = root / spec.folder
            folder.mkdir()
            (folder / spec.primary[0]).write_text(
                "# " + spec.label + "\n" + spec.purpose + "\n",
                encoding="utf-8",
            )
        inventory = profile_inventory(root)
        assert inventory["available"] == 7
        assert inventory["expected"] == 7
        assert len(inventory["profiles"]) == 7
        selected = {record.spec.slug for record in select_profiles("WordPress webshop", root)}
        assert "idekompassen" in selected
        assert "webmaster" in selected
        context = build_context("Installera Fedora och lokal AI", root=root, max_chars=8000)
        assert "default_lens=GG Idékompassen" in context
        assert "ai-installator" in context
        assert "AGENTS.md" in context
        compact = build_context(
            "Jag har en idé om en GPT och vill förstå vad jag menar",
            root=root,
            max_chars=2200,
            include_registry=False,
        )
        assert "Compact turn context" in compact
        assert "[PROFILE idekompassen" in compact
        assert "selected_for_this_turn=idekompassen" in compact

    import main
    from backend.grok_worker_contract import ENGINE_GPT_TUI, ENGINE_LOCAL_QWEN

    compiled = "CHAT=UNIVERSAL\n[GG OMNIGPT PROFILE LAYER]\n..."
    assert main.prompt_for_resident_engine(
        "hej",
        compiled,
        ENGINE_GPT_TUI,
    ) == "hej"
    assert main.prompt_for_resident_engine(
        "hej",
        compiled,
        ENGINE_LOCAL_QWEN,
    ) == compiled

    prompt, _context = main.build_effective_prompt(
        "Jag har en idé om en GPT och vill förstå den innan vi bygger",
        "@current",
        "ws.file.workspace-object-node",
        engine_target=ENGINE_GPT_TUI,
    )
    assert "default_lens=GG Idékompassen (always active)" in prompt
    assert "[PROFILE idekompassen" in prompt
    assert "available_profiles:" in prompt
    print("OMNIGPT_PROFILE_ROUTING_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
