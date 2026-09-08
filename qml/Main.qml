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
    property string engineTarget: "GROK_TUI"
    property string lastSelectedObjectId: ""
    property real alphaChatWidthRatio: 0.31
    property int alphaTelemetryWidth: 168
    property int alphaUtilityHeight: 112
    property bool alphaShowDemoFixtures: false
    property bool showProductSourceTabs: false
    property var surfaceHost: null
    property var liveAidBackend: null
    readonly property var workspace: workspaceLoader.item
    property string grokWalletJson: "{}"
    property string gptWalletJson: "{}"
    property string cryptoStatusJson: "{}"

    onSurfaceHostChanged: {
        root.pullCryptoStatus()
        root.applyDesktopShellNow()
    }

    onDesktopShellChanged: {
        root.persistDesktopSettings()
        root.applyDesktopShellNow()
    }

    onActiveChanged: {
        if (root.active && root.desktopShell)
            root.applyDesktopShellNow()
    }
    property string chatSessionsJson: "[]"
    property string activeChatSession: ""
    property bool shellLoading: true
    property string shellLoadLabel: "LOADING..."
    property int shellLoadPercent: 0
    property string shellLoadCurrent: ""
    property string shellLoadLog: ""
    property string shellLoadQueueJson: "[]"
    property var _shellQueue: []
    property int _shellQueueIndex: 0
    property var _shellComp: null
    readonly property int alphaBottomStripMargin: 8

    property int shellNonce: 0
    property bool _shellHydrated: false
    property bool _utilityBound: false
    property bool _workspaceBound: false
    property real deskX: 420
    property real deskY: 240
    property string deskShape: "default"
    property bool deskFromChrome: false
    property bool deskGrabReady: false

    function grabDesk(path) {
        root.deskGrabReady = false
        var item = root.contentItem
        if (!item || !item.grabToImage) {
            root.deskGrabReady = false
            return false
        }
        item.grabToImage(function(result) {
            var ok = false
            try {
                ok = result.saveToFile(path)
            } catch (err) {
                ok = false
            }
            root.deskGrabReady = ok
        })
        return true
    }

    function setDeskCursor(item, lx, ly, shape) {
        if (!item)
            return
        var p = item.mapToItem(root.contentItem, Number(lx), Number(ly))
        root.deskX = p.x
        root.deskY = p.y
        if (shape && String(shape).length > 0)
            root.deskShape = String(shape)
    }

    function workspaceUrl() {
        return Qt.resolvedUrl("components/WorkspaceSurface.qml")
            + "?r=" + String(root.shellNonce)
    }

    function utilityUrl() {
        return Qt.resolvedUrl("components/UtilitySurface.qml")
            + "?r=" + String(root.shellNonce)
    }

    function unloadDesktopShell() {
        root.shellLoadPercent = 0
        root.shellLoadCurrent = ""
        root.shellLoadLog = ""
        root._shellQueue = []
        root._shellQueueIndex = 0
        root._shellComp = null
        root._shellHydrated = false
        root._utilityBound = false
        root._workspaceBound = false
        workspaceLoader.source = ""
        utilitySurface.source = ""
    }

    function parseShellQueue() {
        var raw = root.shellLoadQueueJson
        if (root.surfaceHost && root.surfaceHost.shellLoadQueue)
            raw = root.surfaceHost.shellLoadQueue()
        var rows = []
        try {
            rows = JSON.parse(raw || "[]")
        } catch (err) {
            rows = []
        }
        if (!rows || !rows.length)
            return ["qml/components/WorkspaceSurface.qml"]
        return rows
    }

    function shellUrl(rel) {
        var path = String(rel || "")
        if (path.indexOf("qml/") === 0)
            path = path.slice(4)
        return Qt.resolvedUrl(path)
    }

    function appendShellLog(name) {
        var lines = root.shellLoadLog.length > 0
            ? root.shellLoadLog.split("\n")
            : []
        lines.push(name)
        if (lines.length > 12)
            lines = lines.slice(lines.length - 12)
        root.shellLoadLog = lines.join("\n")
    }

    function loadNextShellFile() {
        if (root._shellQueueIndex >= root._shellQueue.length) {
            root.shellLoadPercent = 100
            root.loadDesktopShell()
            return
        }
        var rel = String(root._shellQueue[root._shellQueueIndex] || "")
        root.shellLoadCurrent = rel
        root.appendShellLog(rel)
        var total = root._shellQueue.length
        root.shellLoadPercent = Math.round(
            root._shellQueueIndex * 100 / Math.max(1, total)
        )
        var comp = Qt.createComponent(
            root.shellUrl(rel),
            Component.Asynchronous
        )
        root._shellComp = comp
        if (!comp) {
            root.onShellCompFinished()
            return
        }
        if (comp.status === Component.Ready
            || comp.status === Component.Error)
            root.onShellCompFinished()
        else
            comp.statusChanged.connect(root.onShellCompFinished)
    }

    function onShellCompFinished() {
        var comp = root._shellComp
        if (comp && comp.status === Component.Loading)
            return
        if (comp) {
            if (comp.status === Component.Error)
                root.appendShellLog(String(comp.errorString() || "component error"))
            try {
                comp.statusChanged.disconnect(root.onShellCompFinished)
            } catch (err) {
            }
        }
        root._shellComp = null
        root._shellQueueIndex += 1
        var total = Math.max(1, root._shellQueue.length)
        root.shellLoadPercent = Math.round(
            root._shellQueueIndex * 100 / total
        )
        Qt.callLater(root.loadNextShellFile)
    }

    function loadDesktopShell() {
        var rel = "qml/components/WorkspaceSurface.qml"
        root.shellLoadCurrent = rel
        root.appendShellLog(rel)
        root.appendShellLog("qml/components/UtilitySurface.qml")
        utilitySurface.setSource(root.utilityUrl())
        workspaceLoader.setSource(root.workspaceUrl())
    }

    function bindUtility(item) {
        if (!item || root._utilityBound)
            return
        root._utilityBound = true
        item.surfaceHost = Qt.binding(function() {
            return root.surfaceHost
        })
        item.accentColor = Qt.binding(function() {
            return root.cyan
        })
        item.frameBorder = Qt.binding(function() {
            return root.frameBorder
        })
        item.frameRadius = Qt.binding(function() {
            return root.frameRadius
        })
        item.surfaceHeight = Qt.binding(function() {
            return root.alphaUtilityHeight
        })
        item.surfaceRequested.connect(function(kind) {
            if (workspace)
                workspace.setHostKind(kind)
        })
    }

    function bindWorkspace(item) {
        if (!item || root._workspaceBound)
            return
        root._workspaceBound = true
        item.showDemoFixtures = Qt.binding(function() {
            return root.alphaShowDemoFixtures
        })
        item.showProductSourceTabs = Qt.binding(function() {
            return root.showProductSourceTabs
        })
        item.chatWidthRatio = Qt.binding(function() {
            return root.alphaChatWidthRatio
        })
        item.telemetryWidth = Qt.binding(function() {
            return root.alphaTelemetryWidth
        })
        item.accentColor = Qt.binding(function() {
            return root.cyan
        })
        item.frameBorder = Qt.binding(function() {
            return root.frameBorder
        })
        item.frameRadius = Qt.binding(function() {
            return root.frameRadius
        })
        item.showOpenTabInInput = Qt.binding(function() {
            return root.showOpenTabInInput
        })
        item.showInnerEditorChrome = Qt.binding(function() {
            return root.showInnerEditorChrome
        })
        item.chatBusy = Qt.binding(function() {
            return root.bridgeBusy
        })
        item.engineTarget = Qt.binding(function() {
            return root.engineTarget
        })
        item.utilityHeight = Qt.binding(function() {
            return root.alphaUtilityHeight
        })
        item.desktopShell = Qt.binding(function() {
            return root.desktopShell
        })
        item.liveAidBackend = Qt.binding(function() {
            return root.liveAidBackend
        })
        item.chatWidthRatioRequested.connect(function(value) {
            root.alphaChatWidthRatio = value
            root.persistDesktopSettings()
        })
        item.telemetryWidthRequested.connect(function(value) {
            root.alphaTelemetryWidth = value
            root.persistDesktopSettings()
        })
        item.accentColorRequested.connect(function(value) {
            root.cyan = value
            root.persistDesktopSettings()
        })
        item.frameBorderRequested.connect(function(value) {
            root.frameBorder = value
            root.persistDesktopSettings()
        })
        item.frameRadiusRequested.connect(function(value) {
            root.frameRadius = value
            root.persistDesktopSettings()
        })
        item.demoVisibilityRequested.connect(function(value) {
            root.alphaShowDemoFixtures = value
            root.persistDesktopSettings()
        })
        item.productSourceTabsRequested.connect(function(value) {
            root.showProductSourceTabs = value
            root.persistDesktopSettings()
        })
        item.showOpenTabInInputRequested.connect(function(value) {
            root.showOpenTabInInput = value
            root.persistDesktopSettings()
        })
        item.showInnerEditorChromeRequested.connect(function(value) {
            root.showInnerEditorChrome = value
            root.persistDesktopSettings()
        })
        item.engineTargetRequested.connect(function(value) {
            root.engineTarget = value
            root.persistDesktopSettings()
        })
        item.utilityHeightRequested.connect(function(value) {
            root.alphaUtilityHeight = value
            root.persistDesktopSettings()
        })
        item.desktopShellRequested.connect(function(value) {
            root.desktopShell = value
        })
        item.activeObjectChanged.connect(function(objectId, title) {
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
        })
    }

    function beginShellLoad(label) {
        root.shellNonce += 1
        root.shellLoadLabel = label
        root.shellLoading = true
        root.unloadDesktopShell()
        root._shellQueue = root.parseShellQueue()
        root._shellQueueIndex = 0
        if (String(label) !== "RELOAD")
            Qt.callLater(root.loadNextShellFile)
    }

    function finishShellLoad() {
        if (root._shellHydrated)
            return
        if (workspaceLoader.status !== Loader.Ready || !workspaceLoader.item)
            return
        if (
            utilitySurface.status === Loader.Loading
            || utilitySurface.status === Loader.Null
        )
            return
        root.bindWorkspace(workspaceLoader.item)
        if (utilitySurface.item)
            root.bindUtility(utilitySurface.item)
        root.hydrateDesktopShell()
        root._shellHydrated = true
        root.shellLoading = false
    }

    function applyCryptoWalletLabel() {
        var label = "WALLET · DISCONNECTED"
        try {
            var parsed = JSON.parse(root.cryptoStatusJson || "{}")
            var w = parsed.wallet || {}
            if (w.label)
                label = String(w.label)
            else {
                var key = String(w.pubkey || "")
                if (key.length >= 8)
                    label = "WALLET · " + key.slice(0, 4) + "…" + key.slice(-4)
                else if (key.length > 0)
                    label = "WALLET · " + key
            }
        } catch (err) {
        }
        if (workspace)
            workspace.cryptoWalletLabel = label
    }

    function hydrateDesktopShell() {
        root.shellLoadLabel = "HYDRATING..."
        root.appendShellLog("hydrate · tui")
        root.appendShellLog("hydrate · wallet")
        root.appendShellLog("hydrate · chats")
        root.appendShellLog("hydrate · crypto")
        root.appendShellLog("hydrate · snippets")
        root.appendShellLog("hydrate · media")
        root.shellLoadCurrent = "desktop state"
        var raw = ""
        if (root.surfaceHost && root.surfaceHost.hydrateDesktop)
            raw = root.surfaceHost.hydrateDesktop()
        if (raw)
            root.cryptoStatusJson = raw
        else
            root.pullCryptoStatus()
        root.applyCryptoWalletLabel()
        if (workspace && workspace.refreshSiteFiles)
            workspace.refreshSiteFiles()
        if (workspace && workspace.applyCryptoWalletLabel)
            workspace.applyCryptoWalletLabel()
        if (utilitySurface.item && utilitySurface.item.refresh)
            utilitySurface.item.refresh()
    }

    Component.onCompleted: Qt.callLater(function() {
        root.beginShellLoad("LOADING...")
    })

    readonly property bool narrowLayout: width < 1050
    readonly property bool compactTelemetry: width < 1450

    readonly property color canvas: "#121212"
    readonly property color surface: "#161616"
    readonly property color line: "#6a6a6a"
    readonly property color textMain: "#e6e6e6"
    readonly property color textMuted: "#8a8a8a"
    property color cyan: "#8a8a8a"
    property color frameBorder: "#6a6a6a"
    property int frameRadius: 4
    property bool showOpenTabInInput: false
    property bool showInnerEditorChrome: true
    property bool desktopShell: false
    property bool appFullscreen: false
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
        function onGptWalletChanged(payload) {
            root.gptWalletJson = payload
        }
        function onQmlLiveReload() {
            if (!root.shellLoading)
                root.beginShellLoad("RELOAD")
            Qt.callLater(root.loadNextShellFile)
        }
        function onWebOperatorCommand(payload) {
            if (root.workspace && root.workspace.applyWebOperator)
                root.workspace.applyWebOperator(payload)
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

    function pullCryptoStatus() {
        if (!root.surfaceHost)
            return
        var raw = ""
        if (root.surfaceHost.cryptoRailStatus)
            raw = root.surfaceHost.cryptoRailStatus()
        else if (root.surfaceHost.cryptoStatus)
            raw = root.surfaceHost.cryptoStatus()
        else
            return
        if (raw === root.cryptoStatusJson)
            return
        root.cryptoStatusJson = raw
        root.applyCryptoWalletLabel()
    }

    Timer {
        interval: 30000
        running: true
        repeat: true
        onTriggered: root.pullCryptoStatus()
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
            "showDemoFixtures": root.alphaShowDemoFixtures,
            "desktopShell": root.desktopShell
        }))
    }

    function applyDesktopShellNow() {
        if (!root.surfaceHost || !root.surfaceHost.applyDesktopShell)
            return
        root.surfaceHost.applyDesktopShell(root.desktopShell)
    }

    function toggleAppFullscreen() {
        root.appFullscreen = !root.appFullscreen
    }

    title: "GG AI Desktop · Alpha"
    width: 1920
    height: 1080
    minimumWidth: 820
    minimumHeight: 620
    flags: root.desktopShell && !root.appFullscreen
        ? (Qt.FramelessWindowHint | Qt.WindowStaysOnBottomHint)
        : Qt.Window
    visibility: root.appFullscreen
        ? Window.FullScreen
        : (root.desktopShell ? Window.Windowed : Window.Maximized)
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
        var workspaceSnapshot = workspace
            ? workspace.contextSnapshot(32)
            : {}
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
        if (workspace && workspace.currentObjectTitle.length > 0)
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
        if (workspace && workspace.currentObjectTitle.length > 0)
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
        if (!workspace)
            return false
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
        // Keep a reader's manual position.  New streamed nodes may request a
        // tail update, but they must not silently yank the viewport back down
        // after the user has scrolled up to inspect an earlier message.
        if (!root.followChatTail)
            return
        root.stickChatToLatest()
        Qt.callLater(function() {
            if (root.followChatTail)
                root.stickChatToLatest()
        })
    }

    function setBridgeActivity(busy, taskId) {
        root.bridgeBusy = busy
        root.activeTaskId = busy ? taskId : ""
        if (busy) {
            root.followChatTail = true
            root.scrollChatToLatest()
        }
    }

    GgFrame {
        id: topBar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        anchors.topMargin: 12
        height: 54
        leftLegend: "GG AI DESKTOP"
        backgroundColor: root.surface
        borderColor: root.frameBorder
        radius: root.frameRadius
        padding: 12
        leftLegendColor: "#e6edf3"

        Item {
            width: parent.width
            height: 22

            Row {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                spacing: 14

                Text {
                    text: "OBSIDIAN / LEDGER"
                    color: "#c8cdd4"
                    font.family: "monospace"
                    font.pixelSize: 13
                }

                Text {
                    text: "·"
                    color: "#a8b0b8"
                    font.family: "monospace"
                    font.pixelSize: 13
                }

                Text {
                    visible: root.desktopShell
                    text: "DESKTOP"
                    color: "#c8a97e"
                    font.family: "monospace"
                    font.pixelSize: 13
                    font.bold: true
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.desktopShell = false
                    }
                }

                Text {
                    visible: root.desktopShell
                    text: "·"
                    color: "#a8b0b8"
                    font.family: "monospace"
                    font.pixelSize: 13
                }

                Text {
                    id: settingsButton
                    objectName: "topBarSettingsButton"
                    text: "SETTINGS"
                    color: workspace && workspace.settingsOpen ? "#e6edf3" : "#c8cdd4"
                    font.family: "monospace"
                    font.pixelSize: 13
                    font.bold: workspace && workspace.settingsOpen

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (!workspace)
                                return
                            workspace.settingsOpen
                                ? workspace.closeSettings()
                                : workspace.openSettings()
                        }
                    }
                }

                Text {
                    text: "·"
                    color: "#a8b0b8"
                    font.family: "monospace"
                    font.pixelSize: 13
                }

                Text {
                    id: reloadButton
                    objectName: "topBarReloadButton"
                    text: "RELOAD"
                    color: "#c8cdd4"
                    font.family: "monospace"
                    font.pixelSize: 13

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (root.shellLoading)
                                return
                            root.beginShellLoad("RELOAD")
                            if (root.surfaceHost && root.surfaceHost.restartDesktop)
                                root.surfaceHost.restartDesktop()
                        }
                    }
                }

                Text {
                    text: "·"
                    color: "#a8b0b8"
                    font.family: "monospace"
                    font.pixelSize: 13
                }

                Text {
                    id: fullscreenButton
                    objectName: "topBarFullscreenButton"
                    text: root.appFullscreen ? "EXIT FULLSCREEN" : "FULLSCREEN"
                    color: root.appFullscreen ? root.amber : "#c8cdd4"
                    font.family: "monospace"
                    font.pixelSize: 13
                    font.bold: root.appFullscreen

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.toggleAppFullscreen()
                    }
                }
            }

            Row {
                visible: root.narrowLayout
                anchors.centerIn: parent
                spacing: 6

                GgButton {
                    text: "CHAT"
                    checkable: true
                    checked: root.narrowPane === "CHAT"
                    onClicked: root.narrowPane = "CHAT"
                }

                GgButton {
                    text: "WORKSPACE"
                    checkable: true
                    checked: root.narrowPane === "WORKSPACE"
                    onClicked: root.narrowPane = "WORKSPACE"
                }
            }

            Row {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 16

                Text {
                    text: "LOCAL · ALPHA"
                    color: root.cyan
                    font.family: "monospace"
                    font.pixelSize: 13
                }

                Text {
                    objectName: "topBarWalletChip"
                    text: {
                        if (workspace) {
                            var live = String(workspace.cryptoWalletLabel || "")
                            if (
                                live.length > 0
                                && live.indexOf("DISCONNECTED") < 0
                            )
                                return live
                        }
                        try {
                            var parsed = JSON.parse(
                                root.cryptoStatusJson || "{}"
                            )
                            var w = parsed.wallet || {}
                            if (w.label)
                                return String(w.label)
                            var key = String(w.pubkey || "")
                            if (key.length >= 8)
                                return "WALLET · "
                                    + key.slice(0, 4)
                                    + "…"
                                    + key.slice(-4)
                            if (key.length > 0)
                                return "WALLET · " + key
                        } catch (err) {
                        }
                        return "WALLET · DISCONNECTED"
                    }
                    color: {
                        var chip = text
                        return String(chip).indexOf("DISCONNECTED") >= 0
                            ? "#c8cdd4"
                            : root.green
                    }
                    font.family: "monospace"
                    font.pixelSize: 13
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (workspace)
                                workspace.setHostKind("CRYPTO")
                        }
                    }
                }
            }
        }
    }

    Item {
        id: body
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: topBar.bottom
        anchors.bottom: parent.bottom
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        anchors.bottomMargin: 12
        anchors.topMargin: 10

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
                    busy: root.bridgeBusy
                    backgroundColor: root.surface
                    borderColor: root.frameBorder
                    radius: root.frameRadius
                }

                GrokTuiHole {
                    id: grokTuiHost
                    objectName: "grokTuiHost"
                    terminalId: "ws.tui.grok"
                    visible: root.engineTarget === "GROK_TUI"
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: composer.top
                    anchors.leftMargin: chatChrome.padding
                    anchors.rightMargin: chatChrome.padding
                    anchors.topMargin: chatChrome.topChrome
                    anchors.bottomMargin: 0
                    surfaceHost: root.surfaceHost
                }

                GrokTuiHole {
                    id: gptTuiHost
                    objectName: "gptTuiHost"
                    terminalId: "ws.tui.gpt"
                    visible: root.engineTarget === "GPT_TUI"
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: composer.top
                    anchors.leftMargin: chatChrome.padding
                    anchors.rightMargin: chatChrome.padding
                    anchors.topMargin: chatChrome.topChrome
                    anchors.bottomMargin: 0
                    surfaceHost: root.surfaceHost
                }

                Flickable {
                    id: chatFlick
                    objectName: "chatCockpit"
                    visible: root.engineTarget !== "GROK_TUI" && root.engineTarget !== "GPT_TUI"
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: chatStatusDock.top
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    anchors.topMargin: 14
                    anchors.bottomMargin: 8
                    clip: true
                    contentWidth: width
                    contentHeight: Math.max(
                        height,
                        streamWrap.height
                    )
                    enabled: visible
                    flickableDirection: Flickable.VerticalFlick
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: GgScrollBar {
                        objectName: "chatScrollBar"
                        keepVisible: true
                        policy: chatFlick.visible
                            ? ScrollBar.AsNeeded
                            : ScrollBar.AlwaysOff
                    }
                    onContentHeightChanged: {
                        if (root.followChatTail)
                            root.stickChatToLatest()
                    }
                    onHeightChanged: {
                        if (root.followChatTail)
                            root.stickChatToLatest()
                    }
                    onContentYChanged: {
                        // Drop tail-follow as soon as a real drag moves the
                        // viewport away from the newest line.  This happens
                        // before the next streamed update can snap it back.
                        if (
                            chatFlick.moving
                            && chatFlick.contentY
                                + chatFlick.height
                                < chatFlick.contentHeight - 32
                        )
                            root.followChatTail = false
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
                            if (root.followChatTail)
                                root.stickChatToLatest()
                        }

                        Repeater {
                            model: chatModel

                            delegate: Item {
                                id: streamDelegate
                                required property var model

                                width: streamColumn.width
                                height: Math.max(
                                    grokLoader.height,
                                    activityLoader.height,
                                    toolLoader.height,
                                    speechLoader.height
                                )

                                Loader {
                                    id: grokLoader
                                    width: Math.min(
                                        parent.width,
                                        parent.width * 0.92
                                    )
                                    height: item ? item.implicitHeight : 0
                                    active: root.isGrokStreamNode(
                                        streamDelegate.model.nodeKind
                                    )
                                    sourceComponent: Component {
                                        GrokWorkStream {
                                            width: grokLoader.width
                                            authorLabel: streamDelegate.model.authorLabel
                                            nodeKind: streamDelegate.model.nodeKind
                                            stateLabel: streamDelegate.model.stateLabel
                                            contextReference: streamDelegate.model.contextReference
                                            taskId: streamDelegate.model.taskId || ""
                                            workCardsJson: streamDelegate.model.workCardsJson || "[]"
                                            livePulse: root.bridgeBusy
                                                && streamDelegate.model.taskId === root.activeTaskId
                                            onImplicitHeightChanged: {
                                                if (root.followChatTail)
                                                    root.stickChatToLatest()
                                            }
                                        }
                                    }
                                }

                                Loader {
                                    id: activityLoader
                                    width: Math.min(
                                        parent.width,
                                        parent.width * 0.92
                                    )
                                    height: item ? item.implicitHeight : 0
                                    active: root.isActivityNode(
                                        streamDelegate.model.nodeKind
                                    )
                                    sourceComponent: Component {
                                        ChatActivityEvent {
                                            width: activityLoader.width
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
                                    }
                                }

                                Loader {
                                    id: toolLoader
                                    width: Math.min(
                                        parent.width,
                                        parent.width * 0.92
                                    )
                                    height: item ? item.implicitHeight : 0
                                    active: root.isToolNode(
                                        streamDelegate.model.nodeKind
                                    )
                                    sourceComponent: Component {
                                        WorkObject {
                                            width: toolLoader.width
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
                                    }
                                }

                                Loader {
                                    id: speechLoader
                                    width: parent.width
                                    height: item ? item.implicitHeight : 0
                                    active: root.isUserChatNode(
                                        streamDelegate.model.nodeKind
                                    )
                                        || root.isAiSpeechNode(
                                            streamDelegate.model.nodeKind
                                        )
                                    sourceComponent: Component {
                                        ChatNode {
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
                                                streamDelegate.width * (
                                                    root.isUserChatNode(
                                                        streamDelegate.model.nodeKind
                                                    ) ? 0.78 : 0.92
                                                )
                                            )
                                            x: root.isUserChatNode(
                                                streamDelegate.model.nodeKind
                                            )
                                                ? streamDelegate.width - width
                                                : 0
                                            onImplicitHeightChanged: {
                                                if (root.followChatTail)
                                                    root.stickChatToLatest()
                                            }
                                        }
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
                                            workspace
                                            && workspace.currentObjectTitle.length > 0
                                                ? workspace.currentObjectTitle
                                                : "FILE"
                                        )
                                    rightLegend: workspace && workspace.editorDirty
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
                                            text: workspace && workspace.editorLoaded
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
                                            font.pixelSize: 12
                                        }

                                        ScrollBar.vertical: GgScrollBar {}
                                        ScrollBar.horizontal: GgScrollBar {}
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
                                        objectTitle: workspace
                                            ? workspace.currentObjectTitle
                                            : ""
                                        editorLoaded: workspace
                                            ? workspace.editorLoaded
                                            : false
                                        editorLanguage: workspace
                                            ? workspace.editorLanguage
                                            : ""
                                        liveAidState: workspace
                                            ? workspace.liveAidState
                                            : "IDLE"
                                        diagnostics: workspace
                                            ? workspace.liveAidDiagnostics
                                            : []
                                        evidenceSummary: workspace
                                            ? workspace.liveAidEvidenceSummary
                                            : ""
                                        preflightState: workspace
                                            ? workspace.preflightState
                                            : "NOT RUN"
                                        repairState: workspace
                                            ? workspace.repairState
                                            : ""
                                        repairProposalId: workspace
                                            ? workspace.repairProposalId
                                            : ""
                                        postDraftBusy: workspace
                                            ? workspace.postDraftBusy
                                            : false
                                        postDraftState: workspace
                                            ? workspace.postDraftState
                                            : ""

                                        onPostDraftRequested: {
                                            if (workspace)
                                                workspace.requestPostDraftAutomaticRepair()
                                        }
                                        onPreflightRequested: {
                                            if (workspace)
                                                workspace.requestLiveAidPreflight()
                                        }
                                        onRepairRequested: {
                                            if (workspace)
                                                workspace.requestLiveAidRepair()
                                        }
                                        onApplyRequested: {
                                            if (workspace)
                                                workspace.requestApplyRepair()
                                        }
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
                    contextReference: workspace
                        ? workspace.currentContextReference
                        : "@current"
                    workspaceObjectId: (
                        workspace
                        && workspace.currentObjectType === "SITE_PROJECT"
                        && workspace.siteRelativePath.length > 0
                    )
                        ? workspace.siteFileObjectId(
                            workspace.siteRelativePath
                        )
                        : (workspace ? workspace.currentObjectId : "")
                    workspaceObjectTitle: workspace
                        ? workspace.currentObjectTitle
                        : ""
                    bridgeState: "CONNECTED"
                    busy: root.bridgeBusy
                    activeTaskId: root.activeTaskId
                    engineTarget: root.engineTarget
                    frameBorder: root.frameBorder
                    frameRadius: root.frameRadius
                    showOpenTab: root.showOpenTabInInput
                    surfaceHost: root.surfaceHost
                    onEngineTargetRequested: function(value) {
                        if (
                            value === "LOCAL_QWEN"
                            || value === "GROK_WORKER"
                            || value === "GROK_TUI"
                            || value === "GPT_TUI"
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
                                if (workspace)
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
                                        workspace
                                        && workspace.currentObjectTitle.length > 0
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

                Loader {
                    id: workspaceLoader
                    objectName: "workspaceLoader"
                    asynchronous: true
                    visible: !root.narrowLayout || root.narrowPane === "WORKSPACE"
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: utilitySurface.top
                    anchors.bottomMargin: 8
                    onLoaded: root.finishShellLoad()
                    onStatusChanged: {
                        if (status === Loader.Ready)
                            root.finishShellLoad()
                        if (status === Loader.Error) {
                            root.shellLoadCurrent = "LOAD FAILED"
                            root.appendShellLog(String(errorString() || "workspace"))
                        }
                    }
                }

                Loader {
                    id: utilitySurface
                    anchors.bottomMargin: 0
                    objectName: "utilitySurfaceLoader"
                    asynchronous: true
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: utilitySurface.implicitHeight
                    onLoaded: {
                        root.bindUtility(utilitySurface.item)
                        root.finishShellLoad()
                    }
                    onStatusChanged: {
                        if (
                            status === Loader.Ready
                            || status === Loader.Error
                        )
                            root.finishShellLoad()
                    }
                }
            }

            TelemetryRail {
                id: telemetry
                visible: !root.compactTelemetry && !root.narrowLayout
                width: root.alphaTelemetryWidth
                height: body.height
                compactMode: true
                modelState: root.bridgeBusy ? "BUSY" : "READY"
                engineTarget: root.engineTarget
                grokWalletJson: root.grokWalletJson
                gptWalletJson: root.gptWalletJson
                bridgeState: root.bridgeBusy ? "BUSY" : "CONNECTED"
                frameBorder: root.frameBorder
                frameRadius: root.frameRadius
                snippetModel: workspace ? workspace.snippetModel : null
                activeSnippet: workspace ? workspace.siteRelativePath : ""
                chatSessionsJson: root.chatSessionsJson
                activeChatSession: root.activeChatSession
                cryptoStatusJson: root.cryptoStatusJson
                onSnippetChosen: function(path) {
                    if (workspace)
                        workspace.chooseSnippet(path)
                }
                onChatSessionChosen: function(sessionId, engine) {
                    root.activeChatSession = sessionId
                    if (engine === "GPT_TUI" || engine === "GROK_TUI" || engine === "GROK_WORKER" || engine === "LOCAL_QWEN")
                        root.engineTarget = engine
                    if (engine === "GPT_TUI" && root.surfaceHost) {
                        // Let the visibility binding commit before the host
                        // validates/resumes the selected PTY.
                        Qt.callLater(function() {
                            if (root.surfaceHost)
                                root.surfaceHost.activateGptTui(sessionId)
                        })
                    }
                    if (engine === "GROK_TUI" && root.surfaceHost)
                        root.surfaceHost.resumeGrokTui(sessionId)
                }
            }
        }
    }

    Rectangle {
        id: shellLoadOverlay
        objectName: "shellLoadOverlay"
        z: 10000
        anchors.fill: parent
        visible: root.shellLoading
        color: root.canvas

        Column {
            objectName: "shellLoadFileLog"
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.margins: 18
            width: Math.min(parent.width - 36, 640)
            spacing: 4

            Text {
                width: parent.width
                text: root.shellLoadLog
                color: "#a8b0b8"
                font.family: "monospace"
                font.pixelSize: 12
                wrapMode: Text.NoWrap
            }

            Text {
                width: parent.width
                visible: root.shellLoadCurrent.length > 0
                text: root.shellLoadCurrent
                color: "#c8a97e"
                font.family: "monospace"
                font.pixelSize: 12
                wrapMode: Text.NoWrap
                elide: Text.ElideMiddle
            }
        }

        Column {
            anchors.centerIn: parent
            spacing: 14
            width: 280

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: root.shellLoadLabel
                color: "#c8a97e"
                font.family: "monospace"
                font.pixelSize: 14
                font.bold: true
            }

            Rectangle {
                width: parent.width
                height: 8
                color: "#161616"
                border.color: root.line
                border.width: 1

                Rectangle {
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.margins: 1
                    width: Math.max(
                        0,
                        (parent.width - 2) * root.shellLoadPercent / 100
                    )
                    color: "#c8a97e"
                }
            }

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: String(Math.round(root.shellLoadPercent)) + "%"
                color: root.textMuted
                font.family: "monospace"
                font.pixelSize: 12
            }

            BufferMark {
                objectName: "shellLoadBuffer"
                anchors.horizontalCenter: parent.horizontalCenter
                active: root.shellLoading
                cell: 6
            }
        }
    }

    WebAgentCursor {
        id: deskAgentCursor
        objectName: "deskAgentCursor"
        parent: root.contentItem
        z: 10001
        visible: true
        shape: root.deskShape
        x: root.deskX - deskAgentCursor.hotX
        y: root.deskY - deskAgentCursor.hotY
    }
}
