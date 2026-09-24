"""Bounded authored character- and item-asset import contract for the GAME ENGINE.

The runtime simulation must not know anything about a mesh file.  This module
therefore owns the small, deterministic seam between an authored glTF 2.0
asset and the existing animation contract.  It validates local assets before
QtQuick3D's RuntimeLoader sees them, exposes clip names and budgets to the
snapshot, and returns an explicit shared low-poly fallback for anything that
is not safe or complete enough for the current character slot.

The validator is intentionally a manifest reader, not a second glTF renderer.
QtQuick3D remains responsible for decoding geometry, materials and skinning;
the backend only checks bounded structure and keeps the simulation data-only.
Static item meshes use the same gate but have a separate loader budget and
never enter the skinned character slot.  A character has one active visual
model: the authored model when it has real visual children, otherwise one
shared low-poly character geometry.  Missing animation clips do not justify a
second body; the binding reports ROOT_POSE_ONLY and the root pose remains
authoritative.
"""

from __future__ import annotations

import base64
import copy
import json
import math
import struct
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


SCHEMA = "gg.game-engine.assets.v1"

# Enterable stilt hut in local mesh units (Y -1 ground, +1 ridge).
# World size is this times entity sx/sy/sz.  Collision uses the same layout.
HUT_DECK_LOCAL_Y = -0.359
HUT_DECK_HX = 1.005
HUT_DECK_HZ = 0.870
HUT_WALL_HX = 0.625
HUT_WALL_HZ = 0.516
HUT_WALL_T = 0.038
HUT_DOOR_HALF = 0.261
HUT_LADDER_Z = -0.967
HUT_PLAYER_CLEARANCE = 0.32
GLTF_VERSION = "2.0"
SUPPORTED_EXTENSIONS = {".gltf", ".glb"}

# Keep the first runtime importer deliberately small.  These are admission
# limits, not targets for production content; a later offline compiler can
# produce optimized .qml/.mesh packages for larger assets.
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_REFERENCED_BYTES = 32 * 1024 * 1024
MAX_MESHES = 32
MAX_PRIMITIVES = 64
MAX_VERTICES = 200_000
MAX_JOINTS = 128
MAX_ANIMATIONS = 32
MAX_AUTHORED_INSTANCES = 8
MAX_AUTHORED_ITEM_INSTANCES = 24

