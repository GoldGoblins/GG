"""Small QtQuick3D geometry builders for the GAME ENGINE preview.

The simulation owns the terrain field.  This module turns one bounded height
grid from that contract into a native ``QQuick3DGeometry`` object and builds
one reusable low-poly character mesh.  It keeps the renderer cheap (a 5x5
grid for the nearest cell and eight cached character pose phases) while
allowing the surface to show slopes, rounded hills, authored brush relief and
a readable humanoid silhouette instead of one cube or render object per
detail.
"""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject
from PySide6.QtGui import QVector3D
from PySide6.QtQuick3D import QQuick3DGeometry


MAX_GEOMETRIES = 128
VERTEX_STRIDE = 32  # position (3), normal (3), UV (2), all little-endian f32
# The character mesh carries one RGBA vertex color after its position and
# normal.  Keeping this stride separate means terrain and item geometry retain
# their existing ABI while characters can have several readable material
# regions in one Model/draw path.
CHARACTER_VERTEX_STRIDE = 40  # position (3), normal (3), color (4)
CHARACTER_STYLE_ID = "GG_CLAY_LOW_POLY"
CHARACTER_STYLE_VERSION = "v1"
CHARACTER_POSE_BUCKETS = 8
CHARACTER_MOTION_STATES = {"IDLE", "WALK", "SPRINT", "AIR"}
ASSET_VERTEX_STRIDE = 40  # position (3), normal (3), RGBA vertex color (4)
ASSET_STYLE_ID = "GG_CLAY_ASSET_KIT"
ASSET_STYLE_VERSION = "v1"
MAX_ASSET_GEOMETRIES = 96
LOW_POLY_SPHERE_SEGMENTS = 12
LOW_POLY_SPHERE_RINGS = 6
LOW_POLY_SPHERE_RADIUS = 50.0
TERRAIN_SKIRT_DEPTH_M = 0.25
TERRAIN_SKIRT_NORMAL_UP = 0.88


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _cell_coordinates(cell: dict[str, Any]) -> tuple[int, int] | None:
    try:
        return int(cell.get("x", 0)), int(cell.get("z", 0))
    except (TypeError, ValueError):
        return None


CHARACTER_CAST_VARIANTS = ("CROWD", "WANDERER", "GUARDIAN", "CRITTER")


def character_variant_key(value: Any = "CROWD") -> str:
    kind = str(value or "CROWD").strip().upper()
    if kind in {"WANDERER", "GUARDIAN", "CRITTER"}:
        return kind
    return "CROWD"


def character_pose_key(
    motion_state: Any = "IDLE",
    phase: Any = 0.0,
) -> tuple[str, int]:
    """Quantize a pose to a small reusable geometry variant.

    A real skinned importer can later consume the same state and phase.  The
    preview deliberately quantizes the phase so thirty render updates per
    second do not create a new native QObject for every frame.
    """
    state = str(motion_state or "IDLE").strip().upper()
    if state not in CHARACTER_MOTION_STATES:
        state = "IDLE"
    safe_phase = _finite_float(phase) % math.tau
    bucket = int(
        math.floor(
            safe_phase / math.tau * CHARACTER_POSE_BUCKETS + 0.5
        )
    ) % CHARACTER_POSE_BUCKETS
    return state, bucket


def _rotate_x(y: float, z: float, angle: float) -> tuple[float, float]:
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return y * cosine - z * sine, y * sine + z * cosine


def _rotate_y(x: float, z: float, angle: float) -> tuple[float, float]:
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return x * cosine - z * sine, x * sine + z * cosine


def _append_vertex(
    vertex_data: bytearray,
    position: tuple[float, float, float],
    normal: tuple[float, float, float],
    *,
    uv: tuple[float, float] = (0.0, 0.0),
    color: tuple[float, float, float, float] | None = None,
) -> None:
    """Append one interleaved vertex for either legacy or colored geometry."""
    if color is None:
        vertex_data.extend(struct.pack("<8f", *position, *normal, *uv))
        return
    vertex_data.extend(struct.pack("<10f", *position, *normal, *color))


def _grid_for_cell(
    cell: dict[str, Any],
) -> tuple[int, list[float]] | None:
    geometry = cell.get("geometry")
    values = cell.get("height_grid_m")
    if not isinstance(geometry, dict) or not isinstance(values, list):
        return None
    try:
        grid_size = int(geometry.get("vertex_grid", 0))
    except (TypeError, ValueError):
        return None
    if grid_size < 2 or grid_size > 5 or len(values) != grid_size * grid_size:
        return None
    safe_values = [
        _finite_float(value)
        for value in values
    ]
    return grid_size, safe_values


def _normal_grid_for_cell(
    cell: dict[str, Any],
    grid_size: int,
) -> list[tuple[float, float, float]] | None:
    """Read shared-field normals when the terrain contract provides them."""
    values = cell.get("normal_grid")
    if not isinstance(values, list) or len(values) != grid_size * grid_size * 3:
        return None
    safe_values = [_finite_float(value) for value in values]
    result: list[tuple[float, float, float]] = []
    for index in range(0, len(safe_values), 3):
        nx, ny, nz = safe_values[index:index + 3]
        length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        result.append((nx / length, ny / length, nz / length))
    return result


