"""Render-budget contracts for the low-cost-first GAME ENGINE pipeline.

The contract separates policy from the active QtQuick3D fallback.  Optional
upscalers and native instancing can be probed later without making the potato
profile depend on a vendor driver or a heavyweight engine runtime.
"""

from __future__ import annotations

from copy import deepcopy
import os
from typing import Any


SCHEMA = "gg.game-engine.render.v1"
RICH_3D = "RICH_3D"
DOS_2D = "DOS_2D"
PRESENTATION_MODES = (RICH_3D, DOS_2D)
PROFILES = {
    "POTATO": {
        "resolution_scale": 0.67,
        "anti_aliasing": "NONE",
        "upscaler": "NONE",
        "shadow_policy": "BLOB_AND_BAKED",
        "max_visible_instances": 48,
        "max_visible_particles": 32,
        "texture_budget_mb": 128,
    },
    "BALANCED": {
        "resolution_scale": 1.0,
        "anti_aliasing": "MSAA",
        "upscaler": "NONE",
        "shadow_policy": "BAKED_PLUS_ONE_DYNAMIC",
        "max_visible_instances": 96,
        "max_visible_particles": 128,
        "texture_budget_mb": 512,
    },
    "MODERN": {
        "resolution_scale": 1.0,
        "anti_aliasing": "MSAA_PLUS_TEMPORAL_AA",
        "upscaler": "FSR_XESS_DLSS_OPTIONAL",
        "shadow_policy": "CACHED_CASCADES",
        "max_visible_instances": 160,
        "max_visible_particles": 256,
        "texture_budget_mb": 1024,
    },
    "CINEMATIC": {
        "resolution_scale": 1.25,
        "anti_aliasing": "SSAA_PLUS_TEMPORAL_AA",
        "upscaler": "DLSS_OR_FSR_OPTIONAL",
        "shadow_policy": "BAKED_CINEMATIC_PLUS_CONTACT",
        "max_visible_instances": 192,
        "max_visible_particles": 512,
        "texture_budget_mb": 2048,
    },
}
PROFILE_NAMES = tuple(PROFILES)


def optional_layers() -> list[dict[str, str]]:
    """Describe vendor layers without silently pretending they are linked."""
    return [
        {
            "name": "DLSS",
            "status": "NOT_LINKED",
            "activation": "NATIVE_RENDER_PLUGIN_AND_VENDOR_RUNTIME",
        },
        {
            "name": "FSR",
            "status": "NOT_LINKED",
            "activation": "NATIVE_RENDER_PLUGIN_OR_SHADER_PASS",
        },
        {
            "name": "XeSS",
            "status": "NOT_LINKED",
            "activation": "NATIVE_RENDER_PLUGIN_AND_VENDOR_RUNTIME",
        },
        {
            "name": "GPU_TIMESTAMPS",
            "status": "NOT_CONNECTED",
            "activation": "NATIVE_RHI_PROFILING_BRIDGE",
        },
    ]


def normalize_profile(value: Any, default: str = "BALANCED") -> str:
    profile = str(value or default).upper()
    return profile if profile in PROFILES else default


def normalize_presentation_mode(
    value: Any,
    default: str = RICH_3D,
) -> str:
    """Normalize the presentation layer without touching simulation state."""
    mode = str(value or default).upper()
    if mode in PRESENTATION_MODES:
        return mode
    return default if default in PRESENTATION_MODES else ""


def presentation_view(mode: Any, reason: Any = "") -> dict[str, Any]:
    """Describe the two render stages and their shared-data boundary."""
    normalized = normalize_presentation_mode(mode, "")
    if not normalized:
        normalized = RICH_3D
    failure_reason = str(reason or "").strip()[:96]
    if normalized == RICH_3D:
        failure_reason = ""
    return {
        "mode": normalized,
        "rich_3d": normalized == RICH_3D,
        "fallback_available": True,
        "fallback_mode": DOS_2D,
        "reason": failure_reason or "NONE",
        "authority": "SHARED_SIMULATION_SNAPSHOT",
        "simulation_unchanged": True,
        "transition": "PRESENTATION_ONLY_NO_WORLD_RESET",
    }


def build_render_view(
    profile: str,
    *,
    active_entities: int,
    active_particles: int,
    snapshot_build_ms: float = 0.0,
    presentation_mode: str = RICH_3D,
    presentation_reason: str = "",
) -> dict[str, Any]:
    name = normalize_profile(profile)
    policy = deepcopy(PROFILES[name])
    visible_instances = max(0, min(int(active_entities), policy["max_visible_instances"]))
    visible_particles = max(0, min(int(active_particles), policy["max_visible_particles"]))
    return {
        "schema": SCHEMA,
        "profile": name,
        "presentation": presentation_view(
            presentation_mode,
            presentation_reason,
        ),
        "backend": "QT_RHI_AUTO",
        "requested_rhi_backend": str(os.environ.get("QSG_RHI_BACKEND", "AUTO")).upper(),
        "backend_policy": "OPENGL_VULKAN_METAL_D3D_SELECTED_BY_QT_RHI",
        "policy": policy,
        "anti_aliasing": {
            "mode": policy["anti_aliasing"],
            "temporal_history": "OPTIONAL_RENDERER_LAYER",
        },
        "upscaling": {
            "mode": policy["upscaler"],
            "availability": "RUNTIME_PROBE_REQUIRED",
            "fallback": "NATIVE_RESOLUTION_OR_LINEAR_SCALE",
        },
        "optional_layers": optional_layers(),
        "visibility": {
            "strategy": "CELL_PORTAL_HLOD_PROJECTED_ERROR",
            "visible_instances": visible_instances,
            "visible_particles": visible_particles,
        },
        "instancing": {
            "strategy": "BOUNDED_QML_REPEATER3D_FALLBACK",
            "native_bridge": "OPTIONAL_QQUICK3D_INSTANCING_SUBCLASS",
            "per_tick_allocations": 0,
        },
        "measurement": {
            "kind": "CPU_HOST_SNAPSHOT_TIMING",
            "snapshot_build_ms": round(max(0.0, float(snapshot_build_ms)), 4),
            "gpu_timestamp_queries": "NOT_CONNECTED",
        },
        "estimated_draw_calls": 3,
        "honesty": "POLICY_AND_CPU_MEASUREMENT;_GPU_TIMINGS_REQUIRE_NATIVE_RENDER_BRIDGE",
    }
