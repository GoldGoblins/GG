pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick3D

Item {
    id: root
    objectName: "workspaceGameEnginePane"

    property var surfaceHost: null
    property color frameBorder: "#6a6a6a"
    property int frameRadius: 4
    property string statusJson: "{}"
    property string page: "PLAY"
    property real throttle: 0
    property real steer: 0
    property real brake: 0
    property bool boost: false
    property real orbitYaw: 0
    property real cameraDistance: 34
    property real cameraHeight: 23

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
    readonly property var nav: ["PLAY", "SCENE", "PERF", "NET", "ASSETS"]

    readonly property var status: {
        try {
            return JSON.parse(root.statusJson || "{}")
        } catch (err) {
            return {}
        }
    }
    readonly property var simulation: root.status.simulation || ({})
    readonly property var player: root.status.player || ({})
    readonly property var render: root.status.render || ({})
    readonly property var network: root.status.network || ({})
    readonly property var replay: root.status.replay || ({})
    readonly property var chunks: root.status.chunks || ({})
    readonly property var events: root.status.events || []
    readonly property var capabilities: root.status.capabilities || []
    readonly property var renderEntities: root.render.entities || []
    readonly property var renderParticles: root.render.particles || []
    readonly property bool stress: Boolean(root.status.stress)
    readonly property bool running: String(root.status.state || "") === "RUNNING"
    readonly property bool recording: Boolean(root.replay.recording)
    readonly property bool replaying: Boolean(root.replay.replaying)
    readonly property string legend: root.stress
        ? "LOCAL · STRESS"
        : "LOCAL · FIXED 60 HZ"

    function applyRaw(raw) {
        if (raw === undefined || raw === null)
            return
        root.statusJson = String(raw)
    }

    function refresh() {
        if (root.surfaceHost && root.surfaceHost.gameEngineStatus)
            root.applyRaw(root.surfaceHost.gameEngineStatus())
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

    function sendInput() {
        if (!root.surfaceHost || !root.surfaceHost.gameEngineInput)
            return
        root.applyRaw(root.surfaceHost.gameEngineInput(JSON.stringify({
            throttle: root.throttle,
            steer: root.steer,
            brake: root.brake,
            boost: root.boost
        })))
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

    function percent(value, maximum) {
        var max = Math.max(1, number(maximum, 1))
        return Math.max(0, Math.min(1, number(value, 0) / max))
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

    function setKeyState(key, pressed) {
        if (key === Qt.Key_Up || key === Qt.Key_W)
            root.throttle = pressed ? 1 : 0
        else if (key === Qt.Key_Down)
            root.brake = pressed ? 1 : 0
        else if (key === Qt.Key_S)
            root.throttle = pressed ? -1 : 0
        else if (key === Qt.Key_Left || key === Qt.Key_A)
            root.steer = pressed ? -1 : 0
        else if (key === Qt.Key_Right || key === Qt.Key_D)
            root.steer = pressed ? 1 : 0
        else if (key === Qt.Key_Space)
            root.boost = pressed
        else
            return false
        root.sendInput()
        return true
    }

    focus: true
    activeFocusOnTab: true

    Timer {
        id: refreshTimer
        interval: 90
        repeat: true
        running: root.visible
            && root.surfaceHost !== null
            && (root.running || root.replaying)
        onTriggered: root.refresh()
    }

    Component.onCompleted: {
        root.refresh()
        root.forceActiveFocus()
    }

    onPageChanged: root.refresh()
    onVisibleChanged: {
        if (visible) {
            root.refresh()
            root.forceActiveFocus()
        }
    }

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
            color: root.panel
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
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: 124
                color: root.panel
                border.color: "#333333"
                border.width: 1

                Column {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 8
                    spacing: 3

                    Text {
                        width: parent.width
                        height: 25
                        text: "☰"
                        color: root.ink
                        font.pixelSize: 18
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    Repeater {
                        model: root.nav

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

                Column {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.margins: 10
                    spacing: 4

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
                anchors.left: sidebar.right
                anchors.right: inspector.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.leftMargin: 8
                anchors.rightMargin: 8

                View3D {
                    id: view3d
                    anchors.fill: parent
                    environment: SceneEnvironment {
                        clearColor: "#0d1012"
                        backgroundMode: SceneEnvironment.Color
                    }

                    PerspectiveCamera {
                        id: camera
                        position: Qt.vector3d(
                            root.number(root.player.x, 0)
                                + Math.sin(root.orbitYaw * Math.PI / 180)
                                    * root.cameraDistance,
                            root.cameraHeight,
                            root.number(root.player.z, 0)
                                + Math.cos(root.orbitYaw * Math.PI / 180)
                                    * root.cameraDistance
                        )
                        eulerRotation: Qt.vector3d(-27, root.orbitYaw, 0)
                        clipNear: 0.1
                        clipFar: 180
                    }

                    DirectionalLight {
                        eulerRotation: Qt.vector3d(-48, -28, 0)
                        brightness: 1.35
                        color: "#e8e1d2"
                    }

                    PointLight {
                        position: Qt.vector3d(0, 14, 4)
                        brightness: 20
                        color: "#c8a97e"
                        quadraticFade: 0.015
                    }

                    Model {
                        source: "#Cube"
                        position: Qt.vector3d(0, -0.3, 0)
                        scale: Qt.vector3d(60, 0.1, 60)
                        materials: [
                            PrincipledMaterial {
                                baseColor: "#202827"
                                roughness: 0.92
                            }
                        ]
                    }

                    Model {
                        source: "#Cube"
                        position: Qt.vector3d(0, -0.22, 0)
                        scale: Qt.vector3d(3.1, 0.06, 60)
                        materials: [
                            PrincipledMaterial {
                                baseColor: "#2a2b29"
                                roughness: 0.85
                            }
                        ]
                    }

                    Repeater {
                        model: root.renderEntities

                        delegate: Model {
                            id: entityModel
                            required property var modelData
                            property color tint: String(
                                entityModel.modelData.color || "#8fa8a0"
                            )
                            source: "#Cube"
                            position: Qt.vector3d(
                                root.number(entityModel.modelData.x, 0),
                                root.number(entityModel.modelData.y, 0),
                                root.number(entityModel.modelData.z, 0)
                            )
                            scale: Qt.vector3d(
                                Math.max(0.12, root.number(entityModel.modelData.sx, 1)),
                                Math.max(0.12, root.number(entityModel.modelData.sy, 1)),
                                Math.max(0.12, root.number(entityModel.modelData.sz, 1))
                            )
                            eulerRotation.y:
                                root.number(entityModel.modelData.yaw, 0)
                                * 57.2958
                            materials: [
                                PrincipledMaterial {
                                    baseColor: entityModel.tint
                                    roughness: entityModel.modelData.kind === "PLAYER"
                                        ? 0.48 : 0.86
                                    metalness: entityModel.modelData.kind === "PLAYER"
                                        ? 0.22 : 0.04
                                }
                            ]
                        }
                    }

                    Repeater {
                        model: root.renderParticles

                        delegate: Model {
                            id: particleModel
                            required property var modelData
                            property color tint: String(
                                particleModel.modelData.color || "#c8a97e"
                            )
                            source: "#Cube"
                            position: Qt.vector3d(
                                root.number(particleModel.modelData.x, 0),
                                root.number(particleModel.modelData.y, 0),
                                root.number(particleModel.modelData.z, 0)
                            )
                            scale: Qt.vector3d(0.11, 0.11, 0.11)
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

                MouseArea {
                    id: cameraMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: pressed
                        ? Qt.ClosedHandCursor
                        : Qt.OpenHandCursor
                    property real dragStartX: 0
                    property real dragStartYaw: 0

                    onPressed: function(mouse) {
                        root.forceActiveFocus()
                        dragStartX = mouse.x
                        dragStartYaw = root.orbitYaw
                    }

                    onPositionChanged: function(mouse) {
                        if (pressed)
                            root.orbitYaw = dragStartYaw
                                + (mouse.x - dragStartX) * 0.55
                    }

                    onWheel: function(wheel) {
                        root.cameraDistance = Math.max(
                            14,
                            Math.min(58, root.cameraDistance
                                - Number(wheel.angleDelta.y) / 120 * 2)
                        )
                        wheel.accepted = true
                    }
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.margins: 12
                    width: hudColumn.implicitWidth + 18
                    height: hudColumn.implicitHeight + 12
                    color: "#121617cc"
                    border.color: "#4a514f"
                    border.width: 1
                    radius: 2
                    opacity: 0.95

                    Column {
                        id: hudColumn
                        anchors.centerIn: parent
                        spacing: 3

                        Text {
                            text: "PLAYGROUND · " + String(root.status.state || "IDLE")
                            color: root.stateColor(root.status.state)
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
                    }
                }

                Text {
                    anchors.left: parent.left
                    anchors.bottom: parent.bottom
                    anchors.margins: 12
                    text: "WASD / ARROWS · SPACE BOOST · DRAG ORBIT · WHEEL ZOOM"
                    color: root.muted
                    font.family: "monospace"
                    font.pixelSize: 10
                }
            }

            Rectangle {
                id: inspector
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: Math.max(260, Math.min(330, parent.width * 0.29))
                color: root.panel
                border.color: "#333333"
                border.width: 1

                Flickable {
                    anchors.fill: parent
                    anchors.margins: 10
                    clip: true
                    contentWidth: width
                    contentHeight: inspectorColumn.height
                    boundsBehavior: Flickable.StopAtBounds

                    Column {
                        id: inspectorColumn
                        width: parent.width
                        spacing: 10

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
                                text: "INPUT  T " + root.fixed(root.throttle, 1)
                                    + "  S " + root.fixed(root.steer, 1)
                                    + "  B " + root.fixed(root.brake, 1)
                                    + "  BOOST " + (root.boost ? "ON" : "OFF")
                                color: root.text
                                font.family: "monospace"
                                font.pixelSize: 10
                            }

                            Text {
                                width: parent.width
                                text: "TICK " + String(root.simulation.tick || 0)
                                    + "  TIME " + root.fixed(root.simulation.time_s, 2) + "s"
                                    + "\nEVENTS " + String(root.events.length || 0)
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
                                color: root.text
                                font.family: "monospace"
                                font.pixelSize: 10
                            }
                            Repeater {
                                model: root.renderEntities.slice(0, 20)
                                delegate: Rectangle {
                                    required property var modelData
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
                                    + "\nLAST TICK    " + root.fixed(root.simulation.last_tick_ms, 3) + " ms"
                                    + "\nMAX TICK     " + root.fixed(root.simulation.max_tick_ms, 3) + " ms"
                                    + "\nDRAW CALLS   " + String(root.render.draw_calls || 0)
                                color: root.text
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
                            Text {
                                width: parent.width
                                text: "This is an integration seam only. No live server, sockets or account access are enabled."
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
                                text: "BUILTINS       QtQuick3D primitives\nEXTERNAL       none bundled\nLEGAL ASSETS   user-supplied only\nRUNTIME        Python local preview"
                                color: root.text
                                font.family: "monospace"
                                font.pixelSize: 10
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
                                text: "The first slice is intentionally asset-light: mechanics, budgets and inspection come before a content pipeline."
                                color: root.muted
                                wrapMode: Text.WordWrap
                                font.family: "monospace"
                                font.pixelSize: 10
                            }
                        }
                    }
                }
            }
        }
    }
}