def _append_terrain_skirt(
    vertex_data: bytearray,
    index_values: list[int],
    heights: list[float],
    grid_size: int,
    ordered_edge: list[int],
    normal: tuple[float, float, float],
    step: float,
) -> None:
    """Append one cheap vertical edge curtain for LOD seam protection.

    Adjacent patches share the analytic field's endpoint heights, but a 5x5
    patch next to a 3x3 or 2x2 patch can still have a rasterization gap at a
    T-junction.  A shallow curtain hides only that sub-pixel crack and keeps
    the real heightfield untouched.
    """
    top_indices: list[int] = []
    bottom_indices: list[int] = []
    # The curtain is a geometric seam guard, not a cliff face. A purely
    # horizontal normal receives almost no light from the preview's cheap
    # directional key and reads as a black crack in the terrain. Bias its
    # shading toward the terrain's upward normal while retaining a little
    # outward direction so the strip still rolls naturally at the edge.
    raw_nx, _raw_ny, raw_nz = normal
    horizontal = math.sqrt(raw_nx * raw_nx + raw_nz * raw_nz) or 1.0
    upward = TERRAIN_SKIRT_NORMAL_UP
    side = math.sqrt(max(0.0, 1.0 - upward * upward))
    nx = raw_nx / horizontal * side
    ny = upward
    nz = raw_nz / horizontal * side
    for source_index in ordered_edge:
        row, column = divmod(source_index, grid_size)
        x = column * step
        y = float(heights[source_index])
        z = row * step
        top_indices.append(len(vertex_data) // VERTEX_STRIDE)
        vertex_data.extend(
            struct.pack(
                "<8f",
                x,
                y,
                z,
                nx,
                ny,
                nz,
                column / float(grid_size - 1),
                row / float(grid_size - 1),
            )
        )
        bottom_indices.append(len(vertex_data) // VERTEX_STRIDE)
        vertex_data.extend(
            struct.pack(
                "<8f",
                x,
                y - TERRAIN_SKIRT_DEPTH_M,
                z,
                nx,
                ny,
                nz,
                column / float(grid_size - 1),
                row / float(grid_size - 1),
            )
        )
    for index in range(len(top_indices) - 1):
        top_a = top_indices[index]
        top_b = top_indices[index + 1]
        bottom_a = bottom_indices[index]
        bottom_b = bottom_indices[index + 1]
        index_values.extend(
            (
                top_a,
                top_b,
                bottom_b,
                top_a,
                bottom_b,
                bottom_a,
            )
        )


def _append_box(
    vertex_data: bytearray,
    index_values: list[int],
    center: tuple[float, float, float],
    half_size: tuple[float, float, float],
    rotation_x: float = 0.0,
    color: tuple[float, float, float, float] | None = None,
    vertex_stride: int = VERTEX_STRIDE,
) -> None:
    """Append one flat-shaded box to a combined character mesh."""
    cx, cy, cz = center
    hx, hy, hz = half_size
    faces = (
        ((0.0, -1.0, 0.0),
         ((-hx, -hy, -hz), (hx, -hy, -hz),
          (hx, -hy, hz), (-hx, -hy, hz))),
        ((0.0, 1.0, 0.0),
         ((-hx, hy, -hz), (-hx, hy, hz),
          (hx, hy, hz), (hx, hy, -hz))),
        ((0.0, 0.0, -1.0),
         ((-hx, -hy, -hz), (-hx, hy, -hz),
          (hx, hy, -hz), (hx, -hy, -hz))),
        ((0.0, 0.0, 1.0),
         ((-hx, -hy, hz), (hx, -hy, hz),
          (hx, hy, hz), (-hx, hy, hz))),
        ((-1.0, 0.0, 0.0),
         ((-hx, -hy, hz), (-hx, hy, hz),
          (-hx, hy, -hz), (-hx, -hy, -hz))),
        ((1.0, 0.0, 0.0),
         ((hx, -hy, -hz), (hx, hy, -hz),
          (hx, hy, hz), (hx, -hy, hz))),
    )
    for normal, corners in faces:
        start = len(vertex_data) // vertex_stride
        nx, ny, nz = normal
        normal_y, normal_z = _rotate_x(ny, nz, rotation_x)
        for index, (x, y, z) in enumerate(corners):
            rotated_y, rotated_z = _rotate_x(y, z, rotation_x)
            _append_vertex(
                vertex_data,
                (cx + x, cy + rotated_y, cz + rotated_z),
                (nx, normal_y, normal_z),
                uv=(
                    0.0 if index in (0, 3) else 1.0,
                    0.0 if index in (0, 1) else 1.0,
                ),
                color=color,
            )
        index_values.extend(
            (
                start,
                start + 1,
                start + 2,
                start,
                start + 2,
                start + 3,
            )
        )


def _append_ellipsoid(
    vertex_data: bytearray,
    index_values: list[int],
    center: tuple[float, float, float],
    radius: tuple[float, float, float],
    *,
    segments: int = 8,
    rings: int = 4,
    rotation_x: float = 0.0,
    yaw: float = 0.0,
    color: tuple[float, float, float, float] | None = None,
    vertex_stride: int = VERTEX_STRIDE,
) -> None:
    """Append a small smooth low-poly ellipsoid for a torso, limb or frond."""
    cx, cy, cz = center
    rx, ry, rz = radius
    start = len(vertex_data) // vertex_stride
    for ring in range(rings + 1):
        theta = math.pi * ring / float(rings)
        sine = math.sin(theta)
        cosine = math.cos(theta)
        for segment in range(segments):
            phi = math.tau * segment / float(segments)
            x = sine * math.cos(phi)
            y = cosine
            z = sine * math.sin(phi)
            ox, oy, oz = x * rx, y * ry, z * rz
            oy, oz = _rotate_x(oy, oz, rotation_x)
            ox, oz = _rotate_y(ox, oz, yaw)
            nx, ny, nz = x, y, z
            ny, nz = _rotate_x(ny, nz, rotation_x)
            nx, nz = _rotate_y(nx, nz, yaw)
            length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            _append_vertex(
                vertex_data,
                (cx + ox, cy + oy, cz + oz),
                (nx / length, ny / length, nz / length),
                uv=(segment / float(segments), ring / float(rings)),
                color=color,
            )
    for ring in range(rings):
        for segment in range(segments):
            next_segment = (segment + 1) % segments
            top_left = start + ring * segments + segment
            top_right = start + ring * segments + next_segment
            bottom_left = top_left + segments
            bottom_right = start + (ring + 1) * segments + next_segment
            index_values.extend(
                (
                    top_left,
                    bottom_left,
                    top_right,
                    top_right,
                    bottom_left,
                    bottom_right,
                )
            )


def build_low_poly_sphere_geometry() -> QQuick3DGeometry:
    """Build the shared sphere used by small props and item fallbacks.

    Qt's ``#Sphere`` convenience mesh is useful for smoke tests, but its
    default topology is far too dense for dozens of tiny world objects.  This
    sphere keeps the existing 100-unit primitive scale contract (radius 50),
    uses only 12 segments and 6 rings, and shares smooth vertex normals so it
    reads round without paying for thousands of faces per instance.
    """
    segments = LOW_POLY_SPHERE_SEGMENTS
    rings = LOW_POLY_SPHERE_RINGS
    radius = LOW_POLY_SPHERE_RADIUS
    vertex_data = bytearray()

    def append_vertex(x: float, y: float, z: float, u: float, v: float) -> None:
        length = math.sqrt(x * x + y * y + z * z) or 1.0
        vertex_data.extend(
            struct.pack(
                "<8f",
                x * radius,
                y * radius,
                z * radius,
                x / length,
                y / length,
                z / length,
                u,
                v,
            )
        )

    # One shared pole per cap avoids the degenerate triangles produced by a
    # conventional UV grid while the duplicated longitude seam keeps UVs
    # continuous for a future textured item material.
    append_vertex(0.0, 1.0, 0.0, 0.5, 0.0)
    ring_vertex_count = segments + 1
    for ring in range(1, rings):
        theta = math.pi * ring / float(rings)
        sine = math.sin(theta)
        cosine = math.cos(theta)
        for segment in range(ring_vertex_count):
            phi = math.tau * segment / float(segments)
            append_vertex(
                sine * math.cos(phi),
                cosine,
                sine * math.sin(phi),
                segment / float(segments),
                ring / float(rings),
            )
    bottom_index = len(vertex_data) // VERTEX_STRIDE
    append_vertex(0.0, -1.0, 0.0, 0.5, 1.0)

    index_values: list[int] = []
    first_ring = 1
    for segment in range(segments):
        next_segment = segment + 1
        index_values.extend((
            0,
            first_ring + next_segment,
            first_ring + segment,
        ))
    for ring in range(1, rings - 1):
        current = 1 + (ring - 1) * ring_vertex_count
        next_ring = current + ring_vertex_count
        for segment in range(segments):
            next_segment = segment + 1
            top_left = current + segment
            top_right = current + next_segment
            bottom_left = next_ring + segment
            bottom_right = next_ring + next_segment
            index_values.extend((
                top_left,
                bottom_left,
                top_right,
                top_right,
                bottom_left,
                bottom_right,
            ))
    last_ring = 1 + (rings - 2) * ring_vertex_count
    for segment in range(segments):
        next_segment = segment + 1
        index_values.extend((
            last_ring + segment,
            last_ring + next_segment,
            bottom_index,
        ))

    geometry = QQuick3DGeometry()
    geometry.setObjectName("gameLowPolySphereGeometry")
    geometry.setStride(VERTEX_STRIDE)
    geometry.addAttribute(
        QQuick3DGeometry.Attribute.PositionSemantic,
        0,
        QQuick3DGeometry.Attribute.F32Type,
    )
    geometry.addAttribute(
        QQuick3DGeometry.Attribute.NormalSemantic,
        12,
        QQuick3DGeometry.Attribute.F32Type,
    )
    geometry.addAttribute(
        QQuick3DGeometry.Attribute.TexCoordSemantic,
        24,
        QQuick3DGeometry.Attribute.F32Type,
    )
    geometry.addAttribute(
        QQuick3DGeometry.Attribute.IndexSemantic,
        0,
        QQuick3DGeometry.Attribute.U16Type,
    )
    geometry.setVertexData(bytes(vertex_data))
    geometry.setIndexData(struct.pack("<%dH" % len(index_values), *index_values))
    geometry.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
    geometry.setBounds(
        QVector3D(-radius, -radius, -radius),
        QVector3D(radius, radius, radius),
    )
    return geometry


def _append_face(
    vertex_data: bytearray,
    index_values: list[int],
    positions: tuple[tuple[float, float, float], ...],
    normal: tuple[float, float, float],
    color: tuple[float, float, float, float],
) -> None:
    """Append one flat-shaded triangle or quad to a colored asset mesh."""
    start = len(vertex_data) // ASSET_VERTEX_STRIDE
    for position in positions:
        _append_vertex(
            vertex_data,
            position,
            normal,
            color=color,
        )
    if len(positions) == 3:
        index_values.extend((start, start + 1, start + 2))
    elif len(positions) == 4:
        index_values.extend(
            (start, start + 1, start + 2, start, start + 2, start + 3)
        )


def _append_cylinder_y(
    vertex_data: bytearray,
    index_values: list[int],
    center_y: float,
    height: float,
    bottom_radius: float,
    top_radius: float,
    color: tuple[float, float, float, float],
    *,
    segments: int = 8,
    center_x: float = 0.0,
    center_z: float = 0.0,
) -> None:
    """Append a Gouraud-shaded vertical cylinder/cone with real cap geometry.

    Side vertices share radial normals so trunks and posts read as clay
    tubes instead of octagonal crystals.  Caps stay flat.  Optional
    ``center_x`` / ``center_z`` place stilts and poles off the origin.
    """
    segments = max(6, int(segments))
    cx = float(center_x)
    cz = float(center_z)
    bottom_y = center_y - height * 0.5
    top_y = center_y + height * 0.5
    bottom_start = len(vertex_data) // ASSET_VERTEX_STRIDE
    for segment in range(segments):
        angle = math.tau * segment / float(segments)
        nx = math.cos(angle)
        nz = math.sin(angle)
        _append_vertex(
            vertex_data,
            (cx + bottom_radius * nx, bottom_y, cz + bottom_radius * nz),
            (nx, 0.0, nz),
            color=color,
        )
    top_start = len(vertex_data) // ASSET_VERTEX_STRIDE
    for segment in range(segments):
        angle = math.tau * segment / float(segments)
        nx = math.cos(angle)
        nz = math.sin(angle)
        _append_vertex(
            vertex_data,
            (cx + top_radius * nx, top_y, cz + top_radius * nz),
            (nx, 0.0, nz),
            color=color,
        )
    for segment in range(segments):
        next_segment = (segment + 1) % segments
        index_values.extend(
            (
                bottom_start + segment,
                top_start + segment,
                bottom_start + next_segment,
                bottom_start + next_segment,
                top_start + segment,
                top_start + next_segment,
            )
        )

    for y, radius, normal, reverse in (
        (bottom_y, bottom_radius, (0.0, -1.0, 0.0), True),
        (top_y, top_radius, (0.0, 1.0, 0.0), False),
    ):
        center_index = len(vertex_data) // ASSET_VERTEX_STRIDE
        _append_vertex(vertex_data, (cx, y, cz), normal, color=color)
        ring_start = len(vertex_data) // ASSET_VERTEX_STRIDE
        for segment in range(segments):
            angle = math.tau * segment / float(segments)
            _append_vertex(
                vertex_data,
                (cx + radius * math.cos(angle), y, cz + radius * math.sin(angle)),
                normal,
                color=color,
            )
        for segment in range(segments):
            current = ring_start + segment
            following = ring_start + (segment + 1) % segments
            if reverse:
                index_values.extend((center_index, following, current))
            else:
                index_values.extend((center_index, current, following))


def _append_torus_y(
    vertex_data: bytearray,
    index_values: list[int],
    center_y: float,
    major_radius: float,
    tube_radius: float,
    color: tuple[float, float, float, float],
    *,
    major_segments: int = 10,
    tube_segments: int = 4,
) -> None:
    """Append a compact ring around the Y axis for readable metal/clay trim."""
    major_segments = max(6, int(major_segments))
    tube_segments = max(3, int(tube_segments))
    start = len(vertex_data) // ASSET_VERTEX_STRIDE
    for major in range(major_segments):
        u = math.tau * major / float(major_segments)
        for tube in range(tube_segments):
            v = math.tau * tube / float(tube_segments)
            radial = major_radius + tube_radius * math.cos(v)
            position = (
                radial * math.cos(u),
                center_y + tube_radius * math.sin(v),
                radial * math.sin(u),
            )
            normal = (
                math.cos(v) * math.cos(u),
                math.sin(v),
                math.cos(v) * math.sin(u),
            )
            _append_vertex(vertex_data, position, normal, color=color)
    for major in range(major_segments):
        next_major = (major + 1) % major_segments
        for tube in range(tube_segments):
            next_tube = (tube + 1) % tube_segments
            current = start + major * tube_segments + tube
            right = start + next_major * tube_segments + tube
            upper = start + next_major * tube_segments + next_tube
            left = start + major * tube_segments + next_tube
            index_values.extend((current, right, upper, current, upper, left))


def _append_bipyramid_y(
    vertex_data: bytearray,
    index_values: list[int],
    center_y: float,
    height: float,
    radius: float,
    color: tuple[float, float, float, float],
    highlight: tuple[float, float, float, float] | None = None,
    *,
    center_x: float = 0.0,
    center_z: float = 0.0,
    segments: int = 6,
) -> None:
    """Append a faceted crystal with a deliberately small triangle budget."""
    segments = max(4, int(segments))
    top = (center_x, center_y + height * 0.5, center_z)
    bottom = (center_x, center_y - height * 0.5, center_z)
    highlight = highlight or color
    for segment in range(segments):
        angle = math.tau * segment / float(segments)
        next_angle = math.tau * (segment + 1) / float(segments)
        current = (
            center_x + radius * math.cos(angle),
            center_y,
            center_z + radius * math.sin(angle),
        )
        following = (
            center_x + radius * math.cos(next_angle),
            center_y,
            center_z + radius * math.sin(next_angle),
        )
        mid_angle = (angle + next_angle) * 0.5
        top_normal = (0.42 * math.cos(mid_angle), 0.88, 0.42 * math.sin(mid_angle))
        bottom_normal = (0.42 * math.cos(mid_angle), -0.88, 0.42 * math.sin(mid_angle))
        _append_face(vertex_data, index_values, (top, following, current), top_normal, highlight)
        _append_face(vertex_data, index_values, (bottom, current, following), bottom_normal, color)


def _append_tapered_blade_y(
    vertex_data: bytearray,
    index_values: list[int],
    bottom_y: float,
    shoulder_y: float,
    tip_y: float,
    width: float,
    depth: float,
    color: tuple[float, float, float, float],
    highlight: tuple[float, float, float, float],
) -> None:
    """Append a shallow, pointed blade instead of a rectangular weapon block."""
    base = (
        (-width, bottom_y, -depth),
        (width, bottom_y, -depth),
        (width, bottom_y, depth),
        (-width, bottom_y, depth),
    )
    shoulder = (
        (-width * 0.82, shoulder_y, -depth * 0.78),
        (width * 0.82, shoulder_y, -depth * 0.78),
        (width * 0.82, shoulder_y, depth * 0.78),
        (-width * 0.82, shoulder_y, depth * 0.78),
    )
    _append_face(vertex_data, index_values, (base[0], base[1], base[2], base[3]), (0.0, -1.0, 0.0), color)
    for index in range(4):
        following = (index + 1) % 4
        normal = (
            (base[index][0] + base[following][0]) * 0.5,
            0.18,
            (base[index][2] + base[following][2]) * 0.5,
        )
        length = math.sqrt(sum(component * component for component in normal)) or 1.0
        normal = tuple(component / length for component in normal)
        _append_face(
            vertex_data,
            index_values,
            (base[index], base[following], shoulder[following], shoulder[index]),
            normal,
            color if index != 0 else highlight,
        )
    tip = (0.0, tip_y, 0.0)
    for index in range(4):
        following = (index + 1) % 4
        _append_face(
            vertex_data,
            index_values,
            (shoulder[index], shoulder[following], tip),
            (0.0, 0.86, 0.0),
            highlight if index in (0, 1) else color,
        )


def _append_wedge(
    vertex_data: bytearray,
    index_values: list[int],
    half_x: float,
    bottom_y: float,
    top_y: float,
    half_z: float,
    color: tuple[float, float, float, float],
    highlight: tuple[float, float, float, float],
) -> None:
    """Append a sloped ramp/roof prism with a non-box silhouette."""
    a = (-half_x, bottom_y, -half_z)
    b = (half_x, bottom_y, -half_z)
    c = (half_x, bottom_y, half_z)
    d = (-half_x, bottom_y, half_z)
    e = (-half_x, top_y, half_z)
    f = (half_x, top_y, half_z)
    _append_face(vertex_data, index_values, (a, d, c, b), (0.0, -1.0, 0.0), color)
    _append_face(vertex_data, index_values, (a, b, f, e), (0.0, 0.55, -0.83), highlight)
    _append_face(vertex_data, index_values, (d, e, f, c), (0.0, 0.0, 1.0), color)
    _append_face(vertex_data, index_values, (a, e, d), (-1.0, 0.0, 0.0), color)
    _append_face(vertex_data, index_values, (b, c, f), (1.0, 0.0, 0.0), color)


def _build_colored_geometry(
    object_name: str,
    vertex_data: bytearray,
    index_values: list[int],
) -> QQuick3DGeometry:
    """Finalize one cached native asset geometry with the shared color ABI."""
    if not vertex_data or not index_values:
        raise ValueError("colored asset geometry cannot be empty")
    vertex_count = len(vertex_data) // ASSET_VERTEX_STRIDE
    if vertex_count > 65535:
        raise ValueError("colored asset geometry exceeds U16 index budget")
    positions = [
        struct.unpack_from("<3f", vertex_data, index * ASSET_VERTEX_STRIDE)
        for index in range(vertex_count)
    ]
    minimum = tuple(min(position[axis] for position in positions) for axis in range(3))
    maximum = tuple(max(position[axis] for position in positions) for axis in range(3))
    geometry = QQuick3DGeometry()
    geometry.setObjectName(object_name)
    geometry.setStride(ASSET_VERTEX_STRIDE)
    geometry.addAttribute(
        QQuick3DGeometry.Attribute.PositionSemantic,
        0,
        QQuick3DGeometry.Attribute.F32Type,
    )
    geometry.addAttribute(
        QQuick3DGeometry.Attribute.NormalSemantic,
        12,
        QQuick3DGeometry.Attribute.F32Type,
    )
    geometry.addAttribute(
        QQuick3DGeometry.Attribute.ColorSemantic,
        24,
        QQuick3DGeometry.Attribute.F32Type,
    )
    geometry.addAttribute(
        QQuick3DGeometry.Attribute.IndexSemantic,
        0,
        QQuick3DGeometry.Attribute.U16Type,
    )
    geometry.setVertexData(bytes(vertex_data))
    geometry.setIndexData(struct.pack("<%dH" % len(index_values), *index_values))
    geometry.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
    geometry.setBounds(
        QVector3D(*minimum),
        QVector3D(*maximum),
    )
    return geometry


def _asset_mesh_palette() -> dict[str, tuple[float, float, float, float]]:
    """Return the muted, vertex-colored clay palette used by every asset family."""
    return {
        "wood": (0.42, 0.22, 0.12, 1.0),
        "wood_light": (0.65, 0.38, 0.18, 1.0),
        "metal": (0.32, 0.42, 0.52, 1.0),
        "metal_light": (0.58, 0.68, 0.72, 1.0),
        "leather": (0.36, 0.15, 0.09, 1.0),
        "cloth": (0.10, 0.34, 0.32, 1.0),
        "cloth_light": (0.22, 0.52, 0.45, 1.0),
        "coral": (0.82, 0.34, 0.34, 1.0),
        "gold": (0.86, 0.58, 0.18, 1.0),
        "gold_light": (0.98, 0.80, 0.34, 1.0),
        "green": (0.34, 0.72, 0.28, 1.0),
        "green_dark": (0.18, 0.46, 0.16, 1.0),
        "leaf": (0.46, 0.78, 0.28, 1.0),
        "violet": (0.52, 0.34, 0.76, 1.0),
        "glow": (0.46, 0.78, 0.86, 1.0),
        "bone": (0.72, 0.68, 0.50, 1.0),
        "dark": (0.07, 0.055, 0.075, 1.0),
    }


def _build_saber_geometry() -> QQuick3DGeometry:
    palette = _asset_mesh_palette()
    vertices = bytearray()
    indices: list[int] = []
    _append_tapered_blade_y(
        vertices, indices, -0.08, 0.50, 0.66, 0.085, 0.025,
        palette["metal"], palette["metal_light"],
    )
    _append_box(vertices, indices, (0.0, -0.16, 0.0), (0.16, 0.026, 0.055), color=palette["gold"], vertex_stride=ASSET_VERTEX_STRIDE)
    _append_cylinder_y(vertices, indices, -0.36, 0.38, 0.045, 0.052, palette["leather"], segments=7)
    _append_ellipsoid(vertices, indices, (0.0, -0.57, 0.0), (0.08, 0.07, 0.08), segments=6, rings=2, color=palette["gold"], vertex_stride=ASSET_VERTEX_STRIDE)
    return _build_colored_geometry("gameAssetIronSaber", vertices, indices)


def _build_axe_geometry(asset_id: str) -> QQuick3DGeometry:
    palette = _asset_mesh_palette()
    vertices = bytearray()
    indices: list[int] = []
    legendary = "tidebreaker" in asset_id.lower()
    _append_cylinder_y(vertices, indices, -0.02, 0.88, 0.045, 0.058, palette["wood_light"], segments=7)
    _append_box(vertices, indices, (0.13, 0.27, 0.0), (0.16 if legendary else 0.13, 0.18, 0.035), color=palette["gold"] if legendary else palette["metal"], vertex_stride=ASSET_VERTEX_STRIDE)
    _append_ellipsoid(vertices, indices, (0.0, 0.46, 0.0), (0.09, 0.06, 0.07), segments=6, rings=2, color=palette["metal_light"], vertex_stride=ASSET_VERTEX_STRIDE)
    _append_ellipsoid(vertices, indices, (0.0, -0.47, 0.0), (0.07, 0.055, 0.07), segments=6, rings=2, color=palette["leather"], vertex_stride=ASSET_VERTEX_STRIDE)
    return _build_colored_geometry("gameAssetAxe", vertices, indices)


def _build_bow_geometry() -> QQuick3DGeometry:
    palette = _asset_mesh_palette()
    vertices = bytearray()
    indices: list[int] = []
    _append_box(vertices, indices, (0.0, 0.0, 0.0), (0.035, 0.09, 0.045), color=palette["wood_light"], vertex_stride=ASSET_VERTEX_STRIDE)
    _append_ellipsoid(vertices, indices, (-0.11, 0.31, 0.0), (0.055, 0.27, 0.045), segments=6, rings=2, rotation_x=-0.22, color=palette["wood"], vertex_stride=ASSET_VERTEX_STRIDE)
    _append_ellipsoid(vertices, indices, (0.11, 0.31, 0.0), (0.055, 0.27, 0.045), segments=6, rings=2, rotation_x=0.22, color=palette["wood"], vertex_stride=ASSET_VERTEX_STRIDE)
    _append_box(vertices, indices, (0.0, 0.30, -0.012), (0.012, 0.28, 0.012), color=palette["metal_light"], vertex_stride=ASSET_VERTEX_STRIDE)
    return _build_colored_geometry("gameAssetDriftwoodBow", vertices, indices)


def _build_shield_geometry() -> QQuick3DGeometry:
    palette = _asset_mesh_palette()
    vertices = bytearray()
    indices: list[int] = []
    _append_ellipsoid(vertices, indices, (0.0, 0.0, 0.0), (0.42, 0.46, 0.10), segments=8, rings=3, color=palette["metal"], vertex_stride=ASSET_VERTEX_STRIDE)
    _append_torus_y(vertices, indices, 0.0, 0.31, 0.035, palette["gold"], major_segments=10, tube_segments=4)
    _append_bipyramid_y(vertices, indices, 0.0, 0.24, 0.09, palette["gold"], palette["gold_light"], segments=5)
    return _build_colored_geometry("gameAssetBuckler", vertices, indices)


def _build_wearable_geometry(asset_id: str, item_kind: str) -> QQuick3DGeometry:
    palette = _asset_mesh_palette()
    vertices = bytearray()
    indices: list[int] = []
    lower = asset_id.lower()
    if "cloak" in lower:
        _append_ellipsoid(vertices, indices, (0.0, -0.02, 0.04), (0.40, 0.55, 0.10), segments=8, rings=3, color=palette["cloth"], vertex_stride=ASSET_VERTEX_STRIDE)
        _append_box(vertices, indices, (0.0, 0.40, -0.02), (0.22, 0.045, 0.06), color=palette["gold"], vertex_stride=ASSET_VERTEX_STRIDE)
    elif "boot" in lower or "feet" in item_kind.lower():
        _append_box(vertices, indices, (-0.13, -0.06, -0.05), (0.13, 0.28, 0.17), color=palette["leather"], vertex_stride=ASSET_VERTEX_STRIDE)
        _append_ellipsoid(vertices, indices, (0.0, -0.25, -0.13), (0.20, 0.10, 0.26), segments=6, rings=2, color=palette["leather"], vertex_stride=ASSET_VERTEX_STRIDE)
    elif "glove" in lower or "hands" in item_kind.lower():
        for x in (-0.20, 0.20):
            _append_ellipsoid(vertices, indices, (x, 0.0, 0.0), (0.15, 0.20, 0.12), segments=6, rings=2, color=palette["cloth_light"], vertex_stride=ASSET_VERTEX_STRIDE)
    else:
        _append_ellipsoid(vertices, indices, (0.0, 0.0, 0.0), (0.42, 0.50, 0.27), segments=8, rings=3, color=palette["cloth"], vertex_stride=ASSET_VERTEX_STRIDE)
        _append_ellipsoid(vertices, indices, (-0.33, 0.18, 0.0), (0.14, 0.18, 0.16), segments=6, rings=2, color=palette["cloth_light"], vertex_stride=ASSET_VERTEX_STRIDE)
        _append_ellipsoid(vertices, indices, (0.33, 0.18, 0.0), (0.14, 0.18, 0.16), segments=6, rings=2, color=palette["cloth_light"], vertex_stride=ASSET_VERTEX_STRIDE)
        _append_box(vertices, indices, (0.0, -0.18, -0.27), (0.29, 0.04, 0.025), color=palette["gold"], vertex_stride=ASSET_VERTEX_STRIDE)
    return _build_colored_geometry("gameAssetWearable", vertices, indices)


def _build_compass_geometry() -> QQuick3DGeometry:
    palette = _asset_mesh_palette()
    vertices = bytearray()
    indices: list[int] = []
    _append_torus_y(vertices, indices, 0.0, 0.30, 0.045, palette["gold"], major_segments=10, tube_segments=4)
    _append_ellipsoid(vertices, indices, (0.0, 0.0, 0.0), (0.27, 0.035, 0.27), segments=8, rings=2, color=palette["glow"], vertex_stride=ASSET_VERTEX_STRIDE)
    _append_box(vertices, indices, (0.0, 0.045, 0.0), (0.21, 0.018, 0.025), color=palette["coral"], vertex_stride=ASSET_VERTEX_STRIDE)
    return _build_colored_geometry("gameAssetCompass", vertices, indices)


def _build_plant_geometry(asset_id: str) -> QQuick3DGeometry:
    palette = _asset_mesh_palette()
    vertices = bytearray()
    indices: list[int] = []
    _append_cylinder_y(vertices, indices, -0.02, 0.54, 0.025, 0.018, palette["green"], segments=5)
    for x, z, rotation in ((-0.10, 0.0, -0.45), (0.10, 0.02, 0.45), (0.0, 0.06, 0.0)):
        _append_ellipsoid(vertices, indices, (x, 0.20, z), (0.12, 0.035, 0.06), segments=5, rings=2, rotation_x=rotation, color=palette["green"], vertex_stride=ASSET_VERTEX_STRIDE)
    if "seed" in asset_id.lower():
        _append_bipyramid_y(vertices, indices, 0.0, 0.20, 0.08, palette["coral"], palette["gold"], segments=5)
    return _build_colored_geometry("gameAssetPlant", vertices, indices)


def _build_crystal_geometry(asset_id: str) -> QQuick3DGeometry:
    palette = _asset_mesh_palette()
    lower = asset_id.lower()
    primary = palette["violet"] if any(token in lower for token in ("moon", "void", "amethyst", "umbra")) else palette["glow"]
    if "coral" in lower:
        primary = palette["coral"]
    if "bone" in lower or "fang" in lower:
        primary = palette["bone"]
    vertices = bytearray()
    indices: list[int] = []
    _append_bipyramid_y(vertices, indices, 0.0, 0.64, 0.22, primary, palette["gold_light"], segments=6)
    return _build_colored_geometry("gameAssetCrystal", vertices, indices)


def _build_gem_geometry(asset_id: str) -> QQuick3DGeometry:
    """Build a jewel with a belt and crown instead of a generic shard."""
    palette = _asset_mesh_palette()
    lower = asset_id.lower()
    primary = palette["glow"]
    if "ruby" in lower or "coral" in lower:
        primary = palette["coral"]
    elif "emerald" in lower or "wild" in lower:
        primary = palette["green"]
    elif "amethyst" in lower or "sapphire" in lower or "storm" in lower:
        primary = palette["violet"] if "amethyst" in lower else palette["glow"]
    elif "onyx" in lower or "void" in lower:
        primary = palette["dark"]
    vertices = bytearray()
    indices: list[int] = []
    _append_bipyramid_y(
        vertices, indices, 0.0, 0.48, 0.25, primary,
        palette["gold_light"], segments=6,
    )
    _append_torus_y(
        vertices, indices, -0.02, 0.18, 0.018,
        palette["metal_light"], major_segments=8, tube_segments=3,
    )
    return _build_colored_geometry("gameAssetGem", vertices, indices)


def _build_rune_geometry(asset_id: str) -> QQuick3DGeometry:
    """Build a compact rune tablet with a raised central sigil."""
    palette = _asset_mesh_palette()
    lower = asset_id.lower()
    stone = palette["violet"] if any(
        token in lower for token in ("umbra", "vex", "void")
    ) else palette["bone"]
    vertices = bytearray()
    indices: list[int] = []
    _append_cylinder_y(
        vertices, indices, -0.04, 0.12, 0.22, 0.20, stone, segments=6,
    )
    _append_bipyramid_y(
        vertices, indices, 0.08, 0.22, 0.075,
        palette["gold"], palette["gold_light"], segments=5,
    )
    _append_torus_y(
        vertices, indices, -0.04, 0.16, 0.018,
        palette["metal_light"], major_segments=8, tube_segments=3,
    )
    return _build_colored_geometry("gameAssetRune", vertices, indices)


def _build_key_geometry() -> QQuick3DGeometry:
    """Build a readable key with a ring, shaft and two teeth."""
    palette = _asset_mesh_palette()
    vertices = bytearray()
    indices: list[int] = []
    _append_torus_y(
        vertices, indices, -0.34, 0.13, 0.035,
        palette["gold"], major_segments=9, tube_segments=4,
    )
    _append_cylinder_y(
        vertices, indices, -0.04, 0.48, 0.045, 0.055,
        palette["gold_light"], segments=7,
    )
    _append_box(
        vertices, indices, (0.0, 0.20, 0.0), (0.10, 0.035, 0.055),
        color=palette["gold"], vertex_stride=ASSET_VERTEX_STRIDE,
    )
    for x in (-0.07, 0.07):
        _append_box(
            vertices, indices, (x, 0.30, 0.0), (0.025, 0.08, 0.055),
            color=palette["gold_light"], vertex_stride=ASSET_VERTEX_STRIDE,
        )
    return _build_colored_geometry("gameAssetTidegateKey", vertices, indices)


def _build_consumable_geometry(asset_id: str) -> QQuick3DGeometry:
    palette = _asset_mesh_palette()
    vertices = bytearray()
    indices: list[int] = []
    if "fish" in asset_id.lower() or "ration" in asset_id.lower():
        _append_ellipsoid(vertices, indices, (0.0, 0.0, 0.0), (0.36, 0.16, 0.16), segments=8, rings=3, color=palette["wood_light"], vertex_stride=ASSET_VERTEX_STRIDE)
        _append_ellipsoid(vertices, indices, (0.28, 0.0, 0.0), (0.12, 0.13, 0.15), segments=6, rings=2, color=palette["bone"], vertex_stride=ASSET_VERTEX_STRIDE)
        _append_box(vertices, indices, (0.0, 0.0, -0.17), (0.28, 0.025, 0.025), color=palette["gold"], vertex_stride=ASSET_VERTEX_STRIDE)
    else:
        _append_cylinder_y(vertices, indices, -0.02, 0.48, 0.16, 0.13, palette["coral"], segments=8)
        _append_cylinder_y(vertices, indices, 0.28, 0.10, 0.09, 0.09, palette["gold"], segments=7)
        _append_ellipsoid(vertices, indices, (0.0, -0.27, 0.0), (0.17, 0.05, 0.17), segments=7, rings=2, color=palette["wood"], vertex_stride=ASSET_VERTEX_STRIDE)
    return _build_colored_geometry("gameAssetConsumable", vertices, indices)


def _build_crown_geometry(asset_id: str) -> QQuick3DGeometry:
    palette = _asset_mesh_palette()
    vertices = bytearray()
    indices: list[int] = []
    metal = palette["coral"] if "circlet" in asset_id.lower() else palette["gold"]
    _append_torus_y(vertices, indices, -0.08, 0.28, 0.045, metal, major_segments=9, tube_segments=4)
    for index in range(5):
        angle = math.tau * index / 5.0
        _append_bipyramid_y(
            vertices, indices, 0.12 + (0.045 if index % 2 else 0.0), 0.30, 0.065,
            metal, palette["gold_light"], segments=5,
            center_x=0.22 * math.cos(angle),
            center_z=0.22 * math.sin(angle),
        )
    return _build_colored_geometry("gameAssetCrown", vertices, indices)


def _build_totem_geometry() -> QQuick3DGeometry:
    palette = _asset_mesh_palette()
    vertices = bytearray()
    indices: list[int] = []
    _append_cylinder_y(vertices, indices, -0.05, 0.72, 0.09, 0.12, palette["wood"], segments=7)
    _append_ellipsoid(vertices, indices, (0.0, 0.43, 0.0), (0.23, 0.24, 0.20), segments=7, rings=3, color=palette["coral"], vertex_stride=ASSET_VERTEX_STRIDE)
    for x in (-0.075, 0.075):
        _append_ellipsoid(vertices, indices, (x, 0.48, -0.185), (0.028, 0.035, 0.018), segments=5, rings=2, color=palette["gold_light"], vertex_stride=ASSET_VERTEX_STRIDE)
    _append_torus_y(vertices, indices, -0.37, 0.13, 0.025, palette["gold"], major_segments=8, tube_segments=3)
    return _build_colored_geometry("gameAssetGoblinTotem", vertices, indices)


def _build_lantern_geometry() -> QQuick3DGeometry:
    palette = _asset_mesh_palette()
    vertices = bytearray()
    indices: list[int] = []
    _append_cylinder_y(vertices, indices, -0.92, 1.55, 0.055, 0.07, palette["wood"], segments=12)
    _append_box(
        vertices, indices, (0.0, -0.92, 0.0), (0.16, 0.05, 0.16),
        color=palette["wood_light"], vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_box(
        vertices, indices, (0.0, 0.58, 0.0), (0.16, 0.18, 0.16),
        color=palette["metal"], vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_ellipsoid(
        vertices, indices, (0.0, 0.58, 0.0), (0.12, 0.14, 0.12),
        segments=7, rings=2, color=palette["gold_light"],
        vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_torus_y(
        vertices, indices, 0.74, 0.13, 0.025, palette["metal_light"],
        major_segments=8, tube_segments=3,
    )
    return _build_colored_geometry("gameAssetLantern", vertices, indices)


def _build_chest_geometry() -> QQuick3DGeometry:
    palette = _asset_mesh_palette()
    vertices = bytearray()
    indices: list[int] = []
    _append_box(vertices, indices, (0.0, -0.18, 0.0), (0.44, 0.25, 0.34), color=palette["wood"], vertex_stride=ASSET_VERTEX_STRIDE)
    _append_ellipsoid(vertices, indices, (0.0, 0.14, 0.0), (0.44, 0.22, 0.34), segments=8, rings=2, color=palette["wood_light"], vertex_stride=ASSET_VERTEX_STRIDE)
    for x in (-0.31, 0.31):
        _append_box(vertices, indices, (x, -0.18, -0.35), (0.035, 0.27, 0.025), color=palette["metal"], vertex_stride=ASSET_VERTEX_STRIDE)
    _append_box(vertices, indices, (0.0, -0.16, -0.37), (0.08, 0.10, 0.035), color=palette["gold"], vertex_stride=ASSET_VERTEX_STRIDE)
    _append_ellipsoid(vertices, indices, (0.0, -0.12, -0.41), (0.035, 0.045, 0.018), segments=6, rings=2, color=palette["gold_light"], vertex_stride=ASSET_VERTEX_STRIDE)
    return _build_colored_geometry("gameAssetSupplyChest", vertices, indices)


def build_item_geometry(asset_id: Any, item_kind: Any = "ITEM") -> QQuick3DGeometry:
    """Build one original clay-style item mesh from the stable asset id."""
    wanted = str(asset_id or "item.unknown").strip().lower()
    kind = str(item_kind or "ITEM").strip().upper()
    if kind == "CONTAINER" or any(token in wanted for token in ("crate", "cache", "reliquary", "chest")):
        return _build_chest_geometry()
    if "key" in wanted:
        return _build_key_geometry()
    if any(token in wanted for token in ("saber", "sword")):
        return _build_saber_geometry()
    if "hatchet" in wanted or "axe" in wanted:
        return _build_axe_geometry(wanted)
    if "bow" in wanted:
        return _build_bow_geometry()
    if any(token in wanted for token in ("buckler", "shield")):
        return _build_shield_geometry()
    if any(token in wanted for token in ("crown", "circlet")):
        return _build_crown_geometry(wanted)
    if any(token in wanted for token in ("vest", "jacket", "mail", "cloak", "glove", "boot")) or kind == "ARMOR":
        return _build_wearable_geometry(wanted, kind)
    if "compass" in wanted:
        return _build_compass_geometry()
    if "lantern" in wanted:
        return _build_lantern_geometry()
    if "totem" in wanted:
        return _build_totem_geometry()
    if any(token in wanted for token in ("herb", "seed")):
        return _build_plant_geometry(wanted)
    if any(token in wanted for token in ("ration", "fish", "tonic")):
        return _build_consumable_geometry(wanted)
    if "rune" in wanted or kind == "RUNE":
        return _build_rune_geometry(wanted)
    if "gem" in wanted or kind == "GEM":
        return _build_gem_geometry(wanted)
    if any(token in wanted for token in ("shard", "pearl", "fragment", "relic", "fang", "rune", "gem", "heart")) or kind in {"MATERIAL", "RUNE", "GEM", "TRINKET"}:
        return _build_crystal_geometry(wanted)
    return _build_crystal_geometry(wanted)


def _build_palm_geometry() -> QQuick3DGeometry:
    """Sandover palm: a readable trunk with an umbrella crown, not a leaf wall.

    Local Y is -1 at the ground and +1 at the crown so entity ``sy`` is
    half-height in metres.  Fronds stay near the top and stick outward.
    A tall XZ scale must not turn them into a hedge that hides the village.
    """
    trunk = (0.52, 0.32, 0.12, 1.0)
    trunk_ring = (0.64, 0.40, 0.16, 1.0)
    # Sandover reads lime from the 18 m camera. Dark greens collapse to a
    # black asterisk. Keep the crown at the top and let the blades hang.
    frond_a = (0.46, 0.78, 0.22, 1.0)
    frond_b = (0.62, 0.86, 0.28, 1.0)
    frond_c = (0.34, 0.68, 0.18, 1.0)
    heart = (0.40, 0.72, 0.20, 1.0)
    coconut = (0.58, 0.34, 0.10, 1.0)
    coconut_gold = (0.86, 0.58, 0.16, 1.0)
    vertices = bytearray()
    indices: list[int] = []
    _append_ellipsoid(
        vertices, indices, (0.0, -0.98, 0.0), (0.12, 0.05, 0.12),
        segments=8, rings=3, color=trunk, vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_cylinder_y(
        vertices, indices, -0.92, 0.22, 0.085, 0.062, trunk, segments=12
    )
    _append_cylinder_y(
        vertices, indices, 0.18, 0.62, 0.062, 0.040, trunk, segments=12
    )
    for ring_y, radius in ((-0.62, 0.078), (-0.18, 0.068), (0.22, 0.052)):
        _append_torus_y(
            vertices, indices, ring_y, radius, 0.014, trunk_ring,
            major_segments=10, tube_segments=3,
        )
    _append_ellipsoid(
        vertices, indices, (0.0, 0.68, 0.0), (0.09, 0.10, 0.09),
        segments=8, rings=4, color=heart, vertex_stride=ASSET_VERTEX_STRIDE,
    )
    for index in range(10):
        yaw = math.tau * index / 10.0
        color = (frond_a, frond_b, frond_c)[index % 3]
        _append_ellipsoid(
            vertices, indices,
            (0.22 * math.sin(yaw), 0.58, 0.22 * math.cos(yaw)),
            (0.09, 0.032, 0.48),
            segments=10, rings=4, rotation_x=1.05, yaw=yaw,
            color=color, vertex_stride=ASSET_VERTEX_STRIDE,
        )
    for index in range(6):
        yaw = math.tau * index / 6.0 + 0.28
        _append_ellipsoid(
            vertices, indices,
            (0.12 * math.sin(yaw), 0.72, 0.12 * math.cos(yaw)),
            (0.07, 0.026, 0.28),
            segments=8, rings=3, rotation_x=0.72, yaw=yaw,
            color=frond_b, vertex_stride=ASSET_VERTEX_STRIDE,
        )
    for offset, color in (
        ((-0.07, 0.58, 0.05), coconut),
        ((0.08, 0.57, 0.04), coconut_gold),
        ((0.0, 0.56, -0.08), coconut),
    ):
        _append_ellipsoid(
            vertices, indices, offset, (0.045, 0.05, 0.045),
            segments=6, rings=3, color=color, vertex_stride=ASSET_VERTEX_STRIDE,
        )
    return _build_colored_geometry("gameWorldPalm", vertices, indices)


def _build_stilt_hut_geometry() -> QQuick3DGeometry:
    """Enterable stilt house: deck matches the thatch, posts on the edge.

    Local Y is -1 at the ground and +1 at the ridge.  The door is a hole.
    Walk collision uses the same layout in ``game_engine_assets``.
    """
    palette = _asset_mesh_palette()
    thatch = (0.82, 0.38, 0.16, 1.0)
    thatch_dark = (0.55, 0.24, 0.10, 1.0)
    thatch_tip = (0.90, 0.48, 0.20, 1.0)
    plaster = (0.92, 0.78, 0.55, 1.0)
    mat_col = (0.55, 0.22, 0.16, 1.0)
    wood = palette["wood"]
    wood_light = palette["wood_light"]
    wood_dark = (0.28, 0.14, 0.07, 1.0)
    vertices = bytearray()
    indices: list[int] = []
    deck_hx, deck_hz = 1.005, 0.870
    room_hx, room_hz = 0.625, 0.516
    wall_t = 0.038
    door_half = 0.261
    deck_y = -0.359
    wall_mid, wall_hy = 0.065, 0.413
    posts = (
        (-deck_hx + 0.065, -deck_hz + 0.065),
        (0.0, -deck_hz + 0.065),
        (deck_hx - 0.065, -deck_hz + 0.065),
        (-deck_hx + 0.065, 0.0),
        (deck_hx - 0.065, 0.0),
        (-deck_hx + 0.065, deck_hz - 0.065),
        (0.0, deck_hz - 0.065),
        (deck_hx - 0.065, deck_hz - 0.065),
    )
    for x, z in posts:
        _append_cylinder_y(
            vertices, indices, -0.679, 0.641, 0.054, 0.046, wood,
            segments=10, center_x=x, center_z=z,
        )
        _append_box(
            vertices, indices, (x, -0.337, z), (0.065, 0.022, 0.065),
            color=wood_dark, vertex_stride=ASSET_VERTEX_STRIDE,
        )
    for index in range(9):
        plank_z = -deck_hz + 0.087 + index * (deck_hz * 2.0 - 0.174) / 8.0
        _append_box(
            vertices, indices, (0.0, deck_y, plank_z), (0.984, 0.019, 0.076),
            color=wood_light if index % 2 == 0 else wood,
            vertex_stride=ASSET_VERTEX_STRIDE,
        )
    _append_box(
        vertices, indices, (0.0, wall_mid, room_hz),
        (room_hx + wall_t, wall_hy, wall_t),
        color=plaster, vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_box(
        vertices, indices, (-room_hx, wall_mid, 0.0),
        (wall_t, wall_hy, room_hz),
        color=plaster, vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_box(
        vertices, indices, (room_hx, wall_mid, 0.0),
        (wall_t, wall_hy, room_hz),
        color=plaster, vertex_stride=ASSET_VERTEX_STRIDE,
    )
    wing = (room_hx - door_half) * 0.5
    _append_box(
        vertices, indices, (-door_half - wing, wall_mid, -room_hz),
        (wing + wall_t, wall_hy, wall_t),
        color=plaster, vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_box(
        vertices, indices, (door_half + wing, wall_mid, -room_hz),
        (wing + wall_t, wall_hy, wall_t),
        color=plaster, vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_box(
        vertices, indices, (-door_half, wall_mid, -room_hz),
        (0.022, wall_hy, 0.027),
        color=wood, vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_box(
        vertices, indices, (door_half, wall_mid, -room_hz),
        (0.022, wall_hy, 0.027),
        color=wood, vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_box(
        vertices, indices, (0.0, 0.445, -room_hz),
        (door_half + 0.022, 0.033, 0.027),
        color=wood, vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_box(
        vertices, indices, (0.0, -0.343, -room_hz - 0.043),
        (door_half + 0.033, 0.016, 0.054),
        color=wood_dark, vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_box(
        vertices, indices, (room_hx + 0.011, 0.114, 0.190),
        (0.016, 0.076, 0.087),
        color=palette["glow"], vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_box(
        vertices, indices, (0.082, -0.337, 0.054),
        (0.299, 0.011, 0.217),
        color=mat_col, vertex_stride=ASSET_VERTEX_STRIDE,
    )
    for center_y, height, r0, r1, color, segs in (
        (0.405, 0.147, 1.239, 1.060, thatch_dark, 16),
        (0.568, 0.179, 1.076, 0.734, thatch, 16),
        (0.703, 0.201, 0.750, 0.391, thatch_dark, 14),
        (0.837, 0.179, 0.424, 0.065, thatch, 12),
        (0.957, 0.109, 0.076, 0.027, thatch_tip, 8),
    ):
        _append_cylinder_y(
            vertices, indices, center_y, height, r0, r1, color, segments=segs,
        )
    _append_box(
        vertices, indices, (0.0, -0.130, deck_hz - 0.022),
        (0.924, 0.019, 0.016),
        color=wood, vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_box(
        vertices, indices, (-0.571, -0.130, -deck_hz + 0.022),
        (0.391, 0.019, 0.016),
        color=wood, vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_box(
        vertices, indices, (0.571, -0.130, -deck_hz + 0.022),
        (0.391, 0.019, 0.016),
        color=wood, vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_box(
        vertices, indices, (-deck_hx + 0.022, -0.130, 0.082),
        (0.016, 0.019, 0.680),
        color=wood, vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_box(
        vertices, indices, (deck_hx - 0.022, -0.130, 0.082),
        (0.016, 0.019, 0.680),
        color=wood, vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_cylinder_y(
        vertices, indices, -0.641, 0.533, 0.014, 0.014, wood,
        segments=6, center_x=-0.087, center_z=-0.967,
    )
    _append_cylinder_y(
        vertices, indices, -0.641, 0.533, 0.014, 0.014, wood,
        segments=6, center_x=0.087, center_z=-0.967,
    )
    for step_y in (-0.902, -0.772, -0.641, -0.511, -0.391):
        _append_box(
            vertices, indices, (0.0, step_y, -0.967), (0.098, 0.011, 0.014),
            color=wood_light, vertex_stride=ASSET_VERTEX_STRIDE,
        )
    return _build_colored_geometry("gameWorldStiltHut", vertices, indices)


def _build_dock_geometry() -> QQuick3DGeometry:
    """Sandover pier: plank deck, fat pilings, open-water bollard.

    Local Y is -1 at the waterline and +1 at the bollard tip so entity
    ``sy`` is half-height.  Length lives in Z on purpose; do not stretch
    a cube into a pier.
    """
    palette = _asset_mesh_palette()
    wood = palette["wood"]
    wood_light = palette["wood_light"]
    wood_dark = (0.28, 0.14, 0.07, 1.0)
    vertices = bytearray()
    indices: list[int] = []
    for index in range(9):
        plank_z = -3.03 + index * 0.74
        color = wood_light if index % 2 == 0 else wood
        _append_box(
            vertices, indices, (0.0, -0.38, plank_z), (1.07, 0.067, 0.33),
            color=color, vertex_stride=ASSET_VERTEX_STRIDE,
        )
    for pile_z in (-2.81, -0.88, 1.04, 2.82):
        for pile_x in (-0.86, 0.86):
            _append_cylinder_y(
                vertices, indices, -0.63, 0.74, 0.09, 0.08, wood_dark,
                segments=8, center_x=pile_x, center_z=pile_z,
            )
    for beam_z in (-1.84, 0.23, 2.01):
        _append_box(
            vertices, indices, (0.0, -0.56, beam_z), (0.92, 0.074, 0.10),
            color=wood, vertex_stride=ASSET_VERTEX_STRIDE,
        )
    for rail_x in (-1.04, 1.04):
        _append_box(
            vertices, indices, (rail_x, 0.07, -0.88), (0.05, 0.06, 2.00),
            color=wood, vertex_stride=ASSET_VERTEX_STRIDE,
        )
        for post_z in (-2.59, -0.88, 0.82):
            _append_cylinder_y(
                vertices, indices, 0.07, 0.89, 0.04, 0.04, wood,
                segments=6, center_x=rail_x, center_z=post_z,
            )
    _append_cylinder_y(
        vertices, indices, 0.0, 2.0, 0.11, 0.09, wood,
        segments=10, center_z=3.12,
    )
    _append_cylinder_y(
        vertices, indices, 0.44, 0.10, 0.16, 0.16, palette["gold"],
        segments=10, center_x=-0.05, center_z=3.12,
    )
    _append_box(
        vertices, indices, (0.42, -0.08, -2.36), (0.27, 0.24, 0.33),
        color=wood_dark, vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_box(
        vertices, indices, (0.42, 0.18, -2.36), (0.30, 0.04, 0.36),
        color=wood_light, vertex_stride=ASSET_VERTEX_STRIDE,
    )
    return _build_colored_geometry("gameWorldDock", vertices, indices)


def _build_village_totem_geometry() -> QQuick3DGeometry:
    """Original stacked-face shrine pole, not a copy of another game's idol."""
    palette = _asset_mesh_palette()
    vertices = bytearray()
    indices: list[int] = []
    _append_cylinder_y(
        vertices, indices, -0.55, 0.55, 0.10, 0.12, palette["wood"], segments=8
    )
    _append_ellipsoid(
        vertices, indices, (0.0, -0.05, 0.0), (0.22, 0.20, 0.20),
        segments=10, rings=5, color=palette["coral"],
        vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_ellipsoid(
        vertices, indices, (0.0, 0.32, 0.0), (0.18, 0.18, 0.18),
        segments=10, rings=5, color=palette["gold"],
        vertex_stride=ASSET_VERTEX_STRIDE,
    )
    _append_ellipsoid(
        vertices, indices, (0.0, 0.58, 0.0), (0.12, 0.14, 0.12),
        segments=8, rings=4, color=palette["leaf"],
        vertex_stride=ASSET_VERTEX_STRIDE,
    )
    for x in (-0.08, 0.08):
        _append_ellipsoid(
            vertices, indices, (x, 0.0, -0.18), (0.03, 0.035, 0.02),
            segments=6, rings=3, color=palette["gold_light"],
            vertex_stride=ASSET_VERTEX_STRIDE,
        )
    return _build_colored_geometry("gameWorldTotem", vertices, indices)


_GLB_JSON_CHUNK = 0x4E4F534A
_GLB_BIN_CHUNK = 0x004E4942
_GLTF_FLOAT = 5126
_GLTF_UNSIGNED_SHORT = 5123
_GLTF_UNSIGNED_INT = 5125
_GLTF_VEC3 = "VEC3"
_GLTF_SCALAR = "SCALAR"
_GLTF_TYPE_SIZE = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT4": 16,
}
_GLTF_COMPONENT_SIZE = {
    5120: 1,
    5121: 1,
    5122: 2,
    5123: 2,
    5125: 4,
    5126: 4,
}


def _mat4_identity() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _mat4_mul(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [
        [
            sum(left[row][k] * right[k][col] for k in range(4))
            for col in range(4)
        ]
        for row in range(4)
    ]


def _mat4_from_node(node: dict[str, Any]) -> list[list[float]]:
    matrix = node.get("matrix")
    if isinstance(matrix, list) and len(matrix) == 16:
        try:
            values = [float(value) for value in matrix]
        except (TypeError, ValueError):
            values = []
        if len(values) == 16:
            return [
                [values[0], values[4], values[8], values[12]],
                [values[1], values[5], values[9], values[13]],
                [values[2], values[6], values[10], values[14]],
                [values[3], values[7], values[11], values[15]],
            ]
    result = _mat4_identity()
    translation = node.get("translation")
    if isinstance(translation, list) and len(translation) >= 3:
        try:
            tx, ty, tz = (float(translation[0]), float(translation[1]), float(translation[2]))
        except (TypeError, ValueError):
            tx, ty, tz = (0.0, 0.0, 0.0)
        moved = _mat4_identity()
        moved[0][3] = tx
        moved[1][3] = ty
        moved[2][3] = tz
        result = _mat4_mul(result, moved)
    rotation = node.get("rotation")
    if isinstance(rotation, list) and len(rotation) >= 4:
        try:
            qx, qy, qz, qw = (
                float(rotation[0]),
                float(rotation[1]),
                float(rotation[2]),
                float(rotation[3]),
            )
        except (TypeError, ValueError):
            qx, qy, qz, qw = (0.0, 0.0, 0.0, 1.0)
        xx, yy, zz = qx * qx, qy * qy, qz * qz
        xy, xz, yz = qx * qy, qx * qz, qy * qz
        wx, wy, wz = qw * qx, qw * qy, qw * qz
        rotated = [
            [1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy), 0.0],
            [2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx), 0.0],
            [2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy), 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
        result = _mat4_mul(result, rotated)
    scale = node.get("scale")
    if isinstance(scale, list) and len(scale) >= 3:
        try:
            sx, sy, sz = (float(scale[0]), float(scale[1]), float(scale[2]))
        except (TypeError, ValueError):
            sx, sy, sz = (1.0, 1.0, 1.0)
        scaled = _mat4_identity()
        scaled[0][0] = sx
        scaled[1][1] = sy
        scaled[2][2] = sz
        result = _mat4_mul(result, scaled)
    return result


def _mat4_transform_point(
    matrix: list[list[float]],
    x: float,
    y: float,
    z: float,
) -> tuple[float, float, float]:
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z + matrix[0][3],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z + matrix[1][3],
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z + matrix[2][3],
    )


def _mat4_transform_dir(
    matrix: list[list[float]],
    x: float,
    y: float,
    z: float,
) -> tuple[float, float, float]:
    dx = matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z
    dy = matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z
    dz = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length <= 1e-8:
        return (0.0, 1.0, 0.0)
    return (dx / length, dy / length, dz / length)


def _glb_chunks(source: bytes) -> tuple[dict[str, Any], bytes] | None:
    if len(source) < 20:
        return None
    try:
        magic, version, declared = struct.unpack_from("<4sII", source, 0)
    except struct.error:
        return None
    if magic != b"glTF" or version != 2 or declared > len(source):
        return None
    offset = 12
    document: dict[str, Any] | None = None
    blob = b""
    while offset + 8 <= declared:
        try:
            chunk_length, chunk_type = struct.unpack_from("<II", source, offset)
        except struct.error:
            return None
        offset += 8
        end = offset + chunk_length
        if end > declared or end > len(source):
            return None
        payload = source[offset:end]
        offset = end
        if chunk_type == _GLB_JSON_CHUNK:
            try:
                parsed = json.loads(payload.rstrip(b" \t\r\n\x00").decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None
            if isinstance(parsed, dict):
                document = parsed
        elif chunk_type == _GLB_BIN_CHUNK:
            blob = payload
    if document is None:
        return None
    return document, blob


def _gltf_accessor_bytes(
    document: dict[str, Any],
    blob: bytes,
    index: Any,
) -> tuple[bytes, int, int, int] | None:
    accessors = document.get("accessors")
    views = document.get("bufferViews")
    if not isinstance(accessors, list) or not isinstance(views, list):
        return None
    try:
        accessor = accessors[int(index)]
        view = views[int(accessor.get("bufferView", -1))]
    except (TypeError, ValueError, IndexError, AttributeError):
        return None
    if not isinstance(accessor, dict) or not isinstance(view, dict):
        return None
    try:
        count = int(accessor.get("count", 0))
        component_type = int(accessor.get("componentType", 0))
        view_offset = int(view.get("byteOffset", 0))
        accessor_offset = int(accessor.get("byteOffset", 0))
        view_length = int(view.get("byteLength", 0))
    except (TypeError, ValueError):
        return None
    type_name = str(accessor.get("type", _GLTF_SCALAR))
    components = _GLTF_TYPE_SIZE.get(type_name, 0)
    component_size = _GLTF_COMPONENT_SIZE.get(component_type, 0)
    if count <= 0 or components <= 0 or component_size <= 0:
        return None
    stride = int(view.get("byteStride") or 0) or (components * component_size)
    start = view_offset + accessor_offset
    needed = start + stride * (count - 1) + components * component_size
    if start < 0 or needed > len(blob) or needed - view_offset > view_length + accessor_offset:
        if start < 0 or start + count * components * component_size > len(blob):
            return None
        stride = components * component_size
        needed = start + count * stride
        if needed > len(blob):
            return None
    return blob[start:needed], count, stride, component_type


def _gltf_positions(
    document: dict[str, Any],
    blob: bytes,
    index: Any,
) -> list[tuple[float, float, float]] | None:
    unpacked = _gltf_accessor_bytes(document, blob, index)
    if unpacked is None:
        return None
    payload, count, stride, component_type = unpacked
    if component_type != _GLTF_FLOAT:
        return None
    positions: list[tuple[float, float, float]] = []
    for row in range(count):
        offset = row * stride
        try:
            x, y, z = struct.unpack_from("<3f", payload, offset)
        except struct.error:
            return None
        positions.append((float(x), float(y), float(z)))
    return positions


def _gltf_indices(
    document: dict[str, Any],
    blob: bytes,
    index: Any,
) -> list[int] | None:
    unpacked = _gltf_accessor_bytes(document, blob, index)
    if unpacked is None:
        return None
    payload, count, stride, component_type = unpacked
    indices: list[int] = []
    for row in range(count):
        offset = row * stride
        try:
            if component_type == _GLTF_UNSIGNED_SHORT:
                value = struct.unpack_from("<H", payload, offset)[0]
            elif component_type == _GLTF_UNSIGNED_INT:
                value = struct.unpack_from("<I", payload, offset)[0]
            else:
                return None
        except struct.error:
            return None
        indices.append(int(value))
    return indices


def _gltf_material_color(
    document: dict[str, Any],
    index: Any,
) -> tuple[float, float, float, float]:
    materials = document.get("materials")
    default = (0.46, 0.28, 0.12, 1.0)
    if not isinstance(materials, list):
        return default
    try:
        material = materials[int(index)]
    except (TypeError, ValueError, IndexError):
        return default
    if not isinstance(material, dict):
        return default
    pbr = material.get("pbrMetallicRoughness")
    factor = pbr.get("baseColorFactor") if isinstance(pbr, dict) else None
    if not isinstance(factor, list) or len(factor) < 3:
        return default
    try:
        red, green, blue = float(factor[0]), float(factor[1]), float(factor[2])
        alpha = float(factor[3]) if len(factor) > 3 else 1.0
    except (TypeError, ValueError):
        return default
    return (
        max(0.0, min(1.0, red)),
        max(0.0, min(1.0, green)),
        max(0.0, min(1.0, blue)),
        max(0.0, min(1.0, alpha)),
    )


def _geometry_from_authored_world_glb(kind: str) -> QQuick3DGeometry | None:
    """Import one Blender world GLB into the shared native mesh cache.

    Play instantiates this mesh many times.  Decoding the file per tree
    through RuntimeLoader is what made the village hitch; the GLB stays the
    authored source, the runtime keeps one QQuick3DGeometry.
    """
    try:
        from backend.game_engine_assets import AUTHORED_WORLD_SOURCES
    except Exception:
        return None
    spec = AUTHORED_WORLD_SOURCES.get(str(kind or "").strip().upper())
    if not isinstance(spec, dict):
        return None
    source = spec.get("source")
    path = source if isinstance(source, Path) else Path(str(source or ""))
    if not path.is_file():
        return None
    try:
        parsed = _glb_chunks(path.read_bytes())
    except OSError:
        return None
    if parsed is None:
        return None
    document, blob = parsed
    nodes = document.get("nodes")
    meshes = document.get("meshes")
    if not isinstance(nodes, list) or not isinstance(meshes, list):
        return None
    scenes = document.get("scenes")
    scene_index = document.get("scene", 0)
    try:
        scene = scenes[int(scene_index)] if isinstance(scenes, list) else None
    except (TypeError, ValueError, IndexError):
        scene = None
    roots = scene.get("nodes") if isinstance(scene, dict) else None
    if not isinstance(roots, list) or not roots:
        roots = list(range(len(nodes)))

    transformed: list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float, float]]] = []
    triangles: list[tuple[int, int, int]] = []

    def emit_mesh(mesh_index: int, matrix: list[list[float]]) -> None:
        try:
            mesh = meshes[int(mesh_index)]
        except (TypeError, ValueError, IndexError):
            return
        if not isinstance(mesh, dict):
            return
        primitives = mesh.get("primitives")
        if not isinstance(primitives, list):
            return
        for primitive in primitives:
            if not isinstance(primitive, dict):
                continue
            attributes = primitive.get("attributes")
            if not isinstance(attributes, dict):
                continue
            positions = _gltf_positions(document, blob, attributes.get("POSITION"))
            if not positions:
                continue
            normals = _gltf_positions(document, blob, attributes.get("NORMAL"))
            indices = _gltf_indices(document, blob, primitive.get("indices"))
            if not indices:
                continue
            color = _gltf_material_color(document, primitive.get("material"))
            base = len(transformed)
            for vertex_index, position in enumerate(positions):
                world = _mat4_transform_point(matrix, *position)
                if normals and vertex_index < len(normals):
                    normal = _mat4_transform_dir(matrix, *normals[vertex_index])
                else:
                    normal = (0.0, 1.0, 0.0)
                transformed.append((world, normal, color))
            for cursor in range(0, len(indices) - 2, 3):
                triangles.append(
                    (
                        base + indices[cursor],
                        base + indices[cursor + 1],
                        base + indices[cursor + 2],
                    )
                )

    def walk(node_index: Any, parent: list[list[float]]) -> None:
        try:
            node = nodes[int(node_index)]
        except (TypeError, ValueError, IndexError):
            return
        if not isinstance(node, dict):
            return
        world = _mat4_mul(parent, _mat4_from_node(node))
        if "mesh" in node:
            emit_mesh(node.get("mesh"), world)
        children = node.get("children")
        if isinstance(children, list):
            for child in children:
                walk(child, world)

    for root_index in roots:
        walk(root_index, _mat4_identity())
    if not transformed or not triangles:
        return None
    if len(transformed) > 65535:
        return None

    min_x = min(point[0][0] for point in transformed)
    min_y = min(point[0][1] for point in transformed)
    min_z = min(point[0][2] for point in transformed)
    max_x = max(point[0][0] for point in transformed)
    max_y = max(point[0][1] for point in transformed)
    max_z = max(point[0][2] for point in transformed)
    height = max(max_y - min_y, 1e-4)
    scale = 2.0 / height
    mid_x = (min_x + max_x) * 0.5
    mid_z = (min_z + max_z) * 0.5
    vertices = bytearray()
    for position, normal, color in transformed:
        packed = struct.pack(
            "<10f",
            (position[0] - mid_x) * scale,
            (position[1] - min_y) * scale - 1.0,
            (position[2] - mid_z) * scale,
            normal[0],
            normal[1],
            normal[2],
            color[0],
            color[1],
            color[2],
            color[3],
        )
        vertices.extend(packed)
    indices = [index for triangle in triangles for index in triangle]
    if not vertices or not indices:
        return None
    return _build_colored_geometry("gameAuthoredWorld_%s" % kind.lower(), vertices, indices)


def _build_world_prop_geometry(kind: Any, variant: int = 0) -> QQuick3DGeometry:
    """Build a shared world-prop family with four deterministic visual variants."""
    palette = _asset_mesh_palette()
    wanted = str(kind or "PROP").strip().upper()
    variant = int(variant) % 4
    vertices = bytearray()
    indices: list[int] = []
    if "RAMP" in wanted:
        _append_wedge(vertices, indices, 0.5, -1.0, 0.0, 0.5, palette["wood_light"], palette["metal_light"])
        return _build_colored_geometry("gameWorldRamp", vertices, indices)
    if "PALM" in wanted or "TREE" in wanted:
        baked = _geometry_from_authored_world_glb("PALM")
        if baked is not None:
            return baked
        return _build_palm_geometry()
    if "DOCK" in wanted or "PIER" in wanted:
        return _build_dock_geometry()
    if "TOTEM" in wanted or "SHRINE" in wanted:
        return _build_village_totem_geometry()
    if any(token in wanted for token in ("HOUSE", "BUILDING", "STRUCTURE", "HUT", "TIDEHOUSE")):
        return _build_stilt_hut_geometry()
    if "LIGHT" in wanted or "LANTERN" in wanted:
        return _build_lantern_geometry()
    if "SPAWN" in wanted:
        _append_torus_y(vertices, indices, -0.18, 0.34, 0.055, palette["violet"], major_segments=10, tube_segments=4)
        _append_cylinder_y(vertices, indices, -0.48, 0.70, 0.07, 0.10, palette["metal"], segments=7)
        return _build_colored_geometry("gameWorldSpawnMarker", vertices, indices)
    if "STRESS" in wanted:
        _append_ellipsoid(vertices, indices, (0.0, -0.48, 0.0), (0.42, 0.52, 0.36), segments=6, rings=3, color=palette["bone"], vertex_stride=ASSET_VERTEX_STRIDE)
        return _build_colored_geometry("gameWorldStressPebble", vertices, indices)
    if variant == 0:
        _append_ellipsoid(vertices, indices, (0.0, -0.48, 0.0), (0.48, 0.52, 0.40), segments=7, rings=3, color=palette["bone"], vertex_stride=ASSET_VERTEX_STRIDE)
        _append_ellipsoid(vertices, indices, (0.18, -0.35, -0.16), (0.25, 0.30, 0.22), segments=6, rings=2, color=palette["metal_light"], vertex_stride=ASSET_VERTEX_STRIDE)
        _append_ellipsoid(vertices, indices, (-0.22, -0.62, 0.12), (0.22, 0.18, 0.20), segments=6, rings=2, color=palette["wood_light"], vertex_stride=ASSET_VERTEX_STRIDE)
    elif variant == 1:
        # Readable mangrove: trunk, knee-roots and a stacked canopy so the
        # silhouette still works at the default 18 m third-person camera.
        # Canopy tessellation is higher because these instances are metres
        # tall; a 7-segment ellipsoid at 4 m reads as a crystal, not clay.
        _append_cylinder_y(vertices, indices, -0.92, 1.35, 0.11, 0.16, palette["wood"], segments=12)
        for x, z in ((-0.22, 0.18), (0.24, 0.12), (-0.08, -0.24)):
            _append_box(
                vertices, indices, (x, -0.78, z), (0.05, 0.22, 0.05),
                color=palette["wood_light"], vertex_stride=ASSET_VERTEX_STRIDE,
            )
        _append_ellipsoid(
            vertices, indices, (0.0, 0.42, 0.0), (0.62, 0.38, 0.58),
            segments=14, rings=7, color=palette["leaf"],
            vertex_stride=ASSET_VERTEX_STRIDE,
        )
        _append_ellipsoid(
            vertices, indices, (-0.28, 0.18, 0.12), (0.38, 0.28, 0.34),
            segments=12, rings=6, color=palette["green"],
            vertex_stride=ASSET_VERTEX_STRIDE,
        )
        _append_ellipsoid(
            vertices, indices, (0.30, 0.22, -0.10), (0.42, 0.30, 0.36),
            segments=12, rings=6, color=palette["green_dark"],
            vertex_stride=ASSET_VERTEX_STRIDE,
        )
        _append_ellipsoid(
            vertices, indices, (0.04, 0.68, 0.08), (0.28, 0.22, 0.26),
            segments=10, rings=5, color=palette["leaf"],
            vertex_stride=ASSET_VERTEX_STRIDE,
        )
    elif variant == 2:
        _append_cylinder_y(vertices, indices, -0.86, 0.18, 0.36, 0.31, palette["metal"], segments=7)
        _append_cylinder_y(vertices, indices, -0.42, 0.72, 0.22, 0.15, palette["metal_light"], segments=6)
        _append_torus_y(vertices, indices, -0.76, 0.27, 0.03, palette["gold"], major_segments=8, tube_segments=3)
        _append_bipyramid_y(vertices, indices, 0.08, 0.40, 0.16, palette["coral"], palette["gold_light"], segments=5)
    else:
        _append_cylinder_y(vertices, indices, -0.58, 0.78, 0.28, 0.24, palette["wood_light"], segments=8)
        _append_torus_y(vertices, indices, -0.56, 0.27, 0.025, palette["metal"], major_segments=8, tube_segments=3)
        _append_torus_y(vertices, indices, -0.30, 0.27, 0.025, palette["metal"], major_segments=8, tube_segments=3)
    return _build_colored_geometry("gameWorldProp_%d" % variant, vertices, indices)


class AssetGeometryCache(QObject):
    """Keep one native mesh per bounded item/prop family, never per frame."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._items: dict[tuple[str, str], QQuick3DGeometry] = {}
        self._props: dict[tuple[str, int], QQuick3DGeometry] = {}

    @staticmethod
    def _safe_key(value: Any, fallback: str) -> str:
        wanted = str(value or fallback).strip().lower()
        return wanted[:96] or fallback

    def geometry_for_item(self, asset_id: Any, item_kind: Any = "ITEM") -> QQuick3DGeometry:
        key = (self._safe_key(asset_id, "item.unknown"), self._safe_key(item_kind, "ITEM"))
        geometry = self._items.get(key)
        if geometry is None:
            if len(self._items) >= MAX_ASSET_GEOMETRIES:
                # Unknown content shares a deterministic generic mesh once the
                # bounded native family cache is full.
                key = ("item.unknown", "ITEM")
                geometry = self._items.get(key)
            if geometry is None:
                geometry = build_item_geometry(*key)
                self._items[key] = geometry
        return geometry

    def geometry_for_world_prop(self, kind: Any = "PROP", variant: Any = 0) -> QQuick3DGeometry:
        safe_kind = self._safe_key(kind, "PROP").upper()
        # World asset bindings carry a semantic geometry key.  Keep the
        # numeric variant as a compatibility input for older snapshots, but
        # let the declared family win whenever it is present.
        family_variants = {
            "WORLD.PROP.ROCK": 0,
            "WORLD.PROP.MANGROVE": 1,
            "WORLD.PROP.SHRINE": 2,
            "WORLD.PROP.BARREL": 3,
        }
        if safe_kind in family_variants:
            safe_kind = "PROP"
            safe_variant = family_variants[str(kind or "").strip().upper()]
        else:
            safe_variant = 0
        try:
            if safe_kind != "PROP" or str(kind or "").strip().upper() not in family_variants:
                safe_variant = int(variant) % 4
        except (TypeError, ValueError):
            digits = "".join(character for character in str(variant) if character.isdigit())
            try:
                safe_variant = int(digits or "0") % 4
            except ValueError:
                safe_variant = 0
        # Ramps and named structures have one shape; ordinary props are four
        # shared silhouettes selected by a stable entity variant.
        if any(
            token in safe_kind
            for token in (
                "RAMP",
                "HOUSE",
                "BUILDING",
                "STRUCTURE",
                "HUT",
                "PALM",
                "TREE",
                "DOCK",
                "TOTEM",
                "LIGHT",
                "LANTERN",
                "SPAWN",
                "STRESS",
            )
        ):
            safe_variant = 0
        key = (safe_kind, safe_variant)
        geometry = self._props.get(key)
        if geometry is None:
            if len(self._props) >= MAX_ASSET_GEOMETRIES:
                key = ("PROP", safe_variant)
                geometry = self._props.get(key)
            if geometry is None:
                geometry = _build_world_prop_geometry(*key)
                self._props[key] = geometry
        return geometry


def build_character_geometry(
    motion_state: Any = "IDLE",
    phase: Any = 0.0,
    variant: Any = "CROWD",
) -> QQuick3DGeometry:
    """Build the original GG clay-style crowd mesh in gameplay units.

    This is deliberately a single indexed geometry object, not a collection
    of QML Models.  The silhouette is assembled from a small number of
    faceted ellipsoids and boxes, while RGBA vertex colors separate skin,
    cloth, hair, boots and accent pieces without a texture lookup.  The
    resulting mesh is an actual 3D asset generated by the engine and can be
    replaced by an authored/retargeted asset later without changing the
    simulation contract.
    """
    pose_state, pose_bucket = character_pose_key(motion_state, phase)
    pose_phase = pose_bucket / float(CHARACTER_POSE_BUCKETS) * math.tau
    stride = math.sin(pose_phase) if pose_state in {"WALK", "SPRINT"} else 0.0
    swing = (
        0.38 if pose_state == "SPRINT" else 0.28
    ) * stride
    if pose_state == "AIR":
        # A small readable airborne spread; root pitch still comes from the
        # deterministic animation contract.
        swing = 0.22
    if pose_state == "IDLE":
        swing = 0.0

    # Jak/Sly/Fable clay: saturated local colors that still read when a
    # warm key light and a cool sky fill hit the same mesh.  Near-black
    # hair/boots crush to silhouettes under filmic tonemapping.
    cast = character_variant_key(variant)
    skin = (0.94, 0.62, 0.38, 1.0)
    skin_light = (0.99, 0.80, 0.54, 1.0)
    cloth = (0.16, 0.58, 0.52, 1.0)
    cloth_light = (0.32, 0.74, 0.58, 1.0)
    accent = (0.96, 0.50, 0.16, 1.0)
    belt = (0.52, 0.26, 0.12, 1.0)
    hair = (0.28, 0.14, 0.08, 1.0)
    boots = (0.36, 0.20, 0.12, 1.0)
    eyes = (0.10, 0.07, 0.05, 1.0)
    if cast == "WANDERER":
        cloth = (0.78, 0.52, 0.22, 1.0)
        cloth_light = (0.92, 0.70, 0.32, 1.0)
        accent = (0.22, 0.46, 0.58, 1.0)
        hair = (0.18, 0.10, 0.06, 1.0)
    elif cast == "GUARDIAN":
        cloth = (0.28, 0.36, 0.46, 1.0)
        cloth_light = (0.48, 0.56, 0.64, 1.0)
        accent = (0.82, 0.62, 0.22, 1.0)
        belt = (0.42, 0.40, 0.38, 1.0)
        boots = (0.22, 0.22, 0.24, 1.0)
        hair = (0.16, 0.16, 0.18, 1.0)
    elif cast == "CRITTER":
        cloth = (0.42, 0.58, 0.32, 1.0)
        cloth_light = (0.58, 0.72, 0.40, 1.0)
        accent = (0.86, 0.46, 0.28, 1.0)
        skin = (0.82, 0.52, 0.30, 1.0)
        skin_light = (0.92, 0.68, 0.42, 1.0)
        hair = (0.40, 0.22, 0.10, 1.0)

    vertex_data = bytearray()
    index_values: list[int] = []

    def ellipsoid(
        center: tuple[float, float, float],
        radius: tuple[float, float, float],
        color: tuple[float, float, float, float],
        *,
        segments: int = 8,
        rings: int = 3,
        rotation_x: float = 0.0,
    ) -> None:
        _append_ellipsoid(
            vertex_data,
            index_values,
            center,
            radius,
            segments=segments,
            rings=rings,
            rotation_x=rotation_x,
            color=color,
            vertex_stride=CHARACTER_VERTEX_STRIDE,
        )

    def box(
        center: tuple[float, float, float],
        half_size: tuple[float, float, float],
        color: tuple[float, float, float, float],
        *,
        rotation_x: float = 0.0,
    ) -> None:
        _append_box(
            vertex_data,
            index_values,
            center,
            half_size,
            rotation_x=rotation_x,
            color=color,
            vertex_stride=CHARACTER_VERTEX_STRIDE,
        )

    # Rounded torso and pelvis establish the exaggerated readable silhouette.
    # The overlap is intentional: it avoids a visible seam while the color
    # change reads as a short jacket over trousers.
    ellipsoid((0.0, 0.03, 0.0), (0.36, 0.38, 0.25), cloth, segments=12, rings=6)
    ellipsoid((0.0, -0.29, 0.0), (0.29, 0.16, 0.22), boots, segments=10, rings=4)
    box((0.0, -0.245, -0.225), (0.27, 0.052, 0.025), belt)
    box((0.0, 0.03, -0.252), (0.18, 0.16, 0.018), cloth_light)
    ellipsoid((0.0, 0.04, -0.274), (0.055, 0.065, 0.025), accent, segments=8, rings=3)

    # Neck, shoulders and hands make the pose legible even at the distant
    # crowd LOD.  The small shoulder pieces add character without requiring a
    # second clothing model or a normal map.
    ellipsoid((0.0, 0.39, 0.0), (0.115, 0.12, 0.12), skin, segments=8, rings=4)
    for x in (-0.32, 0.32):
        ellipsoid((x, 0.22, 0.0), (0.14, 0.11, 0.16), accent, segments=8, rings=4)

    for x in (-0.42, 0.42):
        arm_swing = -swing if x < 0.0 else swing
        ellipsoid(
            (x, 0.02, 0.0),
            (0.115, 0.255, 0.115),
            cloth_light,
            segments=8,
            rings=5,
            rotation_x=arm_swing,
        )
        ellipsoid(
            (x * 1.08, -0.205, -0.01),
            (0.105, 0.105, 0.105),
            skin_light,
            segments=8,
            rings=4,
            rotation_x=arm_swing,
        )

    for x in (-0.14, 0.14):
        leg_swing = swing if x < 0.0 else -swing
        ellipsoid(
            (x, -0.50, 0.0),
            (0.13, 0.235, 0.14),
            cloth,
            segments=8,
            rings=5,
            rotation_x=leg_swing,
        )
        ellipsoid(
            (x, -0.76, -0.06),
            (0.15, 0.095, 0.225),
            boots,
            segments=8,
            rings=4,
            rotation_x=leg_swing,
        )

    # Smooth Gouraud head: RenderWare-era clay, not a faceted icosahedron.
    ellipsoid((0.0, 0.59, 0.0), (0.235, 0.25, 0.225), skin_light, segments=12, rings=6)
    ellipsoid((0.0, 0.73, 0.018), (0.245, 0.14, 0.232), hair, segments=10, rings=4)
    for x in (-0.235, 0.235):
        ellipsoid((x, 0.59, 0.0), (0.045, 0.075, 0.075), skin, segments=8, rings=3)
    for x in (-0.082, 0.082):
        ellipsoid((x, 0.635, -0.219), (0.027, 0.032, 0.018), eyes, segments=8, rings=3)
    ellipsoid((0.0, 0.585, -0.226), (0.042, 0.050, 0.028), skin, segments=8, rings=3)
    ellipsoid((0.0, 0.835, 0.02), (0.115, 0.095, 0.11), hair, segments=8, rings=4)

    straw = (0.86, 0.62, 0.28, 1.0)
    iron = (0.46, 0.50, 0.56, 1.0)
    if cast == "WANDERER":
        ellipsoid((0.0, 0.84, 0.0), (0.34, 0.05, 0.34), straw, segments=10, rings=3)
        ellipsoid((0.0, 0.92, 0.0), (0.16, 0.09, 0.16), straw, segments=8, rings=3)
        ellipsoid((0.0, 0.06, 0.24), (0.13, 0.11, 0.11), straw, segments=8, rings=4)
    elif cast == "GUARDIAN":
        ellipsoid((0.0, 0.84, 0.02), (0.26, 0.12, 0.22), iron, segments=10, rings=4)
        box((0.0, 0.66, -0.18), (0.16, 0.05, 0.04), iron)
        box((0.0, 0.08, -0.02), (0.28, 0.08, 0.18), iron)
        box((0.0, 0.96, 0.0), (0.03, 0.12, 0.03), accent)
    elif cast == "CRITTER":
        ellipsoid((0.20, 0.78, 0.04), (0.06, 0.14, 0.10), hair, segments=8, rings=3)
        ellipsoid((-0.20, 0.78, 0.04), (0.06, 0.14, 0.10), hair, segments=8, rings=3)
        ellipsoid((0.0, -0.18, 0.28), (0.07, 0.08, 0.16), accent, segments=8, rings=3)

    index_data = struct.pack("<%dH" % len(index_values), *index_values)
    geometry = QQuick3DGeometry()
    default_idle = pose_state == "IDLE" and pose_bucket == 0 and cast == "CROWD"
    geometry.setObjectName(
        "gameCharacterBodyGeometry"
        if default_idle
        else "gameCharacterBodyGeometry_%s_%s_%d" % (cast, pose_state, pose_bucket)
    )
    geometry.setStride(CHARACTER_VERTEX_STRIDE)
    geometry.addAttribute(
        QQuick3DGeometry.Attribute.PositionSemantic,
        0,
        QQuick3DGeometry.Attribute.F32Type,
    )
    geometry.addAttribute(
        QQuick3DGeometry.Attribute.NormalSemantic,
        12,
        QQuick3DGeometry.Attribute.F32Type,
    )
    geometry.addAttribute(
        QQuick3DGeometry.Attribute.ColorSemantic,
        24,
        QQuick3DGeometry.Attribute.F32Type,
    )
    geometry.addAttribute(
        QQuick3DGeometry.Attribute.IndexSemantic,
        0,
        QQuick3DGeometry.Attribute.U16Type,
    )
    geometry.setVertexData(bytes(vertex_data))
    geometry.setIndexData(index_data)
    geometry.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
    geometry.setBounds(
        QVector3D(-0.62, -0.88, -0.52),
        QVector3D(0.62, 0.96, 0.52),
    )
    return geometry


def build_terrain_geometry(cell: dict[str, Any]) -> QQuick3DGeometry | None:
    """Build one indexed, lit patch from a compact terrain cell contract."""
    if not isinstance(cell, dict):
        return None
    coordinates = _cell_coordinates(cell)
    grid = _grid_for_cell(cell)
    if coordinates is None or grid is None:
        return None
    cell_x, cell_z = coordinates
    grid_size, heights = grid
    cell_size = 16.0
    step = cell_size / float(grid_size - 1)
    shared_normals = _normal_grid_for_cell(cell, grid_size)

    vertex_data = bytearray()
    for row in range(grid_size):
        for column in range(grid_size):
            index = row * grid_size + column
            height = heights[index]
            if shared_normals is not None:
                nx, ny, nz = shared_normals[index]
            else:
                if column == 0:
                    slope_x = (heights[index + 1] - height) / step
                elif column == grid_size - 1:
                    slope_x = (height - heights[index - 1]) / step
                else:
                    slope_x = (
                        heights[index + 1] - heights[index - 1]
                    ) / (2.0 * step)
                if row == 0:
                    slope_z = (
                        heights[index + grid_size] - height
                    ) / step
                elif row == grid_size - 1:
                    slope_z = (
                        height - heights[index - grid_size]
                    ) / step
                else:
                    slope_z = (
                        heights[index + grid_size]
                        - heights[index - grid_size]
                    ) / (2.0 * step)
                normal_length = math.sqrt(
                    slope_x * slope_x + 1.0 + slope_z * slope_z
                ) or 1.0
                nx = -slope_x / normal_length
                ny = 1.0 / normal_length
                nz = -slope_z / normal_length
            vertex_data.extend(
                struct.pack(
                    "<8f",
                    column * step,
                    height,
                    row * step,
                    nx,
                    ny,
                    nz,
                    column / float(grid_size - 1),
                    row / float(grid_size - 1),
                )
            )

    index_values: list[int] = []
    for row in range(grid_size - 1):
        for column in range(grid_size - 1):
            top_left = row * grid_size + column
            top_right = top_left + 1
            bottom_left = top_left + grid_size
            bottom_right = bottom_left + 1
            # Counter-clockwise when viewed from above: front faces point +Y.
            index_values.extend(
                (
                    top_left,
                    bottom_left,
                    top_right,
                    top_right,
                bottom_left,
                bottom_right,
            )
        )
    # Keep the patch's actual vertices exactly on the shared heightfield and
    # add only a shallow edge curtain for mismatched neighbouring LODs.
    north_edge = [column for column in range(grid_size)]
    south_edge = [
        (grid_size - 1) * grid_size + column
        for column in range(grid_size - 1, -1, -1)
    ]
    west_edge = [row * grid_size for row in range(grid_size - 1, -1, -1)]
    east_edge = [row * grid_size + (grid_size - 1) for row in range(grid_size)]
    for edge, normal in (
        (north_edge, (0.0, 0.0, -1.0)),
        (south_edge, (0.0, 0.0, 1.0)),
        (west_edge, (-1.0, 0.0, 0.0)),
        (east_edge, (1.0, 0.0, 0.0)),
    ):
        _append_terrain_skirt(
            vertex_data,
            index_values,
            heights,
            grid_size,
            edge,
            normal,
            step,
        )
    index_data = struct.pack(
        "<%dH" % len(index_values),
        *index_values,
    )

    geometry = QQuick3DGeometry()
    geometry.setObjectName(
        "terrainPatch_%s" % str(cell.get("key", "%d:%d" % (cell_x, cell_z)))
    )
    geometry.setStride(VERTEX_STRIDE)
    geometry.addAttribute(
        QQuick3DGeometry.Attribute.PositionSemantic,
        0,
        QQuick3DGeometry.Attribute.F32Type,
    )
    geometry.addAttribute(
        QQuick3DGeometry.Attribute.NormalSemantic,
        12,
        QQuick3DGeometry.Attribute.F32Type,
    )
    geometry.addAttribute(
        QQuick3DGeometry.Attribute.TexCoordSemantic,
        24,
        QQuick3DGeometry.Attribute.F32Type,
    )
    geometry.addAttribute(
        QQuick3DGeometry.Attribute.IndexSemantic,
        0,
        QQuick3DGeometry.Attribute.U16Type,
    )
    geometry.setVertexData(bytes(vertex_data))
    geometry.setIndexData(index_data)
    geometry.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
    min_height = min(heights)
    max_height = max(heights)
    # A completely flat patch has a zero-thickness AABB. Some render paths
    # can cull such a mesh before its triangles are considered, so give it a
    # tiny conservative vertical extent without changing vertex data.
    if max_height - min_height < 0.02:
        min_height -= 0.01
        max_height += 0.01
    min_height -= TERRAIN_SKIRT_DEPTH_M
    geometry.setBounds(
        QVector3D(0.0, min_height, 0.0),
        QVector3D(cell_size, max_height, cell_size),
    )
    return geometry


class TerrainGeometryCache(QObject):
    """Keep current cell geometry alive while bounding native object growth."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._entries: dict[str, tuple[tuple[Any, ...], QQuick3DGeometry]] = {}

    def retain(self, keys: set[str]) -> None:
        for key in tuple(self._entries):
            if key not in keys:
                entry = self._entries.pop(key, None)
                if entry is not None:
                    # QML may still be finishing the old delegate for this
                    # cell during the current event turn. deleteLater keeps
                    # that handoff safe while the QObject parent prevents a
                    # Python/QML ownership race.
                    entry[1].deleteLater()

    def update_cells(self, cells: dict[str, dict[str, Any]]) -> None:
        """Refresh already-instantiated cells without replacing their QObject."""
        for key, cell in cells.items():
            if key in self._entries:
                self.geometry_for_cell(cell)

    def geometry_for_cell(
        self,
        cell: dict[str, Any] | None,
    ) -> QQuick3DGeometry | None:
        if not isinstance(cell, dict):
            return None
        key = str(cell.get("key", ""))
        grid = _grid_for_cell(cell)
        if not key or grid is None:
            entry = self._entries.pop(key, None)
            if entry is not None:
                entry[1].deleteLater()
            return None
        grid_size, heights = grid
        coordinates = _cell_coordinates(cell)
        if coordinates is None:
            return None
        signature = (
            coordinates[0],
            coordinates[1],
            grid_size,
            tuple(heights),
        )
        existing = self._entries.get(key)
        if existing is not None and existing[0] == signature:
            return existing[1]
        geometry = build_terrain_geometry(cell)
        if geometry is None:
            entry = self._entries.pop(key, None)
            if entry is not None:
                entry[1].deleteLater()
            return None
        if existing is not None:
            current_geometry = existing[1]
            # QML keeps the geometry QObject as the Model's property. Updating
            # its buffers in place makes a live terrain edit visible even when
            # Repeater3D reuses the delegate for the same cell key.
            current_geometry.setStride(geometry.stride())
            current_geometry.setVertexData(geometry.vertexData())
            current_geometry.setIndexData(geometry.indexData())
            current_geometry.setBounds(geometry.boundsMin(), geometry.boundsMax())
            self._entries[key] = (signature, current_geometry)
            return current_geometry
        if key not in self._entries and len(self._entries) >= MAX_GEOMETRIES:
            evicted = self._entries.pop(next(iter(self._entries)))
            evicted[1].deleteLater()
        self._entries[key] = (signature, geometry)
        return geometry