PROCEDURAL_CHARACTER_MODE = "PROCEDURAL_GEOMETRY"
PROCEDURAL_CHARACTER_ASSET_ID = "gg-clay-crowd-character"
PROCEDURAL_CHARACTER_STYLE_ID = "GG_CLAY_LOW_POLY"
PROCEDURAL_CHARACTER_VERTEX_RECORDS = 1020
PROCEDURAL_CHARACTER_TRIANGLES = 1592
PROCEDURAL_CHARACTER_VERTEX_STRIDE = 40
PROCEDURAL_CHARACTER_POSE_VARIANTS = 32
PROCEDURAL_ASSET_MODE = "PROCEDURAL_GEOMETRY"
PROCEDURAL_ASSET_VERTEX_STRIDE = 40
PROCEDURAL_ASSET_MAX_FAMILIES = 96
PROCEDURAL_ASSET_STYLE_ID = "GG_CLAY_ASSET_KIT"
PROCEDURAL_ASSET_STYLE_VERSION = "v1"
WORLD_PROP_ASSET_FAMILIES = (
    "world.prop.rock",
    "world.prop.mangrove",
    "world.prop.shrine",
    "world.prop.barrel",
    "world.ramp",
    "world.tidehouse",
    "world.lantern",
    "world.spawn_marker",
    "world.stress_pebble",
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = (PROJECT_ROOT / "qml" / "assets").resolve()
DEFAULT_CHARACTER_ASSET_ID = "gg-clay-hero-a"
DEFAULT_CHARACTER_FILENAME = "authored/gg-clay-hero-a.glb"
DEFAULT_CHARACTER_SOURCE = ASSET_ROOT / DEFAULT_CHARACTER_FILENAME
DEFAULT_CROWD_CHARACTER_ASSET_ID = "kenney-blocky-character-a"
DEFAULT_CROWD_CHARACTER_SOURCE = (
    ASSET_ROOT / "third_party" / "kenney-blocky" / "character-a.glb"
)
CAST_CHARACTER_SOURCES: dict[str, tuple[str, Path]] = {
    "WANDERER": ("gg-clay-fisher", ASSET_ROOT / "authored" / "gg-clay-fisher.glb"),
    "GUARDIAN": ("gg-clay-guard", ASSET_ROOT / "authored" / "gg-clay-guard.glb"),
    "CRITTER": ("gg-clay-critter", ASSET_ROOT / "authored" / "gg-clay-critter.glb"),
}
# World props authored in the EXT Blender desk.  The engine imports the GLB;
# it does not keep a second Python silhouette for the same asset.
AUTHORED_WORLD_SOURCES: dict[str, dict[str, Any]] = {
    "PALM": {
        "asset_id": "gg-clay-palm",
        "source": ASSET_ROOT / "authored" / "world" / "gg-clay-palm.glb",
        "anchor": "FEET",
        "height_m": 4.16,
    },
}

# Static item meshes use the same local-only admission path as characters.
# The unit scales keep authored glTF metres aligned with the existing item
# visual states, whose primitive meshes are converted from Qt's 100-unit
# built-ins by ``sceneScale`` in QML.
DEFAULT_STATIC_ITEM_ASSET_SPECS: dict[str, dict[str, Any]] = {
    "itemmesh.iron_saber": {
        "source": ASSET_ROOT / "gg-authored-saber.gltf",
        "unit_scale": (1.0, 0.5, 3.75),
    },
    "container.supply_crate": {
        "source": ASSET_ROOT / "gg-authored-crate.gltf",
        "unit_scale": (0.5, 0.5, 0.5),
    },
}

# The names are the stable game-side vocabulary.  An authored file may omit a
# clip; in that case the root pose still works and the importer reports the
# missing clip instead of silently inventing one.
CLIP_BY_MOTION_STATE = {
    "IDLE": "Idle",
    "WALK": "Walk",
    "SPRINT": "Sprint",
    "AIR": "Air",
}

# The character visual seam is deliberately one-model wide.  This is a data
# contract consumed by QML and diagnostics, not a promise that every future
# authored file must remain a box forever.
CHARACTER_VISUAL_POLICY = "SINGLE_CHARACTER_MODEL"
CHARACTER_VISUAL_PREFERRED = "AUTHORED_SKINNED"
CHARACTER_VISUAL_FALLBACK = "SHARED_LOW_POLY_CHARACTER_GEOMETRY"

CHARACTER_STYLE_CONTRACT = {
    "id": PROCEDURAL_CHARACTER_STYLE_ID,
    "version": "v1",
    "surface": "MATTE_FACETED_CLAY",
    "palette": "RGBA_VERTEX_COLORS_NO_TEXTURE",
    "silhouette": "EXAGGERATED_READABLE_HUMANOID",
    "geometry": "ONE_SHARED_INDEXED_MESH",
    "animation": "FIXED_STEP_POSE_BUCKETS",
    "crowd_triangle_budget": PROCEDURAL_CHARACTER_TRIANGLES,
    "pose_variants": PROCEDURAL_CHARACTER_POSE_VARIANTS,
    "reference_policy": "INSPIRATION_ONLY_NO_SOURCE_COPY",
}

ASSET_KIT_STYLE_CONTRACT = {
    "id": PROCEDURAL_ASSET_STYLE_ID,
    "version": PROCEDURAL_ASSET_STYLE_VERSION,
    "surface": "MATTE_FACETED_CLAY",
    "palette": "RGBA_VERTEX_COLORS_NO_TEXTURE",
    "silhouette": "READABLE_GAMEPLAY_SCALE",
    "geometry": "ONE_CACHED_INDEXED_MESH_PER_ASSET_FAMILY",
    "materials": "SHARED_PRINCIPLED_DIELECTRIC",
    "item_state": "GROUND_CONTAINER_INVENTORY_EQUIPPED",
    "reference_policy": "INSPIRATION_ONLY_NO_SOURCE_COPY",
}

# Named empties parented to the clay-hero armature.  The rest offsets are
# gameplay-metre poses relative to the entity root and are used only while
# the authored model is not yet the live visual.  Once RuntimeLoader has
# the SOCKET_* node, equipment parents to that node and the rest pose is
# unused.
CHARACTER_ATTACHMENT_SOCKETS = (
    "HEAD",
    "CHEST",
    "MAIN_HAND",
    "OFF_HAND",
    "BACK",
    "FEET",
)
CHARACTER_SOCKET_REST_M = {
    "HEAD": [0.0, 0.83, 0.0],
    "CHEST": [0.0, 0.07, -0.16],
    "MAIN_HAND": [0.48, -0.29, -0.04],
    "OFF_HAND": [-0.48, -0.29, -0.04],
    "BACK": [0.0, 0.13, 0.22],
    "FEET": [0.0, -0.61, 0.0],
}
SLOT_TO_ATTACHMENT_SOCKET = {
    "HEAD": "HEAD",
    "NECK": "HEAD",
    "SHOULDERS": "CHEST",
    "BACK": "BACK",
    "CHEST": "CHEST",
    "FEET": "FEET",
    "MAIN_HAND": "MAIN_HAND",
    "OFF_HAND": "OFF_HAND",
    "RANGED": "MAIN_HAND",
}


def _error(
    asset_id: str,
    code: str,
    message: str,
    *,
    source: str = "",
    file_format: str = "GLTF2",
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "id": str(asset_id or "unknown-asset"),
        "status": "ERROR",
        "mode": "PREVIEW_FALLBACK",
        "source": "",
        "relative_source": "",
        "root_offset_m": 0.0,
        "format": file_format,
        "skinned": False,
        "animation_mode": "NONE",
        "skeleton": {"skins": 0, "joints": 0, "skinned_primitives": 0},
        "meshes": 0,
        "primitives": 0,
        "vertices": 0,
        "animations": 0,
        "clips": [],
        "bytes": 0,
        "attachment_sockets": {},
        "budget": {
            "max_source_bytes": MAX_SOURCE_BYTES,
            "max_referenced_bytes": MAX_REFERENCED_BYTES,
            "max_authored_instances": MAX_AUTHORED_INSTANCES,
        },
        "error": {"code": str(code), "message": str(message)},
        "requested_source": str(source or ""),
    }


def _safe_vec3(value: Any, default: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        value = default
    result: list[float] = []
    for index, fallback in enumerate(default):
        try:
            number = float(value[index])
        except (TypeError, ValueError, IndexError):
            number = fallback
        result.append(round(number if math.isfinite(number) else fallback, 4))
    return result


def empty_attachment() -> dict[str, Any]:
    return {"socket": "", "node": "", "rest": [0.0, 0.0, 0.0]}


def default_socket_row(socket_id: str) -> dict[str, Any]:
    wanted = str(socket_id or "").strip().upper()
    if wanted not in CHARACTER_ATTACHMENT_SOCKETS:
        return empty_attachment()
    return {
        "id": wanted,
        "socket": wanted,
        "node": f"SOCKET_{wanted}",
        "rest": list(CHARACTER_SOCKET_REST_M[wanted]),
    }


def _extract_attachment_sockets(nodes: Any) -> dict[str, dict[str, Any]]:
    """Read named SOCKET_* empties from a glTF node array."""
    found: dict[str, dict[str, Any]] = {}
    if not isinstance(nodes, list):
        return found
    for node in nodes:
        if not isinstance(node, dict):
            continue
        extras = node.get("extras") if isinstance(node.get("extras"), dict) else {}
        name = str(node.get("name") or "").strip()
        socket_id = str(extras.get("gg_socket") or "").strip().upper()
        if not socket_id and name.upper().startswith("SOCKET_"):
            socket_id = name.split("_", 1)[-1].strip().upper()
        if socket_id not in CHARACTER_ATTACHMENT_SOCKETS or socket_id in found:
            continue
        row = default_socket_row(socket_id)
        if name:
            row["node"] = name
        row["local_translation"] = _safe_vec3(node.get("translation"))
        found[socket_id] = row
    return found


def attachment_for_slot(slot: Any, sockets: Any = None) -> dict[str, Any]:
    """Map one gear slot onto a character attachment socket."""
    wanted = SLOT_TO_ATTACHMENT_SOCKET.get(str(slot or "").strip().upper(), "")
    if not wanted:
        return empty_attachment()
    row = sockets.get(wanted) if isinstance(sockets, dict) else None
    if not isinstance(row, dict):
        row = default_socket_row(wanted)
    rest = _safe_vec3(row.get("rest"), tuple(CHARACTER_SOCKET_REST_M[wanted]))
    node = str(row.get("node") or f"SOCKET_{wanted}").strip() or f"SOCKET_{wanted}"
    return {
        "socket": wanted,
        "node": node,
        "rest": rest,
    }


def _asset_id_for_path(path: Path) -> str:
    stem = path.stem.strip().lower().replace(" ", "-")
    return stem or "authored-asset"


def _path_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_local_source(source: Any) -> tuple[Path | None, str | None]:
    """Resolve one source without allowing URLs or path traversal."""
    raw = str(source or "").strip()
    if not raw:
        return None, "ASSET_SOURCE_EMPTY"

    parsed = urlparse(raw)
    if parsed.scheme:
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            return None, "ASSET_SOURCE_NOT_LOCAL"
        raw_path = unquote(parsed.path)
        candidate = Path(raw_path)
    else:
        candidate = Path(raw)
        if not candidate.is_absolute():
            # Both "hero.gltf" and the UI-friendly "assets/hero.gltf" are
            # accepted, but both still resolve under the bundled asset root.
            if candidate.parts and candidate.parts[0].lower() == "assets":
                candidate = ASSET_ROOT.parent.joinpath(*candidate.parts[1:])
            else:
                candidate = ASSET_ROOT / candidate

    try:
        resolved = candidate.resolve(strict=False)
    except OSError:
        return None, "ASSET_SOURCE_UNRESOLVABLE"
    if not _path_inside(resolved, ASSET_ROOT):
        return None, "ASSET_SOURCE_OUTSIDE_ALLOWLIST"
    if resolved.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return None, "ASSET_FORMAT_UNSUPPORTED"
    return resolved, None


def _read_json_document(path: Path) -> tuple[dict[str, Any] | None, bytes, str | None]:
    try:
        source_bytes = path.read_bytes()
    except OSError as exc:
        return None, b"", "ASSET_SOURCE_UNREADABLE:" + type(exc).__name__
    if len(source_bytes) > MAX_SOURCE_BYTES:
        return None, source_bytes, "ASSET_SOURCE_TOO_LARGE"

    if path.suffix.lower() == ".gltf":
        try:
            document = json.loads(source_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, source_bytes, "GLTF_JSON_INVALID"
        return (document if isinstance(document, dict) else None), source_bytes, (
            None if isinstance(document, dict) else "GLTF_ROOT_INVALID"
        )

    if len(source_bytes) < 20:
        return None, source_bytes, "GLB_HEADER_INVALID"
    try:
        magic, version, declared_length = struct.unpack_from("<4sII", source_bytes, 0)
    except struct.error:
        return None, source_bytes, "GLB_HEADER_INVALID"
    if magic != b"glTF" or version != 2:
        return None, source_bytes, "GLB_VERSION_UNSUPPORTED"
    if declared_length > len(source_bytes) or declared_length > MAX_SOURCE_BYTES:
        return None, source_bytes, "GLB_LENGTH_INVALID"

    offset = 12
    json_chunk: bytes | None = None
    while offset + 8 <= declared_length:
        chunk_length, chunk_type = struct.unpack_from("<II", source_bytes, offset)
        offset += 8
        end = offset + chunk_length
        if end > declared_length or end > len(source_bytes):
            return None, source_bytes, "GLB_CHUNK_INVALID"
        if chunk_type == 0x4E4F534A:  # ASCII JSON in little-endian uint32 form.
            json_chunk = source_bytes[offset:end].rstrip(b" \t\r\n\x00")
            break
        offset = end
    if json_chunk is None:
        return None, source_bytes, "GLB_JSON_CHUNK_MISSING"
    try:
        document = json.loads(json_chunk.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, source_bytes, "GLB_JSON_INVALID"
    return (document if isinstance(document, dict) else None), source_bytes, (
        None if isinstance(document, dict) else "GLB_ROOT_INVALID"
    )


def _accessor(document: dict[str, Any], index: Any) -> dict[str, Any] | None:
    accessors = document.get("accessors")
    if not isinstance(accessors, list):
        return None
    try:
        safe_index = int(index)
    except (TypeError, ValueError):
        return None
    if safe_index < 0 or safe_index >= len(accessors):
        return None
    value = accessors[safe_index]
    return value if isinstance(value, dict) else None


def _safe_count(accessor: dict[str, Any] | None) -> int:
    if not accessor:
        return 0
    try:
        count = int(accessor.get("count", 0))
    except (TypeError, ValueError):
        return 0
    return max(0, count)


def _validate_buffer_uris(path: Path, document: dict[str, Any]) -> tuple[int, str | None]:
    """Validate referenced buffers without decoding arbitrary remote data."""
    buffers = document.get("buffers", [])
    if not isinstance(buffers, list):
        return 0, "GLTF_BUFFERS_INVALID"
    total = 0
    for buffer in buffers:
        if not isinstance(buffer, dict):
            return total, "GLTF_BUFFER_INVALID"
        try:
            declared = int(buffer.get("byteLength", 0))
        except (TypeError, ValueError):
            return total, "GLTF_BUFFER_LENGTH_INVALID"
        if declared < 0 or declared > MAX_REFERENCED_BYTES:
            return total, "GLTF_BUFFER_TOO_LARGE"
        uri = buffer.get("uri")
        if uri is not None:
            if not isinstance(uri, str) or not uri:
                return total, "GLTF_BUFFER_URI_INVALID"
            if uri.startswith("data:"):
                try:
                    header, payload = uri.split(",", 1)
                    if ";base64" in header.lower():
                        actual = len(base64.b64decode(payload, validate=True))
                    else:
                        actual = len(unquote(payload).encode("utf-8"))
                except (ValueError, UnicodeError):
                    return total, "GLTF_DATA_URI_INVALID"
                if actual > MAX_REFERENCED_BYTES or actual < declared:
                    return total, "GLTF_DATA_URI_LENGTH_INVALID"
            else:
                parsed = urlparse(uri)
                if parsed.scheme or parsed.netloc or "\\" in uri:
                    return total, "GLTF_EXTERNAL_URI_INVALID"
                referenced = (path.parent / unquote(uri)).resolve(strict=False)
                if not _path_inside(referenced, ASSET_ROOT):
                    return total, "GLTF_EXTERNAL_URI_OUTSIDE_ALLOWLIST"
                try:
                    actual = referenced.stat().st_size
                except OSError:
                    return total, "GLTF_EXTERNAL_URI_MISSING"
                if actual > MAX_REFERENCED_BYTES or actual < declared:
                    return total, "GLTF_EXTERNAL_URI_LENGTH_INVALID"
        total += declared
        if total > MAX_REFERENCED_BYTES:
            return total, "GLTF_REFERENCED_DATA_TOO_LARGE"
    return total, None


def _validate_image_uris(path: Path, document: dict[str, Any]) -> tuple[int, str | None]:
    """Validate texture references before RuntimeLoader opens the asset.

    glTF may keep an image in a bufferView or beside the document.  The first
    runtime seam supports both forms, but external files must remain inside
    the same bundled allowlist as the model.  This prevents a seemingly local
    character from pulling arbitrary files into the renderer.
    """
    images = document.get("images", [])
    if not isinstance(images, list):
        return 0, "GLTF_IMAGES_INVALID"
    buffer_views = document.get("bufferViews", [])
    if not isinstance(buffer_views, list):
        return 0, "GLTF_BUFFER_VIEWS_INVALID"
    total = 0
    for image in images:
        if not isinstance(image, dict):
            return total, "GLTF_IMAGE_INVALID"
        uri = image.get("uri")
        if uri is None:
            try:
                buffer_view = int(image.get("bufferView", -1))
            except (TypeError, ValueError):
                return total, "GLTF_IMAGE_BUFFER_VIEW_INVALID"
            if buffer_view < 0 or buffer_view >= len(buffer_views):
                return total, "GLTF_IMAGE_BUFFER_VIEW_INVALID"
            view = buffer_views[buffer_view]
            if not isinstance(view, dict):
                return total, "GLTF_IMAGE_BUFFER_VIEW_INVALID"
            try:
                length = int(view.get("byteLength", 0))
            except (TypeError, ValueError):
                return total, "GLTF_IMAGE_LENGTH_INVALID"
            if length < 0 or length > MAX_REFERENCED_BYTES:
                return total, "GLTF_IMAGE_TOO_LARGE"
            continue
        if not isinstance(uri, str) or not uri:
            return total, "GLTF_IMAGE_URI_INVALID"
        if uri.startswith("data:"):
            try:
                header, payload = uri.split(",", 1)
                if ";base64" in header.lower():
                    actual = len(base64.b64decode(payload, validate=True))
                else:
                    actual = len(unquote(payload).encode("utf-8"))
            except (ValueError, UnicodeError):
                return total, "GLTF_IMAGE_DATA_URI_INVALID"
        else:
            parsed = urlparse(uri)
            if parsed.scheme or parsed.netloc or "\\" in uri:
                return total, "GLTF_IMAGE_EXTERNAL_URI_INVALID"
            referenced = (path.parent / unquote(uri)).resolve(strict=False)
            if not _path_inside(referenced, ASSET_ROOT):
                return total, "GLTF_IMAGE_OUTSIDE_ALLOWLIST"
            try:
                actual = referenced.stat().st_size
            except OSError:
                return total, "GLTF_IMAGE_MISSING"
        if actual > MAX_REFERENCED_BYTES:
            return total, "GLTF_IMAGE_TOO_LARGE"
        total += actual
        if total > MAX_REFERENCED_BYTES:
            return total, "GLTF_REFERENCED_IMAGES_TOO_LARGE"
    return total, None


def _validate_document(
    path: Path,
    source_bytes: bytes,
    document: dict[str, Any],
    asset_id: str,
) -> dict[str, Any]:
    asset_meta = document.get("asset")
    if not isinstance(asset_meta, dict) or str(asset_meta.get("version", "")) != GLTF_VERSION:
        return _error(asset_id, "GLTF_VERSION_UNSUPPORTED", "Only glTF 2.0 is admitted.", source=str(path))

    referenced_bytes, buffer_error = _validate_buffer_uris(path, document)
    if buffer_error:
        return _error(asset_id, buffer_error, "Referenced buffer data failed the local budget check.", source=str(path))
    image_bytes, image_error = _validate_image_uris(path, document)
    if image_error:
        return _error(asset_id, image_error, "Referenced image data failed the local budget check.", source=str(path))
    referenced_bytes += image_bytes
    if referenced_bytes > MAX_REFERENCED_BYTES:
        return _error(asset_id, "GLTF_REFERENCED_DATA_TOO_LARGE", "Referenced model and image data exceed the runtime admission budget.", source=str(path))

    meshes = document.get("meshes", [])
    nodes = document.get("nodes", [])
    skins = document.get("skins", [])
    animations = document.get("animations", [])
    if not isinstance(meshes, list) or not isinstance(nodes, list):
        return _error(asset_id, "GLTF_SCENE_ARRAYS_INVALID", "Meshes and nodes must be arrays.", source=str(path))
    if not isinstance(skins, list) or not isinstance(animations, list):
        return _error(asset_id, "GLTF_ANIMATION_ARRAYS_INVALID", "Skins and animations must be arrays.", source=str(path))
    if not meshes:
        return _error(asset_id, "GLTF_MESH_MISSING", "The authored asset contains no mesh.", source=str(path))
    if len(meshes) > MAX_MESHES or len(animations) > MAX_ANIMATIONS:
        return _error(asset_id, "GLTF_OBJECT_BUDGET_EXCEEDED", "Mesh or animation count exceeds the runtime admission budget.", source=str(path))

    primitive_count = 0
    vertex_count = 0
    skinned_primitives = 0
    for mesh in meshes:
        if not isinstance(mesh, dict) or not isinstance(mesh.get("primitives", []), list):
            return _error(asset_id, "GLTF_MESH_INVALID", "Every mesh must contain a primitive array.", source=str(path))
        for primitive in mesh["primitives"]:
            primitive_count += 1
            if primitive_count > MAX_PRIMITIVES or not isinstance(primitive, dict):
                return _error(asset_id, "GLTF_PRIMITIVE_BUDGET_EXCEEDED", "Primitive count or shape is outside the admission budget.", source=str(path))
            attributes = primitive.get("attributes", {})
            if not isinstance(attributes, dict) or _accessor(document, attributes.get("POSITION")) is None:
                return _error(asset_id, "GLTF_POSITION_MISSING", "Every primitive needs a valid POSITION accessor.", source=str(path))
            vertex_count += _safe_count(_accessor(document, attributes.get("POSITION")))
            if vertex_count > MAX_VERTICES:
                return _error(asset_id, "GLTF_VERTEX_BUDGET_EXCEEDED", "Vertex count exceeds the runtime admission budget.", source=str(path))
            joints = attributes.get("JOINTS_0")
            weights = attributes.get("WEIGHTS_0")
            if joints is not None or weights is not None:
                if _accessor(document, joints) is None or _accessor(document, weights) is None:
                    return _error(asset_id, "GLTF_SKIN_ATTRIBUTES_INVALID", "JOINTS_0 and WEIGHTS_0 must both reference valid accessors.", source=str(path))
                skinned_primitives += 1

    joint_count = 0
    for skin in skins:
        if not isinstance(skin, dict) or not isinstance(skin.get("joints", []), list):
            return _error(asset_id, "GLTF_SKIN_INVALID", "Every skin must contain a joint array.", source=str(path))
        joints = skin["joints"]
        joint_count += len(joints)
        if joint_count > MAX_JOINTS:
            return _error(asset_id, "GLTF_JOINT_BUDGET_EXCEEDED", "Joint count exceeds the runtime admission budget.", source=str(path))
        for joint in joints:
            try:
                joint_index = int(joint)
            except (TypeError, ValueError):
                return _error(asset_id, "GLTF_JOINT_INDEX_INVALID", "A skin references a non-integer joint.", source=str(path))
            if joint_index < 0 or joint_index >= len(nodes):
                return _error(asset_id, "GLTF_JOINT_INDEX_INVALID", "A skin references a node outside the node array.", source=str(path))

    clips: list[dict[str, Any]] = []
    seen_clip_names: set[str] = set()
    for index, animation in enumerate(animations):
        if not isinstance(animation, dict):
            return _error(asset_id, "GLTF_ANIMATION_INVALID", "Every animation must be an object.", source=str(path))
        name = str(animation.get("name", "") or f"ANIMATION_{index + 1}").strip()
        if not name:
            name = f"ANIMATION_{index + 1}"
        if name in seen_clip_names:
            return _error(asset_id, "GLTF_ANIMATION_NAME_DUPLICATE", "Animation names must be unique.", source=str(path))
        seen_clip_names.add(name)
        samplers = animation.get("samplers", [])
        channels = animation.get("channels", [])
        if not isinstance(samplers, list) or not isinstance(channels, list):
            return _error(asset_id, "GLTF_ANIMATION_INVALID", "Animation samplers and channels must be arrays.", source=str(path))
        duration = 0.0
        for sampler in samplers:
            if not isinstance(sampler, dict):
                return _error(asset_id, "GLTF_ANIMATION_SAMPLER_INVALID", "Animation sampler is not an object.", source=str(path))
            input_accessor = _accessor(document, sampler.get("input"))
            output_accessor = _accessor(document, sampler.get("output"))
            if input_accessor is None or output_accessor is None:
                return _error(asset_id, "GLTF_ANIMATION_ACCESSOR_INVALID", "Animation sampler references a missing accessor.", source=str(path))
            minimum = input_accessor.get("max", [0.0])
            try:
                duration = max(duration, float(minimum[-1] if isinstance(minimum, list) and minimum else 0.0))
            except (TypeError, ValueError):
                duration = 0.0
        clips.append({"name": name, "duration_s": round(max(0.0, duration), 3)})

    skinned = bool(skins and skinned_primitives)
    if skinned:
        mode = "AUTHORED_SKINNED"
        animation_mode = "GLTF_SKINNED"
    elif animations:
        # Kenney's blocky characters are intentionally admitted as a separate
        # mode. They animate node transforms rather than a shared skin, so
        # they must use the timeline adapter and never masquerade as a
        # skinned/retargetable asset.
        mode = "AUTHORED_NODE_ANIMATED"
        animation_mode = "GLTF_NODE_TIMELINE"
    else:
        mode = "AUTHORED_STATIC"
        animation_mode = "NONE"
    try:
        # Keep nested third-party assets addressable from the QML root.  Using
        # only ``path.name`` would flatten a texture/model pack and make the
        # snapshot claim a path that the RuntimeLoader cannot resolve.
        relative_source = path.relative_to(PROJECT_ROOT / "qml").as_posix()
    except ValueError:
        # This branch is retained for test fixtures or future local roots that
        # are admitted without living below the normal QML asset directory.
        relative_source = "assets/" + path.name
    return {
        "schema": SCHEMA,
        "id": str(asset_id),
        "status": "READY",
        "mode": mode,
        "source": path.as_uri(),
        "relative_source": relative_source,
        # Simulation entity Y is the stable avatar anchor used by the preview
        # mesh (roughly the hip/root).  Authored character files conventionally
        # place their local origin at the feet, so this keeps the fixture's
        # feet on the same terrain sample without changing physics or camera.
        "root_offset_m": -0.65,
        "format": "GLTF2",
        "skinned": skinned,
        "animation_mode": animation_mode,
        "skeleton": {
            "skins": len(skins),
            "joints": joint_count,
            "skinned_primitives": skinned_primitives,
        },
        "meshes": len(meshes),
        "primitives": primitive_count,
        "vertices": vertex_count,
        "animations": len(clips),
        "clips": clips,
        "bytes": len(source_bytes),
        "referenced_bytes": referenced_bytes,
        "attachment_sockets": _extract_attachment_sockets(nodes),
        "budget": {
            "max_source_bytes": MAX_SOURCE_BYTES,
            "max_referenced_bytes": MAX_REFERENCED_BYTES,
            "max_authored_instances": MAX_AUTHORED_INSTANCES,
        },
        "error": None,
    }


def inspect_asset(source: Any, asset_id: str | None = None) -> dict[str, Any]:
    """Validate one allowlisted local glTF/GLB and return its manifest view."""
    requested = str(source or "")
    path, error_code = _resolve_local_source(source)
    resolved_id = str(asset_id or (_asset_id_for_path(path) if path else "unknown-asset"))
    if error_code or path is None:
        return _error(resolved_id, error_code or "ASSET_SOURCE_INVALID", "Asset source is not an allowlisted local glTF file.", source=requested)
    try:
        if not path.is_file():
            return _error(resolved_id, "ASSET_SOURCE_MISSING", "The authored asset file does not exist.", source=requested)
    except OSError:
        return _error(resolved_id, "ASSET_SOURCE_UNREADABLE", "The authored asset file cannot be inspected.", source=requested)
    document, source_bytes, read_error = _read_json_document(path)
    if read_error or document is None:
        return _error(resolved_id, read_error or "GLTF_DOCUMENT_INVALID", "The glTF document could not be read.", source=requested)
    return _validate_document(path, source_bytes, document, resolved_id)


def _inspect_static_item_asset(
    asset_id: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    """Inspect one item mesh and keep skinned files out of item slots."""
    view = inspect_asset(spec.get("source"), asset_id)
    unit_scale = spec.get("unit_scale", (1.0, 1.0, 1.0))
    if not isinstance(unit_scale, (list, tuple)) or len(unit_scale) != 3:
        unit_scale = (1.0, 1.0, 1.0)
    safe_scale: list[float] = []
    for value in unit_scale:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = 1.0
        safe_scale.append(round(number if math.isfinite(number) and number > 0.0 else 1.0, 4))
    view["unit_scale"] = safe_scale
    if isinstance(view.get("budget"), dict):
        view["budget"]["max_authored_item_instances"] = MAX_AUTHORED_ITEM_INSTANCES
    if view.get("status") == "READY" and view.get("skinned"):
        view = copy.deepcopy(view)
        view["status"] = "ERROR"
        view["mode"] = "PRIMITIVE_FALLBACK"
        view["source"] = ""
        view["error"] = {
            "code": "ITEM_SKIN_UNEXPECTED",
            "message": "Static item slots do not admit skinned character assets.",
        }
        view["unit_scale"] = safe_scale
    return view


def procedural_character_asset() -> dict[str, Any]:
    """Describe the original runtime-generated crowd mesh as a real asset.

    It has no file URI by design: the geometry is built from the renderer's
    stable code contract and cached by pose bucket.  Calling it ``READY`` is
    not a placeholder claim; it means the runtime geometry and its material
    attributes are available before the QML scene is created.
    """
    return {
        "schema": SCHEMA,
        "id": PROCEDURAL_CHARACTER_ASSET_ID,
        "status": "READY",
        "mode": PROCEDURAL_CHARACTER_MODE,
        "source": "",
        "relative_source": "",
        "root_offset_m": -0.65,
        "format": "QQUICK3D_GEOMETRY",
        "skinned": False,
        "animation_mode": "FIXED_STEP_POSE_BUCKETS",
        "skeleton": {
            "skins": 0,
            "joints": 0,
            "skinned_primitives": 0,
        },
        "meshes": 1,
        "primitives": 1,
        "vertices": PROCEDURAL_CHARACTER_VERTEX_RECORDS,
        "triangles": PROCEDURAL_CHARACTER_TRIANGLES,
        "animations": 4,
        "clips": [
            {"name": "Idle", "duration_s": 0.0},
            {"name": "Walk", "duration_s": 0.0},
            {"name": "Sprint", "duration_s": 0.0},
            {"name": "Air", "duration_s": 0.0},
        ],
        "bytes": (
            PROCEDURAL_CHARACTER_VERTEX_RECORDS * PROCEDURAL_CHARACTER_VERTEX_STRIDE
            + PROCEDURAL_CHARACTER_TRIANGLES * 3 * 2
        ),
        "referenced_bytes": 0,
        "budget": {
            "max_source_bytes": MAX_SOURCE_BYTES,
            "max_referenced_bytes": MAX_REFERENCED_BYTES,
            "max_authored_instances": MAX_AUTHORED_INSTANCES,
        },
        "geometry": {
            "vertex_stride": PROCEDURAL_CHARACTER_VERTEX_STRIDE,
            "vertex_color": True,
            "pose_variants": PROCEDURAL_CHARACTER_POSE_VARIANTS,
        },
        "style": dict(CHARACTER_STYLE_CONTRACT),
        "attachment_sockets": {},
        "license": "ORIGINAL_RUNTIME_GENERATED",
        "error": None,
    }


def procedural_item_asset(asset_id: Any, item_kind: Any = "ITEM") -> dict[str, Any]:
    """Describe one native item-family mesh available before authored import.

    The returned record is intentionally a real renderer binding: the host
    resolves ``geometry_key`` to a cached ``QQuick3DGeometry`` object.  It is
    not a claim that an external file exists, and it does not hide a failed
    loader behind a fake success state.
    """
    wanted = str(asset_id or "item.unknown").strip()[:96] or "item.unknown"
    kind = str(item_kind or "ITEM").strip().upper()[:32] or "ITEM"
    return {
        "schema": SCHEMA,
        "id": wanted,
        "asset_id": wanted,
        "geometry_key": wanted,
        "asset_class": kind,
        "status": "READY",
        "mode": PROCEDURAL_ASSET_MODE,
        "source": "",
        "relative_source": "",
        "unit_scale": [1.0, 1.0, 1.0],
        "format": "QQUICK3D_GEOMETRY",
        "skinned": False,
        "animation_mode": "STATIC_STATEFUL_PRESENTATION",
        "meshes": 1,
        "primitives": 1,
        "geometry": {
            "vertex_stride": PROCEDURAL_ASSET_VERTEX_STRIDE,
            "vertex_color": True,
            "cache": "BOUNDED_ASSET_FAMILY",
            "topology": "INDEXED_TRIANGLES",
            "runtime_resolved": True,
            "budget": {
                "max_vertex_records": 4096,
                "max_triangles": 4096,
            },
        },
        "style": dict(ASSET_KIT_STYLE_CONTRACT),
        "license": "ORIGINAL_RUNTIME_GENERATED",
        "error": None,
    }


def _world_prop_variant(entity_id: Any) -> int:
    """Derive one stable prop silhouette without consulting render state."""
    digits = "".join(character for character in str(entity_id or "") if character.isdigit())
    try:
        return int(digits or "0") % 4
    except ValueError:
        return 0


def world_prop_asset(entity_kind: Any, entity_id: Any = "") -> dict[str, Any]:
    """Describe one world asset family for the native geometry renderer.

    World props are simulation entities, so their visual identity belongs in
    the same snapshot as position, scale and collision state.  The renderer
    can then select a cached geometry family from authored data instead of
    inferring a primitive from a QML fallback or from an entity id alone.
    """
    wanted = str(entity_kind or "PROP").strip().upper()
    variant = _world_prop_variant(entity_id)
    if "RAMP" in wanted:
        geometry_key = "world.ramp"
        asset_class = "RAMP"
        variant = 0
    elif any(token in wanted for token in ("HOUSE", "BUILDING", "STRUCTURE", "HUT")):
        geometry_key = "world.stilt_hut"
        asset_class = "HOUSE"
        variant = 0
    elif "PALM" in wanted or "TREE" in wanted:
        geometry_key = "world.palm"
        asset_class = "PALM"
        variant = 0
        authored = AUTHORED_WORLD_SOURCES.get("PALM") or {}
        authored_path = authored.get("source")
        if isinstance(authored_path, Path) and authored_path.is_file():
            try:
                relative_source = authored_path.relative_to(PROJECT_ROOT / "qml").as_posix()
            except ValueError:
                relative_source = "assets/" + authored_path.name
            return {
                "schema": SCHEMA,
                "id": geometry_key,
                "asset_id": str(authored.get("asset_id") or "gg-clay-palm"),
                "geometry_key": geometry_key,
                "asset_class": asset_class,
                "variant": 0,
                "mode": "AUTHORED_STATIC",
                "status": "READY",
                "source": authored_path.as_uri(),
                "relative_source": relative_source,
                "anchor": str(authored.get("anchor") or "FEET"),
                "height_m": float(authored.get("height_m") or 4.16),
                "unit_scale": [1.0, 1.0, 1.0],
                "style_id": PROCEDURAL_ASSET_STYLE_ID,
                "style": dict(ASSET_KIT_STYLE_CONTRACT),
                "format": "GLB",
                "state": "WORLD",
                "license": "ORIGINAL_BLENDER_AUTHORED",
                "error": None,
            }
    elif "DOCK" in wanted or "PIER" in wanted:
        geometry_key = "world.dock"
        asset_class = "DOCK"
        variant = 0
    elif "TOTEM" in wanted or "SHRINE" in wanted:
        geometry_key = "world.totem"
        asset_class = "TOTEM"
        variant = 0
    elif "LIGHT" in wanted or "LANTERN" in wanted:
        geometry_key = "world.lantern"
        asset_class = "LANTERN"
        variant = 0
    elif "SPAWN" in wanted:
        geometry_key = "world.spawn_marker"
        asset_class = "SPAWN_MARKER"
        variant = 0
    elif "STRESS" in wanted:
        geometry_key = "world.stress_pebble"
        asset_class = "STRESS_PROP"
        variant = 0
    else:
        geometry_key = WORLD_PROP_ASSET_FAMILIES[variant]
        asset_class = "PROP"
    return {
        "schema": SCHEMA,
        "id": geometry_key,
        "asset_id": geometry_key,
        "geometry_key": geometry_key,
        "asset_class": asset_class,
        "variant": variant,
        "mode": PROCEDURAL_ASSET_MODE,
        "status": "READY",
        "source": "",
        "unit_scale": [1.0, 1.0, 1.0],
        "style_id": PROCEDURAL_ASSET_STYLE_ID,
        "style": dict(ASSET_KIT_STYLE_CONTRACT),
        "format": "QQUICK3D_GEOMETRY",
        "state": "WORLD",
        "license": "ORIGINAL_RUNTIME_GENERATED",
        "error": None,
    }


def default_catalog() -> dict[str, Any]:
    """Return the stable catalog exposed by the runtime snapshot."""
    selected = inspect_asset(DEFAULT_CHARACTER_SOURCE, DEFAULT_CHARACTER_ASSET_ID)
    # The default character slot specifically requires skinning.  A valid but
    # static file is still reported, but is not allowed to replace the preview.
    if selected.get("status") == "READY" and not selected.get("skinned"):
        selected = copy.deepcopy(selected)
        selected["status"] = "ERROR"
        selected["mode"] = "PREVIEW_FALLBACK"
        selected["source"] = ""
        selected["error"] = {
            "code": "CHARACTER_SKIN_MISSING",
            "message": "The default character asset must contain a skin and JOINTS_0/WEIGHTS_0.",
        }
    # The blocky CC0 importer remains available as a validated reference
    # candidate, but it is intentionally not the live crowd style.  The live
    # population uses the original vertex-colored clay mesh below so the
    # visual contract is not tied to a third-party silhouette or texture pack.
    crowd_selected = procedural_character_asset()
    cast: dict[str, dict[str, Any]] = {}
    for role, (asset_id, source) in CAST_CHARACTER_SOURCES.items():
        view = inspect_asset(source, asset_id)
        if view.get("status") == "READY" and view.get("skinned"):
            cast[role] = view
    static_items = {
        asset_id: _inspect_static_item_asset(asset_id, spec)
        for asset_id, spec in DEFAULT_STATIC_ITEM_ASSET_SPECS.items()
    }
    return {
        "schema": SCHEMA,
        "policy": "ALLOWLISTED_LOCAL_GLTF2_RUNTIME_LOADER",
        "selected": selected,
        "cast": cast,
        "crowd_selected": crowd_selected,
        "crowd_visual": {
            "policy": "ORIGINAL_CLAY_LOW_POLY_CROWD",
            "driver": "FIXED_STEP_POSE_GEOMETRY",
            "license": "ORIGINAL_RUNTIME_GENERATED",
            "source_url": "",
            "reference_sources": [
                "https://www.kenney.nl/assets/blocky-characters",
                "https://quaternius.com/packs/rpgcharacters.html",
            ],
            "reference_policy": "INSPIRATION_ONLY_NO_SOURCE_COPY",
            "max_active_models": MAX_AUTHORED_INSTANCES,
        },
        "character_style": dict(CHARACTER_STYLE_CONTRACT),
        "asset_kit": dict(ASSET_KIT_STYLE_CONTRACT),
        "procedural_asset_budget": PROCEDURAL_ASSET_MAX_FAMILIES,
        "instance_budget": MAX_AUTHORED_INSTANCES,
        "static_items": static_items,
        "item_instance_budget": MAX_AUTHORED_ITEM_INSTANCES,
        "fallback": {
            "mode": CHARACTER_VISUAL_FALLBACK,
            "reason": "One shared low-poly character geometry stays visible until the authored model has real visual children.",
        },
        "character_visual": {
            "policy": CHARACTER_VISUAL_POLICY,
            "preferred": CHARACTER_VISUAL_PREFERRED,
            "fallback": CHARACTER_VISUAL_FALLBACK,
            "max_active_models_per_character": 1,
        },
        "clip_contract": dict(CLIP_BY_MOTION_STATE),
    }


def extend_static_items(
    catalog: dict[str, Any],
    specs: Any,
) -> dict[str, Any]:
    """Admit additional local static meshes for an activated content page."""
    result = copy.deepcopy(catalog) if isinstance(catalog, dict) else default_catalog()
    static_items = result.setdefault("static_items", {})
    if not isinstance(static_items, dict):
        static_items = {}
        result["static_items"] = static_items
    if not isinstance(specs, dict):
        return result
    for asset_id, raw_spec in list(specs.items())[:MAX_AUTHORED_ITEM_INSTANCES]:
        if not isinstance(raw_spec, dict):
            continue
        wanted = str(asset_id or "").strip()[:96]
        if not wanted:
            continue
        static_items[wanted] = _inspect_static_item_asset(wanted, raw_spec)
    result["static_items"] = dict(list(static_items.items())[:MAX_AUTHORED_ITEM_INSTANCES])
    result["item_instance_budget"] = MAX_AUTHORED_ITEM_INSTANCES
    return result


def entity_binding(
    catalog: dict[str, Any],
    motion_state: Any,
    phase: Any,
    instance_rank: int,
    *,
    asset_role: str = "DEFAULT",
) -> dict[str, Any]:
    """Map one simulation pose to an authored asset slot or explicit fallback."""
    state = str(motion_state or "IDLE").strip().upper()
    if state not in CLIP_BY_MOTION_STATE:
        state = "IDLE"
    try:
        safe_phase = float(phase)
    except (TypeError, ValueError):
        safe_phase = 0.0
    if not math.isfinite(safe_phase):
        safe_phase = 0.0
    safe_phase = math.fmod(safe_phase, math.tau)
    if safe_phase < 0.0:
        safe_phase += math.tau
    runtime_clip = ""
    selected = catalog.get("selected") if isinstance(catalog, dict) else None
    role = str(asset_role or "DEFAULT").upper()
    if isinstance(catalog, dict) and isinstance(catalog.get("cast"), dict):
        cast_row = catalog["cast"].get(role)
        if isinstance(cast_row, dict) and cast_row.get("status") == "READY":
            selected = cast_row
    if role == "CROWD":
        crowd_selected = catalog.get("crowd_selected") if isinstance(catalog, dict) else None
        if isinstance(crowd_selected, dict):
            selected = crowd_selected
    budget = MAX_AUTHORED_INSTANCES
    if isinstance(catalog, dict):
        try:
            budget = max(0, min(MAX_AUTHORED_INSTANCES, int(catalog.get("instance_budget", budget))))
        except (TypeError, ValueError):
            budget = MAX_AUTHORED_INSTANCES
    try:
        rank = int(instance_rank)
    except (TypeError, ValueError):
        rank = -1
    ready = (
        isinstance(selected, dict)
        and selected.get("status") == "READY"
        and selected.get("mode") in {
            "AUTHORED_SKINNED",
            "AUTHORED_NODE_ANIMATED",
            PROCEDURAL_CHARACTER_MODE,
        }
    )
    in_budget = 0 <= rank < budget
    if ready and in_budget:
        source = str(selected.get("source", ""))
        mode = str(selected.get("mode", "AUTHORED_SKINNED"))
        error = None
        requested_clip = CLIP_BY_MOTION_STATE[state]
        if mode == PROCEDURAL_CHARACTER_MODE:
            # The pose is generated from the same fixed-step state and phase;
            # it does not pretend to be a RuntimeLoader timeline clip.
            clip = requested_clip
            runtime_clip = ""
            clip_status = "PROCEDURAL_POSE"
        else:
            available_clips = {
                str(row.get("name", "")).casefold(): str(row.get("name", ""))
                for row in selected.get("clips", [])
                if isinstance(row, dict) and str(row.get("name", "")).strip()
            }
            runtime_clip = available_clips.get(requested_clip.casefold(), "")
            clip = requested_clip if runtime_clip else ""
            clip_status = "READY" if clip else "ROOT_POSE_ONLY"
    else:
        source = ""
        if ready and not in_budget and isinstance(selected, dict):
            mode = (
                "PROCEDURAL_BUDGET"
                if selected.get("mode") == PROCEDURAL_CHARACTER_MODE
                else "PREVIEW_BUDGET"
            )
        else:
            mode = "PREVIEW_FALLBACK"
        error = selected.get("error") if isinstance(selected, dict) else None
        clip = ""
        clip_status = "NOT_LOADED"
    try:
        root_offset_m = float(
            selected.get("root_offset_m", 0.0)
            if isinstance(selected, dict)
            else 0.0
        )
    except (TypeError, ValueError):
        root_offset_m = 0.0
    if not math.isfinite(root_offset_m):
        root_offset_m = 0.0
    return {
        "id": str(selected.get("id", DEFAULT_CHARACTER_ASSET_ID)) if isinstance(selected, dict) else DEFAULT_CHARACTER_ASSET_ID,
        "mode": mode,
        "source": source,
        "root_offset_m": round(root_offset_m, 4),
        "instance_rank": rank,
        "instance_budget": budget,
        "clip": clip,
        "runtime_clip": runtime_clip,
        "clip_status": clip_status,
        "animation_mode": str(
            selected.get("animation_mode", "NONE")
            if isinstance(selected, dict)
            else "NONE"
        ),
        "attachment_sockets": (
            dict(selected.get("attachment_sockets"))
            if (
                ready
                and in_budget
                and isinstance(selected, dict)
                and isinstance(selected.get("attachment_sockets"), dict)
                and str(selected.get("mode", "")) == "AUTHORED_SKINNED"
            )
            else {}
        ),
        "style_id": str(
            selected.get("style", {}).get("id", "")
            if isinstance(selected, dict)
            and isinstance(selected.get("style"), dict)
            else ""
        ),
        "phase": round(safe_phase, 5),
        "error": error,
    }


def item_binding(
    catalog: dict[str, Any],
    asset_id: Any,
    instance_rank: int,
    item_kind: Any = "ITEM",
) -> dict[str, Any]:
    """Map every item visual to the bounded native clay asset kit.

    Authored static glTF remains validated and exposed in ``static_items`` for
    an explicit promotion later.  The live presentation uses the native kit
    for every item family so a saber, chest, material and equipped object all
    share the same low-poly/clay language and no item silently becomes a cube.
    """
    wanted = str(asset_id or "item.unknown").strip()[:96] or "item.unknown"
    kind = str(item_kind or "ITEM").strip().upper()[:32] or "ITEM"
    static_items = catalog.get("static_items") if isinstance(catalog, dict) else None
    selected = static_items.get(wanted) if isinstance(static_items, dict) else None
    budget = MAX_AUTHORED_ITEM_INSTANCES
    if isinstance(catalog, dict):
        try:
            budget = max(
                0,
                min(
                    MAX_AUTHORED_ITEM_INSTANCES,
                    int(catalog.get("item_instance_budget", budget)),
                ),
            )
        except (TypeError, ValueError):
            budget = MAX_AUTHORED_ITEM_INSTANCES
    try:
        rank = int(instance_rank)
    except (TypeError, ValueError):
        rank = -1
    native = procedural_item_asset(wanted, kind)
    binding = {
        "schema": SCHEMA,
        "asset_id": wanted,
        "geometry_key": wanted,
        "asset_class": kind,
        "id": wanted,
        "mode": PROCEDURAL_ASSET_MODE,
        "status": "READY",
        "source": "",
        "relative_source": "",
        "unit_scale": [1.0, 1.0, 1.0],
        "instance_rank": rank,
        "instance_budget": budget,
        "style_id": PROCEDURAL_ASSET_STYLE_ID,
        "style": dict(ASSET_KIT_STYLE_CONTRACT),
        "format": "QQUICK3D_GEOMETRY",
        "geometry": dict(native.get("geometry", {})),
        "license": "ORIGINAL_RUNTIME_GENERATED",
        "error": None,
    }
    # Keep the validated file visible to inspectors without allowing it to
    # create a second live Model.  This makes promotion an explicit content
    # decision instead of an accidental per-item visual split.
    if isinstance(selected, dict):
        binding["authored_candidate"] = {
            "id": str(selected.get("id", wanted)),
            "status": str(selected.get("status", "ERROR")),
            "mode": str(selected.get("mode", "PREVIEW_FALLBACK")),
            "source": str(selected.get("source", "")),
        }
    return binding
