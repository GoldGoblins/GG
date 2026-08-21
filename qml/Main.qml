pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Window
import "components"

ApplicationWindow {
    id: root

    property string workbenchVersion: "1.1"
    property string dataMode: "LOCAL_UI_ONLY"
    property string interactionModel: "GG_INTENT_NATIVE_DESKTOP"
    property string visualChangePolicy: "PROPOSE_PREVIEW_DISCUSS_APPROVE_APPLY"
    property string operatorTerminalPolicy: "FORBIDDEN"
    property string reasoningEvidencePolicy: "REQUIRED"
    property string liveAidDraftBlocking: "NO"
    property string shadowVerificationMode: "NOT_CONNECTED"

    property string narrowPane: "CHAT"
    property bool bridgeBusy: false
    property bool followChatTail: true
    property string activeTaskId: ""
    property string engineTarget: "LOCAL_QWEN"
    property string lastSelectedObjectId: ""
    property real alphaChatWidthRatio: 0.31
    property int alphaTelemetryWidth: 168
    property int alphaUtilityHeight: 112
    property bool alphaShowDemoFixtures: false
    property bool showProductSourceTabs: false
    property var surfaceHost: null
    property string grokWalletJson: "{}"
    property string chatSessionsJson: "[]"
    property string activeChatSession: ""
    readonly property int alphaBottomStripMargin: 8

    readonly property bool narrowLayout: width < 1050
    readonly property bool compactTelemetry: width < 1450

    readonly property color canvas: "#121212"
    readonly property color surface: "#161616"
    readonly property color line: "#6a6a6a"
    readonly property color textMain: "#e6e6e6"
    readonly property color textMuted: "#8a8a8a"
    property color cyan: "#8a8a8a"
    property color frameBorder: "#6a6a6a"
    property int frameRadius: 2
    property bool showOpenTabInInput: false
    property bool showInnerEditorChrome: true
    readonly property color violet: "#b6a6c8"
    readonly property color green: "#8db89a"
    readonly property color amber: "#c8a97e"

    signal bridgeSubmit(
        string text,
        string contextReference,
        string workspaceObjectId
    )
    signal contextSnapshotSync(string snapshotJson)
    signal bridgeStop()
    signal bridgeAssignmentSet(
        string participant,
        string creatorActor
    )
    signal bridgeAssignmentClear()

    Connections {
        target: root.surfaceHost
        function onGrokWalletChanged(payload) {
            root.grokWalletJson = payload
        }
        function onChatSessionsChanged(payload) {
            root.chatSessionsJson = payload
            try {
                var rows = JSON.parse(payload || "[]")
                var i
                for (i = 0; i < rows.length; i++) {
                    if (rows[i] && rows[i].current) {
                        root.activeChatSession = String(rows[i].session_id)
                        break
                    }
                }
            } catch (err) {
            }
        }
    }

    function colorHex(value) {
        var text = String(value || "")
        if (text.length === 9 && text.indexOf("#ff") === 0)
            return "#" + text.slice(3)
        if (text.length === 9 && text.indexOf("#FF") === 0)
            return "#" + text.slice(3)
        if (text.length >= 7 && text.charAt(0) === "#")
            return text.slice(0, 7)
        return text
    }

    function persistDesktopSettings() {
        if (!root.surfaceHost)
            return
        root.surfaceHost.saveDesktopSettings(JSON.stringify({
            "engineTarget": root.engineTarget,
            "chatWidthRatio": root.alphaChatWidthRatio,
            "telemetryWidth": root.alphaTelemetryWidth,
            "utilityHeight": root.alphaUtilityHeight,
            "accentColor": root.colorHex(root.cyan),
            "frameBorder": root.colorHex(root.frameBorder),
            "frameRadius": root.frameRadius,
            "showOpenTabInInput": root.showOpenTabInInput,
            "showInnerEditorChrome": root.showInnerEditorChrome,
            "showProductSourceTabs": root.showProductSourceTabs,
            "showDemoFixtures": root.alphaShowDemoFixtures
        }))
    }

    title: "GG AI Desktop · Alpha"
    width: 1920
    height: 1080
    minimumWidth: 820
    minimumHeight: 620
    visibility: Window.Maximized
    color: root.canvas

    ListModel {
        id: chatModel

        ListElement {
            authorLabel: "GG SYSTEM"
            nodeKind: "BASELINE"
            bodyText: "Local alpha is ready. @current follows the active real Workspace object. Local Chat Bridge is connected."
            contextReference: "@workspace"
            provenanceClass: "REAL_UI_STATE"
            stateLabel: "READY"
            laneOffset: 0
            taskId: ""
            workStagesJson: ""
            workCardsJson: ""
        }
    }

    function upsertAutonomyNode(
        taskId,
        phase,
        stateLabel,
        stageText,
        contextReference
    ) {
        for (var i = chatModel.count - 1; i >= 0; --i) {
            var item = chatModel.get(i)

            if (item.nodeKind === "AUTONOMY" && item.taskId === taskId) {
                var current = {}

                if (item.workStagesJson && item.workStagesJson.length > 0)
                    current = JSON.parse(item.workStagesJson)

                current[phase] = {
                    "phase": phase,
                    "state": stateLabel,
                    "text": stageText
                }

                chatModel.setProperty(
                    i,
                    "workStagesJson",
                    JSON.stringify(current)
                )
                chatModel.setProperty(i, "stateLabel", stateLabel)
                return
            }
        }

        var first = {}

        first[phase] = {
            "phase": phase,
            "state": stateLabel,
            "text": stageText
        }

        chatModel.append({
            "authorLabel": "GG AI",
            "nodeKind": "AUTONOMY",
            "bodyText": "",
            "contextReference": contextReference,
            "provenanceClass": "REAL_UI_STATE",
            "stateLabel": stateLabel,
            "laneOffset": 28,
            "taskId": taskId,
            "workStagesJson": JSON.stringify(first)
        })

        root.scrollChatToLatest()
    }

    function boundedContextString(value, maximum) {
        if (value === undefined || value === null)
            return ""

        return String(value).slice(0, maximum)
    }

    function buildContextSnapshotJson() {
        var workspaceSnapshot = workspace.contextSnapshot(32)
        var recentChat = []
        var start = Math.max(
            0,
            chatModel.count - 12
        )

        for (var i = start; i < chatModel.count; ++i) {
            var item = chatModel.get(i)

            recentChat.push({
                "authorLabel": root.boundedContextString(
                    item.authorLabel,
                    1024
                ),
                "nodeKind": root.boundedContextString(
                    item.nodeKind,
                    1024
                ),
                "bodyText": root.boundedContextString(
                    item.bodyText,
                    2000
                ),
                "contextReference": root.boundedContextString(
                    item.contextReference,
                    1024
                ),
                "provenanceClass": root.boundedContextString(
                    item.provenanceClass,
                    1024
                )
            })
        }

        return JSON.stringify({
            "schema": "gg.workbench.context-snapshot.v1",
            "workspace": workspaceSnapshot,
            "recentChat": recentChat
        })
    }

    function parseWorkCards(raw) {
        if (raw === undefined || raw === null || String(raw).length === 0)
            return []

        try {
            var parsed = JSON.parse(String(raw))
            if (parsed !== null && typeof parsed === "object" && parsed.length !== undefined)
                return parsed
        } catch (parseError) {
            return []
        }

        return []
    }

    function beginGrokWorkerStream(requestId, contextReference) {
        for (var i = chatModel.count - 1; i >= 0; --i) {
            var existing = chatModel.get(i)
            if (
                existing.nodeKind === "GROK_STREAM"
                && existing.taskId === requestId
            )
                return
        }

        var streamContext = contextReference
        if (workspace.currentObjectTitle.length > 0)
            streamContext = contextReference
                + " · "
                + workspace.currentObjectTitle

        chatModel.append({
            "authorLabel": "GG AI",
            "nodeKind": "GROK_STREAM",
            "bodyText": "",
            "contextReference": streamContext,
            "provenanceClass": "REAL_UI_STATE",
            "stateLabel": "STARTING",
            "laneOffset": 28,
            "taskId": requestId,
            "workStagesJson": "",
            "workCardsJson": "[]"
        })
        root.scrollChatToLatest()
    }

    function chatFenceLooksLikeShell(body) {
        var text = String(body || "").replace(/^\s+/, "")
        if (text.length === 0)
            return false
        if (text.indexOf("$ ") === 0)
            return true
        var first = text.split(" ")[0]
        return (
            first === "echo"
            || first === "pwd"
            || first === "date"
            || first === "ls"
            || first === "cat"
            || first === "cd"
        )
    }

    function chatFenceIsEditorCode(lang) {
        var name = String(lang || "").toLowerCase()
        return (
            name === "qml"
            || name === "javascript"
            || name === "js"
            || name === "typescript"
            || name === "ts"
            || name === "python"
            || name === "py"
            || name === "json"
            || name === "css"
            || name === "html"
            || name === "php"
            || name === "c"
            || name === "cpp"
            || name === "h"
            || name === "rs"
            || name === "rust"
            || name === "go"
            || name === "java"
            || name === "xml"
            || name === "yaml"
            || name === "yml"
            || name === "sql"
            || name === "lua"
            || name === "vue"
        )
    }

    function extractEditorCodeFence(kind, title, text) {
        var body = String(text || "")
        var label = String(title || "").toLowerCase()
        if (kind === "stdout" || kind === "thought" || kind === "error")
            return ""
        if (label === "diff")
            return root.diffAddedSource(body)
        if (
            label === "terminal"
            || label.indexOf("read") === 0
            || label.indexOf("grep") === 0
        )
            return ""
        var rest = body
        var last = ""
        while (rest.length > 0) {
            var start = rest.indexOf("```")
            if (start < 0)
                break
            var after = rest.slice(start + 3)
            var nl = after.indexOf("\n")
            if (nl < 0)
                break
            var lang = after.slice(0, nl).trim()
            var tail = after.slice(nl + 1)
            var closer = tail.indexOf("```")
            if (closer < 0)
                break
            var chunk = tail.slice(0, closer).replace(/\s+$/, "")
            if (lang.toLowerCase() === "diff") {
                var added = root.diffAddedSource(chunk)
                if (added.length > 0)
                    last = added
            } else if (
                chunk.length > 0
                && root.chatFenceIsEditorCode(lang)
                && !root.chatFenceLooksLikeShell(chunk)
            )
                last = chunk
            rest = tail.slice(closer + 3)
        }
        if (last.length > 0)
            return last
        if (
            kind === "code"
            && body.indexOf("function") >= 0
            && !root.chatFenceLooksLikeShell(body)
        )
            return body
        return ""
    }

    function diffAddedSource(body) {
        var lines = String(body || "").split("\n")
        var added = []
        for (var i = 0; i < lines.length; ++i) {
            var line = lines[i]
            if (
                line.indexOf("+++") === 0
                || line.indexOf("---") === 0
                || line.indexOf("@@") === 0
            )
                continue
            if (line.charAt(0) === "+")
                added.push(line.slice(1))
        }
        return added.join("\n").replace(/\s+$/, "")
    }

    function applyChatFenceToScratch(kind, title, text) {
        var source = root.extractEditorCodeFence(kind, title, text)
        if (source.length === 0)
            return false
        if (workspace && workspace.applyChatCodeToCurrent)
            return workspace.applyChatCodeToCurrent(source)
        return false
    }

    function upsertGrokWorkerCard(
        requestId,
        cardId,
        kind,
        title,
        text,
        state
    ) {
        for (var i = chatModel.count - 1; i >= 0; --i) {
            var item = chatModel.get(i)
            if (
                !root.isGrokStreamNode(item.nodeKind)
                || item.taskId !== requestId
            )
                continue

            var cards = root.parseWorkCards(item.workCardsJson)
            var found = false
            var card = {
                "id": cardId,
                "kind": kind,
                "title": title,
                "text": text,
                "state": state
            }

            for (var j = 0; j < cards.length; ++j) {
                if (String(cards[j].id) === String(cardId)) {
                    var previousTitle = String(cards[j].title || "")
                    if (
                        (
                            String(title || "") === "tool"
                            || String(title || "").length === 0
                        )
                        && previousTitle.length > 0
                        && previousTitle !== "tool"
                    )
                        card.title = previousTitle
                    cards[j] = card
                    found = true
                    break
                }
            }

            if (!found)
                cards.push(card)

            chatModel.setProperty(
                i,
                "workCardsJson",
                JSON.stringify(cards)
            )
            chatModel.setProperty(i, "stateLabel", state)
            root.applyChatFenceToScratch(kind, title, text)
            root.scrollChatToLatest()
            return true
        }

        return false
    }

    function updateGrokWorkerState(requestId, stateLabel) {
        for (var i = chatModel.count - 1; i >= 0; --i) {
            var item = chatModel.get(i)
            if (
                root.isGrokStreamNode(item.nodeKind)
                && item.taskId === requestId
            ) {
                chatModel.setProperty(i, "stateLabel", stateLabel)
                return true
            }
        }

        return false
    }

    function beginStreamingResponse(requestId, contextReference) {
        for (var i = chatModel.count - 1; i >= 0; --i) {
            var existing = chatModel.get(i)
            if (
                root.isGrokStreamNode(existing.nodeKind)
                && existing.taskId === requestId
            )
                return
        }

        var streamContext = contextReference
        if (workspace.currentObjectTitle.length > 0)
            streamContext = contextReference
                + " · "
                + workspace.currentObjectTitle

        chatModel.append({
            "authorLabel": "GG AI",
            "nodeKind": "STREAM",
            "bodyText": "",
            "contextReference": streamContext,
            "provenanceClass": "REAL_UI_STATE",
            "stateLabel": "STARTING",
            "laneOffset": 28,
            "taskId": requestId,
            "workStagesJson": "",
            "workCardsJson": "[]"
        })
        root.scrollChatToLatest()
    }

    function updateStreamingResponse(requestId, bodyText, stateLabel) {
        for (var i = chatModel.count - 1; i >= 0; --i) {
            var item = chatModel.get(i)
            if (
                item.taskId !== requestId
                || (
                    item.nodeKind !== "RESPONSE"
                    && !root.isGrokStreamNode(item.nodeKind)
                )
            )
                continue
            chatModel.setProperty(i, "bodyText", bodyText)
            chatModel.setProperty(i, "stateLabel", stateLabel)
            root.scrollChatToLatest()
            return true
        }
        return false
    }

  function appendRealNode(
        authorLabel,
        nodeKind,
        bodyText,
        contextReference,
        stateLabel,
        laneOffset,
        taskId
    ) {
        chatModel.append({
            "authorLabel": authorLabel,
            "nodeKind": nodeKind,
            "bodyText": bodyText,
            "contextReference": contextReference,
            "provenanceClass": "REAL_UI_STATE",
            "stateLabel": stateLabel,
            "laneOffset": laneOffset,
            "taskId": taskId || ""
        })
        root.scrollChatToLatest()
    }

    function isUserChatNode(kind) {
        return kind === "REQUEST"
    }

    function isAiSpeechNode(kind) {
        return kind === "RESPONSE"
    }

    function isActivityNode(kind) {
        return kind !== "REQUEST"
            && kind !== "RESPONSE"
            && kind !== "TOOL"
            && kind !== "GROK_STREAM"
            && kind !== "STREAM"
    }

    function isToolNode(kind) {
        return kind === "TOOL"
    }

    function isGrokStreamNode(kind) {
        return kind === "GROK_STREAM" || kind === "STREAM"
    }

    function countNodeKind(kind) {
        var total = 0
        for (var i = 0; i < chatModel.count; ++i) {
            if (chatModel.get(i).nodeKind === kind)
                total += 1
        }
        return total
    }

    function activeWorkState() {
        if (!root.bridgeBusy)
            return ""

        for (var i = chatModel.count - 1; i >= 0; --i) {
            var item = chatModel.get(i)
            if (
                item.taskId === root.activeTaskId
                && item.stateLabel
                && item.stateLabel.length > 0
            )
                return item.stateLabel
        }

        return "RUNNING"
    }

    function activeWorkLabel() {
        if (!root.bridgeBusy)
            return ""

        var state = root.activeWorkState()
        for (var i = chatModel.count - 1; i >= 0; --i) {
            var item = chatModel.get(i)
            if (item.taskId !== root.activeTaskId)
                continue

            if (root.isGrokStreamNode(item.nodeKind)) {
                var cards = root.parseWorkCards(item.workCardsJson)
                for (var j = cards.length - 1; j >= 0; --j) {
                    var card = cards[j]
                    var kind = String(card.kind || "")
                    if (kind === "end" || kind === "user")
                        continue
                    var title = String(card.title || "")
                    if (kind === "thought")
                        return "Thinking"
                    if (kind === "text")
                        return "Writing"
                    if (
                        kind === "tool_call"
                        || kind === "tool_call_update"
                    ) {
                        if (title.length > 0)
                            return title
                        return "Working"
                    }
                    if (kind === "stdout")
                        return "Terminal"
                }
            }

            if (item.nodeKind === "RESPONSE") {
                if (state === "STARTING")
                    return "Starting"
                if (state === "GENERATING")
                    return "Waiting for response"
                if (state === "STREAMING")
                    return "Writing"
                if (state === "RUNNING")
                    return "Working"
            }
            break
        }

        if (state === "STARTING")
            return "Starting"
        if (state === "GENERATING" || state === "WAITING")
            return "Waiting for response"
        if (state === "STREAMING")
            return "Writing"
        if (state === "STOPPING")
            return "Stopping"
        return state.length > 0 ? state : "Working"
    }

    function latestKindState(kind) {
        for (var i = chatModel.count - 1; i >= 0; --i) {
            var item = chatModel.get(i)
            if (item.nodeKind === kind)
                return item.stateLabel || kind
        }
        return "EMPTY"
    }

    function liveAidWorkVisible() {
        if (
            !workspace.editorLoaded
            || workspace.editorLanguage !== "qml"
        )
            return false

        if (workspace.postDraftBusy)
            return true

        if (
            workspace.preflightState === "RUNNING"
            || workspace.preflightState === "FAIL"
            || workspace.preflightState === "PASS"
        )
            return true

        if (
            workspace.repairState === "RUNNING"
            || workspace.repairState === "READY"
        )
            return true

        return false
    }

    function stickChatToLatest() {
        if (chatFlick.height <= 0)
            return
        chatFlick.contentY = Math.max(
            0,
            chatFlick.contentHeight - chatFlick.height
        )
    }

    function scrollChatToLatest() {
        root.followChatTail = true
        root.stickChatToLatest()
        Qt.callLater(root.stickChatToLatest)
    }

    function setBridgeActivity(busy, taskId) {
        root.bridgeBusy = busy
        root.activeTaskId = busy ? taskId : ""
        if (busy) {
            root.followChatTail = true
            root.scrollChatToLatest()
        }
    }

    Rectangle {
        id: topBar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 52
        color: "#141414"
        border.width: 1
        border.color: root.line

        Row {
            anchors.left: parent.left
            anchors.leftMargin: 16
            anchors.verticalCenter: parent.verticalCenter
            spacing: 14

            Text {
                text: "GG AI DESKTOP"
                color: root.textMain
                font.family: "monospace"
                font.pixelSize: 16
                font.bold: true
            }

            Text {
                text: "OBSIDIAN / LEDGER"
                color: root.textMuted
                font.family: "monospace"
                font.pixelSize: 10
            }

            Text {
                text: "."
                color: "#5d6670"
                font.family: "monospace"
                font.pixelSize: 10
            }

            Text {
                id: settingsButton
                objectName: "topBarSettingsButton"
                text: "SETTINGS"
                color: workspace.settingsOpen ? "#d8dee9" : "#5d6670"
                font.family: "monospace"
                font.pixelSize: 10
                font.bold: workspace.settingsOpen

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: workspace.settingsOpen
                        ? workspace.closeSettings()
                        : workspace.openSettings()
                }
            }
        }

        Row {
            visible: root.narrowLayout
            anchors.centerIn: parent
            spacing: 6

            Button {
                text: "CHAT"
                checkable: true
                checked: root.narrowPane === "CHAT"
                onClicked: root.narrowPane = "CHAT"
            }

            Button {
                text: "WORKSPACE"
                checkable: true
                checked: root.narrowPane === "WORKSPACE"
                onClicked: root.narrowPane = "WORKSPACE"
            }
        }

        Row {
            anchors.right: parent.right
            anchors.rightMargin: 16
            anchors.verticalCenter: parent.verticalCenter
            spacing: 16

            Text {
                text: "LOCAL · ALPHA"
                color: root.cyan
                font.family: "monospace"
                font.pixelSize: 9
            }

            Text {
                text: "AUTHORITY · NONE"
                color: root.amber
                font.family: "monospace"
                font.pixelSize: 9
                font.bold: true
            }
        }
    }

    Item {
        id: body
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: topBar.bottom
        anchors.bottom: parent.bottom
        anchors.margins: 12

        Row {
            anchors.fill: parent
            spacing: 10

            Item {
                id: chatSurface
                objectName: "chatSurface"
                visible: !root.narrowLayout || root.narrowPane === "CHAT"
                width: root.narrowLayout
                    ? body.width
                      : Math.max(
                          420,
                          body.width * root.alphaChatWidthRatio
                      )
                height: body.height
                // A1.2.1.1: GgFrame is visual chrome only.
                GgFrame {
                    id: chatChrome
                    anchors.fill: parent
                    leftLegend: "CHAT · UNIVERSAL OPERATIONAL STREAM"
                    rightLegend: "BRIDGE · CONNECTED"
                    backgroundColor: root.surface
                    borderColor: root.frameBorder
                    radius: root.frameRadius
                }

                GrokTuiHole {
                    id: grokTuiHost
                    objectName: "grokTuiHost"
                    visible: root.engineTarget === "GROK_TUI"
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: composer.top
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    anchors.topMargin: 22
                    anchors.bottomMargin: 2
                    surfaceHost: root.surfaceHost
                }

                Flickable {
                    id: chatFlick
                    objectName: "chatCockpit"
                    visible: root.engineTarget !== "GROK_TUI"
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: chatStatusDock.top
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    anchors.topMargin: 22
                    anchors.bottomMargin: 8
                    clip: true
                    contentWidth: width
                    contentHeight: Math.max(
                        height,
                        streamWrap.height
                    )
                    flickableDirection: Flickable.VerticalFlick
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar {}
                    onContentHeightChanged: {
                        if (root.followChatTail || root.bridgeBusy)
                            root.stickChatToLatest()
                    }
                    onHeightChanged: {
                        if (root.followChatTail || root.bridgeBusy)
                            root.stickChatToLatest()
                    }
                    onMovementStarted: {
                        root.followChatTail = (
                            chatFlick.contentY
                            + chatFlick.height
                            >= chatFlick.contentHeight - 32
                        )
                    }
                    onMovementEnded: {
                        root.followChatTail = (
                            chatFlick.contentY
                            + chatFlick.height
                            >= chatFlick.contentHeight - 32
                        )
                    }

                    Item {
                        id: streamWrap
                        width: chatFlick.width
                        height: Math.max(
                            chatFlick.height,
                            streamColumn.implicitHeight + 16
                        )

                    Column {
                        id: streamColumn
                        objectName: "chatActivityStream"
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        spacing: 8
                        onImplicitHeightChanged: {
                            if (root.followChatTail || root.bridgeBusy)
                                root.stickChatToLatest()
                        }

                        Repeater {
                            model: chatModel

                            delegate: Item {
                                id: streamDelegate
                                required property var model

                                width: streamColumn.width
                                height: {
                                    if (grokStream.visible)
                                        return grokStream.implicitHeight
                                    if (activityEvent.visible)
                                        return activityEvent.implicitHeight
                                    if (toolTerminal.visible)
                                        return toolTerminal.implicitHeight
                                    return speechNode.implicitHeight
                                }

                                GrokWorkStream {
                                    id: grokStream
                                    x: 0
                                    width: Math.min(
                                        parent.width,
                                        parent.width * 0.92
                                    )
                                    visible: root.isGrokStreamNode(
                                        streamDelegate.model.nodeKind
                                    )
                                    height: visible ? implicitHeight : 0
                                    authorLabel: streamDelegate.model.authorLabel
                                    nodeKind: streamDelegate.model.nodeKind
                                    stateLabel: streamDelegate.model.stateLabel
                                    contextReference: streamDelegate.model.contextReference
                                    taskId: streamDelegate.model.taskId || ""
                                    workCardsJson: streamDelegate.model.workCardsJson || "[]"
                                    livePulse: root.bridgeBusy
                                        && streamDelegate.model.taskId === root.activeTaskId
                                    onImplicitHeightChanged: {
                                        if (root.followChatTail || root.bridgeBusy)
                                            root.stickChatToLatest()
                                    }
                                }

                                ChatActivityEvent {
                                    id: activityEvent
                                    x: 0
                                    width: Math.min(
                                        parent.width,
                                        parent.width * 0.92
                                    )
                                    visible: root.isActivityNode(
                                        streamDelegate.model.nodeKind
                                    )
                                    height: visible ? implicitHeight : 0
                                    authorLabel: streamDelegate.model.authorLabel
                                    nodeKind: streamDelegate.model.nodeKind
                                    bodyText: streamDelegate.model.bodyText
                                    stateLabel: streamDelegate.model.stateLabel
                                    contextReference: streamDelegate.model.contextReference
                                    taskId: streamDelegate.model.taskId || ""
                                    workStagesJson: streamDelegate.model.workStagesJson || ""
                                    livePulse: root.bridgeBusy
                                        && streamDelegate.model.taskId === root.activeTaskId
                                }

                                WorkObject {
                                    id: toolTerminal
                                    x: 0
                                    width: Math.min(
                                        parent.width,
                                        parent.width * 0.92
                                    )
                                    visible: root.isToolNode(streamDelegate.model.nodeKind)
                                    objectType: {
                                        var body = String(
                                            streamDelegate.model.bodyText || ""
                                        )
                                        if (body.indexOf("READ ") === 0)
                                            return "CODE"
                                        return "TERMINAL"
                                    }
                                    title: {
                                        var body = String(
                                            streamDelegate.model.bodyText || ""
                                        )
                                        if (body.indexOf("READ ") === 0)
                                            return "read"
                                        if (body.indexOf("SEARCH ") === 0)
                                            return "search"
                                        if (
                                            body.indexOf("TEST ") === 0
                                            || body.indexOf("RUN ") === 0
                                        )
                                            return "terminal"
                                        return streamDelegate.model.taskId || "tool"
                                    }
                                    bodyText: streamDelegate.model.bodyText
                                    provenanceClass: "REAL_UI_STATE"
                                    activityState: streamDelegate.model.stateLabel
                                    realPercentage: -1
                                    contextReference: streamDelegate.model.contextReference
                                }

                                ChatNode {
                                    id: speechNode
                                    visible: root.isUserChatNode(
                                        streamDelegate.model.nodeKind
                                    )
                                    || root.isAiSpeechNode(
                                        streamDelegate.model.nodeKind
                                    )
                                    height: visible ? implicitHeight : 0
                                    authorLabel: streamDelegate.model.authorLabel
                                    nodeKind: streamDelegate.model.nodeKind
                                    bodyText: streamDelegate.model.bodyText
                                    contextReference: streamDelegate.model.contextReference
                                    provenanceClass: streamDelegate.model.provenanceClass
                                    stateLabel: streamDelegate.model.stateLabel
                                    laneOffset: 0
                                    taskId: streamDelegate.model.taskId || ""
                                    workStagesJson: streamDelegate.model.workStagesJson || ""
                                    maxBubbleWidth: Math.floor(
                                        parent.width * (
                                            root.isUserChatNode(
                                                streamDelegate.model.nodeKind
                                            ) ? 0.78 : 0.92
                                        )
                                    )
                                    x: root.isUserChatNode(streamDelegate.model.nodeKind)
                                        ? parent.width - width
                                        : 0
                                    onImplicitHeightChanged: {
                                        if (root.followChatTail || root.bridgeBusy)
                                            root.stickChatToLatest()
                                    }
                                }
                            }
                        }

                        Item {
                            id: artifactRow
                            objectName: "chatArtifactPane"
                            width: parent.width
                            visible: root.liveAidWorkVisible()
                            height: visible
                                ? Math.max(
                                    180,
                                    chatLiveAidWork.implicitHeight
                                )
                                : 0

                            Row {
                                anchors.fill: parent
                                anchors.leftMargin: 16
                                spacing: 6

                                GgFrame {
                                    id: chatCodeblock
                                    width: parent.width
                                        - liveAidColumn.width
                                        - parent.spacing
                                    height: parent.height
                                    leftLegend: "CODEBLOCK · "
                                        + (
                                            workspace.currentObjectTitle.length > 0
                                                ? workspace.currentObjectTitle
                                                : "FILE"
                                        )
                                    rightLegend: workspace.editorDirty
                                        ? "BUFFER · UNSAVED"
                                        : "BUFFER · DISK BASE"
                                    backgroundColor: "#070a0e"
                                    borderColor: "#6a6a6a"

                                    Flickable {
                                        id: codeblockFlick
                                        width: parent.width
                                        height: Math.max(
                                            1,
                                            chatCodeblock.height - 36
                                        )
                                        clip: true
                                        boundsBehavior: Flickable.StopAtBounds
                                        contentWidth: Math.max(
                                            width,
                                            codeblockView.contentWidth
                                        )
                                        contentHeight: Math.max(
                                            height,
                                            codeblockView.contentHeight
                                        )
                                        interactive: contentHeight > height
                                            || contentWidth > width
                                        visible: !root.alphaShowDemoFixtures

                                        TextEdit {
                                            id: codeblockView
                                            text: workspace.editorLoaded
                                                ? workspace.editorText
                                                : ""
                                            color: "#d8dee9"
                                            readOnly: true
                                            selectByMouse: true
                                            selectByKeyboard: true
                                            persistentSelection: true
                                            textFormat: TextEdit.PlainText
                                            wrapMode: TextEdit.NoWrap
                                            font.family: "monospace"
                                            font.pixelSize: 11
                                        }

                                        ScrollBar.vertical: ScrollBar {
                                            policy: ScrollBar.AsNeeded
                                        }
                                        ScrollBar.horizontal: ScrollBar {
                                            policy: ScrollBar.AsNeeded
                                        }
                                    }
                                }

                                Item {
                                    id: liveAidColumn
                                    width: Math.max(
                                        168,
                                        Math.min(214, parent.width * 0.38)
                                    )
                                    height: parent.height

                                    ChatLiveAidWork {
                                        id: chatLiveAidWork
                                        width: parent.width
                                        height: parent.height
                                        objectTitle:
                                            workspace.currentObjectTitle
                                        editorLoaded: workspace.editorLoaded
                                        editorLanguage:
                                            workspace.editorLanguage
                                        liveAidState: workspace.liveAidState
                                        diagnostics:
                                            workspace.liveAidDiagnostics
                                        evidenceSummary:
                                            workspace.liveAidEvidenceSummary
                                        preflightState:
                                            workspace.preflightState
                                        repairState: workspace.repairState
                                        repairProposalId:
                                            workspace.repairProposalId
                                        postDraftBusy: workspace.postDraftBusy
                                        postDraftState:
                                            workspace.postDraftState

                                        onPostDraftRequested:
                                            workspace.requestPostDraftAutomaticRepair()
                                        onPreflightRequested:
                                            workspace.requestLiveAidPreflight()
                                        onRepairRequested:
                                            workspace.requestLiveAidRepair()
                                        onApplyRequested:
                                            workspace.requestApplyRepair()
                                    }
                                }
                            }
                        }

                        WorkObject {
                            visible: root.alphaShowDemoFixtures
                            width: parent.width
                            objectType: "TERMINAL"
                            title: "tool stream"
                            provenanceClass: "SYNTHETIC_UI_FIXTURE"
                            activityState: "IDLE"
                            realPercentage: -1
                            bodyText: "$ sample only\n"
                                + "No process started.\n"
                                + "No exit status claimed."
                        }

                        WorkObject {
                            visible: root.alphaShowDemoFixtures
                            width: parent.width
                            objectType: "CODE"
                            title: "header.css"
                            provenanceClass: "SYNTHETIC_UI_FIXTURE"
                            activityState: "IDLE"
                            realPercentage: -1
                            bodyText: "/* DEMO / SAMPLE — not a real edit */\n"
                                + ".hero {\n"
                                + "    padding-block: var(--space-xl);\n"
                                + "}"
                        }
                    }
                    }
                }

                Item {
                    id: chatStatusDock
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: composer.top
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    height: root.bridgeBusy ? chatStatusStrip.implicitHeight : 0

                    ActivityStrip {
                        id: chatStatusStrip
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        width: parent.width
                        visible: root.bridgeBusy
                        activityState: root.activeWorkState()
                        headline: root.activeWorkLabel()
                        percentage: -1
                    }
                }

                // A1.2.1.1: ordinary chatSurface owns composer geometry.
                ContextComposer {
                    id: composer
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8
                    anchors.bottomMargin: 0
                    height: composer.implicitHeight
                    contextReference: workspace.currentContextReference
                    workspaceObjectId: (
                        workspace.currentObjectType === "SITE_PROJECT"
                        && workspace.siteRelativePath.length > 0
                    )
                        ? workspace.siteFileObjectId(
                            workspace.siteRelativePath
                        )
                        : workspace.currentObjectId
                    workspaceObjectTitle: workspace.currentObjectTitle
                    bridgeState: "CONNECTED"
                    busy: root.bridgeBusy
                    activeTaskId: root.activeTaskId
                    engineTarget: root.engineTarget
                    frameBorder: root.frameBorder
                    frameRadius: root.frameRadius
                    showOpenTab: root.showOpenTabInInput
                    onEngineTargetRequested: function(value) {
                        if (
                            value === "LOCAL_QWEN"
                            || value === "GROK_WORKER"
                            || value === "GROK_TUI"
                        ) {
                            root.engineTarget = value
                            root.persistDesktopSettings()
                        }
                    }

                    onAssignmentSetRequested: function(participant, creatorActor) {
                        root.bridgeAssignmentSet(
                            participant,
                            creatorActor
                        )
                    }

                    onAssignmentClearRequested: function() {
                        root.bridgeAssignmentClear()
                    }

                    onSubmitRequested: function(text, contextReference, workspaceObjectId) {
                        if (root.surfaceHost) {
                            var kind = root.surfaceHost.parseSurfaceIntent(text)
                            if (kind && kind.length > 0) {
                                workspace.setHostKind(kind)
                                return
                            }
                        }
                        root.contextSnapshotSync(root.buildContextSnapshotJson())
                        if (
                            !(
                                root.bridgeBusy
                                && root.engineTarget === "GROK_WORKER"
                            )
                        ) {
                            root.appendRealNode(
                                "YOU",
                                "REQUEST",
                                text,
                                contextReference
                                    + " · "
                                    + (
                                        workspace.currentObjectTitle.length > 0
                                            ? workspace.currentObjectTitle
                                            : workspaceObjectId
                                    ),
                                "SUBMITTED",
                                0,
                                ""
                            )
                        }

                        root.bridgeSubmit(
                            text,
                            contextReference,
                            workspaceObjectId
                        )
                    }

                    onStopRequested: root.bridgeStop()
                }
}

            Item {
                id: centerColumn
                objectName: "centerColumn"
                visible: !root.narrowLayout || root.narrowPane === "WORKSPACE"
                width: root.narrowLayout
                    ? body.width
                    : Math.max(
                        380,
                        body.width
                            - chatSurface.width
                            - (telemetry.visible ? telemetry.width : 0)
                            - (telemetry.visible ? 20 : 10)
                    )
                height: body.height

                WorkspaceSurface {
                    id: workspace
                    visible: !root.narrowLayout || root.narrowPane === "WORKSPACE"
                    showDemoFixtures: root.alphaShowDemoFixtures
                    showProductSourceTabs: root.showProductSourceTabs
                    chatWidthRatio: root.alphaChatWidthRatio
                    telemetryWidth: root.alphaTelemetryWidth
                    accentColor: root.cyan
                    frameBorder: root.frameBorder
                    frameRadius: root.frameRadius
                    showOpenTabInInput: root.showOpenTabInInput
                    showInnerEditorChrome: root.showInnerEditorChrome
                    chatBusy: root.bridgeBusy
                    engineTarget: root.engineTarget
                    utilityHeight: root.alphaUtilityHeight

                    onChatWidthRatioRequested: function(value) {
                        root.alphaChatWidthRatio = value
                        root.persistDesktopSettings()
                    }

                    onTelemetryWidthRequested: function(value) {
                        root.alphaTelemetryWidth = value
                        root.persistDesktopSettings()
                    }

                    onAccentColorRequested: function(value) {
                        root.cyan = value
                        root.persistDesktopSettings()
                    }

                    onFrameBorderRequested: function(value) {
                        root.frameBorder = value
                        root.persistDesktopSettings()
                    }

                    onFrameRadiusRequested: function(value) {
                        root.frameRadius = value
                        root.persistDesktopSettings()
                    }

                    onDemoVisibilityRequested: function(value) {
                        root.alphaShowDemoFixtures = value
                        root.persistDesktopSettings()
                    }

                    onProductSourceTabsRequested: function(value) {
                        root.showProductSourceTabs = value
                        root.persistDesktopSettings()
                    }

                    onShowOpenTabInInputRequested: function(value) {
                        root.showOpenTabInInput = value
                        root.persistDesktopSettings()
                    }

                    onShowInnerEditorChromeRequested: function(value) {
                        root.showInnerEditorChrome = value
                        root.persistDesktopSettings()
                    }

                    onEngineTargetRequested: function(value) {
                        root.engineTarget = value
                        root.persistDesktopSettings()
                    }

                    onUtilityHeightRequested: function(value) {
                        root.alphaUtilityHeight = value
                        root.persistDesktopSettings()
                    }
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: utilitySurface.top
                    anchors.bottomMargin: 8

                    onActiveObjectChanged: function(objectId, title) {
                        if (objectId === root.lastSelectedObjectId)
                            return
                        root.lastSelectedObjectId = objectId
                        root.appendRealNode(
                            "GG SYSTEM",
                            "CONTEXT",
                            "Active Workspace object changed to "
                                + title
                                + ". @current now resolves to "
                                + objectId
                                + ".",
                            "@current",
                            "SELECTED",
                            20,
                            ""
                        )
                    }
                }

                UtilitySurface {
                    id: utilitySurface
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 0
                    height: utilitySurface.implicitHeight
                    surfaceHeight: root.alphaUtilityHeight
                    accentColor: root.cyan
                    frameBorder: root.frameBorder
                    frameRadius: root.frameRadius
                }
            }

            TelemetryRail {
                id: telemetry
                visible: !root.compactTelemetry && !root.narrowLayout
                width: root.alphaTelemetryWidth
                height: body.height
                compactMode: true
                actionAuthority: "NONE"
                networkAuthority: "NONE"
                modelState: root.bridgeBusy ? "BUSY" : "READY"
                engineTarget: root.engineTarget
                grokWalletJson: root.grokWalletJson
                bridgeState: root.bridgeBusy ? "BUSY" : "CONNECTED"
                frameBorder: root.frameBorder
                frameRadius: root.frameRadius
                snippetModel: workspace.snippetModel
                activeSnippet: workspace.siteRelativePath
                chatSessionsJson: root.chatSessionsJson
                activeChatSession: root.activeChatSession
                onSnippetChosen: function(path) {
                    workspace.chooseSnippet(path)
                }
                onChatSessionChosen: function(sessionId, engine) {
                    root.activeChatSession = sessionId
                    if (engine === "GROK_TUI" || engine === "GROK_WORKER" || engine === "LOCAL_QWEN")
                        root.engineTarget = engine
                    if (engine === "GROK_TUI" && root.surfaceHost)
                        root.surfaceHost.resumeGrokTui(sessionId)
                }
            }
        }
    }


}
