# GG Blender asset pipeline

This directory contains the first authored-content generator for the GAME
ENGINE. It runs with Blender's bundled Python and keeps generated assets
separate from the runtime fallback geometry until they pass visual and import
regression checks.

## First authored character

From the repository root:

```bash
blender --factory-startup --background \
  --python tools/blender/build_gg_clay_hero.py -- \
  --out qml/assets/authored/gg-clay-hero-a.glb \
  --preview /tmp/gg-clay-hero-a.png
```

The script produces an original faceted clay character with a real armature,
skinned mesh pieces, `HEAD/CHEST/MAIN_HAND/OFF_HAND/BACK/FEET` sockets and the
GAME ENGINE clips `Idle`, `Walk`, `Sprint` and `Air`. It does not copy a mesh
or texture from a reference game.

`authored/gg-clay-hero-a.glb` is the canonical player asset after passing the
local validator and QML RuntimeLoader test. The historical
`gg-authored-hero.gltf` plus its sibling `.bin` are kept as a one-file-path
compatibility alias for desktop processes that were already open before the
promotion; they contain the same generated character, not a second visual
model.

## World kit

Coastal props (mangrove, cottage, lantern post) use the same clay language:

```bash
blender --factory-startup --background \
  --python tools/blender/build_gg_clay_world.py -- \
  --out-dir qml/assets/authored/world
```

Live world volume still renders through the bounded native geometry cache so
dozens of trees do not each take a RuntimeLoader slot. The GLBs are the
authored source of the same silhouettes.

## Visual EXT desk + MCP

The GG AI Desktop EXT tab hosts a real Blender window (same X11 embed path as
DRAW). A localhost sidecar inside that GUI exposes `ping`, `scene`, `exec`,
`screenshot`, `inspect`, `turnaround`, `deform_rig`, `clean` and `export_glb`
on `127.0.0.1:19876`. Grok talks to it through the project MCP server
`gg-blender` instead of a headless CLI render. `inspect` counts holes and
joints, `turnaround` writes front/side/back/three-quarter plus a wireframe,
`deform_rig` builds the 90-joint deformation skeleton, and `clean` refuses
to edit until `apply` is true.

```bash
python3 tools/blender/gg_blender_mcp.py
```

Open EXT, wait until the status says MCP LIVE, then screenshot or exec against
the visible viewport. Headless `blender --background` generators above stay
for deterministic batch exports.
