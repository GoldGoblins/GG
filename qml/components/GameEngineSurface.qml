pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick3D
import QtQuick3D.AssetUtils
import QtQuick3D.Helpers

Item {
    id: root
    objectName: "workspaceGameEnginePane"

    property var surfaceHost: null
    property color frameBorder: "#6a6a6a"
    property int frameRadius: 4
    // WorkspaceSurface keeps this pane loaded while hidden.  paneLive is
    // the Loader's visible flag; local `visible` stays true on the child.
    property bool paneLive: true
    property bool resumeWhenShown: false
    property string statusJson: "{}"
    // The full status drives inspectors at a bounded cadence.  The render
    // status is a compact transform/pose stream and may update every frame
    // without reparsing inventories, NPC identities and content catalogs.
    property string renderStatusJson: "{}"
    // UI deltas replace only dynamic inspector sections over the last full
    // snapshot.  They never own simulation state or the render model.
    property string uiStatusJson: "{}"
    property bool fullStatusApplyInProgress: false
    property bool fullStatusReady: false
    property bool renderStreamPrimed: false
    property string page: "PLAY"
    property string selectedItemId: ""
    property real throttle: 0
    property real steer: 0
    property real strafe: 0
    property real brake: 0
    property real vertical: 0
    property bool boost: false
    property bool jump: false
    // Presentation is disposable; the simulation remains authoritative when
    // the rich scene is unavailable.  This local flag is also useful for a
    // future native graphics watchdog that cannot safely mutate game state.
    property bool localGraphicsFailure: false
    // WoW-style input: A/D rotate the avatar, Q/E strafe, and the camera is a
    // separate right-mouse orbit.  The action registry below keeps this
    // readable grammar remappable without scattering key codes through QML.
    property var pressedTokens: ({})
    property string bindingCaptureAction: ""
    property real orbitYaw: 0
    // The authored character fixture is 1.5 m tall.  An 18 m default orbit
    // gives that metre scale enough context to read the island as a world
    // instead of a tabletop, while the wheel still allows a close 6 m view.
    property real cameraDistance: 18
    property real orbitPitch: -27
    // The navigation rail and the inspector are independent overlays.  Their
    // collapsed forms deliberately keep a small click target over the scene
    // instead of removing the route or stealing space from the engine view.
    property bool leftMenuCollapsed: false
    property bool inspectorCollapsed: false
    // QtQuick3D's built-in primitive meshes are authored at 100 units.  The
    // simulation uses compact gameplay coordinates, so keep the conversion in
    // one place instead of distorting the physics data.
    readonly property real sceneScale: 0.01
    readonly property real terrainCellSize: 16.0
    // One directional shadow pass is affordable for the bounded preview;
    // POTATO remains deliberately unshadowed. Point-light shadows are kept
    // off because Qt renders them as six cubemap passes.
    readonly property bool shadowMappingEnabled:
        String(root.render.profile || "BALANCED") !== "POTATO"
    property bool applyingRenderStatus: false
    property var renderModelIndex: ({
        "terrainRow": ({}),
        "entityRow": ({}),
        "particleRow": ({})
    })
    // Replace Qt's dense convenience sphere with one shared native mesh.
    // GG_CLAY_ASSET_KIT is the shared item/prop style contract: one cached
    // indexed mesh family, vertex-colored matte clay, no primitive disguise.
    // The QML helper is a capability fallback for an already-running host
    // whose Python bridge predates this property.  It is deliberately
    // configured to the same 12-segment/6-ring budget, never Qt's dense
    // built-in #Sphere.
    SphereGeometry {
        id: lowPolySphereGeometryFallback
        objectName: "gameLowPolySphereGeometryFallback"
        radius: 50
        rings: 6
        segments: 12
        asynchronous: false
    }
    readonly property var lowPolySphereGeometry:
        root.surfaceHost
        && typeof root.surfaceHost.gameEngineLowPolySphereGeometry === "function"
            ? (root.surfaceHost.gameEngineLowPolySphereGeometry()
                || lowPolySphereGeometryFallback)
            : lowPolySphereGeometryFallback
    // The character fallback is one shared low-poly humanoid geometry in
    // gameplay metre units. A minimal/older host may not expose that native
    // cache yet; in that case the already shared low-poly sphere is safer than
    // creating a cube or a second per-character mesh. The real host exposes
    // gameEngineCharacterGeometry(), so normal runtime uses the humanoid
    // silhouette without changing the simulation contract.
    readonly property var nativeLowPolyCharacterGeometry:
        root.surfaceHost
        && typeof root.surfaceHost.gameEngineCharacterGeometry === "function"
            ? root.surfaceHost.gameEngineCharacterGeometry() : null
    readonly property var lowPolyCharacterGeometry:
        root.nativeLowPolyCharacterGeometry || root.lowPolySphereGeometry
    function characterGeometryForCast(role) {
        if (
            root.surfaceHost
            && typeof root.surfaceHost.gameEngineCharacterGeometryForRole === "function"
        ) {
            var geometry = root.surfaceHost.gameEngineCharacterGeometryForRole(
                String(role || "CROWD")
            )
            if (geometry)
                return geometry
        }
        return root.lowPolyCharacterGeometry
    }
    readonly property bool lowPolyCharacterUsesGameplayUnits:
        Boolean(root.nativeLowPolyCharacterGeometry)
    // The target is intentionally UI state.  The authoritative edit and its
    // undo history remain in the bounded backend terrain document.
    property bool terrainTargetSelected: false
    property int terrainTargetX: 0
    property int terrainTargetZ: 0
    property string terrainTargetKey: ""
    property real terrainBrushX: terrainCellSize * 0.5
    property real terrainBrushZ: terrainCellSize * 0.5
    property real terrainBrushRadius: 4.0
    property string terrainBrushFalloff: "SMOOTH"
    property bool terrainBrushEnabled: false
    property string terrainBrushOperation: "RAISE"

    readonly property color ink: "#e6edf3"
    readonly property color text: "#c8cdd4"
    readonly property color muted: "#7f8993"
    readonly property color panel: "#181818"
    readonly property color panelRaised: "#202020"
    readonly property color selectedPanel: "#34383d"
    readonly property color ledgerGold: "#c8a97e"
    readonly property color ledgerGreen: "#8db89a"
    readonly property color signalBlue: "#7fa9c4"
    readonly property color signalRed: "#c98989"
    readonly property color signalViolet: "#b6a6c8"
    // OSINT density: overlays carry the data while the 3D scene remains
    // visible underneath. Raised cards are still transparent enough to read
    // as instrumentation rather than a second application window.
    readonly property color panelOverlay: Qt.rgba(0.067, 0.082, 0.09, 0.24)
    readonly property color panelOverlayRaised: Qt.rgba(0.067, 0.082, 0.09, 0.30)
    readonly property var nav: [
        "PLAY", "BAG", "SCENE", "PERF", "NET", "ASSETS", "UI"
    ]
    readonly property var terrainBrushFalloffs: [
        "SMOOTH", "LINEAR", "SHARP", "GAUSSIAN"
    ]

    // The 3D repeaters must receive a stable model identity.  Replacing a JavaScript
    // array at 30 Hz makes QtQuick3D destroy and recreate every delegate,
    // which is visible as asset flicker and can briefly expose an empty scene.
    // Each list keeps one bounded row per render object and updates it by the
    // authoritative stable key.  A cell/NPC/item entering or leaving the view
    // must not tear down unrelated RuntimeLoader or pose delegates.
    ListModel {
        id: terrainRenderModel
        objectName: "gameEngineTerrainRenderModel"
    }
    ListModel {
        id: entityRenderModel
        objectName: "gameEngineEntityRenderModel"
    }
    ListModel {
        id: particleRenderModel
        objectName: "gameEngineParticleRenderModel"
    }

    readonly property var baseStatus: {
        try {
            return JSON.parse(root.statusJson || "{}")
        } catch (err) {
            return {}
        }
    }
    readonly property var uiStatus: {
        try {
            return JSON.parse(root.uiStatusJson || "{}")
        } catch (err) {
            return {}
        }
    }
    readonly property var status: {
        // Keep the full snapshot as the authoritative catalogue/document and
        // overlay only explicitly supplied top-level UI sections.  This is a
        // shallow transport merge: nested gameplay data is never invented or
        // reconstructed in QML.
        var merged = ({})
        var base = root.baseStatus || ({})
        var delta = root.uiStatus || ({})
        var baseKey
        for (baseKey in base)
            merged[baseKey] = base[baseKey]
        var deltaKey
        for (deltaKey in delta) {
            if (deltaKey !== "schema")
                merged[deltaKey] = delta[deltaKey]
        }
        return merged
    }
    readonly property var renderStatus: {
        try {
            return JSON.parse(root.renderStatusJson || "{}")
        } catch (err) {
            return {}
        }
    }
    readonly property var simulation: root.renderStatus.simulation
        || root.status.simulation || ({})
    readonly property var player: root.renderStatus.player
        || root.status.player || ({})
    readonly property var inputState: root.status.input || ({})
    readonly property var render: root.renderStatus.render
        || root.status.render || ({})
    readonly property var presentation: root.render.presentation || ({})
    readonly property var fallbackView: root.render.fallback
        || (root.status.render ? root.status.render.fallback : ({}))
    readonly property string presentationMode: String(
        root.presentation.mode || "RICH_3D"
    )
    readonly property string presentationReason: String(
        root.presentation.reason || "NONE"
    )
    readonly property bool dosFallbackActive: root.localGraphicsFailure
        || root.presentationMode === "DOS_2D"
    readonly property var network: root.status.network || ({})
    readonly property var replay: root.status.replay || ({})
    readonly property var chunks: root.status.chunks || ({})
    readonly property var world: root.status.world || ({})
    readonly property var worldStreaming: root.world.streaming || ({})
    readonly property var combat: root.status.combat || ({})
    readonly property var controller: root.status.controller || ({})
    readonly property var inventory: root.status.inventory || ({})
    readonly property var items: root.status.items || ({})
    readonly property var economy: root.status.economy || ({})
    readonly property var itemInteraction: root.items.interaction_target || ({})
    readonly property var life: root.status.life || ({})
    readonly property var crafting: root.status.crafting || ({})
    readonly property var progression: root.status.progression || ({})
    readonly property var quests: root.status.quests || ({})
    readonly property var factions: root.status.factions || ({})
    readonly property var dialogue: root.status.dialogue || ({})
    readonly property var social: root.status.social || ({})
    readonly property var livingWorld: root.status.living_world || ({})
    readonly property var worldEvents: root.status.world_events || ({})
    readonly property var contentPacks: root.status.content_packs || ({})
    readonly property var editor: root.status.editor || ({})
    readonly property var cinematic: root.status.cinematic || ({})
    readonly property var content: root.status.content || ({})
    // The stream contract, rather than a renderer-only constant, owns the
    // amount of world that the presentation must cover.  The render ring is
    // deliberately larger than gameplay interest: its outer cells are HLOD
    // only and do not expand physics, NPC navigation or network state.
    readonly property real streamInterestRadius: Math.max(
        0,
        root.number(
            root.worldStreaming.render_radius,
            root.number(root.worldStreaming.interest_radius, 3)
        )
    )
    readonly property real streamCoverageSize: Math.max(
        80,
        root.number(
            root.worldStreaming.render_coverage_diameter_m,
            (2 * root.streamInterestRadius + 1) * root.terrainCellSize
        )
    )
    readonly property var assets: root.status.assets || ({})
    readonly property var characterVisual: root.assets.character_visual || ({})
    readonly property var selectedAsset: root.assets.selected || ({})
    readonly property int assetInstanceBudget: Math.max(
        0,
        Math.floor(root.number(root.assets.instance_budget, 0))
    )
    readonly property var terrain: root.status.terrain || ({})
    readonly property var navigation: root.status.navigation || ({})
    readonly property var terrainCells: root.terrain.cells || []
    readonly property var terrainSurface: root.uiStatus.terrain_surface
        || root.terrain.player_surface || ({})
    readonly property var terrainEditor: root.status.terrain_editor
        || root.terrain.authoring || ({})
    readonly property int terrainGeometryRevision: Math.max(
        0,
        Math.floor(root.number(root.terrainEditor.revision, 0))
    )
    readonly property var npc: root.status.npc || ({})
    readonly property var npcInteraction: root.npc.interaction || ({})
    readonly property var people: root.status.people || ({})
    readonly property var gear: root.status.gear || ({})
    readonly property var physics: root.status.physics || ({})
    readonly property var terrainTargetCell: root.terrainCellForKey(
        root.terrainTargetKey
    ) || ({})
    readonly property var events: root.status.events || []
    readonly property var eventJournal: root.status.event_journal || ({})
    readonly property var dos: root.status.dos || ({})
    readonly property var capabilities: root.status.capabilities || []
    readonly property var keyBindings: root.status.keybindings || ({})
    readonly property var addonState: root.status.addons || ({})
    readonly property var renderEntities: root.render.entities || []
    readonly property var renderParticles: root.render.particles || []

    function runtimeLoaderHasVisualContent(loader) {
        // RuntimeLoader.Success means decoding completed, but the imported
        // scene is represented by child nodes.  Keep the one primitive
        // rectangle visible until at least one actual Model/geometry child
        // is present; this closes the small status-success/first-scene-frame
        // gap without inventing a second gameplay state.
        if (!loader || loader.status !== RuntimeLoader.Success)
            return false
        function hasVisual(node) {
            if (!node)
                return false
            var sourceValue = node.source
            if (sourceValue !== undefined && String(sourceValue) !== "")
                return node.visible !== false
            var geometryValue = node.geometry
            if (geometryValue !== undefined && geometryValue !== null)
                return node.visible !== false
            var nested = node.children || []
            for (var childIndex = 0; childIndex < nested.length; ++childIndex) {
                if (hasVisual(nested[childIndex]))
                    return true
            }
            return false
        }
        var children = loader.children || []
        for (var index = 0; index < children.length; ++index) {
            if (hasVisual(children[index]))
                return true
        }
        return false
    }
    function authoredClipForMotionState(value) {
        var state = String(value || "IDLE").toUpperCase()
        if (state === "WALK")
            return "Walk"
        if (state === "SPRINT")
            return "Sprint"
        if (state === "AIR")
            return "Air"
        return "Idle"
    }
    readonly property bool stress: root.renderStatus.stress !== undefined
        ? Boolean(root.renderStatus.stress) : Boolean(root.status.stress)
    readonly property bool running: String(
        root.renderStatus.state || root.status.state || ""
    ) === "RUNNING"
    readonly property bool recording: Boolean(root.replay.recording)
    readonly property bool replaying: Boolean(root.replay.replaying)
    readonly property string movementMode: String(
        root.player.movement_mode || root.inputState.movement_mode || "GROUND"
    )
    readonly property int renderUpdateHz: Math.max(
        1,
        Math.floor(root.number(
            root.render.update_hz,
            root.stress ? 20 : 30
        ))
    )
    readonly property int renderUpdateIntervalMs: Math.max(
        16,
        Math.round(1000 / root.renderUpdateHz)
    )
    // Full status construction remains available for commands and initial
    // binding.  During movement the inspector samples an authoritative delta
    // at 2 Hz (1 Hz under stress), leaving the fixed-step/render paths alone.
    readonly property int statusUpdateIntervalMs: root.stress ? 750 : 500
    readonly property string legend: root.stress
        ? "LOCAL · STRESS · RENDER 20 HZ · UI 1 HZ"
        : "LOCAL · FIXED 60 HZ · RENDER 30 HZ · UI 2 HZ"

    function installFullStatus(raw, immediateRender) {
        if (raw === undefined || raw === null)
            return
        root.fullStatusApplyInProgress = true
        root.uiStatusJson = "{}"
        root.statusJson = String(raw)
        root.renderStatusJson = String(raw)
        root.fullStatusApplyInProgress = false
        root.fullStatusReady = true
        // Commands need an immediate visual response.  Periodic full UI
        // refreshes do not: the compact render stream will carry transforms
        // and structural changes on its next bounded tick.
        if (immediateRender || !root.renderStreamPrimed) {
            root.syncRenderModels(root.renderStatusJson)
            root.renderStreamPrimed = true
        }
    }

    function applyRaw(raw) {
        root.installFullStatus(raw, true)
    }

    function renderSignature(value, roleName) {
        if (!value)
            return "NULL"
        if (roleName === "terrainRow") {
            var authoring = value.authoring || ({})
            return [
                value.key,
                value.lod,
                value.visibility ? value.visibility.render : true,
                authoring.overridden,
                authoring.brush_count,
                authoring.height_delta_m,
                authoring.biome,
                authoring.water_mode
            ].join("|")
        }
        if (roleName === "particleRow") {
            return [value.x, value.y, value.z, value.life, value.color].join("|")
        }
        if (roleName === "entityRow") {
            // Static bindings (assets, equipment and entity kind) are kept in
            // the delegate's entityRow role.  Positions and poses travel in
            // entityDynamic so a moving NPC does not cause RuntimeLoader,
            // materials or nested equipment repeaters to reevaluate.
            var staticAsset = value.asset || ({})
            var staticItem = value.item || ({})
            var staticItemAsset = staticItem.asset || ({})
            var staticEquipment = value.equipment || []
            var equipmentKeys = ""
            for (var equipmentIndex = 0;
                 equipmentIndex < staticEquipment.length;
                 ++equipmentIndex) {
                var equipped = staticEquipment[equipmentIndex] || ({})
                equipmentKeys += String(equipped.instance_id || "")
                    + ":" + String(equipped.equipped_slot || "") + ";"
            }
            return [
                value.id,
                value.kind,
                value.sx,
                value.sy,
                value.sz,
                value.color,
                staticAsset.id,
                staticAsset.mode,
                staticAsset.source,
                staticAsset.root_offset_m,
                staticAsset.instance_rank,
                staticAsset.instance_budget,
                staticItem.instance_id,
                staticItem.location,
                staticItemAsset.mode,
                staticItemAsset.source,
                equipmentKeys
            ].join("|")
        }
        var animation = value.animation || ({})
        var asset = value.asset || ({})
        var item = value.item || ({})
        var itemAsset = item.asset || ({})
        var itemVisual = item.visual || ({})
        return [
            value.id,
            value.kind,
            value.x,
            value.y,
            value.z,
            value.yaw,
            value.sx,
            value.sy,
            value.sz,
            value.lod,
            value.speed,
            value.motion_state,
            animation.state,
            animation.phase,
            animation.bob_m,
            animation.lean_deg,
            animation.sway_deg,
            animation.squash,
            asset.mode,
            asset.source,
            asset.instance_rank,
            asset.root_offset_m,
            item.instance_id,
            item.location,
            itemAsset.mode,
            itemVisual.bob_m,
            itemVisual.rotation_y
        ].join("|")
    }

    function renderDynamicSignature(value) {
        if (!value)
            return "NULL"
        var animation = value.animation || ({})
        var asset = value.asset || ({})
        var item = value.item || ({})
        var visual = item.visual || ({})
        return [
            value.id,
            value.x,
            value.y,
            value.z,
            value.yaw,
            value.speed,
            value.lod,
            value.motion_state,
            animation.state,
            animation.phase,
            animation.bob_m,
            animation.lean_deg,
            animation.sway_deg,
            animation.squash,
            asset.clip,
            asset.clip_status,
            asset.runtime_clip,
            visual.bob_m,
            visual.rotation_y
        ].join("|")
    }

    function renderDynamicValue(value) {
        if (!value)
            return ({})
        return {
            id: value.id,
            x: value.x,
            y: value.y,
            z: value.z,
            yaw: value.yaw,
            speed: value.speed,
            lod: value.lod,
            motion_state: value.motion_state,
            animation: value.animation || ({}),
            asset: value.asset || ({}),
            item: value.item || ({})
        }
    }

    function rebuildRenderModelIndex(model, roleName) {
        var map = ({})
        for (var index = 0; index < model.count; ++index)
            map[String(model.get(index).renderKey)] = index
        root.renderModelIndex[roleName] = map
    }

    function syncRenderModel(model, rows, roleName) {
        if (!Array.isArray(rows))
            return
        var indexByKey = root.renderModelIndex[roleName]
        if (!indexByKey)
            indexByKey = ({})
        var keyCount = 0
        var mappedKey
        for (mappedKey in indexByKey)
            keyCount += 1
        if (keyCount !== model.count) {
            root.rebuildRenderModelIndex(model, roleName)
            indexByKey = root.renderModelIndex[roleName]
        }
        var nextKeys = ({})
        var structural = false
        for (var rowIndex = 0; rowIndex < rows.length; ++rowIndex) {
            var value = rows[rowIndex]
            var sourceKey = value && (value.id !== undefined
                ? value.id
                : (value.key !== undefined ? value.key : rowIndex))
            var stableKey = roleName + "::" + String(sourceKey)
            var signature = root.renderSignature(value, roleName)
            var dynamicSignature = roleName === "entityRow"
                ? root.renderDynamicSignature(value) : ""
            nextKeys[stableKey] = true
            var existingIndex = indexByKey[stableKey]
            if (existingIndex === undefined || existingIndex === null)
                existingIndex = -1
            if (existingIndex < 0) {
                var row = {
                    "renderKey": stableKey,
                    "renderSignature": signature
                }
                row[roleName] = value
                if (roleName === "entityRow") {
                    row.entityDynamic = root.renderDynamicValue(value)
                    row.renderDynamicSignature = dynamicSignature
                }
                model.append(row)
                structural = true
            } else {
                var current = model.get(existingIndex)
                if (String(current.renderSignature) !== signature) {
                    model.setProperty(existingIndex, roleName, value)
                    model.setProperty(existingIndex, "renderSignature", signature)
                }
                if (roleName === "entityRow"
                    && String(current.renderDynamicSignature) !== dynamicSignature) {
                    model.setProperty(
                        existingIndex,
                        "entityDynamic",
                        root.renderDynamicValue(value)
                    )
                    model.setProperty(
                        existingIndex,
                        "renderDynamicSignature",
                        dynamicSignature
                    )
                }
            }
        }
        for (var removeIndex = model.count - 1; removeIndex >= 0; --removeIndex) {
            if (!nextKeys[String(model.get(removeIndex).renderKey)]) {
                model.remove(removeIndex)
                structural = true
            }
        }
        if (structural)
            root.rebuildRenderModelIndex(model, roleName)
    }

    function denseTerrainCells(cells) {
        // Play draws the nearby heightfield only.  ORBIT is one sea/horizon
        // plane, not a QQuick3D node per 16 m cell out to 336 m.
        if (!Array.isArray(cells))
            return []
        var dense = []
        for (var index = 0; index < cells.length; ++index) {
            var cell = cells[index] || ({})
            var geometry = cell.geometry || ({})
            if (root.number(geometry.vertex_grid, 1) > 1)
                dense.push(cell)
        }
        return dense
    }

    function syncTerrainModel(raw) {
        var snapshot = root.status
        if (raw !== undefined && raw !== null) {
            try {
                snapshot = JSON.parse(String(raw))
            } catch (err) {
                snapshot = {}
            }
        }
        var terrainView = snapshot.terrain || ({})
        if (Array.isArray(terrainView.cells))
            root.syncRenderModel(
                terrainRenderModel,
                root.denseTerrainCells(terrainView.cells),
                "terrainRow"
            )
    }

    function syncRenderModels(raw) {
        // A QML change handler can run before dependent readonly properties
        // have re-evaluated. Parse the changed value directly so PLAY never
        // observes a one-frame empty render list. The 30 Hz path passes the
        // already-parsed renderStatus object so PLAY does not JSON.parse twice.
        var snapshot = root.status
        if (raw !== undefined && raw !== null && typeof raw === "object")
            snapshot = raw
        else if (raw !== undefined && raw !== null) {
            try {
                snapshot = JSON.parse(String(raw))
            } catch (err) {
                snapshot = {}
            }
        }
        var renderView = snapshot.render || ({})
        var terrainView = snapshot.terrain || ({})
        // Compact render snapshots intentionally omit terrain cells; the full
        // status stream owns that static geometry and updates it only when the
        // terrain document/cell interest set actually changes.
        if (Array.isArray(terrainView.cells)) {
            root.syncRenderModel(
                terrainRenderModel,
                root.denseTerrainCells(terrainView.cells),
                "terrainRow"
            )
        }
        root.syncRenderModel(
            entityRenderModel,
            Array.isArray(renderView.entities) ? renderView.entities : [],
            "entityRow"
        )
        root.syncRenderModel(
            particleRenderModel,
            Array.isArray(renderView.particles) ? renderView.particles : [],
            "particleRow"
        )
    }

    onStatusJsonChanged: {
        if (root.fullStatusApplyInProgress)
            root.syncTerrainModel(root.statusJson)
        else {
            root.fullStatusReady = true
            root.syncRenderModels(root.statusJson)
            root.renderStreamPrimed = true
        }
        if (dosFallbackCanvas)
            dosFallbackCanvas.requestPaint()
    }

    onRenderStatusJsonChanged: {
        if (!root.fullStatusApplyInProgress && !root.applyingRenderStatus) {
            root.syncRenderModels(root.renderStatusJson)
            root.renderStreamPrimed = true
        }
        if (dosFallbackCanvas)
            dosFallbackCanvas.requestPaint()
    }

    onUiStatusJsonChanged: {
        // UI deltas deliberately do not touch any 3D repeater model.  The
        // DOS view reads the same merged status and may repaint cheaply.
        if (dosFallbackCanvas)
            dosFallbackCanvas.requestPaint()
    }

    onDosFallbackActiveChanged: {
        if (dosFallbackCanvas)
            dosFallbackCanvas.requestPaint()
    }

    function refresh() {
        if (!root.surfaceHost)
            return
        if (!root.fullStatusReady || !root.surfaceHost.gameEngineUiStatus) {
            if (root.surfaceHost.gameEngineStatus)
                root.installFullStatus(root.surfaceHost.gameEngineStatus(), false)
            return
        }
        var raw = root.surfaceHost.gameEngineUiStatus()
        if (raw !== undefined && raw !== null)
            root.uiStatusJson = String(raw)
    }

    function refreshRender() {
        if (root.surfaceHost && root.surfaceHost.gameEngineRenderStatus) {
            var raw = root.surfaceHost.gameEngineRenderStatus()
            if (raw === undefined || raw === null)
                return
            var text = String(raw)
            if (text === root.renderStatusJson)
                return
            root.applyingRenderStatus = true
            root.renderStatusJson = text
            root.applyingRenderStatus = false
            root.syncRenderModels(root.renderStatus)
            root.renderStreamPrimed = true
        } else {
            // Test bridges and older embedding hosts may expose only the full
            // status slot; keep that compatibility path explicit.
            root.refresh()
        }
    }

    function startRuntime() {
        if (root.surfaceHost && root.surfaceHost.gameEngineStart)
            root.applyRaw(root.surfaceHost.gameEngineStart())
    }

    function pauseRuntime() {
        if (root.surfaceHost && root.surfaceHost.gameEnginePause)
            root.applyRaw(root.surfaceHost.gameEnginePause())
    }

    function resetRuntime() {
        if (root.surfaceHost && root.surfaceHost.gameEngineReset)
            root.applyRaw(root.surfaceHost.gameEngineReset())
    }

    function stepRuntime() {
        if (root.surfaceHost && root.surfaceHost.gameEngineStep)
            root.applyRaw(root.surfaceHost.gameEngineStep())
    }

    function burstRuntime() {
        if (root.surfaceHost && root.surfaceHost.gameEngineBurst)
            root.applyRaw(root.surfaceHost.gameEngineBurst())
    }

    function stressRuntime() {
        if (root.surfaceHost && root.surfaceHost.gameEngineStress)
            root.applyRaw(root.surfaceHost.gameEngineStress(!root.stress))
    }

    function setMovementMode(mode) {
        if (root.surfaceHost && root.surfaceHost.gameEngineMovementMode)
            root.applyRaw(root.surfaceHost.gameEngineMovementMode(String(mode)))
        else
            root.sendInput()
    }

    function useAbility(abilityId) {
        if (root.surfaceHost && root.surfaceHost.gameEngineAbility)
            root.applyRaw(root.surfaceHost.gameEngineAbility(
                String(abilityId || "ability.surge")
            ))
    }

    function claimLoot() {
        if (root.surfaceHost && root.surfaceHost.gameEngineLoot)
            root.applyRaw(root.surfaceHost.gameEngineLoot())
    }

    function craftRecipe(recipeId) {
        if (root.surfaceHost && root.surfaceHost.gameEngineCraft)
            root.applyRaw(root.surfaceHost.gameEngineCraft(
                String(recipeId || "recipe.field_ration")
            ))
    }

    function craftGear(recipeId, stationId) {
        if (root.surfaceHost && root.surfaceHost.gameEngineGearCraft)
            root.applyRaw(root.surfaceHost.gameEngineGearCraft(
                String(recipeId || "recipe.fiber_rope"),
                String(stationId || "")
            ))
    }

    function findAttachmentNode(loader, name) {
        if (!loader || !name)
            return null
        if (root.surfaceHost
            && typeof root.surfaceHost.gameEngineFindNamedNode === "function")
            return root.surfaceHost.gameEngineFindNamedNode(loader, String(name))
        return null
    }

    function socketItem(instanceId, insertableId) {
        if (root.surfaceHost && root.surfaceHost.gameEngineItemSocket)
            root.applyRaw(root.surfaceHost.gameEngineItemSocket(
                String(instanceId || root.selectedItemId || ""),
                String(insertableId || "")
            ))
    }

    function enchantGear(instanceId, enchantId) {
        if (root.surfaceHost && root.surfaceHost.gameEngineGearEnchant)
            root.applyRaw(root.surfaceHost.gameEngineGearEnchant(
                String(instanceId || root.selectedItemId || ""),
                String(enchantId || "")
            ))
    }

    function enchantLoot(enchantId) {
        if (root.surfaceHost && root.surfaceHost.gameEngineEnchant)
            root.applyRaw(root.surfaceHost.gameEngineEnchant(
                String(enchantId || "enchant.wayfinder")
            ))
    }

    function interactItem() {
        if (root.surfaceHost && root.surfaceHost.gameEngineItemInteract)
            root.applyRaw(root.surfaceHost.gameEngineItemInteract())
    }

    function pickupItem(instanceId) {
        if (root.surfaceHost && root.surfaceHost.gameEngineItemPickup)
            root.applyRaw(root.surfaceHost.gameEngineItemPickup(
                String(instanceId || "")
            ))
    }

    function openContainer(instanceId) {
        if (root.surfaceHost && root.surfaceHost.gameEngineContainerOpen)
            root.applyRaw(root.surfaceHost.gameEngineContainerOpen(
                String(instanceId || "")
            ))
    }

    function lootContainer(instanceId) {
        if (root.surfaceHost && root.surfaceHost.gameEngineContainerLoot)
            root.applyRaw(root.surfaceHost.gameEngineContainerLoot(
                String(instanceId || "")
            ))
    }

    function equipItem(instanceId) {
        if (root.surfaceHost && root.surfaceHost.gameEngineItemEquip)
            root.applyRaw(root.surfaceHost.gameEngineItemEquip(
                String(instanceId || "")
            ))
    }

    function dropItem(instanceId) {
        if (root.surfaceHost && root.surfaceHost.gameEngineItemDrop)
            root.applyRaw(root.surfaceHost.gameEngineItemDrop(
                String(instanceId || "")
            ))
    }

    function gainXp(amount) {
        if (root.surfaceHost && root.surfaceHost.gameEngineXp)
            root.applyRaw(root.surfaceHost.gameEngineXp(Number(amount || 25)))
    }

    function spendTalent(talentId) {
        if (root.surfaceHost && root.surfaceHost.gameEngineTalent)
            root.applyRaw(root.surfaceHost.gameEngineTalent(
                String(talentId || "trailblazer")
            ))
    }

    function selectRace(race) {
        if (root.surfaceHost && root.surfaceHost.gameEngineRace)
            root.applyRaw(root.surfaceHost.gameEngineRace(String(race)))
    }

    function selectSpec(spec) {
        if (root.surfaceHost && root.surfaceHost.gameEngineSpec)
            root.applyRaw(root.surfaceHost.gameEngineSpec(String(spec)))
    }

    function placeEditorObject(kind) {
        if (root.surfaceHost && root.surfaceHost.gameEngineEditorPlace)
            root.applyRaw(root.surfaceHost.gameEngineEditorPlace(String(kind || "PROP")))
    }

    function undoEditorObject() {
        if (root.surfaceHost && root.surfaceHost.gameEngineEditorUndo)
            root.applyRaw(root.surfaceHost.gameEngineEditorUndo())
    }

    function interactNpc() {
        if (root.surfaceHost && root.surfaceHost.gameEngineNpcInteract)
            root.applyRaw(root.surfaceHost.gameEngineNpcInteract())
    }

    function talkNpc(choiceId, npcId) {
        if (root.surfaceHost && root.surfaceHost.gameEngineNpcTalk)
            root.applyRaw(root.surfaceHost.gameEngineNpcTalk(
                String(npcId || (root.dialogue.active || {}).npc_id
                    || root.npcInteraction.target_id || ""),
                String(choiceId || "")
            ))
    }

    function activateContentPack(packId) {
        if (root.surfaceHost && root.surfaceHost.gameEngineContentPack)
            root.applyRaw(root.surfaceHost.gameEngineContentPack(
                String(packId || "pack.tidefall-frontier")
            ))
    }

    function attackNpc(targetId) {
        if (root.surfaceHost && root.surfaceHost.gameEngineAttack)
            root.applyRaw(root.surfaceHost.gameEngineAttack(
                String(targetId || "")
            ))
    }

    function acceptQuest(questId) {
        if (root.surfaceHost && root.surfaceHost.gameEngineQuestAccept)
            root.applyRaw(root.surfaceHost.gameEngineQuestAccept(
                String(questId || "quest.shoreline-first")
            ))
    }

    function claimQuest(questId) {
        if (root.surfaceHost && root.surfaceHost.gameEngineQuestClaim)
            root.applyRaw(root.surfaceHost.gameEngineQuestClaim(
                String(questId || "")
            ))
    }

    function tradeItems(npcId, giveInstanceId, receiveInstanceId) {
        if (root.surfaceHost && root.surfaceHost.gameEngineTrade)
            root.applyRaw(root.surfaceHost.gameEngineTrade(
                String(npcId || ""),
                String(giveInstanceId || ""),
                String(receiveInstanceId || "")
            ))
    }

    function buyFromVendor(vendorId, instanceId) {
        if (root.surfaceHost && root.surfaceHost.gameEngineVendorBuy)
            root.applyRaw(root.surfaceHost.gameEngineVendorBuy(
                String(vendorId || ""),
                String(instanceId || "")
            ))
    }

    function sellToVendor(vendorId, instanceId) {
        if (root.surfaceHost && root.surfaceHost.gameEngineVendorSell)
            root.applyRaw(root.surfaceHost.gameEngineVendorSell(
                String(vendorId || ""),
                String(instanceId || "")
            ))
    }

    function terrainCellForKey(key) {
        var wanted = String(key || "")
        if (!wanted)
            return null
        var cells = root.terrainCells || []
        for (var index = 0; index < cells.length; ++index) {
            var cell = cells[index]
            if (cell && String(cell.key || "") === wanted)
                return cell
        }
        return null
    }

    function setTerrainBrushPoint(cell, worldX, worldZ) {
        if (!cell)
            return
        var minX = root.number(cell.x, 0) * root.terrainCellSize
        var maxX = (root.number(cell.x, 0) + 1) * root.terrainCellSize
        var minZ = root.number(cell.z, 0) * root.terrainCellSize
        var maxZ = (root.number(cell.z, 0) + 1) * root.terrainCellSize
        var pointX = Number(worldX)
        var pointZ = Number(worldZ)
        if (!isFinite(pointX))
            pointX = (minX + maxX) * 0.5
        if (!isFinite(pointZ))
            pointZ = (minZ + maxZ) * 0.5
        terrainBrushX = Math.max(minX, Math.min(maxX, pointX))
        terrainBrushZ = Math.max(minZ, Math.min(maxZ, pointZ))
    }

    function setTerrainTarget(cell, worldX, worldZ) {
        if (!cell)
            return ""
        terrainTargetX = Math.floor(root.number(cell.x, 0))
        terrainTargetZ = Math.floor(root.number(cell.z, 0))
        terrainTargetKey = String(
            cell.key || ("0:" + terrainTargetX + ":" + terrainTargetZ)
        )
        terrainTargetSelected = true
        root.setTerrainBrushPoint(cell, worldX, worldZ)
        return terrainTargetKey
    }

    function adjustTerrainBrushRadius(delta) {
        terrainBrushRadius = Math.max(
            0.75,
            Math.min(
                root.terrainCellSize * 1.25,
                root.number(terrainBrushRadius, 4) + Number(delta || 0)
            )
        )
    }

    function cycleTerrainBrushFalloff() {
        var current = root.terrainBrushFalloffs.indexOf(
            String(root.terrainBrushFalloff || "SMOOTH").toUpperCase()
        )
        terrainBrushFalloff = root.terrainBrushFalloffs[
            (current + 1) % root.terrainBrushFalloffs.length
        ]
    }

    function clearTerrainTarget() {
        terrainTargetSelected = false
        terrainTargetKey = ""
    }

    function pickTerrainCell(viewX, viewY) {
        var pickedCell = null
        var pickedPointX = Number.NaN
        var pickedPointZ = Number.NaN
        try {
            var hit = view3d.pick(Number(viewX), Number(viewY))
            if (hit && hit.objectHit && hit.objectHit.modelData) {
                var hitData = hit.objectHit.modelData
                if (root.terrainCellForKey(String(hitData.key || ""))) {
                    pickedCell = hitData
                    if (hit.scenePosition) {
                        var sceneX = Number(hit.scenePosition.x)
                        var sceneZ = Number(hit.scenePosition.z)
                        if (isFinite(sceneX) && isFinite(sceneZ)) {
                            pickedPointX = sceneX
                            pickedPointZ = sceneZ
                        }
                    }
                }
            }
        } catch (err) {
            pickedCell = null
        }

        // Deep-water cells have no visible slab in the cheap preview.  The
        // projected center fallback still lets the editor target every loaded
        // cell, while never inventing an unloaded world coordinate.
        if (!pickedCell) {
            var bestCell = null
            var bestDistance = Number.POSITIVE_INFINITY
            var bestScreenX = 0
            var bestScreenY = 0
            var cells = root.terrainCells || []
            for (var index = 0; index < cells.length; ++index) {
                var cell = cells[index]
                var center = cell && cell.center_m
                if (!center)
                    continue
                try {
                    var screen = view3d.mapFrom3DScene(Qt.vector3d(
                        root.number(center.x, 0),
                        root.number(center.y, 0),
                        root.number(center.z, 0)
                    ))
                    var screenX = Number(screen.x)
                    var screenY = Number(screen.y)
                    if (!isFinite(screenX) || !isFinite(screenY))
                        continue
                    var distance = Math.hypot(
                        screenX - Number(viewX),
                        screenY - Number(viewY)
                    )
                    if (distance < bestDistance) {
                        bestDistance = distance
                        bestCell = cell
                        bestScreenX = screenX
                        bestScreenY = screenY
                    }
                } catch (projectionError) {
                    // The first frame can be before View3D has a projection.
                }
            }
            var selectionRadius = Math.max(
                42,
                Math.min(stage.width, stage.height) * 0.18
            )
            if (bestCell && bestDistance <= selectionRadius) {
                pickedCell = bestCell
                var offsetX = Math.max(
                    -0.5,
                    Math.min(
                        0.5,
                        (Number(viewX) - bestScreenX) / selectionRadius
                    )
                )
                var offsetZ = Math.max(
                    -0.5,
                    Math.min(
                        0.5,
                        (Number(viewY) - bestScreenY) / selectionRadius
                    )
                )
                pickedPointX = (
                    root.number(bestCell.x, 0) + 0.5 + offsetX
                ) * root.terrainCellSize
                pickedPointZ = (
                    root.number(bestCell.z, 0) + 0.5 + offsetZ
                ) * root.terrainCellSize
            }
        }

        // Before the first renderer frame, projection/picking can legitimately
        // be unavailable.  Keep the editor usable with a deterministic local
        // grid estimate until QtQuick3D has a valid scene hit.
        if (!pickedCell) {
            var gridCells = root.terrainCells || []
            var horizontal = (
                Number(viewX) / Math.max(1, stage.width) - 0.5
            ) * root.terrainCellSize * 5.0
            var depth = (
                Number(viewY) / Math.max(1, stage.height) - 0.5
            ) * root.terrainCellSize * 5.0
            var yawRadians = root.orbitYaw * Math.PI / 180.0
            var projectedX = root.number(root.player.x, 0)
                + horizontal * Math.cos(yawRadians)
                + depth * Math.sin(yawRadians)
            var projectedZ = root.number(root.player.z, 0)
                - horizontal * Math.sin(yawRadians)
                + depth * Math.cos(yawRadians)
            var wantedX = Math.floor(projectedX / root.terrainCellSize)
            var wantedZ = Math.floor(projectedZ / root.terrainCellSize)
            var bestGridDistance = Number.POSITIVE_INFINITY
            for (var gridIndex = 0; gridIndex < gridCells.length; ++gridIndex) {
                var gridCell = gridCells[gridIndex]
                if (!gridCell)
                    continue
                var gridDistance = Math.abs(
                    root.number(gridCell.x, 0) - wantedX
                ) + Math.abs(root.number(gridCell.z, 0) - wantedZ)
                if (gridDistance < bestGridDistance) {
                    bestGridDistance = gridDistance
                    pickedCell = gridCell
                }
            }
        }
        return root.setTerrainTarget(pickedCell, pickedPointX, pickedPointZ)
    }

    function editTerrain(operation) {
        var normalized = String(operation || "RAISE").toUpperCase()
        terrainBrushOperation = normalized
        if (!root.surfaceHost)
            return
        var target = root.terrainTargetSelected
            ? root.terrainCellForKey(root.terrainTargetKey)
            : null
        if (!target && root.terrainTargetSelected)
            root.clearTerrainTarget()
        var targetX = target
            ? root.terrainTargetX
            : Math.floor(root.number(root.player.x, 0) / root.terrainCellSize)
        var targetZ = target
            ? root.terrainTargetZ
            : Math.floor(root.number(root.player.z, 0) / root.terrainCellSize)
        if (
            (normalized === "RAISE" || normalized === "LOWER")
            && root.surfaceHost.gameEngineTerrainBrush
        ) {
            var brushX = target ? root.terrainBrushX : root.number(root.player.x, 0)
            var brushZ = target ? root.terrainBrushZ : root.number(root.player.z, 0)
            root.applyRaw(
                root.surfaceHost.gameEngineTerrainBrush(
                    normalized,
                    targetX,
                    targetZ,
                    brushX,
                    brushZ,
                    root.terrainBrushRadius,
                    root.terrainBrushFalloff
                )
            )
        } else if (root.surfaceHost.gameEngineTerrainEdit) {
            root.applyRaw(root.surfaceHost.gameEngineTerrainEdit(
                normalized,
                targetX,
                targetZ
            ))
        }
    }

    function undoTerrain() {
        if (root.surfaceHost && root.surfaceHost.gameEngineTerrainUndo)
            root.applyRaw(root.surfaceHost.gameEngineTerrainUndo())
    }

    function saveGameState() {
        if (root.surfaceHost && root.surfaceHost.gameEngineSave)
            root.applyRaw(root.surfaceHost.gameEngineSave())
    }

    function loadGameState() {
        if (root.surfaceHost && root.surfaceHost.gameEngineLoad)
            root.applyRaw(root.surfaceHost.gameEngineLoad())
    }

    function setRenderProfile(profile) {
        if (root.surfaceHost && root.surfaceHost.gameEngineRenderProfile)
            root.applyRaw(root.surfaceHost.gameEngineRenderProfile(String(profile)))
    }

    function setPresentationMode(mode) {
        var normalized = String(mode || "RICH_3D").toUpperCase()
        if (root.surfaceHost && root.surfaceHost.gameEnginePresentationMode) {
            root.localGraphicsFailure = false
            root.applyRaw(root.surfaceHost.gameEnginePresentationMode(normalized))
        } else {
            root.localGraphicsFailure = normalized === "DOS_2D"
        }
    }

    function reportGraphicsFailure(reason) {
        root.localGraphicsFailure = true
        if (root.surfaceHost && root.surfaceHost.gameEngineGraphicsFailure)
            root.applyRaw(root.surfaceHost.gameEngineGraphicsFailure(
                String(reason || "GRAPHICS_STAGE_FAILURE")
            ))
    }

    function setCinematicPreset(preset) {
        if (root.surfaceHost && root.surfaceHost.gameEngineCinematic)
            root.applyRaw(root.surfaceHost.gameEngineCinematic(String(preset)))
    }

    function sendInput() {
        if (!root.surfaceHost || !root.surfaceHost.gameEngineInput)
            return
        var payload = JSON.stringify({
            throttle: root.throttle,
            steer: root.steer,
            turn: root.steer,
            brake: root.brake,
            boost: root.boost,
            forward: root.throttle,
            strafe: root.strafe,
            vertical: root.vertical,
            jump: root.jump,
            movement_mode: root.movementMode,
            camera_yaw: root.orbitYaw,
            camera_pitch: root.orbitPitch,
            camera_distance: root.cameraDistance
        })
        if (root.surfaceHost.gameEngineInputRender) {
            // Movement is already committed to the authoritative fixed-step
            // runtime.  Do not parse/rebind the full inspector document for a
            // key transition; the compact render stream gives the scene its
            // immediate position/camera response and UI cadence updates the
            // inspector separately.
            var renderRaw = root.surfaceHost.gameEngineInputRender(payload)
            if (renderRaw !== undefined && renderRaw !== null)
                root.renderStatusJson = String(renderRaw)
        } else {
            // Compatibility path for older embedding hosts that expose only
            // the original full input slot.
            root.applyRaw(root.surfaceHost.gameEngineInput(payload))
        }
    }

    function dosCommand(command) {
        if (root.surfaceHost && root.surfaceHost.gameEngineDosCommand)
            root.applyRaw(root.surfaceHost.gameEngineDosCommand(
                String(command || "")
            ))
    }

    function startRecording() {
        if (root.surfaceHost && root.surfaceHost.gameEngineRecordStart)
            root.applyRaw(root.surfaceHost.gameEngineRecordStart())
    }

    function stopRecording() {
        if (root.surfaceHost && root.surfaceHost.gameEngineRecordStop)
            root.applyRaw(root.surfaceHost.gameEngineRecordStop())
    }

    function replayRuntime() {
        if (root.surfaceHost && root.surfaceHost.gameEngineReplay)
            root.applyRaw(root.surfaceHost.gameEngineReplay())
    }

    function number(value, fallback) {
        var parsed = Number(value)
        return isFinite(parsed) ? parsed : (fallback || 0)
    }

    function fixed(value, decimals) {
        return number(value, 0).toFixed(decimals === undefined ? 1 : decimals)
    }

    function combatActor(actorId) {
        var actors = root.combat.actors || []
        for (var index = 0; index < actors.length; ++index) {
            if (actors[index] && String(actors[index].id || "") === String(actorId || ""))
                return actors[index]
        }
        return ({})
    }

    function fallbackTerminalText() {
        var terminal = root.fallbackView.terminal || ({})
        var lines = terminal.lines || []
        return Array.isArray(lines) ? lines.join("\n") : String(lines || "")
    }

    function assetClipSummary() {
        var clips = root.selectedAsset.clips || []
        var names = []
        for (var index = 0; index < clips.length; ++index) {
            if (clips[index] && clips[index].name)
                names.push(String(clips[index].name))
        }
        return names.length ? names.join(", ") : "-"
    }

    function percent(value, maximum) {
        var max = Math.max(1, number(maximum, 1))
        return Math.max(0, Math.min(1, number(value, 0) / max))
    }

    function biomeColor(value) {
        var biome = String(value || "")
        if (biome === "FIRST_ISLAND")
            return "#c2d15a"
        if (biome === "LAND")
            return "#7eab46"
        if (biome === "CLIFF")
            return "#d2b17a"
        if (biome === "REEF")
            return "#2f9d8c"
        if (biome === "DEEP_WATER")
            return "#15657a"
        return "#1f88a0"
    }

    function terrainMaterialFor(biome, waterCell) {
        if (waterCell)
            return String(biome) === "DEEP_WATER"
                ? deepTerrainMaterial : shallowTerrainMaterial
        if (String(biome) === "FIRST_ISLAND")
            return islandTerrainMaterial
        if (String(biome) === "CLIFF")
            return cliffTerrainMaterial
        if (String(biome) === "REEF")
            return reefTerrainMaterial
        if (String(biome) === "LAND")
            return landTerrainMaterial
        return shallowTerrainMaterial
    }

    function stateColor(value) {
        var state = String(value || "")
        if (state === "RUNNING" || state === "READY")
            return root.ledgerGreen
        if (state === "PAUSED" || state === "IDLE")
            return root.ledgerGold
        if (state.indexOf("NOT") === 0 || state === "BLOCKED")
            return root.signalRed
        return root.text
    }

    function bindingMap() {
        return root.keyBindings.bindings || ({})
    }

    function keysFor(action) {
        var keys = bindingMap()[String(action || "")] || []
        if (typeof keys === "string")
            return keys
        return keys.join(" / ")
    }

    function isActionBound(action, token) {
        var keys = bindingMap()[String(action || "")] || []
        if (typeof keys === "string")
            return keys === token
        for (var index = 0; index < keys.length; ++index) {
            if (String(keys[index]) === String(token))
                return true
        }
        return false
    }

    function actionDown(action) {
        var keys = bindingMap()[String(action || "")] || []
        if (typeof keys === "string")
            keys = [keys]
        for (var index = 0; index < keys.length; ++index) {
            if (Boolean(root.pressedTokens[String(keys[index])]))
                return true
        }
        return false
    }

    function axisFor(negativeAction, positiveAction) {
        return (root.actionDown(positiveAction) ? 1 : 0)
            - (root.actionDown(negativeAction) ? 1 : 0)
    }

    function updateInputStates() {
        root.throttle = root.axisFor("MOVE_BACK", "MOVE_FORWARD")
        // QtQuick3D's positive Y rotation turns a -Z-facing avatar toward
        // screen-left.  The gameplay grammar therefore negates the raw
        // key-axis so A is visually LEFT and D is visually RIGHT.
        root.steer = -root.axisFor("TURN_LEFT", "TURN_RIGHT")
        root.strafe = root.axisFor("STRAFE_LEFT", "STRAFE_RIGHT")
        root.vertical = root.axisFor("VERTICAL_DOWN", "VERTICAL_UP")
        root.boost = root.actionDown("SPRINT")
        root.jump = root.actionDown("JUMP")
    }

    function keyToken(key) {
        if (key === Qt.Key_Space)
            return "SPACE"
        if (key === Qt.Key_Shift)
            return "SHIFT"
        if (key === Qt.Key_Control)
            return "CONTROL"
        if (key === Qt.Key_Alt)
            return "ALT"
        if (key === Qt.Key_Tab)
            return "TAB"
        if (key === Qt.Key_Return || key === Qt.Key_Enter)
            return "ENTER"
        if (key === Qt.Key_Escape)
            return "ESCAPE"
        if (key === Qt.Key_Backspace)
            return "BACKSPACE"
        if (key === Qt.Key_Delete)
            return "DELETE"
        if (key === Qt.Key_Up)
            return "UP"
        if (key === Qt.Key_Down)
            return "DOWN"
        if (key === Qt.Key_Left)
            return "LEFT"
        if (key === Qt.Key_Right)
            return "RIGHT"
        if (key >= Qt.Key_A && key <= Qt.Key_Z)
            return String.fromCharCode(key)
        if (key >= Qt.Key_0 && key <= Qt.Key_9)
            return String.fromCharCode(key)
        return ""
    }

    function rebindKey(action, token) {
        if (!root.surfaceHost || !root.surfaceHost.gameEngineKeybinding)
            return
        root.applyRaw(root.surfaceHost.gameEngineKeybinding(
            String(action || ""),
            String(token || "")
        ))
        root.bindingCaptureAction = ""
        root.pressedTokens = ({})
        root.updateInputStates()
    }

    function resetKeybindings() {
        if (root.surfaceHost && root.surfaceHost.gameEngineKeybindingsReset)
            root.applyRaw(root.surfaceHost.gameEngineKeybindingsReset())
        root.bindingCaptureAction = ""
        root.pressedTokens = ({})
        root.updateInputStates()
    }

    function toggleAddon(addonId, currentlyEnabled) {
        if (root.surfaceHost && root.surfaceHost.gameEngineAddon)
            root.applyRaw(root.surfaceHost.gameEngineAddon(
                String(addonId || ""),
                !Boolean(currentlyEnabled)
            ))
    }

    function addonEnabled(addonId) {
        var rows = root.addonState.addons || []
        for (var index = 0; index < rows.length; ++index) {
            if (String(rows[index].id || "") === String(addonId || ""))
                return Boolean(rows[index].enabled)
        }
        return false
    }

    function bindingRows() {
        return [
            { id: "MOVE_FORWARD", label: "MOVE FORWARD" },
            { id: "MOVE_BACK", label: "MOVE BACK" },
            { id: "TURN_LEFT", label: "TURN LEFT" },
            { id: "TURN_RIGHT", label: "TURN RIGHT" },
            { id: "STRAFE_LEFT", label: "STRAFE LEFT" },
            { id: "STRAFE_RIGHT", label: "STRAFE RIGHT" },
            { id: "JUMP", label: "JUMP" },
            { id: "SPRINT", label: "SPRINT" },
            { id: "VERTICAL_UP", label: "SWIM / FLY UP" },
            { id: "VERTICAL_DOWN", label: "SWIM / FLY DOWN" },
            { id: "ABILITY_SURGE", label: "ABILITY SURGE" },
            { id: "ABILITY_UNDERTOW", label: "ABILITY UNDERTOW" },
            { id: "ABILITY_SKY_LEAP", label: "ABILITY SKY LEAP" },
        ]
    }

    function setKeyState(key, pressed) {
        var token = root.keyToken(key)
        if (!token)
            return false

        // The UI captures the next physical key, just like a conventional
        // WoW keybinding screen.  Capture happens before gameplay actions so
        // a requested rebind never also turns, strafes or fires an ability.
        if (pressed && root.bindingCaptureAction !== "") {
            root.rebindKey(root.bindingCaptureAction, token)
            return true
        }

        root.pressedTokens[token] = Boolean(pressed)
        if (pressed && key === Qt.Key_1) {
            root.setMovementMode("GROUND")
            return true
        }
        if (pressed && key === Qt.Key_2) {
            root.setMovementMode("SWIM")
            return true
        }
        if (pressed && key === Qt.Key_3) {
            root.setMovementMode("FLY")
            return true
        }
        if (root.isActionBound("ABILITY_SURGE", token)) {
            if (pressed)
                root.useAbility("ability.surge")
            return true
        }
        if (root.isActionBound("ABILITY_UNDERTOW", token)) {
            if (pressed)
                root.useAbility("ability.undertow")
            return true
        }
        if (root.isActionBound("ABILITY_SKY_LEAP", token)) {
            if (pressed)
                root.useAbility("ability.sky_leap")
            return true
        }

        var movementAction = root.isActionBound("MOVE_FORWARD", token)
            || root.isActionBound("MOVE_BACK", token)
            || root.isActionBound("TURN_LEFT", token)
            || root.isActionBound("TURN_RIGHT", token)
            || root.isActionBound("STRAFE_LEFT", token)
            || root.isActionBound("STRAFE_RIGHT", token)
            || root.isActionBound("JUMP", token)
            || root.isActionBound("SPRINT", token)
            || root.isActionBound("VERTICAL_UP", token)
            || root.isActionBound("VERTICAL_DOWN", token)
        if (!movementAction)
            return false
        root.updateInputStates()
        root.sendInput()
        return true
    }

    focus: true
    activeFocusOnTab: true

    Timer {
        id: refreshTimer
        interval: root.renderUpdateIntervalMs
        repeat: true
        running: root.paneLive
            && root.surfaceHost !== null
            && (root.running || root.replaying)
        onTriggered: root.refreshRender()
    }

    Timer {
        id: statusRefreshTimer
        interval: root.statusUpdateIntervalMs
        repeat: true
        running: root.paneLive
            && root.surfaceHost !== null
            && (root.running || root.replaying)
        onTriggered: root.refresh()
    }

    Component.onCompleted: {
        if (!root.paneLive)
            return
        root.refresh()
        root.forceActiveFocus()
    }

    onPageChanged: root.refresh()
    onVisibleChanged: {
        if (visible && root.paneLive) {
            root.refresh()
            root.forceActiveFocus()
        } else if (!visible) {
            root.suspendRuntime()
        }
    }

    onPaneLiveChanged: {
        if (root.paneLive) {
            if (root.resumeWhenShown)
                root.startRuntime()
            root.resumeWhenShown = false
            root.refresh()
            root.refreshRender()
            root.forceActiveFocus()
        } else {
            root.resumeWhenShown = root.running
            root.suspendRuntime()
        }
    }

    function suspendRuntime() {
        if (root.running)
            root.pauseRuntime()
    }

    // The workspace keeps this surface loaded after the first visit.
    // Hidden tabs must still stop the render timers and the host tick.
    Component.onDestruction: root.suspendRuntime()

    Keys.onPressed: function(event) {
        if (event.isAutoRepeat)
            return
        if (root.setKeyState(event.key, true))
            event.accepted = true
    }

    Keys.onReleased: function(event) {
        if (event.isAutoRepeat)
            return
        if (root.setKeyState(event.key, false))
            event.accepted = true
    }

    Rectangle {
        anchors.fill: parent
        color: "#161616"
        border.color: root.frameBorder
        border.width: 1
        radius: root.frameRadius
        antialiasing: false
    }

    Item {
        id: chrome
        anchors.fill: parent
        anchors.leftMargin: 10
        anchors.rightMargin: 12
        anchors.topMargin: 9
        anchors.bottomMargin: 9

        Rectangle {
            id: toolbar
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 34
            color: root.panelOverlayRaised
            border.color: "#333333"
            border.width: 1

            Text {
                anchors.left: parent.left
                anchors.leftMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                text: "GG / GAME ENGINE · LOCAL PLAYGROUND"
                color: root.ledgerGold
                font.family: "monospace"
                font.pixelSize: 11
            }

            Row {
                anchors.right: parent.right
                anchors.rightMargin: 10
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6

                GgButton {
                    objectName: "gameEnginePlayButton"
                    text: root.running ? "PAUSE" : "PLAY"
                    implicitWidth: 66
                    implicitHeight: 25
                    checked: root.running
                    onClicked: root.running
                        ? root.pauseRuntime()
                        : root.startRuntime()
                }

                GgButton {
                    text: "RESET"
                    implicitWidth: 62
                    implicitHeight: 25
                    onClicked: root.resetRuntime()
                }

                GgButton {
                    text: "BURST"
                    implicitWidth: 62
                    implicitHeight: 25
                    onClicked: root.burstRuntime()
                }
            }
        }

        Item {
            id: body
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: toolbar.bottom
            anchors.bottom: parent.bottom
            anchors.topMargin: 8

            Rectangle {
                id: sidebar
                objectName: "gameEngineSidebar"
                z: 30
                anchors.left: parent.left
                anchors.top: parent.top
                width: root.leftMenuCollapsed ? 34 : 124
                height: root.leftMenuCollapsed
                    ? 49
                    : 16 + 25 + 3 + root.nav.length * 29
                        + Math.max(0, root.nav.length - 1) * 3
                color: root.panelOverlay
                border.color: "#46504f"
                border.width: 1

                Column {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 8
                    spacing: 3

                    Rectangle {
                        id: leftMenuToggle
                        objectName: "gameEngineLeftMenuToggle"
                        width: parent.width
                        height: 25
                        color: root.leftMenuCollapsed
                            ? root.selectedPanel : "transparent"
                        border.color: root.leftMenuCollapsed
                            ? "#5f646a" : "transparent"
                        border.width: 1

                        Text {
                            anchors.fill: parent
                            text: root.leftMenuCollapsed ? "›" : "☰"
                            color: root.ink
                            font.pixelSize: root.leftMenuCollapsed ? 18 : 16
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.leftMenuCollapsed =
                                !root.leftMenuCollapsed
                        }
                    }

                    Repeater {
                        model: root.leftMenuCollapsed ? [] : root.nav

                        delegate: Rectangle {
                            required property string modelData
                            width: parent.width
                            height: 29
                            radius: 2
                            color: root.page === modelData
                                ? root.selectedPanel
                                : "transparent"
                            border.color: root.page === modelData
                                ? "#5f646a"
                                : "transparent"
                            border.width: 1

                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 10
                                anchors.verticalCenter: parent.verticalCenter
                                text: parent.modelData
                                color: root.page === parent.modelData
                                    ? root.ink
                                    : root.text
                                font.family: "monospace"
                                font.pixelSize: 11
                                font.bold: root.page === parent.modelData
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    root.page = parent.modelData
                                    root.forceActiveFocus()
                                }
                            }
                        }
                    }
                }

            }

            Rectangle {
                id: engineRail
                objectName: "gameEngineEngineRail"
                z: 30
                anchors.left: sidebar.left
                anchors.bottom: parent.bottom
                width: sidebar.width
                height: root.leftMenuCollapsed ? 36 : 72
                color: root.panelOverlay
                border.color: "#46504f"
                border.width: 1

                Text {
                    anchors.centerIn: parent
                    visible: root.leftMenuCollapsed
                    text: "E"
                    color: root.ledgerGreen
                    font.family: "monospace"
                    font.pixelSize: 13
                    font.bold: true
                }

                Column {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 10
                    spacing: 4
                    visible: !root.leftMenuCollapsed

                    Text {
                        text: "ENGINE"
                        color: root.ledgerGreen
                        font.family: "monospace"
                        font.pixelSize: 12
                        font.bold: true
                    }
                    Text {
                        width: parent.width
                        text: "BOUNDED\nLOCAL\nDETERMINISTIC"
                        color: root.muted
                        font.family: "monospace"
                        font.pixelSize: 10
                        lineHeight: 1.1
                    }
                }
            }

            Item {
                id: stage
                objectName: "gameEngineStage"
                anchors.fill: parent

                View3D {
                    id: view3d
                    anchors.fill: parent
                    // Hiding the rich renderer is presentation-only.  The
                    // fixed-step host keeps producing the same entity/item/
                    // NPC rows for the DOS canvas below.
                    visible: !root.dosFallbackActive && root.paneLive
                    camera: camera
                    environment: SceneEnvironment {
                        // Jak/Sly/Fable coastal daylight: a readable cyan
                        // sky, not a crushed black void.  Presentation only;
                        // the simulation sea level and biomes stay the same.
                        clearColor: "#7eb7d2"
                        backgroundMode: SceneEnvironment.Color
                        antialiasingMode: root.render.profile === "POTATO"
                            ? SceneEnvironment.NoAA
                            : (root.render.profile === "CINEMATIC"
                                ? SceneEnvironment.SSAA : SceneEnvironment.MSAA)
                        antialiasingQuality: root.render.profile === "CINEMATIC"
                            ? SceneEnvironment.VeryHigh
                            : (root.render.profile === "MODERN"
                                ? SceneEnvironment.High : SceneEnvironment.Medium)
                        temporalAAEnabled: root.render.profile === "MODERN"
                            || root.render.profile === "CINEMATIC"
                        temporalAAStrength: root.render.profile === "CINEMATIC" ? 0.85 : 0.55
                        tonemapMode: SceneEnvironment.TonemapModeFilmic
                        aoEnabled: root.render.profile !== "POTATO"
                        aoStrength: root.render.profile === "CINEMATIC" ? 0.32 : 0.14
                    }

                    PerspectiveCamera {
                        id: camera
                        position: Qt.vector3d(
                            root.number(root.player.x, 0)
                                + Math.sin(root.orbitYaw * Math.PI / 180)
                                    * root.cameraDistance
                                    * (root.cinematic.preset === "ORBIT_WORLD_SCALE" ? 2.2 : 1),
                            root.number(root.player.y, 0)
                                - Math.sin(root.orbitPitch * Math.PI / 180)
                                    * root.cameraDistance
                                    * (root.cinematic.preset === "ORBIT_WORLD_SCALE" ? 2.2 : 1),
                            root.number(root.player.z, 0)
                                + Math.cos(root.orbitYaw * Math.PI / 180)
                                    * root.cameraDistance
                                    * (root.cinematic.preset === "ORBIT_WORLD_SCALE" ? 2.2 : 1)
                        )
                        eulerRotation: Qt.vector3d(
                            root.cinematic.preset === "ORBIT_WORLD_SCALE"
                                ? -42 : root.orbitPitch,
                            root.orbitYaw,
                            0
                        )
                        clipNear: root.number(
                            root.world.camera
                                ? root.world.camera.clip_near_m : 0.1,
                            0.1
                        )
                        clipFar: root.cinematic.preset === "ORBIT_WORLD_SCALE"
                            ? Math.max(
                                640,
                                root.number(
                                    root.world.camera
                                        ? root.world.camera.clip_far_m : 360,
                                    360
                                )
                            )
                            : (root.render.profile === "CINEMATIC"
                                ? Math.max(
                                    root.streamCoverageSize * 2.5,
                                    root.number(
                                        root.world.camera
                                            ? root.world.camera.clip_far_m : 360,
                                        360
                                    )
                                )
                                : 240)
                    }

                    DirectionalLight {
                        objectName: "gameKeyLight"
                        eulerRotation: Qt.vector3d(-58, 42, 0)
                        brightness: 1.22
                        color: "#ffe3b0"
                        castsShadow: root.shadowMappingEnabled
                        shadowMapQuality: root.render.profile === "CINEMATIC"
                            ? Light.ShadowMapQualityHigh
                            : Light.ShadowMapQualityMedium
                        shadowMapFar: root.render.profile === "CINEMATIC"
                            ? Math.max(root.streamCoverageSize * 1.5, 180)
                            : 80
                        shadowFactor: 32
                    }

                    DirectionalLight {
                        objectName: "gameSkyFillLight"
                        eulerRotation: Qt.vector3d(-18, -135, 0)
                        brightness: 0.55
                        color: "#9fd4ee"
                        castsShadow: false
                    }

                    PointLight {
                        position: Qt.vector3d(
                            root.number(root.player.x, 0),
                            root.number(root.player.y, 0) + 16,
                            root.number(root.player.z, 0) + 5
                        )
                        brightness: 4.2
                        color: "#ffc27a"
                        quadraticFade: 0.008
                        // A point-light shadow map costs six render passes;
                        // the directional light above owns the scene shadow.
                        castsShadow: false
                    }

                    // One material object per look, not one per Model.  Same
                    // sun, same albedo; the Repeater must not allocate a new
                    // PBR material for every palm, hut and terrain cell.
                    PrincipledMaterial {
                        id: clayPropMaterial
                        objectName: "gameClayPropMaterial"
                        baseColor: "#ffffff"
                        vertexColorsEnabled: true
                        roughness: 0.52
                        metalness: 0.02
                        specularAmount: 0.34
                    }
                    PrincipledMaterial {
                        id: clayCharacterMaterial
                        objectName: "gameClayCharacterMaterial"
                        baseColor: "#fff6e8"
                        vertexColorsEnabled: true
                        roughness: 0.48
                        metalness: 0.0
                        specularAmount: 0.42
                    }
                    PrincipledMaterial {
                        id: islandTerrainMaterial
                        baseColor: "#c2d15a"
                        roughness: 0.9
                        metalness: 0.02
                    }
                    PrincipledMaterial {
                        id: landTerrainMaterial
                        baseColor: "#7eab46"
                        roughness: 0.9
                        metalness: 0.02
                    }
                    PrincipledMaterial {
                        id: cliffTerrainMaterial
                        baseColor: "#d2b17a"
                        roughness: 0.9
                        metalness: 0.02
                    }
                    PrincipledMaterial {
                        id: reefTerrainMaterial
                        baseColor: "#2f9d8c"
                        roughness: 0.9
                        metalness: 0.02
                    }
                    PrincipledMaterial {
                        id: shallowTerrainMaterial
                        baseColor: "#1a7a8c"
                        roughness: 0.76
                        metalness: 0.05
                    }
                    PrincipledMaterial {
                        id: deepTerrainMaterial
                        baseColor: "#0f5364"
                        roughness: 0.76
                        metalness: 0.05
                    }
                    PrincipledMaterial {
                        id: seaPlaneMaterial
                        baseColor: "#1f8aa2"
                        roughness: 0.22
                        metalness: 0.04
                        specularAmount: 0.55
                    }
                    PrincipledMaterial {
                        id: coverageSlabMaterial
                        baseColor: "#111719"
                        roughness: 0.92
                    }
                    PrincipledMaterial {
                        id: coverageStripMaterial
                        baseColor: "#252a2d"
                        roughness: 0.85
                    }

                    Model {
                        source: root.lowPolySphereGeometry ? "" : "#Cube"
                        geometry: root.lowPolySphereGeometry
                        visible: root.cinematic.preset === "ORBIT_WORLD_SCALE"
                        position: Qt.vector3d(
                            root.number(root.player.x, 0),
                            root.number(root.player.y, 0) - 6,
                            root.number(root.player.z, 0)
                        )
                        scale: Qt.vector3d(0.58, 0.58, 0.58)
                        materials: [
                            PrincipledMaterial {
                                baseColor: "#1d3944"
                                roughness: 0.96
                                metalness: 0.02
                            }
                        ]
                    }

                    Model {
                        source: "#Cube"
                        visible: root.cinematic.preset !== "ORBIT_WORLD_SCALE"
                        position: Qt.vector3d(0, -0.3, 0)
                        scale: Qt.vector3d(
                            root.streamCoverageSize * root.sceneScale,
                            0.1 * root.sceneScale,
                            root.streamCoverageSize * root.sceneScale
                        )
                        castsShadows: false
                        receivesShadows: false
                        materials: [coverageSlabMaterial]
                    }

                    Model {
                        source: "#Cube"
                        visible: root.cinematic.preset !== "ORBIT_WORLD_SCALE"
                        position: Qt.vector3d(0, -0.22, 0)
                        scale: Qt.vector3d(
                            3.1 * root.sceneScale,
                            0.06 * root.sceneScale,
                            root.streamCoverageSize * root.sceneScale
                        )
                        castsShadows: false
                        receivesShadows: false
                        materials: [coverageStripMaterial]
                    }

                    Model {
                        id: waterSurface
                        source: "#Cube"
                        visible: root.cinematic.preset !== "ORBIT_WORLD_SCALE"
                            && Boolean(root.terrain.water)
                        position: Qt.vector3d(
                            root.number(root.player.x, 0),
                            root.number(root.terrain.water
                                ? root.terrain.water.sea_level_m : 0, 0),
                            root.number(root.player.z, 0)
                        )
                        scale: Qt.vector3d(
                            root.streamCoverageSize * root.sceneScale,
                            0.025 * root.sceneScale,
                            root.streamCoverageSize * root.sceneScale
                        )
                        castsShadows: false
                        receivesShadows: false
                        materials: [seaPlaneMaterial]
                    }

                    Repeater3D {
                        model: terrainRenderModel

                        delegate: Model {
                            id: terrainModel
                            objectName: "terrainPatchModel"
                            required property var terrainRow
                            property var modelData: terrainModel.terrainRow
                            property var center: terrainModel.modelData.center_m || ({})
                            property var bounds: terrainModel.modelData.bounds_m || ({})
                            property int vertexGrid: Math.max(
                                1,
                                Math.floor(root.number(
                                    terrainModel.modelData.geometry
                                        ? terrainModel.modelData.geometry.vertex_grid
                                        : 1,
                                    1
                                ))
                            )
                            property var patchGeometry: {
                                // Reading the grid makes this binding refresh
                                // when an authored patch changes in place.
                                var heightGrid = terrainModel.modelData.height_grid_m
                                var key = String(terrainModel.modelData.key || "")
                                var revision = root.terrainGeometryRevision
                                if (!heightGrid
                                    || terrainModel.vertexGrid <= 1
                                    || !key
                                    || revision < 0
                                    || !root.surfaceHost
                                    || !root.surfaceHost.gameEngineTerrainGeometry)
                                    return null
                                return root.surfaceHost.gameEngineTerrainGeometry(key)
                            }
                            property var visibilityData:
                                terrainModel.modelData.visibility || ({})
                            property string biome: String(
                                terrainModel.modelData.biome || "LAND"
                            )
                            property bool waterCell:
                                String(terrainModel.modelData.surface || "LAND") === "WATER"
                            source: ""
                            geometry: terrainModel.patchGeometry
                            castsShadows: root.shadowMappingEnabled
                                && !terrainModel.waterCell
                                && Boolean(terrainModel.visibilityData.shadow_caster)
                            receivesShadows: root.shadowMappingEnabled
                                && Boolean(terrainModel.visibilityData.shadow_caster)
                            visible: root.cinematic.preset !== "ORBIT_WORLD_SCALE"
                                && Boolean(terrainModel.visibilityData.render)
                            position: Qt.vector3d(
                                root.number(terrainModel.bounds.min_x,
                                    root.number(terrainModel.center.x, 0)),
                                0,
                                root.number(terrainModel.bounds.min_z,
                                    root.number(terrainModel.center.z, 0))
                            )
                            materials: [
                                root.terrainMaterialFor(
                                    terrainModel.biome,
                                    terrainModel.waterCell
                                )
                            ]

                            // ORBIT cells intentionally carry no dense
                            // height grid.  They still need a real visual
                            // representation, otherwise increasing the
                            // interest radius only creates an invisible
                            // horizon.  This thin tile is the bounded HLOD
                            // representation of that authoritative cell;
                            // nearby cells continue to use the heightfield
                            // mesh above.
                            Model {
                                objectName: "terrainHlodTileModel"
                                visible: root.cinematic.preset !== "ORBIT_WORLD_SCALE"
                                    && Boolean(terrainModel.visibilityData.render)
                                    && terrainModel.vertexGrid <= 1
                                source: "#Cube"
                                position: Qt.vector3d(
                                    root.terrainCellSize * 0.5,
                                    root.number(terrainModel.center.y, 0),
                                    root.terrainCellSize * 0.5
                                )
                                scale: Qt.vector3d(
                                    root.terrainCellSize * root.sceneScale,
                                    0.025 * root.sceneScale,
                                    root.terrainCellSize * root.sceneScale
                                )
                                castsShadows: false
                                receivesShadows: root.shadowMappingEnabled
                                    && Boolean(terrainModel.visibilityData.shadow_caster)
                                materials: [
                                    root.terrainMaterialFor(
                                        terrainModel.biome,
                                        terrainModel.waterCell
                                    )
                                ]
                            }
                        }
                    }

                    Model {
                        id: terrainTargetMarker
                        source: "#Cube"
                        property var targetCenter:
                            root.terrainTargetCell.center_m || ({})
                        property bool targetIsWater:
                            String(root.terrainTargetCell.surface || "LAND")
                            === "WATER"
                        visible: root.cinematic.preset !== "ORBIT_WORLD_SCALE"
                            && root.terrainTargetSelected
                            && Boolean(root.terrainTargetCell.key)
                        position: Qt.vector3d(
                            root.terrainBrushX,
                            terrainTargetMarker.targetIsWater
                                ? root.number(root.terrain.water
                                    ? root.terrain.water.sea_level_m : 0, 0)
                                    + 0.22
                                : root.number(terrainTargetMarker.targetCenter.y,
                                    0) + 0.45,
                            root.terrainBrushZ
                        )
                        scale: Qt.vector3d(
                            root.terrainBrushRadius * 2 * root.sceneScale,
                            0.16 * root.sceneScale,
                            root.terrainBrushRadius * 2 * root.sceneScale
                        )
                        materials: [
                            PrincipledMaterial {
                                baseColor: root.terrainBrushEnabled
                                    ? "#e3bd63" : "#d6e1a0"
                                roughness: 0.38
                                metalness: 0.12
                            }
                        ]
                    }

                    Repeater3D {
                        model: entityRenderModel

                        delegate: Node {
                            id: entityModel
                            objectName: "gameEntityFigure"
                            required property var entityRow
                            required property var entityDynamic
                            property var modelData: entityModel.entityRow
                            property var dynamicData:
                                entityModel.entityDynamic || entityModel.entityRow
                            property string entityKind: String(
                                entityModel.modelData.kind || "PROP"
                            )
                            property color tint: String(
                                entityModel.modelData.color || "#8fa8a0"
                            )
                            property bool characterLike: entityModel.entityKind === "PLAYER"
                                || entityModel.entityKind === "NPC"
                                || entityModel.entityKind === "ACTOR"
                                || entityModel.entityKind.indexOf("NPC") >= 0
                            property real entitySx: Math.max(
                                0.35,
                                root.number(entityModel.modelData.sx, 1)
                            )
                            property real entitySy: Math.max(
                                0.35,
                                root.number(entityModel.modelData.sy, 1)
                            )
                            property real entitySz: Math.max(
                                0.35,
                                root.number(entityModel.modelData.sz, 1)
                            )
                            property real characterYScale: Math.max(
                                0.9,
                                Math.min(1.25, entityModel.entitySy)
                            )
                            property var entityPose: entityModel.dynamicData.animation
                                || ({})
                            property var entityAsset: entityModel.modelData.asset
                                || ({})
                            property var entityAssetMotion:
                                entityModel.dynamicData.asset
                                || entityModel.entityAsset
                                || ({})
                            property bool proceduralCharacter:
                                entityModel.characterLike
                                && String(
                                    entityModel.entityAsset.mode || ""
                                ) === "PROCEDURAL_GEOMETRY"
                            property var itemState: entityModel.dynamicData.item
                                || ({})
                            property var itemVisual: entityModel.itemState.visual
                                || ({})
                            property var itemAsset: entityModel.itemState.asset
                                || ({})
                            property bool itemLike: entityModel.entityKind === "GROUND_ITEM"
                                || entityModel.entityKind === "CHEST"
                            // All non-authored item families resolve to one
                            // cached native clay mesh. The geometry key is
                            // data-driven by the item table, not by a QML
                            // primitive name, so a weapon/chest/loot object
                            // cannot silently regress to a cube.
                            property var itemGeometry:
                                entityModel.itemLike
                                && root.surfaceHost
                                && typeof root.surfaceHost
                                    .gameEngineItemGeometry === "function"
                                    ? root.surfaceHost.gameEngineItemGeometry(
                                        String(
                                            entityModel.itemAsset.geometry_key
                                                || entityModel.itemVisual.asset_id
                                                || "item.unknown"
                                        ),
                                        String(
                                            entityModel.itemAsset.asset_class
                                                || entityModel.itemState.kind
                                                || entityModel.entityKind
                                        )
                                    ) : null
                            property bool authoredWorldProp:
                                !entityModel.characterLike
                                && !entityModel.itemLike
                                && String(entityModel.entityAsset.mode || "")
                                    === "AUTHORED_STATIC"
                                && String(entityModel.entityAsset.source || "") !== ""
                            property string authoredWorldSource: {
                                var uri = String(entityModel.entityAsset.source || "")
                                if (uri.indexOf("file:") === 0 || uri.indexOf("/") === 0)
                                    return uri
                                var relative = String(
                                    entityModel.entityAsset.relative_source || ""
                                )
                                if (relative.length > 0)
                                    return Qt.resolvedUrl("../" + relative)
                                return uri
                            }
                            property var authoredWorldRuntimeLoader:
                                authoredWorldLoader.item || null
                            property bool authoredWorldVisible:
                                entityModel.authoredWorldProp
                                && !Boolean(entityModel.worldPropGeometry)
                                && root.runtimeLoaderHasVisualContent(
                                    entityModel.authoredWorldRuntimeLoader
                                )
                            property var worldPropGeometry:
                                !entityModel.characterLike
                                && !entityModel.itemLike
                                && root.surfaceHost
                                && typeof root.surfaceHost
                                    .gameEngineWorldPropGeometry === "function"
                                ? root.surfaceHost.gameEngineWorldPropGeometry(
                                    String(
                                        entityModel.entityAsset.geometry_key
                                            || entityModel.entityKind
                                    ),
                                    String(
                                        entityModel.entityAsset.variant
                                            !== undefined
                                            ? entityModel.entityAsset.variant
                                            : (entityModel.modelData.id || "0")
                                    )
                                ) : null
                            // QtQuick3D resolves Model.source once during
                            // delegate construction.  The host is attached
                            // immediately after the root is created, so the
                            // first evaluation may still be the primitive
                            // path even though the cache is already ready.
                            // Apply the real geometry at the change boundary
                            // as well; this is a presentation binding only
                            // and never creates a second visual object.
                            function applyNativeGeometry(model, geometry) {
                                if (!model || !geometry)
                                    return
                                model.source = ""
                                model.geometry = geometry
                            }
                            onItemGeometryChanged: {
                                if (itemGeometry)
                                    entityModel.applyNativeGeometry(
                                        gameWorldItemModel,
                                        itemGeometry
                                    )
                            }
                            onWorldPropGeometryChanged: {
                                if (worldPropGeometry)
                                    entityModel.applyNativeGeometry(
                                        gameEntityProxyModel,
                                        worldPropGeometry
                                    )
                            }
                            property string lodTier: String(
                                entityModel.dynamicData.lod || "NEAR"
                            )
                            property var equipment: entityModel.modelData.equipment
                                || []
                            property var equippedVisual: entityModel.equipment.length > 0
                                && entityModel.equipment[0]
                                ? (entityModel.equipment[0].visual || ({}))
                                : ({})
                            // A desktop process that was opened before the
                            // authored hero promotion can still carry the
                            // old fixture URI in its in-memory snapshot.
                            // Redirect only that historical URI to the
                            // canonical Blender asset while the process is
                            // alive.  The backend contract remains the
                            // authority on eligibility, rank and animation;
                            // this is a source migration, not a second body
                            // or a presentation fallback.
                            property string authoredCharacterSource: {
                                var source = String(
                                    entityModel.entityAsset.source || ""
                                )
                                if (source.indexOf("gg-authored-hero.gltf") >= 0)
                                    return Qt.resolvedUrl(
                                        "../assets/authored/gg-clay-hero-a.glb"
                                    )
                                return source
                            }
                            property bool authoredAssetEligible:
                                entityModel.characterLike
                                && (
                                    String(entityModel.entityAsset.mode || "")
                                        === "AUTHORED_SKINNED"
                                    || String(entityModel.entityAsset.mode || "")
                                        === "AUTHORED_NODE_ANIMATED"
                                )
                                && String(entityModel.entityAsset.source || "")
                                    !== ""
                                && root.number(
                                    entityModel.entityAsset.instance_rank,
                                    -1
                                ) >= 0
                                && root.number(
                                    entityModel.entityAsset.instance_rank,
                                    -1
                                ) < root.number(
                                    entityModel.entityAsset.instance_budget,
                                    root.assetInstanceBudget
                                )
                            property bool authoredItemEligible:
                                entityModel.itemLike
                                && String(entityModel.itemAsset.mode || "")
                                    === "AUTHORED_STATIC"
                                && String(entityModel.itemAsset.source || "")
                                    !== ""
                                && root.number(
                                    entityModel.itemAsset.instance_rank,
                                    -1
                                ) >= 0
                                && root.number(
                                    entityModel.itemAsset.instance_rank,
                                    -1
                                ) < root.number(
                                    entityModel.itemAsset.instance_budget,
                                    0
                                )
                            property string authoredAssetClipStatus: String(
                                entityModel.entityAssetMotion.clip_status
                                    || entityModel.entityAsset.clip_status
                                    || "NOT_LOADED"
                            )
                            property string authoredAssetClip: String(
                                entityModel.entityAssetMotion.clip
                                    || entityModel.entityAsset.clip
                                    || ""
                            )
                            property string authoredAssetRuntimeClip: String(
                                entityModel.entityAssetMotion.runtime_clip
                                    || entityModel.entityAsset.runtime_clip
                                    || entityModel.authoredAssetClip
                                    || ""
                            )
                            property string requestedAuthoredClip: String(
                                root.authoredClipForMotionState(
                                    entityModel.entityPose.state || "IDLE"
                                )
                            )
                            property bool authoredAssetVisualContent:
                                entityModel.authoredAssetEligible
                                && root.runtimeLoaderHasVisualContent(
                                    entityModel.authoredAssetRuntimeLoader
                                )
                            property bool authoredAssetVisible:
                                entityModel.authoredAssetVisualContent
                                && (
                                    entityModel.authoredAssetClipStatus
                                        === "ROOT_POSE_ONLY"
                                    || (
                                        entityModel.authoredAssetClipStatus
                                            === "READY"
                                        && entityModel.authoredAssetClip
                                            === entityModel.requestedAuthoredClip
                                    )
                                )
                            property bool characterFallbackVisible:
                                entityModel.characterLike
                                && !entityModel.authoredAssetVisible
                            // Keep one native body geometry for the complete
                            // lifetime of this delegate.  The fixed-step
                            // animation contract still supplies state,
                            // phase, bob, lean, sway and squash below, but a
                            // live QtQuick3D Model must not swap its geometry
                            // object whenever WALK crosses a pose bucket.
                            // Such swaps can detach the vertex buffer during
                            // a render pass: the entity remains in the
                            // snapshot and its head/other props can remain,
                            // while the body disappears.  Pose variation is
                            // therefore represented by the deterministic
                            // transforms, not by replacing the mesh.
                            property var characterPoseGeometry:
                                entityModel.characterLike
                                ? root.characterGeometryForCast(
                                    entityModel.modelData.cast
                                        || entityModel.modelData.archetype
                                        || (
                                            entityModel.entityKind === "PLAYER"
                                                ? "PLAYER"
                                                : "CROWD"
                                        )
                                )
                                : null
                            property bool authoredItemVisible:
                                entityModel.authoredItemEligible
                                && root.runtimeLoaderHasVisualContent(
                                    entityModel.authoredItemRuntimeLoader
                                )
                            property var authoredAssetRuntimeLoader:
                                authoredAssetLoader.item || null
                            property var authoredItemRuntimeLoader:
                                authoredItemLoader.item || null
                            property int authoredSocketRevision: 0
                            property real poseBob: root.number(
                                entityModel.entityPose.bob_m, 0
                            )
                            property real poseLean: root.number(
                                entityModel.entityPose.lean_deg, 0
                            )
                            property real poseSway: root.number(
                                entityModel.entityPose.sway_deg, 0
                            )
                            property real poseSquash: root.number(
                                entityModel.entityPose.squash, 0
                            )
                            function applyAuthoredRuntimeClip() {
                                if (!entityModel.authoredAssetEligible
                                    || !entityModel.authoredAssetRuntimeLoader
                                    || !root.surfaceHost
                                    || typeof root.surfaceHost.gameEngineRuntimeClip
                                        !== "function")
                                    return
                                root.surfaceHost.gameEngineRuntimeClip(
                                    entityModel.authoredAssetRuntimeLoader,
                                    String(
                                        entityModel.authoredAssetRuntimeClip
                                            || ""
                                    )
                                )
                            }
                            onAuthoredAssetVisibleChanged:
                                entityModel.applyAuthoredRuntimeClip()
                            onAuthoredAssetClipChanged:
                                entityModel.applyAuthoredRuntimeClip()
                            onAuthoredAssetRuntimeClipChanged:
                                entityModel.applyAuthoredRuntimeClip()
                            Connections {
                                target: entityModel.authoredAssetRuntimeLoader
                                function onStatusChanged() {
                                    entityModel.applyAuthoredRuntimeClip()
                                    entityModel.authoredSocketRevision += 1
                                }
                            }
                            position: Qt.vector3d(
                                root.number(entityModel.dynamicData.x, 0),
                                root.number(entityModel.dynamicData.y, 0),
                                root.number(entityModel.dynamicData.z, 0)
                            )
                            eulerRotation.y:
                                root.number(entityModel.dynamicData.yaw, 0)
                                * 57.2958
                            // One native geometry slot serves each prop and
                            // ramp. Item fallbacks keep their named model
                            // below so the asset test and authored handoff
                            // remain explicit. This removes one hidden Model
                            // from every mixed entity delegate.
                            Model {
                                id: gameEntityProxyModel
                                objectName: "gameEntityProxyModel"
                                // ORBIT is a presentation LOD, not a vanish
                                // distance. Keep this single cheap primitive
                                // alive until Qt's camera frustum/clip plane
                                // removes it at the actual horizon.
                                visible: !entityModel.characterLike
                                    && !entityModel.itemLike
                                    && !entityModel.authoredWorldVisible
                                property bool usesNativeGeometry:
                                    Boolean(entityModel.worldPropGeometry)
                                property bool usesLowPolySphere:
                                    !Boolean(entityModel.worldPropGeometry)
                                    && entityModel.entityKind !== "RAMP"
                                source: entityModel.worldPropGeometry
                                    ? ""
                                    : (Boolean(root.lowPolySphereGeometry)
                                    && entityModel.entityKind !== "RAMP"
                                    && root.lowPolySphereGeometry
                                    ? ""
                                    : "#Cube")
                                geometry: entityModel.worldPropGeometry
                                    ? entityModel.worldPropGeometry
                                    : (Boolean(root.lowPolySphereGeometry)
                                        && entityModel.entityKind !== "RAMP"
                                        ? root.lowPolySphereGeometry : null)
                                position: Qt.vector3d(0, 0, 0)
                                eulerRotation.x: entityModel.entityKind === "RAMP"
                                    ? -12 : 0
                                scale: Qt.vector3d(
                                    entityModel.entitySx * (entityModel.worldPropGeometry ? 1 : root.sceneScale),
                                    entityModel.entitySy * (entityModel.worldPropGeometry ? 1 : root.sceneScale),
                                    entityModel.entitySz * (entityModel.worldPropGeometry ? 1 : root.sceneScale)
                                )
                                castsShadows: root.shadowMappingEnabled
                                receivesShadows: root.shadowMappingEnabled
                                materials: [clayPropMaterial]
                            }

                            Component {
                                id: authoredWorldComponent
                                RuntimeLoader {
                                    objectName: "gameAuthoredWorldLoader"
                                    source: entityModel.authoredWorldSource
                                    visible: true
                                }
                            }
                            Loader3D {
                                id: authoredWorldLoader
                                objectName: "gameAuthoredWorldLoaderHost"
                                active: entityModel.authoredWorldProp
                                    && !Boolean(entityModel.worldPropGeometry)
                                asynchronous: false
                                sourceComponent: authoredWorldComponent
                                visible: entityModel.authoredWorldVisible
                                position: Qt.vector3d(
                                    0,
                                    String(entityModel.entityAsset.anchor || "") === "FEET"
                                        ? -entityModel.entitySy
                                        : 0,
                                    0
                                )
                                scale: {
                                    var height = Math.max(
                                        0.5,
                                        root.number(
                                            entityModel.entityAsset.height_m,
                                            4.16
                                        )
                                    )
                                    return Qt.vector3d(
                                        entityModel.entitySx,
                                        (2.0 * entityModel.entitySy) / height,
                                        entityModel.entitySz
                                    )
                                }
                            }

                            // Every world item has a real native 3D state. The
                            // item definition selects a cached family mesh,
                            // rarity material and a context-specific pose;
                            // ground items also receive deterministic motion.
                            Model {
                                id: gameWorldItemModel
                                objectName: "gameWorldItemModel"
                                visible: entityModel.itemLike
                                    && !entityModel.authoredItemVisible
                                property string requestedModel: String(
                                    entityModel.itemVisual.model || "#Sphere"
                                )
                                property bool usesNativeGeometry:
                                    Boolean(entityModel.itemGeometry)
                                property bool usesLowPolySphere:
                                    !Boolean(entityModel.itemGeometry)
                                    && entityModel.requestedModel === "#Sphere"
                                source: entityModel.itemGeometry
                                    ? ""
                                    : (Boolean(root.lowPolySphereGeometry)
                                    && entityModel.requestedModel === "#Sphere"
                                    && root.lowPolySphereGeometry
                                    ? ""
                                    : (entityModel.requestedModel === "#Sphere"
                                        ? "#Cube" : String(entityModel.requestedModel || "#Cube")))
                                geometry: entityModel.itemGeometry
                                    ? entityModel.itemGeometry
                                    : (Boolean(root.lowPolySphereGeometry)
                                        && entityModel.requestedModel === "#Sphere"
                                        ? root.lowPolySphereGeometry : null)
                                position: Qt.vector3d(
                                    0,
                                    root.number(
                                        entityModel.itemVisual.offset_y,
                                        0.16
                                    ) + root.number(
                                        entityModel.itemVisual.bob_m,
                                        0
                                    ),
                                    0
                                )
                                eulerRotation: Qt.vector3d(
                                    root.number(
                                        entityModel.itemVisual.rotation
                                            ? entityModel.itemVisual.rotation[0] : 0,
                                        0
                                    ),
                                    root.number(entityModel.itemVisual.rotation_y, 0),
                                    root.number(
                                        entityModel.itemVisual.rotation
                                            ? entityModel.itemVisual.rotation[2] : 0,
                                        0
                                    )
                                )
                                scale: Qt.vector3d(
                                    root.number(
                                        entityModel.itemVisual.scale
                                            ? entityModel.itemVisual.scale[0] : 0.16,
                                        0.16
                                        ) * entityModel.entitySx * (entityModel.itemGeometry ? 1 : root.sceneScale),
                                    root.number(
                                        entityModel.itemVisual.scale
                                            ? entityModel.itemVisual.scale[1] : 0.16,
                                        0.16
                                        ) * entityModel.entitySy * (entityModel.itemGeometry ? 1 : root.sceneScale),
                                    root.number(
                                        entityModel.itemVisual.scale
                                            ? entityModel.itemVisual.scale[2] : 0.16,
                                        0.16
                                        ) * entityModel.entitySz * (entityModel.itemGeometry ? 1 : root.sceneScale)
                                )
                                castsShadows: root.shadowMappingEnabled
                                receivesShadows: root.shadowMappingEnabled
                                materials: [clayPropMaterial]
                            }

                            // Static authored item meshes take over only after
                            // the nested RuntimeLoader succeeds.  Loader3D is
                            // active only for an eligible item, so ordinary
                            // entities do not carry an empty asset loader.
                            Component {
                                id: authoredItemComponent
                                RuntimeLoader {
                                    objectName: "gameAuthoredItemLoader"
                                    source: String(
                                        entityModel.itemAsset.source || ""
                                    )
                                    visible: true
                                }
                            }
                            Loader3D {
                                id: authoredItemLoader
                                objectName: "gameAuthoredItemLoaderHost"
                                active: entityModel.authoredItemEligible
                                asynchronous: false
                                sourceComponent: authoredItemComponent
                                visible: entityModel.authoredItemVisible
                                position: Qt.vector3d(
                                    0,
                                    root.number(
                                        entityModel.itemVisual.offset_y,
                                        0.16
                                    ) + root.number(
                                        entityModel.itemVisual.bob_m,
                                        0
                                    ),
                                    0
                                )
                                eulerRotation: Qt.vector3d(
                                    root.number(
                                        entityModel.itemVisual.rotation
                                            ? entityModel.itemVisual.rotation[0] : 0,
                                        0
                                    ),
                                    root.number(entityModel.itemVisual.rotation_y, 0),
                                    root.number(
                                        entityModel.itemVisual.rotation
                                            ? entityModel.itemVisual.rotation[2] : 0,
                                        0
                                    )
                                )
                                scale: Qt.vector3d(
                                    root.number(
                                        entityModel.itemVisual.scale
                                            ? entityModel.itemVisual.scale[0] : 0.16,
                                        0.16
                                    ) * root.number(
                                        entityModel.itemAsset.unit_scale
                                            ? entityModel.itemAsset.unit_scale[0] : 1,
                                        1
                                    ) * entityModel.entitySx,
                                    root.number(
                                        entityModel.itemVisual.scale
                                            ? entityModel.itemVisual.scale[1] : 0.16,
                                        0.16
                                    ) * root.number(
                                        entityModel.itemAsset.unit_scale
                                            ? entityModel.itemAsset.unit_scale[1] : 1,
                                        1
                                    ) * entityModel.entitySy,
                                    root.number(
                                        entityModel.itemVisual.scale
                                            ? entityModel.itemVisual.scale[2] : 0.16,
                                        0.16
                                    ) * root.number(
                                        entityModel.itemAsset.unit_scale
                                            ? entityModel.itemAsset.unit_scale[2] : 1,
                                        1
                                    ) * entityModel.entitySz
                                )
                            }

                            // Authored files enter through one bounded
                            // RuntimeLoader per eligible character.  The
                            // loader inherits the entity root transform and
                            // the existing deterministic pose accents.  A
                            // missing clip is still a valid root-only
                            // authored model, so it does not summon a second
                            // character body.
                            Component {
                                id: authoredCharacterComponent
                                RuntimeLoader {
                                    objectName: "gameAuthoredAssetLoader"
                                    source: entityModel.authoredCharacterSource
                                    visible: true
                                }
                            }
                            Loader3D {
                                id: authoredAssetLoader
                                objectName: "gameAuthoredAssetLoaderHost"
                                active: entityModel.authoredAssetEligible
                                asynchronous: false
                                sourceComponent: authoredCharacterComponent
                                visible: entityModel.authoredAssetVisible
                                position: Qt.vector3d(
                                    0,
                                    root.number(
                                        entityModel.entityAsset.root_offset_m,
                                        -0.65
                                    ) + entityModel.poseBob,
                                    0
                                )
                                eulerRotation: Qt.vector3d(
                                    entityModel.poseLean,
                                    entityModel.poseSway,
                                    0
                                )
                                scale: Qt.vector3d(
                                    entityModel.entitySx,
                                    entityModel.characterYScale
                                        * (1 + entityModel.poseSquash),
                                    entityModel.entitySz
                                )
                            }

                            // The character seam is deliberately one-model
                            // wide. The imported authored model is preferred;
                            // this shared low-poly humanoid is the only
                            // fallback while it loads or fails. It receives
                            // the same fixed-step bob/lean/sway/squash
                            // contract, so no head, limbs or alternate pose
                            // geometry can survive as a second body.
                            // This is a direct Model rather than a Loader3D:
                            // Qt can retain loader children during a status
                            // transition, while this node has one identity for
                            // the whole lifetime of the entity delegate.
                            Model {
                                objectName: "gameCharacterBodyModel"
                                visible: entityModel.characterFallbackVisible
                                source: entityModel.characterPoseGeometry ? "" : "#Cube"
                                geometry: entityModel.characterPoseGeometry
                                position: Qt.vector3d(
                                    0, 0.10 + entityModel.poseBob, 0
                                )
                                eulerRotation: Qt.vector3d(
                                    entityModel.poseLean,
                                    entityModel.poseSway,
                                    0
                                )
                                scale: root.lowPolyCharacterUsesGameplayUnits
                                    ? Qt.vector3d(
                                        0.96 * entityModel.entitySx,
                                        0.90 * entityModel.characterYScale
                                            * (1 + entityModel.poseSquash),
                                        0.94 * entityModel.entitySz
                                    )
                                    : Qt.vector3d(
                                        0.68 * root.sceneScale
                                            * entityModel.entitySx,
                                        1.50 * root.sceneScale
                                            * entityModel.characterYScale
                                            * (1 + entityModel.poseSquash),
                                        0.44 * root.sceneScale
                                            * entityModel.entitySz
                                    )
                                castsShadows: root.shadowMappingEnabled
                                receivesShadows: root.shadowMappingEnabled
                                materials: [clayCharacterMaterial]
                            }

                            Repeater3D {
                                model: entityModel.entityKind === "PLAYER"
                                    ? entityModel.equipment.slice(0, 8) : []
                                delegate: Node {
                                    id: wornItem
                                    objectName: "gameEquippedItemModel"
                                    required property var modelData
                                    readonly property var visual: modelData.visual || ({})
                                    readonly property var itemAsset: modelData.asset || ({})
                                    readonly property var attachment: modelData.attachment
                                        || wornItem.visual.attachment
                                        || ({})
                                    readonly property string slot: String(modelData.equipped_slot || "")
                                    readonly property string socketId: String(
                                        wornItem.attachment.socket || wornItem.slot
                                    )
                                    readonly property string socketNodeName: String(
                                        wornItem.attachment.node
                                            || (wornItem.socketId
                                                ? "SOCKET_" + wornItem.socketId
                                                : "")
                                    )
                                    readonly property var rest: wornItem.attachment.rest || []
                                    property var socketNode: {
                                        var revision = entityModel.authoredSocketRevision
                                        if (!entityModel.authoredAssetVisible
                                            || !entityModel.authoredAssetRuntimeLoader
                                            || !wornItem.socketNodeName)
                                            return null
                                        return root.findAttachmentNode(
                                            entityModel.authoredAssetRuntimeLoader,
                                            wornItem.socketNodeName
                                        )
                                    }
                                    parent: wornItem.socketNode || entityModel
                                    property var itemGeometry:
                                        root.surfaceHost
                                        && typeof root.surfaceHost
                                            .gameEngineItemGeometry === "function"
                                        ? root.surfaceHost.gameEngineItemGeometry(
                                            String(
                                                wornItem.itemAsset.geometry_key
                                                    || wornItem.visual.asset_id
                                                    || "item.unknown"
                                            ),
                                            String(
                                                wornItem.itemAsset.asset_class
                                                    || modelData.kind
                                                    || "ITEM"
                                            )
                                        ) : null
                                    onItemGeometryChanged: {
                                        if (itemGeometry)
                                            entityModel.applyNativeGeometry(
                                                gameEquippedItemPrimitive,
                                                itemGeometry
                                            )
                                    }
                                    property bool authoredItemEligible:
                                        String(wornItem.itemAsset.mode || "")
                                            === "AUTHORED_STATIC"
                                        && String(wornItem.itemAsset.source || "") !== ""
                                    property bool authoredItemVisible:
                                        wornItem.authoredItemEligible
                                        && authoredEquippedItemLoader.status
                                            === RuntimeLoader.Success
                                    position: wornItem.socketNode
                                        ? Qt.vector3d(0, 0, 0)
                                        : Qt.vector3d(
                                            root.number(
                                                wornItem.rest[0],
                                                wornItem.slot === "MAIN_HAND"
                                                    ? 0.48
                                                    : (wornItem.slot === "OFF_HAND" ? -0.48 : 0)
                                            ),
                                            root.number(
                                                wornItem.rest[1],
                                                wornItem.slot === "HEAD"
                                                    ? 0.83
                                                    : (wornItem.slot === "CHEST"
                                                        ? 0.07
                                                        : (wornItem.slot === "BACK"
                                                            ? 0.13
                                                            : (wornItem.slot === "FEET" ? -0.61 : -0.29)))
                                            ) + entityModel.poseBob,
                                            root.number(
                                                wornItem.rest[2],
                                                wornItem.slot === "CHEST"
                                                    ? -0.16
                                                    : (wornItem.slot === "BACK" ? 0.22 : -0.04)
                                            )
                                        )
                                    eulerRotation: Qt.vector3d(
                                        root.number(visual.rotation ? visual.rotation[0] : 0, 0),
                                        root.number(visual.rotation_y, 0),
                                        root.number(visual.rotation ? visual.rotation[2] : 0, 0)
                                    )
                                    Model {
                                        id: gameEquippedItemPrimitive
                                        objectName: "gameEquippedItemPrimitive"
                                        visible: !wornItem.authoredItemVisible
                                        property string requestedModel: String(
                                            visual.model || "#Cube"
                                        )
                                        property bool usesNativeGeometry:
                                            Boolean(wornItem.itemGeometry)
                                        property bool usesLowPolySphere:
                                            !Boolean(wornItem.itemGeometry)
                                            && wornItem.requestedModel === "#Sphere"
                                        source: wornItem.itemGeometry
                                            ? ""
                                            : (Boolean(root.lowPolySphereGeometry)
                                            && wornItem.requestedModel === "#Sphere"
                                            && root.lowPolySphereGeometry
                                            ? ""
                                            : (wornItem.requestedModel === "#Sphere"
                                                ? "#Cube" : String(wornItem.requestedModel || "#Cube")))
                                        geometry: wornItem.itemGeometry
                                            ? wornItem.itemGeometry
                                            : (Boolean(root.lowPolySphereGeometry)
                                                && wornItem.requestedModel === "#Sphere"
                                                ? root.lowPolySphereGeometry : null)
                                        scale: Qt.vector3d(
                                            root.number(visual.scale ? visual.scale[0] : 0.16, 0.16) * (wornItem.itemGeometry ? 1 : root.sceneScale),
                                            root.number(visual.scale ? visual.scale[1] : 0.16, 0.16) * (wornItem.itemGeometry ? 1 : root.sceneScale),
                                            root.number(visual.scale ? visual.scale[2] : 0.16, 0.16) * (wornItem.itemGeometry ? 1 : root.sceneScale)
                                        )
                                        castsShadows: root.shadowMappingEnabled
                                        receivesShadows: root.shadowMappingEnabled
                                        materials: PrincipledMaterial {
                                            baseColor: String(
                                                wornItem.visual.base_color
                                                    || modelData.rarity_color
                                                    || "#d6d6d6"
                                            )
                                            vertexColorsEnabled: false
                                            roughness: root.number(
                                                wornItem.visual.roughness, 0.42
                                            )
                                            metalness: root.number(
                                                wornItem.visual.metalness, 0.34
                                            )
                                            emissiveFactor: Qt.vector3d(
                                                root.number(wornItem.visual.glow, 0),
                                                root.number(wornItem.visual.glow, 0) * 0.7,
                                                root.number(wornItem.visual.glow, 0) * 0.35
                                            )
                                        }
                                    }
                                    RuntimeLoader {
                                        id: authoredEquippedItemLoader
                                        objectName: "gameAuthoredEquippedItemLoader"
                                        source: wornItem.authoredItemEligible
                                            ? String(wornItem.itemAsset.source || "")
                                            : ""
                                        visible: wornItem.authoredItemVisible
                                        scale: Qt.vector3d(
                                            root.number(visual.scale ? visual.scale[0] : 0.16, 0.16) * root.number(
                                                wornItem.itemAsset.unit_scale
                                                    ? wornItem.itemAsset.unit_scale[0] : 1,
                                                1
                                            ),
                                            root.number(visual.scale ? visual.scale[1] : 0.16, 0.16) * root.number(
                                                wornItem.itemAsset.unit_scale
                                                    ? wornItem.itemAsset.unit_scale[1] : 1,
                                                1
                                            ),
                                            root.number(visual.scale ? visual.scale[2] : 0.16, 0.16) * root.number(
                                                wornItem.itemAsset.unit_scale
                                                    ? wornItem.itemAsset.unit_scale[2] : 1,
                                                1
                                            )
                                        )
                                    }
                                }
                            }
                        }
                    }

                    Repeater3D {
                        model: particleRenderModel

                        delegate: Model {
                            id: particleModel
                            required property var particleRow
                            property var modelData: particleModel.particleRow
                            property color tint: String(
                                particleModel.modelData.color || "#c8a97e"
                            )
                            source: "#Cube"
                            position: Qt.vector3d(
                                root.number(particleModel.modelData.x, 0),
                                root.number(particleModel.modelData.y, 0),
                                root.number(particleModel.modelData.z, 0)
                            )
                            scale: Qt.vector3d(
                                0.11 * root.sceneScale,
                                0.11 * root.sceneScale,
                                0.11 * root.sceneScale
                            )
                            castsShadows: false
                            receivesShadows: false
                            materials: [
                                PrincipledMaterial {
                                    baseColor: particleModel.tint
                                    roughness: 0.36
                                    metalness: 0.15
                                }
                            ]
                        }
                    }
                }

                // Terminal fallback: this layer consumes the same bounded
                // render rows as View3D.  It is deliberately a sibling of
                // the rich scene so changing presentation cannot reset, slow
                // or fork the simulation.
                Item {
                    id: dosFallbackLayer
                    objectName: "gameEngineDosFallback"
                    anchors.fill: parent
                    visible: root.dosFallbackActive
                    z: 25

                    Rectangle {
                        anchors.fill: parent
                        color: "#030604"
                        border.color: "#2f6b3b"
                        border.width: 1
                    }

                    Canvas {
                        id: dosFallbackCanvas
                        objectName: "gameEngineDosFallbackCanvas"
                        anchors.fill: parent
                        visible: root.dosFallbackActive
                        onPaint: {
                            var ctx = getContext("2d")
                            var w = width
                            var h = height
                            var palette = root.fallbackView.palette || ({})
                            var camera = root.fallbackView.camera || ({})
                            var centerX = root.number(camera.center_x, root.number(root.player.x, 0))
                            var centerZ = root.number(camera.center_z, root.number(root.player.z, 0))
                            var radius = Math.max(6, root.number(camera.radius_m, 18))
                            var scale = Math.min(w, h) * 0.42 / radius

                            ctx.clearRect(0, 0, w, h)
                            ctx.fillStyle = String(palette.background || "#030604")
                            ctx.fillRect(0, 0, w, h)
                            ctx.strokeStyle = String(palette.grid || "#173117")
                            ctx.lineWidth = 1
                            var gridStep = Math.max(18, Math.min(64, Math.min(w, h) / 12))
                            for (var gx = 0; gx <= w; gx += gridStep) {
                                ctx.beginPath()
                                ctx.moveTo(gx, 0)
                                ctx.lineTo(gx, h)
                                ctx.stroke()
                            }
                            for (var gy = 0; gy <= h; gy += gridStep) {
                                ctx.beginPath()
                                ctx.moveTo(0, gy)
                                ctx.lineTo(w, gy)
                                ctx.stroke()
                            }

                            function screenX(worldX) {
                                return w * 0.5 + (Number(worldX) - centerX) * scale
                            }
                            function screenY(worldZ) {
                                return h * 0.5 + (Number(worldZ) - centerZ) * scale
                            }

                            var terrainRows = root.fallbackView.terrain || []
                            ctx.font = "12px monospace"
                            ctx.textAlign = "center"
                            ctx.textBaseline = "middle"
                            for (var terrainIndex = 0; terrainIndex < terrainRows.length; ++terrainIndex) {
                                var terrainRow = terrainRows[terrainIndex]
                                if (!terrainRow)
                                    continue
                                var terrainX = screenX(root.number(terrainRow.x, 0))
                                var terrainY = screenY(root.number(terrainRow.z, 0))
                                if (terrainX < -20 || terrainX > w + 20 || terrainY < -20 || terrainY > h + 20)
                                    continue
                                ctx.fillStyle = String(terrainRow.surface || "LAND") === "WATER"
                                    ? String(palette.water || "#4c9ca0")
                                    : String(palette.muted || "#5d9b66")
                                ctx.fillText(String(terrainRow.glyph || ","), terrainX, terrainY)
                            }

                            var entityRows = root.fallbackView.entities || root.renderEntities || []
                            for (var entityIndex = 0; entityIndex < entityRows.length; ++entityIndex) {
                                var entityRow = entityRows[entityIndex]
                                if (!entityRow)
                                    continue
                                var entityX = root.number(entityRow.x, 0)
                                var entityZ = root.number(entityRow.z, 0)
                                if (Math.abs(entityX - centerX) > radius || Math.abs(entityZ - centerZ) > radius)
                                    continue
                                var markerX = screenX(entityX)
                                var markerY = screenY(entityZ)
                                var markerColor = String(entityRow.color || palette.text || "#9fe3a4")
                                if (String(entityRow.kind || "") === "PLAYER")
                                    markerColor = String(palette.player || "#e3bd63")
                                ctx.fillStyle = markerColor
                                ctx.fillText(String(entityRow.glyph || "."), markerX, markerY)
                                if (String(entityRow.kind || "") === "PLAYER"
                                    || String(entityRow.kind || "") === "NPC") {
                                    ctx.font = "10px monospace"
                                    ctx.textAlign = "left"
                                    ctx.fillText(String(entityRow.label || entityRow.id || ""), markerX + 8, markerY)
                                    var worn = entityRow.equipment || []
                                    if (worn.length) {
                                        ctx.font = "9px monospace"
                                        ctx.textAlign = "center"
                                        for (var gearIndex = 0; gearIndex < worn.length; ++gearIndex) {
                                            var wornRow = worn[gearIndex] || ({})
                                            ctx.fillStyle = String(wornRow.color || markerColor)
                                            ctx.fillText(
                                                String(wornRow.glyph || "+"),
                                                markerX + ((gearIndex % 3) - 1) * 8,
                                                markerY - 10 - Math.floor(gearIndex / 3) * 8
                                            )
                                        }
                                    }
                                    ctx.font = "12px monospace"
                                    ctx.textAlign = "center"
                                }
                            }

                            ctx.strokeStyle = String(palette.player || "#e3bd63")
                            ctx.strokeRect(w * 0.5 - 7, h * 0.5 - 7, 14, 14)
                        }
                    }

                    Column {
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.margins: 18
                        spacing: 5

                        Text {
                            text: "GG//DOS FRONTIER  ·  LOW GRAPHICS MODE"
                            color: root.ledgerGreen
                            font.family: "monospace"
                            font.pixelSize: 14
                            font.bold: true
                        }
                        Text {
                            text: "RICH 3D UNAVAILABLE  ·  " + root.presentationReason
                                + "\nSIMULATION CONTINUES  ·  FIXED 60 HZ  ·  SHARED DATA"
                            color: root.text
                            font.family: "monospace"
                            font.pixelSize: 10
                        }
                        Text {
                            text: root.fallbackTerminalText()
                            color: String((root.fallbackView.palette || ({})).text || "#9fe3a4")
                            font.family: "monospace"
                            font.pixelSize: 10
                            lineHeight: 1.15
                        }
                        Row {
                            spacing: 5
                            Text {
                                text: ">"
                                color: root.ledgerGold
                                font.family: "monospace"
                                font.pixelSize: 11
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Rectangle {
                                width: 320
                                height: 26
                                color: "#071007"
                                border.color: root.ledgerGreen
                                border.width: 1
                                TextInput {
                                    id: dosCommandInput
                                    anchors.fill: parent
                                    anchors.leftMargin: 6
                                    anchors.rightMargin: 6
                                    color: root.ledgerGreen
                                    selectionColor: root.ledgerGold
                                    font.family: "monospace"
                                    font.pixelSize: 11
                                    clip: true
                                    maximumLength: 96
                                    onAccepted: {
                                        root.dosCommand(text)
                                        text = ""
                                    }
                                }
                            }
                            GgButton {
                                text: "RUN"
                                implicitWidth: 52
                                implicitHeight: 26
                                onClicked: {
                                    root.dosCommand(dosCommandInput.text)
                                    dosCommandInput.text = ""
                                }
                            }
                        }
                    }

                    Row {
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 18
                        spacing: 6

                        GgButton {
                            text: "RETRY 3D"
                            implicitWidth: 82
                            implicitHeight: 25
                            onClicked: root.setPresentationMode("RICH_3D")
                        }
                        GgButton {
                            text: "DOS LOCK"
                            implicitWidth: 82
                            implicitHeight: 25
                            checked: root.presentationMode === "DOS_2D"
                            onClicked: root.setPresentationMode("DOS_2D")
                        }
                    }
                }

                MouseArea {
                    id: cameraMouse
                    anchors.fill: parent
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    hoverEnabled: true
                    cursorShape: terrainPicking
                        ? Qt.CrossCursor
                        : (cameraDragging
                            ? Qt.ClosedHandCursor : Qt.OpenHandCursor)
                    property real dragStartX: 0
                    property real dragStartY: 0
                    property real dragStartYaw: 0
                    property real dragStartPitch: -27
                    property bool cameraDragging: false
                    property bool terrainPicking: false
                    property string brushLastKey: ""
                    property real brushLastX: Number.NaN
                    property real brushLastZ: Number.NaN

                    onPressed: function(mouse) {
                        root.forceActiveFocus()
                        if (
                            mouse.button === Qt.LeftButton
                            && (mouse.modifiers & Qt.ShiftModifier) !== 0
                        ) {
                            terrainPicking = true
                            brushLastKey = ""
                            brushLastX = Number.NaN
                            brushLastZ = Number.NaN
                            var selectedKey = root.pickTerrainCell(
                                mouse.x,
                                mouse.y
                            )
                            if (root.terrainBrushEnabled && selectedKey) {
                                brushLastKey = selectedKey
                                brushLastX = root.terrainBrushX
                                brushLastZ = root.terrainBrushZ
                                root.editTerrain(root.terrainBrushOperation)
                            }
                            mouse.accepted = true
                            return
                        }
                        if (mouse.button !== Qt.RightButton) {
                            mouse.accepted = false
                            return
                        }
                        cameraDragging = true
                        dragStartX = mouse.x
                        dragStartY = mouse.y
                        dragStartYaw = root.orbitYaw
                        dragStartPitch = root.orbitPitch
                    }

                    onPositionChanged: function(mouse) {
                        if (terrainPicking && pressed) {
                            var selectedKey = root.pickTerrainCell(
                                mouse.x,
                                mouse.y
                            )
                            var distanceSinceBrush = Math.hypot(
                                root.terrainBrushX - brushLastX,
                                root.terrainBrushZ - brushLastZ
                            )
                            var shouldPaint = selectedKey
                                && (
                                    selectedKey !== brushLastKey
                                    || !isFinite(brushLastX)
                                    || distanceSinceBrush >= Math.max(
                                        0.5,
                                        root.terrainBrushRadius * 0.35
                                    )
                                )
                            if (
                                root.terrainBrushEnabled
                                && shouldPaint
                            ) {
                                brushLastKey = selectedKey
                                brushLastX = root.terrainBrushX
                                brushLastZ = root.terrainBrushZ
                                root.editTerrain(root.terrainBrushOperation)
                            }
                            return
                        }
                        if (cameraDragging && pressed) {
                            root.orbitYaw = dragStartYaw
                                + (mouse.x - dragStartX) * 0.55
                            root.orbitPitch = Math.max(
                                -55,
                                Math.min(
                                    -12,
                                    dragStartPitch
                                        - (mouse.y - dragStartY) * 0.35
                                )
                            )
                        }
                    }

                    onReleased: {
                        if (terrainPicking) {
                            terrainPicking = false
                            brushLastKey = ""
                            brushLastX = Number.NaN
                            brushLastZ = Number.NaN
                        } else if (cameraDragging) {
                            cameraDragging = false
                            root.sendInput()
                        }
                    }

                    onWheel: function(wheel) {
                        root.cameraDistance = Math.max(
                            6,
                            Math.min(48, root.cameraDistance
                                - Number(wheel.angleDelta.y) / 120 * 2)
                        )
                        root.sendInput()
                        wheel.accepted = true
                    }
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.leftMargin: sidebar.width + 14
                    anchors.topMargin: 12
                    width: hudColumn.implicitWidth + 18
                    height: hudColumn.implicitHeight + 12
                    color: root.panelOverlayRaised
                    border.color: "#4a514f"
                    border.width: 1
                    radius: 2

                    Column {
                        id: hudColumn
                        anchors.centerIn: parent
                        spacing: 3

                        Text {
                            text: "PLAYGROUND · " + String(
                                root.renderStatus.state || root.status.state || "IDLE"
                            )
                            color: root.stateColor(
                                root.renderStatus.state || root.status.state
                            )
                            font.family: "monospace"
                            font.pixelSize: 11
                            font.bold: true
                        }
                        Text {
                            text: "SPEED " + root.fixed(root.player.speed, 1)
                                + "  DRIFT " + root.fixed(root.player.drift, 1)
                            color: root.ink
                            font.family: "monospace"
                            font.pixelSize: 11
                        }
                        Text {
                            text: "ENT " + String(root.simulation.render_entity_count || 0)
                                + " / " + String(root.simulation.active_entities || 0)
                                + "  FX " + String(root.simulation.active_particles || 0)
                            color: root.text
                            font.family: "monospace"
                            font.pixelSize: 10
                        }
                        Text {
                            text: root.movementMode + "  CELL "
                                + String(root.player.cell_key || "0:0")
                            color: root.ledgerGold
                            font.family: "monospace"
                            font.pixelSize: 10
                        }
                    }
                }

                // PitBull/oUF-inspired unit state: one compact data frame
                // sits over the world and can later be replaced by an
                // authored layout without changing the simulation contract.
                Rectangle {
                    objectName: "gameEngineUnitFrames"
                    z: 4
                    enabled: false
                    visible: root.addonEnabled("UNIT_FRAMES")
                    anchors.left: parent.left
                    anchors.bottom: parent.bottom
                    anchors.leftMargin: sidebar.width + 14
                    anchors.bottomMargin: 34
                    width: 252
                    height: 82
                    color: root.panelOverlay
                    border.color: "#4a514f"
                    border.width: 1
                    radius: 2

                    Column {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 3

                        Text {
                            width: parent.width
                            text: "PLAYER  ·  LV "
                                + String(root.progression.level || 1)
                                + "  ·  " + String(
                                    root.player.movement_mode || "GROUND"
                                )
                            color: root.ledgerGreen
                            font.family: "monospace"
                            font.pixelSize: 10
                            font.bold: true
                            elide: Text.ElideRight
                        }
                        Text {
                            width: parent.width
                            text: "HP " + root.fixed(root.combatActor("player").health, 0)
                                + " / " + root.fixed(root.combatActor("player").max_health, 0)
                                + "  ·  RESOURCE " + root.fixed(root.combat.resource, 0)
                                + " / " + String(
                                    root.combat.resource_capacity || 100
                                )
                                + "  ·  SPEED " + root.fixed(root.player.speed, 1)
                            color: root.ink
                            font.family: "monospace"
                            font.pixelSize: 10
                            elide: Text.ElideRight
                        }
                        Rectangle {
                            width: parent.width
                            height: 4
                            color: Qt.rgba(0.02, 0.03, 0.03, 0.34)
                            border.color: Qt.rgba(0.55, 0.68, 0.63, 0.35)
                            border.width: 1

                            Rectangle {
                                width: parent.width * root.percent(
                                    root.combat.resource,
                                    root.combat.resource_capacity || 100
                                )
                                height: parent.height
                                color: root.ledgerGreen
                            }
                        }
                        Text {
                            width: parent.width
                            text: "CELL " + String(root.player.cell_key || "0:0")
                                + "  ·  " + String(root.player.medium || "LAND")
                                + "  ·  TARGET " + (
                                    root.addonEnabled("NPC_TRACKER")
                                        && root.npcInteraction.available
                                        ? String(root.npcInteraction.target_id || "NPC")
                                        : "NONE"
                                )
                            color: root.muted
                            font.family: "monospace"
                            font.pixelSize: 9
                            elide: Text.ElideRight
                        }
                    }
                }

                Text {
                    anchors.left: parent.left
                    anchors.bottom: parent.bottom
                    anchors.leftMargin: sidebar.width + 14
                    anchors.bottomMargin: 12
                    text: "W/S MOVE · A/D TURN · Q/E STRAFE · RMB CAMERA · SPACE JUMP · SHIFT SPRINT · 1/2/3 MODE · R/F VERTICAL · Z/X/C ABILITIES"
                    color: root.muted
                    font.family: "monospace"
                    font.pixelSize: 10
                }
            }

            Rectangle {
                id: inspector
                objectName: "gameEngineInspector"
                z: 30
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.margins: 10
                width: root.inspectorCollapsed
                    ? 34
                    : Math.max(244, Math.min(286, parent.width * 0.24))
                color: root.panelOverlay
                border.color: "#46504f"
                border.width: 1

                Rectangle {
                    id: inspectorToggle
                    objectName: "gameEngineInspectorToggle"
                    z: 5
                    anchors.top: parent.top
                    anchors.right: parent.right
                    anchors.topMargin: 5
                    anchors.rightMargin: 5
                    width: 24
                    height: 24
                    color: root.inspectorCollapsed
                        ? root.selectedPanel : root.panelOverlayRaised
                    border.color: "#5f646a"
                    border.width: 1

                    Text {
                        anchors.fill: parent
                        text: root.inspectorCollapsed ? "‹" : "›"
                        color: root.ink
                        font.pixelSize: 17
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.inspectorCollapsed =
                            !root.inspectorCollapsed
                    }
                }

                Flickable {
                    visible: !root.inspectorCollapsed
                    anchors.fill: parent
                    anchors.margins: 10
                    anchors.topMargin: 38
                    clip: true
                    contentWidth: width
                    contentHeight: inspectorColumn.height
                    boundsBehavior: Flickable.StopAtBounds

                    Column {
                        id: inspectorColumn
                        width: parent.width
                        spacing: 10

                        Column {
                            width: parent.width
                            spacing: 6
                            visible: root.page === "BAG"
                            Text {
                                text: "INVENTORY / EQUIPMENT"
                                color: root.ledgerGold
                                font.family: "monospace"
                            }
                            Repeater {
                                model: (root.items.equipment || []).concat(root.items.inventory || [])
                                delegate: GgButton {
                                    required property var modelData
                                    width: parent.width
                                    implicitHeight: 30
                                    text: String(modelData.name) + " ×" + String(modelData.quantity)
                                        + (modelData.location === "EQUIPPED"
                                            ? " [" + String(modelData.equipped_slot) + "]" : "")
                                        + (modelData.gear
                                            ? " S" + String(modelData.gear.socket_count)
                                                + "/" + String(modelData.gear.socket_capacity)
                                                + (modelData.gear.runeword
                                                    ? " " + String(modelData.gear.runeword.name)
                                                    : "")
                                            : "")
                                    checked: root.selectedItemId === String(modelData.instance_id)
                                    onClicked: root.selectedItemId = String(modelData.instance_id)
                                }
                            }
                            Row {
                                spacing: 6
                                GgButton {
                                    text: "EQUIP"
                                    enabled: root.selectedItemId !== ""
                                    onClicked: root.equipItem(root.selectedItemId)
                                }
                                GgButton {
                                    text: "DROP"
                                    enabled: root.selectedItemId !== ""
                                    onClicked: {
                                        root.dropItem(root.selectedItemId)
                                        root.selectedItemId = ""
                                    }
                                }
                                GgButton {
                                    text: "SOCKET"
                                    enabled: root.selectedItemId !== ""
                                    onClicked: root.socketItem(root.selectedItemId, "")
                                }
                                GgButton {
                                    text: "ENCHANT"
                                    enabled: root.selectedItemId !== ""
                                    onClicked: root.enchantGear(root.selectedItemId, "")
                                }
                            }
                            Text {
                                width: parent.width
                                text: "GEAR  " + String(root.gear.runewords || 0)
                                    + " runewords · " + String(root.gear.runes || 0)
                                    + " runes · " + String(root.gear.gems || 0)
                                    + " gems"
                                color: root.ledgerGreen
                                font.family: "monospace"
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }
                            Text {
                                width: parent.width
                                text: String(root.status.error || "")
                                color: root.signalRed
                                wrapMode: Text.WordWrap
                            }
                        }

                        Column {
                            width: parent.width
                            spacing: 5
                            visible: root.page === "BAG"
                            Text {
                                width: parent.width
                                text: "WALLET  " + String(
                                    root.economy.wallet
                                        ? root.economy.wallet.gold || 0
                                        : 0
                                ) + " GOLD"
                                color: root.ledgerGold
                                font.family: "monospace"
                                font.bold: true
                            }
                            Repeater {
                                model: root.economy.vendors || []
                                delegate: Column {
                                    id: vendorCard
                                    required property var modelData
                                    property var vendorRow: modelData
                                    width: parent.width
                                    spacing: 3
                                    Text {
                                        width: parent.width
                                        text: String(vendorCard.vendorRow.name || "VENDOR")
                                            + " · " + String(
                                                vendorCard.vendorRow.presence
                                                    && vendorCard.vendorRow.presence.available
                                                    ? "READY" : "OUT OF REACH"
                                            )
                                            + " · " + String(vendorCard.vendorRow.gold || 0)
                                            + "G"
                                        color: vendorCard.vendorRow.presence
                                            && vendorCard.vendorRow.presence.available
                                            ? root.ledgerGreen : root.muted
                                        font.family: "monospace"
                                        font.pixelSize: 10
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        width: parent.width
                                        text: "STOCK " + String(
                                            vendorCard.vendorRow.stock_count || 0
                                        ) + "/" + String(
                                            vendorCard.vendorRow.restock
                                                ? vendorCard.vendorRow.restock.stock_limit || 0
                                                : 0
                                        ) + " · RESTOCK " + String(
                                            vendorCard.vendorRow.restock
                                                ? vendorCard.vendorRow.restock.successful || 0
                                                : 0
                                        )
                                        color: root.muted
                                        font.family: "monospace"
                                        font.pixelSize: 9
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        width: parent.width
                                        visible: Boolean(
                                            vendorCard.vendorRow.decision
                                                && String(
                                                    vendorCard.vendorRow.decision.action || ""
                                                ) !== ""
                                        )
                                        text: "DECISION " + String(
                                            vendorCard.vendorRow.decision
                                                ? vendorCard.vendorRow.decision.action || ""
                                                : ""
                                        ) + " · " + String(
                                            vendorCard.vendorRow.decision
                                                ? vendorCard.vendorRow.decision.reason || ""
                                                : ""
                                        ) + (
                                            vendorCard.vendorRow.decision
                                                && vendorCard.vendorRow.decision.focus_definition_id
                                                ? " · WANT " + String(
                                                    vendorCard.vendorRow.decision
                                                        .focus_definition_id
                                                )
                                                : ""
                                        )
                                        color: root.ledgerGold
                                        font.family: "monospace"
                                        font.pixelSize: 9
                                        elide: Text.ElideRight
                                    }
                                    Repeater {
                                        model: vendorCard.vendorRow.offers
                                            ? (vendorCard.vendorRow.offers.buy || []) : []
                                        delegate: GgButton {
                                            required property var modelData
                                            width: parent.width
                                            implicitHeight: 24
                                            text: "BUY " + String(modelData.item.name || modelData.definition_id)
                                                + " · " + String(modelData.total_price || 0) + "G"
                                            enabled: Boolean(
                                                vendorCard.vendorRow.presence
                                                    && vendorCard.vendorRow.presence.available
                                            ) && root.number(root.economy.wallet
                                                ? root.economy.wallet.gold : 0, 0)
                                                >= root.number(modelData.total_price, 0)
                                            onClicked: root.buyFromVendor(
                                                String(vendorCard.vendorRow.id || ""),
                                                String(modelData.instance_id || "")
                                            )
                                        }
                                    }
                                    Repeater {
                                        model: vendorCard.vendorRow.offers
                                            ? (vendorCard.vendorRow.offers.sell || []) : []
                                        delegate: GgButton {
                                            required property var modelData
                                            width: parent.width
                                            implicitHeight: 24
                                            text: "SELL " + String(modelData.item.name || modelData.definition_id)
                                                + " · +" + String(modelData.total_price || 0) + "G"
                                            enabled: Boolean(
                                                vendorCard.vendorRow.presence
                                                    && vendorCard.vendorRow.presence.available
                                            ) && root.number(vendorCard.vendorRow.gold, 0)
                                                >= root.number(modelData.total_price, 0)
                                            onClicked: root.sellToVendor(
                                                String(vendorCard.vendorRow.id || ""),
                                                String(modelData.instance_id || "")
                                            )
                                        }
                                    }
                                }
                            }
                            Text {
                                width: parent.width
                                text: "Physical stock only · every offer has a real instance ID"
                                color: root.muted
                                font.family: "monospace"
                                font.pixelSize: 9
                                wrapMode: Text.WordWrap
                            }
                        }

                        Row {
                            width: parent.width
                            spacing: 8

                            Text {
                                text: root.page
                                color: root.ink
                                font.family: "monospace"
                                font.pixelSize: 15
                                font.bold: true
                            }

                            Text {
                                width: parent.width - 80
                                text: root.legend
                                color: root.ledgerGold
                                font.family: "monospace"
                                font.pixelSize: 10
                                horizontalAlignment: Text.AlignRight
                                verticalAlignment: Text.AlignVCenter
                            }
                        }

                        Rectangle {
                            width: parent.width
                            height: 1
                            color: "#333333"
                        }

                        Column {
                            width: parent.width
                            spacing: 6
                            visible: root.page === "PLAY"

                            Text {
                                width: parent.width
                                text: "LOCAL FIXED-STEP SIMULATION"
                                color: root.ledgerGreen
                                font.family: "monospace"
                                font.pixelSize: 11
                                font.bold: true
                            }

                            Text {
                                width: parent.width
                                text: "A bounded playground for driving, collisions, pooled debris and replay."
                                color: root.text
                                wrapMode: Text.WordWrap
                                font.family: "monospace"
                                font.pixelSize: 10
                            }

                            Row {
                                width: parent.width
                                spacing: 6

                                GgButton {
                                    text: "STEP"
                                    implicitWidth: 58
                                    implicitHeight: 26
                                    enabled: !root.running
                                    onClicked: root.stepRuntime()
                                }
                                GgButton {
                                    text: root.stress ? "NORMAL" : "STRESS"
                                    implicitWidth: 78
                                    implicitHeight: 26
                                    checked: root.stress
                                    onClicked: root.stressRuntime()
                                }
                            }

                            Row {
                                width: parent.width
                                spacing: 4

                                Text {
                                    text: "MODE"
                                    color: root.muted
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                    verticalAlignment: Text.AlignVCenter
                                }

                                Repeater {
                                    model: ["GROUND", "SWIM", "FLY"]
                                    delegate: GgButton {
                                        required property string modelData
                                        text: modelData
                                        implicitWidth: 58
                                        implicitHeight: 25
                                        checked: root.movementMode === modelData
                                        onClicked: root.setMovementMode(modelData)
                                    }
                                }
                            }

                            Row {
                                width: parent.width
                                spacing: 4
                                Text {
                                    text: "STAGE"
                                    color: root.muted
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                    verticalAlignment: Text.AlignVCenter
                                }
                                GgButton {
                                    text: "3D"
                                    implicitWidth: 54
                                    implicitHeight: 24
                                    checked: root.presentationMode === "RICH_3D"
                                    onClicked: root.setPresentationMode("RICH_3D")
                                }
                                GgButton {
                                    text: "DOS"
                                    implicitWidth: 54
                                    implicitHeight: 24
                                    checked: root.dosFallbackActive
                                    onClicked: root.setPresentationMode("DOS_2D")
                                }
                                Text {
                                    text: root.dosFallbackActive
                                        ? "FAILOVER ACTIVE" : "RICH 3D ACTIVE"
                                    color: root.dosFallbackActive
                                        ? root.signalRed : root.ledgerGreen
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                    verticalAlignment: Text.AlignVCenter
                                }
                            }

                            Text {
                                width: parent.width
                                text: "BIOME " + String(root.terrainSurface.biome || "-")
                                    + "  MEDIUM " + String(root.terrainSurface.medium || "-")
                                    + "\nSURFACE " + root.fixed(root.terrainSurface.height_m, 2)
                                    + " m  WATER DEPTH "
                                    + root.fixed(root.terrainSurface.water_depth_m, 2) + " m"
                                color: root.signalBlue
                                font.family: "monospace"
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }

                            Row {
                                width: parent.width
                                spacing: 5
                                visible: root.addonEnabled("ACTION_BAR")

                                GgButton {
                                    text: "SURGE"
                                    implicitWidth: 64
                                    implicitHeight: 25
                                    onClicked: root.useAbility("ability.surge")
                                }
                                GgButton {
                                    text: "TIDE"
                                    implicitWidth: 56
                                    implicitHeight: 25
                                    onClicked: root.useAbility("ability.undertow")
                                }
                                GgButton {
                                    text: "LEAP"
                                    implicitWidth: 56
                                    implicitHeight: 25
                                    onClicked: root.useAbility("ability.sky_leap")
                                }
                            }

                            Column {
                                width: parent.width
                                spacing: 4
                                visible: Boolean(root.dialogue.open)

                                Text {
                                    width: parent.width
                                    text: String((root.dialogue.node || {}).speaker || "NPC")
                                        + " · " + String((root.dialogue.node || {}).text || "")
                                    color: root.ledgerGold
                                    font.family: "monospace"
                                    font.pixelSize: 9
                                    wrapMode: Text.WordWrap
                                }
                                Flow {
                                    width: parent.width
                                    spacing: 4
                                    Repeater {
                                        model: (root.dialogue.node || {}).choices || []
                                        delegate: GgButton {
                                            required property var modelData
                                            text: String(modelData.label || modelData.id || "CHOICE")
                                            implicitWidth: Math.min(176, Math.max(82,
                                                18 + text.length * 6))
                                            implicitHeight: 24
                                            onClicked: root.talkNpc(
                                                String(modelData.id || ""),
                                                String((root.dialogue.active || {}).npc_id
                                                    || root.npcInteraction.target_id || "")
                                            )
                                        }
                                    }
                                }
                            }

                            Row {
                                width: parent.width
                                spacing: 5
                                visible: root.addonEnabled("LOOT_LEDGER")

                                GgButton {
                                    text: "LOOT"
                                    implicitWidth: 56
                                    implicitHeight: 25
                                    onClicked: root.claimLoot()
                                }
                                GgButton {
                                    text: "ENCHANT"
                                    implicitWidth: 78
                                    implicitHeight: 25
                                    onClicked: root.enchantLoot("enchant.wayfinder")
                                }
                                GgButton {
                                    text: "CRAFT"
                                    implicitWidth: 64
                                    implicitHeight: 25
                                    onClicked: root.craftRecipe("recipe.field_ration")
                                }
                                GgButton {
                                    text: "SOCKET"
                                    implicitWidth: 72
                                    implicitHeight: 25
                                    onClicked: root.socketItem("", "")
                                }
                                GgButton {
                                    text: "GEAR CRAFT"
                                    implicitWidth: 86
                                    implicitHeight: 25
                                    onClicked: root.craftGear("recipe.fiber_rope", "station.workbench")
                                }
                                GgButton {
                                    text: "PACK"
                                    implicitWidth: 58
                                    implicitHeight: 25
                                    onClicked: root.activateContentPack("pack.tidefall-frontier")
                                }
                            }

                            Text {
                                width: parent.width
                                text: "WORLD ITEMS " + String(
                                        root.items.ground ? root.items.ground.length : 0
                                    )
                                    + " · EQUIPPED " + String(
                                        root.items.equipment ? root.items.equipment.length : 0
                                    )
                                    + "\nTARGET " + String(
                                        root.itemInteraction.name || "NONE"
                                    )
                                    + " · " + String(
                                        root.itemInteraction.action || "MOVE CLOSER"
                                    )
                                color: root.signalViolet
                                font.family: "monospace"
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                width: parent.width
                                text: "LIFE " + String(root.life.population || 0)
                                    + " / " + String(root.life.budget || 0)
                                    + " · " + String(root.life.clock
                                        ? root.life.clock.label : "--:--")
                                    + " " + String(root.life.clock
                                        ? root.life.clock.phase : "-")
                                    + "\nFISH " + String(root.life.activities
                                        ? root.life.activities.FISHING || 0 : 0)
                                    + " · TRAVEL " + String(root.life.activities
                                        ? root.life.activities.TRAVELING || 0 : 0)
                                    + " · SCOUT " + String(root.life.activities
                                        ? root.life.activities.SCOUTING || 0 : 0)
                                    + " · HAUL " + String(root.life.activities
                                        ? root.life.activities.HAULING || 0 : 0)
                                    + " · NOTICE " + String(root.life.stimuli
                                        ? root.life.stimuli.PLAYER_NEAR || 0 : 0)
                                    + "\nPEOPLE " + String(root.people.population || 0)
                                    + " · UNIQUE " + String(root.people.unique_names || 0)
                                    + " · MEMORY " + String(root.people.memory_events || 0)
                                color: root.ledgerGreen
                                font.family: "monospace"
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }

                            Row {
                                width: parent.width
                                spacing: 5
                                GgButton {
                                    text: "INTERACT"
                                    implicitWidth: 76
                                    implicitHeight: 25
                                    onClicked: root.interactItem()
                                }
                                GgButton {
                                    text: "PICKUP"
                                    implicitWidth: 62
                                    implicitHeight: 25
                                    onClicked: root.pickupItem("")
                                }
                                GgButton {
                                    text: "EQUIP"
                                    implicitWidth: 58
                                    implicitHeight: 25
                                    onClicked: root.equipItem("")
                                }
                            }

                            Row {
                                width: parent.width
                                spacing: 5
                                GgButton {
                                    text: "OPEN CACHE"
                                    implicitWidth: 88
                                    implicitHeight: 25
                                    onClicked: root.openContainer("")
                                }
                                GgButton {
                                    text: "LOOT CACHE"
                                    implicitWidth: 88
                                    implicitHeight: 25
                                    onClicked: root.lootContainer("")
                                }
                                GgButton {
                                    text: "DROP"
                                    implicitWidth: 52
                                    implicitHeight: 25
                                    onClicked: root.dropItem("")
                                }
                            }

                            Text {
                                width: parent.width
                                text: "RESOURCE " + root.fixed(root.combat.resource, 0)
                                    + " / 100  ·  LV " + String(root.progression.level || 1)
                                    + "  ·  XP " + String(root.progression.xp || 0)
                                color: root.ledgerGold
                                font.family: "monospace"
                                font.pixelSize: 10
                            }

                            Text {
                                width: parent.width
                                text: "CTRL " + String(
                                    root.controller.model
                                        || "WOW_CLASSIC_THIRD_PERSON"
                                )
                                    + "\nINPUT CHARACTER_FORWARD_RIGHT · " + String(
                                        root.controller.movement_grammar
                                            || "W_S_MOVE_A_D_TURN_Q_E_STRAFE"
                                    )
                                    + "\nGROUND "
                                    + (root.player.grounded ? "YES" : "AIR")
                                    + "  SPRINT "
                                    + (root.player.sprinting ? "ON" : "OFF")
                                    + "\nCAM "
                                    + root.fixed(root.controller.camera
                                        ? root.controller.camera.distance_m : 12, 1)
                                    + " m  PITCH "
                                    + root.fixed(root.controller.camera
                                        ? root.controller.camera.pitch : -27, 1)
                                color: root.signalViolet
                                font.family: "monospace"
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                width: parent.width
                                text: "FIELD LEDGER " + String(
                                    root.physics.model || "TSEU_INSPIRED_BOOKKEEPING"
                                )
                                    + "\nE " + root.fixed(root.physics.total_energy, 2)
                                    + "  M " + root.fixed(root.physics.mass_equivalent, 3)
                                    + "  |V| " + root.fixed(root.physics.speed, 2)
                                    + "\nGRAVITY " + String(
                                        root.physics.gravity_status || "NOT_CONNECTED"
                                    )
                                color: root.signalViolet
                                font.family: "monospace"
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                width: parent.width
                                visible: root.addonEnabled("NPC_TRACKER")
                                text: "NPC " + String(root.npc.active || 0)
                                    + " / " + String(root.npc.capacity || 0)
                                    + "  ·  AI " + String(root.npc.decision_hz || 20)
                                    + " HZ"
                                    + "\nWANDER " + String(root.npc.states
                                        ? root.npc.states.WANDER || 0 : 0)
                                    + "  FOLLOW " + String(root.npc.states
                                        ? root.npc.states.FOLLOW || 0 : 0)
                                    + "  ALERT " + String(root.npc.states
                                        ? root.npc.states.ALERT || 0 : 0)
                                    + "  FLEE " + String(root.npc.states
                                        ? root.npc.states.FLEE || 0 : 0)
                                    + "  DEAD " + String(root.npc.states
                                        ? root.npc.states.DEAD || 0 : 0)
                                    + "\nSENSE " + String(root.npc.perception
                                        || "RADIAL_LOS_BOUNDED")
                                    + "\nNAV " + String(root.npc.navigation
                                        || "DIRECT_STEERING_BOUNDED")
                                    + "\nPATH " + String(root.navigation.model
                                        || "TILED_HEIGHTFIELD_ASTAR")
                                    + "  " + String(root.navigation.walkable_tiles
                                        || 0) + "/" + String(
                                            root.navigation.streaming
                                                ? root.navigation.streaming.loaded_tiles
                                                : 0
                                        )
                                color: root.ledgerGreen
                                font.family: "monospace"
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }

                            Repeater {
                                model: (root.npc.agents || []).slice(0, 4)
                                visible: root.addonEnabled("NPC_TRACKER")
                                delegate: Text {
                                    required property var modelData
                                    width: parent.width
                                    text: "· " + String(modelData.archetype || "NPC")
                                        + " / " + String(modelData.state || "WANDER")
                                    + "  " + root.fixed(modelData.x, 1)
                                        + "," + root.fixed(modelData.z, 1)
                                        + "  S " + root.fixed(modelData.speed, 1)
                                    + "  HP " + root.fixed(
                                        modelData.combat
                                            ? modelData.combat.health : 0,
                                        0
                                    ) + "/" + root.fixed(
                                        modelData.combat
                                            ? modelData.combat.max_health : 0,
                                        0
                                    )
                                    + "  " + (modelData.line_of_sight
                                            ? "LOS" : "NO-LOS")
                                    + "  " + String(modelData.stimulus || "NONE")
                                    + "  PATH " + String(modelData.path_status || "-")
                                        + "/" + String(modelData.path_nodes || 0)
                                    + "\n  USE " + String(
                                        modelData.individual
                                            && modelData.individual.world_action
                                            ? (modelData.individual.world_action.last_action
                                                || "NONE")
                                            : "NONE"
                                    ) + " " + String(
                                        modelData.individual
                                            && modelData.individual.world_action
                                            ? (modelData.individual.world_action.status
                                                || "NONE")
                                            : "NONE"
                                    ) + " #" + String(
                                        modelData.individual
                                            && modelData.individual.world_action
                                            ? (modelData.individual.world_action.count
                                                || 0)
                                            : 0
                                    ) + "\n  LV " + String(
                                        modelData.individual
                                            && modelData.individual.progression
                                            ? (modelData.individual.progression.level || 1)
                                            : 1
                                    ) + " / " + String(
                                        modelData.individual
                                            && modelData.individual.progression
                                            ? (modelData.individual.progression.spec || "EXPLORER")
                                            : "EXPLORER"
                                    ) + "  PWR " + root.fixed(
                                        modelData.individual
                                            && modelData.individual.progression
                                            ? (modelData.individual.progression.power_score || 0)
                                            : 0,
                                        0
                                    ) + "  GEAR " + root.fixed(
                                        modelData.individual
                                            && modelData.individual.progression
                                            ? (modelData.individual.progression.gear_score || 0)
                                            : 0,
                                        0
                                    )
                                    color: String(modelData.state || "") === "FLEE"
                                        ? root.signalRed : root.text
                                    font.family: "monospace"
                                    font.pixelSize: 9
                                    elide: Text.ElideRight
                                }
                            }

                            Text {
                                width: parent.width
                                text: "WORLD POP " + String(root.livingWorld.promoted_count || 0)
                                    + "/" + String(root.livingWorld.promotion_budget || 0)
                                    + " PROMOTED  AMBIENT " + String(
                                        root.livingWorld.ambient_count || 0
                                    ) + "  SOCIAL " + String(
                                        root.social.relationship_count || 0
                                    ) + "  EVENTS " + String(
                                        root.worldEvents.active_count || 0
                                    ) + "  PACKS " + String(
                                        root.contentPacks.active_count || 0
                                    )
                                color: root.muted
                                font.family: "monospace"
                                font.pixelSize: 9
                                elide: Text.ElideRight
                            }

                            Row {
                                width: parent.width
                                spacing: 5
                                visible: root.addonEnabled("NPC_TRACKER")
                                GgButton {
                                    text: "ATTACK"
                                    implicitWidth: 70
                                    implicitHeight: 24
                                    enabled: Boolean(root.npcInteraction.available)
                                    onClicked: root.attackNpc(
                                        root.npcInteraction.target_id || ""
                                    )
                                }
                                GgButton {
                                    text: "INTERACT"
                                    implicitWidth: 76
                                    implicitHeight: 24
                                    enabled: Boolean(root.npcInteraction.available)
                                    onClicked: root.interactNpc()
                                }
                                Text {
                                    width: parent.width - 151
                                    text: root.npcInteraction.available
                                        ? String(root.npcInteraction.target_id || "NPC")
                                            + " · " + root.fixed(
                                                root.npcInteraction.target_distance_m,
                                                1
                                            ) + " m"
                                        : "NO NPC IN TALK RADIUS"
                                    color: root.npcInteraction.available
                                        ? root.ledgerGold : root.muted
                                    font.family: "monospace"
                                    font.pixelSize: 9
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                            }

                            Row {
                                width: parent.width
                                spacing: 5
                                GgButton {
                                    text: "ACCEPT QUEST"
                                    implicitWidth: 108
                                    implicitHeight: 24
                                    onClicked: root.acceptQuest("quest.shoreline-first")
                                }
                                GgButton {
                                    text: "CLAIM QUEST"
                                    implicitWidth: 104
                                    implicitHeight: 24
                                    enabled: (root.quests.ready || 0) > 0
                                    onClicked: root.claimQuest("")
                                }
                                Text {
                                    width: parent.width - 222
                                    text: "ACTIVE " + String(root.quests.active_count || 0)
                                        + " READY " + String(root.quests.ready || 0)
                                    color: root.ledgerGold
                                    font.family: "monospace"
                                    font.pixelSize: 9
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                            }

                            Row {
                                width: parent.width
                                spacing: 5
                                GgButton {
                                    text: "+25 XP"
                                    implicitWidth: 68
                                    implicitHeight: 24
                                    onClicked: root.gainXp(25)
                                }
                                GgButton {
                                    text: "TALENT +"
                                    implicitWidth: 78
                                    implicitHeight: 24
                                    onClicked: root.spendTalent("trailblazer")
                                }
                            }

                            Row {
                                width: parent.width
                                spacing: 6

                                GgButton {
                                    text: root.recording ? "STOP REC" : "RECORD"
                                    implicitWidth: 88
                                    implicitHeight: 26
                                    checked: root.recording
                                    onClicked: root.recording
                                        ? root.stopRecording()
                                        : root.startRecording()
                                }
                                GgButton {
                                    text: "REPLAY"
                                    implicitWidth: 74
                                    implicitHeight: 26
                                    enabled: !root.recording
                                    onClicked: root.replayRuntime()
                                }
                            }

                            Text {
                                width: parent.width
                                text: "INPUT  F " + root.fixed(root.throttle, 1)
                                    + "  TURN " + root.fixed(root.steer, 1)
                                    + "  STRAFE " + root.fixed(root.strafe, 1)
                                    + "  V " + root.fixed(root.vertical, 1)
                                    + "  SPRINT " + (root.boost ? "ON" : "OFF")
                                color: root.text
                                font.family: "monospace"
                                font.pixelSize: 10
                            }

                            Text {
                                width: parent.width
                                text: "TICK " + String(root.simulation.tick || 0)
                                    + "  TIME " + root.fixed(root.simulation.time_s, 2) + "s"
                                    + "\nEVENTS " + String(root.eventJournal.count || root.events.length || 0)
                                    + "  REPLAY " + String(root.replay.recorded_inputs || 0)
                                color: root.muted
                                font.family: "monospace"
                                font.pixelSize: 10
                            }

                            Rectangle {
                                width: parent.width
                                height: 1
                                color: "#333333"
                            }

                            Text {
                                text: "EVENT STREAM"
                                color: root.ledgerGold
                                font.family: "monospace"
                                font.pixelSize: 10
                                font.bold: true
                            }

                            Repeater {
                                model: root.events.slice(0, 6)
                                delegate: Text {
                                    required property var modelData
                                    width: parent.width
                                    text: String(modelData.kind || "") + " · "
                                        + String(modelData.text || "")
                                    color: root.text
                                    elide: Text.ElideRight
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                }
                            }
                        }

                        Column {
                            width: parent.width
                            spacing: 6
                            visible: root.page === "SCENE"

                            Text {
                                text: "SCENE INSPECTOR"
                                color: root.ledgerGreen
                                font.family: "monospace"
                                font.pixelSize: 11
                                font.bold: true
                            }
                            Text {
                                width: parent.width
                                text: "ACTIVE " + String(root.simulation.active_entities || 0)
                                    + " / " + String(root.simulation.entity_capacity || 0)
                                    + "\nRENDER " + String(root.simulation.render_entity_count || 0)
                                    + " · CHUNKS " + String(root.chunks.loaded_count || 0)
                                    + "\nTERRAIN " + String(root.terrain.streaming
                                        ? root.terrain.streaming.loaded_count : 0)
                                        + " · LOD " + String(root.terrain.streaming
                                        ? root.terrain.streaming.render_candidates : 0)
                                    + "\nNAV " + String(root.navigation.walkable_tiles
                                        || 0) + " WALK / " + String(
                                            root.navigation.blocked_tiles || 0
                                        ) + " BLOCK"
                                    + "\nEDITOR " + String(root.editor.placement_count || 0)
                                    + " / " + String(root.editor.budget
                                        ? root.editor.budget.placements : 128)
                                color: root.text
                                font.family: "monospace"
                                font.pixelSize: 10
                            }
                            Text {
                                width: parent.width
                                text: "TARGET " + (root.terrainTargetSelected
                                    ? root.terrainTargetKey : "PLAYER CELL")
                                    + "  ·  SHIFT+CLICK / DRAG"
                                    + "\nPOINT " + root.fixed(root.terrainBrushX, 1)
                                    + "," + root.fixed(root.terrainBrushZ, 1)
                                    + "  ·  R " + root.fixed(root.terrainBrushRadius, 1)
                                    + " m"
                                    + "\nBRUSH " + (root.terrainBrushEnabled
                                        ? "ON · " + root.terrainBrushOperation
                                        : "OFF")
                                    + "  ·  " + root.terrainBrushFalloff
                                color: root.terrainTargetSelected
                                    ? root.ledgerGold : root.muted
                                font.family: "monospace"
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }
                            Row {
                                width: parent.width
                                spacing: 4
                                GgButton {
                                    text: root.terrainBrushEnabled
                                        ? "BRUSH ON" : "BRUSH OFF"
                                    implicitWidth: 86
                                    implicitHeight: 24
                                    checked: root.terrainBrushEnabled
                                    onClicked: root.terrainBrushEnabled =
                                        !root.terrainBrushEnabled
                                }
                                GgButton {
                                    text: "CLEAR TARGET"
                                    implicitWidth: 102
                                    implicitHeight: 24
                                    enabled: root.terrainTargetSelected
                                    onClicked: root.clearTerrainTarget()
                                }
                            }
                            Row {
                                width: parent.width
                                spacing: 4
                                GgButton {
                                    text: "R-"
                                    implicitWidth: 34
                                    implicitHeight: 24
                                    onClicked: root.adjustTerrainBrushRadius(-1)
                                }
                                Text {
                                    width: 54
                                    text: root.fixed(root.terrainBrushRadius, 1) + " m"
                                    color: root.text
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                    verticalAlignment: Text.AlignVCenter
                                    horizontalAlignment: Text.AlignHCenter
                                }
                                GgButton {
                                    text: "R+"
                                    implicitWidth: 34
                                    implicitHeight: 24
                                    onClicked: root.adjustTerrainBrushRadius(1)
                                }
                                GgButton {
                                    text: "F " + root.terrainBrushFalloff
                                    implicitWidth: 108
                                    implicitHeight: 24
                                    onClicked: root.cycleTerrainBrushFalloff()
                                }
                            }
                            Row {
                                width: parent.width
                                spacing: 5
                                GgButton {
                                    text: "PLACE PROP"
                                    implicitWidth: 92
                                    implicitHeight: 25
                                    onClicked: root.placeEditorObject("PROP")
                                }
                                GgButton {
                                    text: "PLACE RAMP"
                                    implicitWidth: 92
                                    implicitHeight: 25
                                    onClicked: root.placeEditorObject("RAMP")
                                }
                            }
                            Row {
                                width: parent.width
                                spacing: 5
                                GgButton {
                                    text: "PLACE NPC"
                                    implicitWidth: 92
                                    implicitHeight: 25
                                    onClicked: root.placeEditorObject("NPC")
                                }
                                Text {
                                    width: parent.width - 97
                                    text: "WANDERER · bounded local AI"
                                    color: root.ledgerGreen
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                            }
                            Row {
                                width: parent.width
                                spacing: 4
                                GgButton {
                                    text: "RAISE"
                                    implicitWidth: 54
                                    implicitHeight: 24
                                    onClicked: root.editTerrain("RAISE")
                                }
                                GgButton {
                                    text: "LOWER"
                                    implicitWidth: 54
                                    implicitHeight: 24
                                    onClicked: root.editTerrain("LOWER")
                                }
                                GgButton {
                                    text: "LAND"
                                    implicitWidth: 50
                                    implicitHeight: 24
                                    onClicked: root.editTerrain("LAND")
                                }
                                GgButton {
                                    text: "WATER"
                                    implicitWidth: 58
                                    implicitHeight: 24
                                    onClicked: root.editTerrain("WATER")
                                }
                            }
                            Row {
                                width: parent.width
                                spacing: 4
                                GgButton {
                                    text: "REEF"
                                    implicitWidth: 50
                                    implicitHeight: 24
                                    onClicked: root.editTerrain("REEF")
                                }
                                GgButton {
                                    text: "ISLAND"
                                    implicitWidth: 58
                                    implicitHeight: 24
                                    onClicked: root.editTerrain("ISLAND")
                                }
                                GgButton {
                                    text: "CLEAR"
                                    implicitWidth: 54
                                    implicitHeight: 24
                                    onClicked: root.editTerrain("CLEAR")
                                }
                                GgButton {
                                    text: "UNDO TERRAIN"
                                    implicitWidth: 92
                                    implicitHeight: 24
                                    onClicked: root.undoTerrain()
                                }
                            }
                            Row {
                                width: parent.width
                                spacing: 5
                                GgButton {
                                    text: "UNDO"
                                    implicitWidth: 64
                                    implicitHeight: 25
                                    onClicked: root.undoEditorObject()
                                }
                                GgButton {
                                    text: "DIORAMA"
                                    implicitWidth: 76
                                    implicitHeight: 25
                                    checked: root.cinematic.preset === "FIRST_ISLAND_DIORAMA"
                                    onClicked: root.setCinematicPreset("FIRST_ISLAND_DIORAMA")
                                }
                                GgButton {
                                    text: "ORBIT"
                                    implicitWidth: 58
                                    implicitHeight: 25
                                    checked: root.cinematic.preset === "ORBIT_WORLD_SCALE"
                                    onClicked: root.setCinematicPreset("ORBIT_WORLD_SCALE")
                                }
                            }
                            Text {
                                width: parent.width
                                text: "PRESET " + String(root.cinematic.preset || "FIRST_ISLAND_DIORAMA")
                                    + "\nAUTHORING " + String(root.editor.authoring || "LOCAL")
                                    + "\nSTREAM " + String(root.terrain.streaming
                                        ? root.terrain.streaming.policy : "-")
                                    + "\nTRANSITION " + String(root.terrain.transition
                                        ? root.terrain.transition.land_water_air : "-")
                                    + "\nTERRAIN EDIT " + String(root.terrainEditor.override_count || 0)
                                        + " / " + String(root.terrainEditor.budget
                                            ? root.terrainEditor.budget.cells : 64)
                                color: root.ledgerGold
                                font.family: "monospace"
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }
                            Repeater {
                                model: root.renderEntities.slice(0, 20)
                                delegate: Rectangle {
                                    required property var modelData
                                    required property int index
                                    width: parent.width
                                    height: 23
                                    color: index % 2 ? "transparent" : "#1e2020"

                                    Text {
                                        anchors.left: parent.left
                                        anchors.leftMargin: 5
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: String(parent.modelData.id || "") + "  "
                                            + String(parent.modelData.kind || "")
                                        color: parent.modelData.kind === "PLAYER"
                                            ? root.ledgerGold : root.text
                                        font.family: "monospace"
                                        font.pixelSize: 10
                                    }
                                    Text {
                                        anchors.right: parent.right
                                        anchors.rightMargin: 5
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: root.fixed(parent.modelData.x, 1)
                                            + "," + root.fixed(parent.modelData.z, 1)
                                        color: root.muted
                                        font.family: "monospace"
                                        font.pixelSize: 10
                                    }
                                }
                            }
                        }

                        Column {
                            width: parent.width
                            spacing: 7
                            visible: root.page === "PERF"

                            Text {
                                text: "PERFORMANCE CONTRACT"
                                color: root.ledgerGreen
                                font.family: "monospace"
                                font.pixelSize: 11
                                font.bold: true
                            }

                            Text {
                                width: parent.width
                                text: "FIXED HZ     " + String(root.simulation.fixed_hz || 60)
                                + "\nDT           " + root.fixed(root.simulation.dt_ms, 3) + " ms"
                                + "\nRENDER UPDATE " + String(root.renderUpdateHz) + " Hz"
                                    + "\nLAST TICK    " + root.fixed(root.simulation.last_tick_ms, 3) + " ms"
                                    + "\nMAX TICK     " + root.fixed(root.simulation.max_tick_ms, 3) + " ms"
                                + "\nDRAW CALLS   " + String(root.render.draw_calls || 0)
                                    + "\nVISIBLE      " + String(root.render.visibility
                                        ? root.render.visibility.visible_instances : 0)
                                    + "\nTERRAIN      " + String(root.terrain.streaming
                                        ? root.terrain.streaming.loaded_count : 0)
                                    + " CELLS / " + String(root.terrain.streaming
                                        ? root.terrain.streaming.render_triangles : 0)
                                        + " TRI"
                                color: root.text
                                font.family: "monospace"
                                font.pixelSize: 10
                            }

                            Row {
                                width: parent.width
                                spacing: 4
                                Text {
                                    text: "PROFILE"
                                    color: root.muted
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                    verticalAlignment: Text.AlignVCenter
                                }
                                Repeater {
                                    model: ["POTATO", "BALANCED", "MODERN", "CINEMATIC"]
                                    delegate: GgButton {
                                        required property string modelData
                                        text: modelData
                                        implicitWidth: 61
                                        implicitHeight: 24
                                        checked: root.render.profile === modelData
                                        onClicked: root.setRenderProfile(modelData)
                                    }
                                }
                            }

                            Text {
                                width: parent.width
                                text: root.page !== "PERF" ? "" : (
                                    "AA           " + String(root.render.anti_aliasing
                                        ? root.render.anti_aliasing.mode : "-")
                                    + "\nUPSCALER     " + String(root.render.upscaling
                                        ? root.render.upscaling.mode : "-")
                                    + "\nSNAPSHOT     " + root.fixed(root.render.measurement
                                        ? root.render.measurement.snapshot_build_ms : 0, 3) + " ms"
                                    + "\nQT FRAME     " + root.fixed(view3d.renderStats
                                        ? view3d.renderStats.frameTime : 0, 3) + " ms"
                                    + " · GPU " + root.fixed(view3d.renderStats
                                        ? view3d.renderStats.renderTime : 0, 3) + " ms"
                                )
                                color: root.ledgerGold
                                font.family: "monospace"
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                width: parent.width
                                text: "OPTIONAL GPU  DLSS / FSR / XeSS\n"
                                    + "STATUS         runtime probe required"
                                color: root.muted
                                font.family: "monospace"
                                font.pixelSize: 10
                            }

                            Text {
                                width: parent.width
                                text: "ENTITY POOL  " + String(root.simulation.active_entities || 0)
                                    + " / " + String(root.simulation.entity_capacity || 0)
                                    + "\nPARTICLE POOL " + String(root.simulation.active_particles || 0)
                                    + " / " + String(root.simulation.particle_capacity || 0)
                                color: root.text
                                font.family: "monospace"
                                font.pixelSize: 10
                            }

                            Rectangle {
                                width: parent.width
                                height: 8
                                color: "#252928"
                                border.color: "#454b49"
                                border.width: 1
                                Rectangle {
                                    height: parent.height
                                    width: parent.width * root.percent(
                                        root.simulation.active_entities,
                                        root.simulation.entity_capacity
                                    )
                                    color: root.ledgerGreen
                                }
                            }
                            Rectangle {
                                width: parent.width
                                height: 8
                                color: "#252928"
                                border.color: "#454b49"
                                border.width: 1
                                Rectangle {
                                    height: parent.height
                                    width: parent.width * root.percent(
                                        root.simulation.active_particles,
                                        root.simulation.particle_capacity
                                    )
                                    color: root.signalViolet
                                }
                            }
                        }

                        Column {
                            width: parent.width
                            spacing: 7
                            visible: root.page === "NET"

                            Text {
                                text: "NETWORK SEAM"
                                color: root.ledgerGreen
                                font.family: "monospace"
                                font.pixelSize: 11
                                font.bold: true
                            }
                            Text {
                                width: parent.width
                                text: "MODE          " + String(root.network.mode || "LOCAL_LOOPBACK")
                                    + "\nTRANSPORT     " + String(root.network.transport || "NOT_CONNECTED")
                                    + "\nSERVER        " + (root.network.authoritative_server ? "YES" : "NO")
                                    + "\nSNAPSHOT HZ   " + String(root.network.snapshot_hz || 20)
                                    + "\nSEQUENCE      " + String(root.network.sequence || 0)
                                    + "\nEST. BYTES    " + String(root.network.estimated_bytes || 0)
                                    + "\nINTEREST      " + String(root.network.interest_entities || 0)
                                color: root.text
                                font.family: "monospace"
                                font.pixelSize: 10
                            }
                            Row {
                                width: parent.width
                                spacing: 5
                                GgButton {
                                    text: "SAVE MEMORY"
                                    implicitWidth: 104
                                    implicitHeight: 25
                                    onClicked: root.saveGameState()
                                }
                                GgButton {
                                    text: "LOAD MEMORY"
                                    implicitWidth: 104
                                    implicitHeight: 25
                                    onClicked: root.loadGameState()
                                }
                            }
                            Text {
                                width: parent.width
                                text: "PERSISTENCE " + String(root.network.persistence
                                    ? root.network.persistence.mode : "MEMORY_ONLY")
                                    + " · REV " + String(root.network.persistence
                                        ? root.network.persistence.revision : 0)
                                    + "\nNo live server, sockets or account access are enabled."
                                color: root.muted
                                wrapMode: Text.WordWrap
                                font.family: "monospace"
                                font.pixelSize: 10
                            }
                        }

                        Column {
                            width: parent.width
                            spacing: 7
                            visible: root.page === "ASSETS"

                            Text {
                                text: "ASSET / RUNTIME BOUNDARY"
                                color: root.ledgerGreen
                                font.family: "monospace"
                                font.pixelSize: 11
                                font.bold: true
                            }
                            Text {
                                width: parent.width
                                text: "FORMAT         " + String(root.selectedAsset.format || "-")
                                    + "\nSOURCE         " + String(
                                        root.selectedAsset.relative_source || "none"
                                    )
                                    + "\nSTATUS         " + String(
                                        root.selectedAsset.status || "NO_ASSET"
                                    )
                                    + " · " + String(
                                        root.selectedAsset.mode || "PREVIEW_FALLBACK"
                                    )
                                    + "\nRUNTIME        QtQuick3D RuntimeLoader"
                                color: root.text
                                font.family: "monospace"
                                font.pixelSize: 10
                            }
                            Text {
                                width: parent.width
                                text: "SKIN           " + String(
                                        root.selectedAsset.skinned ? "READY" : "NO"
                                    )
                                    + " · " + String(
                                        root.selectedAsset.skeleton
                                            ? root.selectedAsset.skeleton.joints : 0
                                    ) + " joints · " + String(
                                        root.selectedAsset.vertices || 0
                                    ) + " vertices"
                                    + "\nCLIPS          " + root.assetClipSummary()
                                    + "\nAUTHORED       " + String(
                                        root.render.asset_instances
                                            ? root.render.asset_instances.authored_requested
                                            : 0
                                    ) + "/" + String(root.assetInstanceBudget)
                                    + " instances"
                                    + "\nCHARACTERS     one active low-poly model"
                                    + "\nCROWD          " + String(
                                        root.assets.crowd_selected
                                            ? root.assets.crowd_selected.mode
                                            : "NO_ASSET"
                                    ) + " · " + String(
                                        root.assets.crowd_selected
                                            ? root.assets.crowd_selected.animations : 0
                                    ) + " clips"
                                    + "\nSTYLE          " + String(
                                        root.assets.character_style
                                            ? root.assets.character_style.id
                                            : "-"
                                    ) + " · matte faceted"
                                    + "\nPROCEDURAL     " + String(
                                        root.render.asset_instances
                                            ? root.render.asset_instances
                                                .procedural_requested : 0
                                    ) + " active · " + String(
                                        root.assets.character_style
                                            ? root.assets.character_style.crowd_triangle_budget
                                            : 0
                                    ) + " tris"
                                    + "\nPOSE SEAM      IDLE/WALK/SPRINT/AIR → fixed-step geometry/timeline"
                                color: root.ledgerGreen
                                font.family: "monospace"
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }
                            Text {
                                width: parent.width
                                text: "CONTENT       " + String(root.content.abilities || 0)
                                    + " abilities · " + String(root.content.items || 0) + " items"
                                    + "\nRECIPES       " + String(root.content.recipes || 0)
                                    + " · AFFIXES " + String(root.content.affixes || 0)
                                    + "\nGEAR          " + String(root.content.gear_slots || 0)
                                    + " slots · " + String(root.content.runes || 0)
                                    + " runes · " + String(root.content.gems || 0)
                                    + " gems · " + String(root.content.runewords || 0)
                                    + " runewords"
                                    + "\nCRAFTING      " + String(root.content.workstations || 0)
                                    + " stations · " + String(root.content.gear_recipes || 0)
                                    + " recipes · " + String(root.content.gear_materials || 0)
                                    + " materials"
                                    + "\nCLASS         " + String(root.progression.class_id || "-")
                                    + " / " + String(root.progression.spec || "-")
                                    + "\nTALENTS       " + String(root.progression.talent_points || 0)
                                    + " points · ASC " + String(root.progression.ascension || 0)
                                color: root.ledgerGold
                                font.family: "monospace"
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }
                            Text {
                                width: parent.width
                                text: "ITEM GRAPH    " + String(
                                        root.items.catalog
                                            ? root.items.catalog.definitions : 0
                                    ) + " definitions · " + String(
                                        root.items.catalog
                                            ? root.items.catalog.loot_tables : 0
                                    ) + " loot tables"
                                    + "\n3D STATES     GROUND · CONTAINER · INVENTORY"
                                    + " · EQUIPPED · POCKET"
                                    + "\nRARITY        TRASH · COMMON · UNCOMMON · RARE"
                                    + " · EPIC · LEGENDARY · ARTIFACT"
                                    + "\nWORLD         " + String(
                                        root.items.counts
                                            ? root.items.counts.player_owned : 0
                                    ) + " player-owned · " + String(
                                        root.items.instances || 0
                                    ) + " live instances"
                                    + "\nAUTHORED ITEM " + String(
                                        root.render.item_asset_instances
                                            ? root.render.item_asset_instances.authored_requested
                                            : 0
                                    ) + "/" + String(
                                        root.render.item_asset_instances
                                            ? root.render.item_asset_instances.budget : 0
                                    ) + " RuntimeLoader · " + String(
                                        root.render.item_asset_instances
                                            ? root.render.item_asset_instances.primitive_fallback : 0
                                    ) + " primitive fallback"
                                    + "\nLIFE          " + String(root.life.population || 0)
                                    + " proxies · " + String(root.life.clock
                                        ? root.life.clock.phase : "-")
                                    + " · " + String(root.life.simulation || "-")
                                    + "\nASSET TABLE   " + String(root.items.catalog
                                        ? root.items.catalog.asset_rows : 0)
                                    + " rows · " + String(root.items.catalog
                                        ? root.items.catalog.insertables : 0)
                                    + " insertables"
                                color: root.signalViolet
                                font.family: "monospace"
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }
                            Row {
                                width: parent.width
                                spacing: 4
                                Text {
                                    text: "RACE"
                                    color: root.muted
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                    verticalAlignment: Text.AlignVCenter
                                }
                                Repeater {
                                    model: ["ISLANDER", "TIDEBORN", "SKYKIN"]
                                    delegate: GgButton {
                                        required property string modelData
                                        text: modelData
                                        implicitWidth: 62
                                        implicitHeight: 24
                                        checked: root.progression.race === modelData
                                        onClicked: root.selectRace(modelData)
                                    }
                                }
                            }
                            Row {
                                width: parent.width
                                spacing: 4
                                Text {
                                    text: "SPEC"
                                    color: root.muted
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                    verticalAlignment: Text.AlignVCenter
                                }
                                Repeater {
                                    model: ["EXPLORER", "WARDEN", "DUELIST"]
                                    delegate: GgButton {
                                        required property string modelData
                                        text: modelData
                                        implicitWidth: 62
                                        implicitHeight: 24
                                        checked: root.progression.spec === modelData
                                        onClicked: root.selectSpec(modelData)
                                    }
                                }
                            }
                            Text {
                                width: parent.width
                                text: "CAPABILITIES"
                                color: root.ledgerGold
                                font.family: "monospace"
                                font.pixelSize: 10
                                font.bold: true
                            }
                            Repeater {
                                model: root.capabilities
                                delegate: Text {
                                    required property string modelData
                                    width: parent.width
                                    text: "· " + modelData
                                    color: root.text
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                }
                            }
                            Text {
                                width: parent.width
                                text: "ALLOWLIST       local glTF 2.0 · max 8 authored instances\nThe bundled hero is a seam fixture, not final production art."
                                color: root.muted
                                wrapMode: Text.WordWrap
                                font.family: "monospace"
                                font.pixelSize: 10
                            }
                        }

                        Column {
                            width: parent.width
                            spacing: 7
                            visible: root.page === "UI"

                            Text {
                                text: "UI / ADDONS"
                                color: root.ledgerGreen
                                font.family: "monospace"
                                font.pixelSize: 11
                                font.bold: true
                            }
                            Text {
                                width: parent.width
                                text: "OSINT OVERLAY  24%  ·  DATA-FIRST  ·  EVENT-DRIVEN"
                                    + "\nUNIT FRAMES  " + (
                                        root.addonEnabled("UNIT_FRAMES")
                                            ? "VISIBLE" : "HIDDEN"
                                    )
                                    + "  ·  MEMORY " + String(
                                        root.addonState.active_memory_budget_kb || 0
                                    ) + " KB"
                                color: root.muted
                                font.family: "monospace"
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                text: "KEYBINDINGS  ·  WOW CLASSIC"
                                color: root.ledgerGold
                                font.family: "monospace"
                                font.pixelSize: 10
                                font.bold: true
                            }

                            Repeater {
                                model: root.bindingRows()
                                delegate: Row {
                                    required property var modelData
                                    width: parent.width
                                    spacing: 4

                                    Text {
                                        width: parent.width - 78
                                        text: modelData.label
                                        color: root.text
                                        font.family: "monospace"
                                        font.pixelSize: 9
                                        verticalAlignment: Text.AlignVCenter
                                        elide: Text.ElideRight
                                    }
                                    GgButton {
                                        text: root.bindingCaptureAction === modelData.id
                                            ? "PRESS…"
                                            : root.keysFor(modelData.id)
                                        implicitWidth: 74
                                        implicitHeight: 22
                                        checked: root.bindingCaptureAction === modelData.id
                                        onClicked: {
                                            root.bindingCaptureAction = modelData.id
                                            root.forceActiveFocus()
                                        }
                                    }
                                }
                            }

                            Row {
                                width: parent.width
                                spacing: 5
                                GgButton {
                                    text: "RESET BINDS"
                                    implicitWidth: 104
                                    implicitHeight: 24
                                    onClicked: root.resetKeybindings()
                                }
                                Text {
                                    width: parent.width - 109
                                    text: root.bindingCaptureAction !== ""
                                        ? "PRESS A KEY…"
                                        : "Q/E STRAFE · A/D TURN"
                                    color: root.bindingCaptureAction !== ""
                                        ? root.ledgerGold : root.muted
                                    font.family: "monospace"
                                    font.pixelSize: 9
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                            }

                            Rectangle {
                                width: parent.width
                                height: 1
                                color: "#333333"
                            }

                            Text {
                                text: "BUILT-IN ADDONS"
                                color: root.ledgerGold
                                font.family: "monospace"
                                font.pixelSize: 10
                                font.bold: true
                            }

                            Repeater {
                                model: root.addonState.addons || []
                                delegate: Row {
                                    required property var modelData
                                    width: parent.width
                                    spacing: 4

                                    GgButton {
                                        text: modelData.enabled ? "ON" : "OFF"
                                        implicitWidth: 38
                                        implicitHeight: 22
                                        checked: Boolean(modelData.enabled)
                                        onClicked: root.toggleAddon(
                                            modelData.id,
                                            modelData.enabled
                                        )
                                    }
                                    Column {
                                        width: parent.width - 42
                                        spacing: 1
                                        Text {
                                            width: parent.width
                                            text: String(modelData.name || modelData.id)
                                            color: root.text
                                            font.family: "monospace"
                                            font.pixelSize: 9
                                            elide: Text.ElideRight
                                        }
                                        Text {
                                            width: parent.width
                                            text: String(modelData.category || "UI")
                                                + " · " + String(
                                                    modelData.memory_budget_kb || 0
                                                ) + " KB · " + String(
                                                    modelData.status || "DISABLED"
                                                )
                                            color: root.muted
                                            font.family: "monospace"
                                            font.pixelSize: 8
                                            elide: Text.ElideRight
                                        }
                                    }
                                }
                            }

                            Text {
                                width: parent.width
                                text: "ADDON ABI  " + String(
                                    root.addonState.execution
                                        || "NATIVE_DATA_ONLY_EVENT_DRIVEN"
                                )
                                    + "\nTHIRD PARTY  " + String(
                                        root.addonState.third_party
                                            ? root.addonState.third_party.status
                                            : "NOT_ENABLED"
                                    )
                                color: root.muted
                                font.family: "monospace"
                                font.pixelSize: 9
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }
            }
        }
    }
}
