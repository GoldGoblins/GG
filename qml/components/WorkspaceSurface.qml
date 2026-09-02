pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Window

Item {
    id: root
    objectName: "workspaceSurface"

    signal activeObjectChanged(string objectId, string title)

    property var liveAidBackend: null
    property bool editorLoaded: false
    property bool editorDirty: false
    property string editorBaseText: ""
    property string editorSourceName: ""
    property string editorLanguage: ""
    property string editorBaseSha256: ""
    readonly property string editorText: codeEditor.text
    property string liveAidState: "IDLE"
    property var liveAidDiagnostics: []
    property string liveAidEvidenceSummary: ""
    property string preflightState: "NOT RUN"
    property string preflightSourceText: ""
    property string preflightReportSha256: ""
    property string repairState: "IDLE"
    property string repairProposalId: ""
    property string repairSourceText: ""
    property string repairOldText: ""
    property string repairNewText: ""
    property string postDraftState: "IDLE"
    property string postDraftSourceText: ""
    property string postDraftGateReportSha256: ""
    property bool postDraftApplyingCandidate: false
    readonly property bool postDraftBusy:
        root.postDraftState === "VERIFYING"
        || root.postDraftState === "GENERATING"
        || root.postDraftState === "REPAIRING"

    property int currentIndex: 0
    property string currentObjectId: ""
    property string currentObjectTitle: ""
    property string currentObjectType: ""
    property string currentObjectProvenance: ""
    property string currentObjectSourcePath: ""
    readonly property string currentContextReference:
        root.currentObjectId.length > 0 ? "@current" : "@workspace"

    function contextSnapshot(maximumObjects) {
        var maximum = Math.max(
            0,
            Math.floor(maximumObjects)
        )
        var limit = Math.min(
            workspaceObjects.count,
            maximum
        )
        var objects = []

        for (var i = 0; i < limit; ++i) {
            var item = workspaceObjects.get(i)

            objects.push({
                "objectId": String(item.objectId || ""),
                "title": String(item.title || ""),
                "objectType": String(item.objectType || ""),
                "provenanceClass": String(item.provenanceClass || ""),
                "sourcePath": String(item.sourcePath || ""),
                "activityState": String(item.activityState || "")
            })
        }

        return {
            "currentIndex": workspaceObjects.count > 0
                ? root.currentIndex
                : -1,
            "currentObjectId": workspaceObjects.count > 0
                ? root.currentObjectId
                : "",
            "objects": objects
        }
    }

    function resetAuthoringBuffer() {
        root.editorLoaded = false
        root.editorDirty = false
        root.editorBaseText = ""
        root.editorSourceName = ""
        root.editorLanguage = ""
        root.editorBaseSha256 = ""
        root.liveAidState = "IDLE"
        root.liveAidDiagnostics = []
        root.liveAidEvidenceSummary = ""
        root.preflightState = "NOT RUN"
        root.preflightSourceText = ""
        root.preflightReportSha256 = ""
        root.repairState = "IDLE"
        root.repairProposalId = ""
        root.repairSourceText = ""
        root.repairOldText = ""
        root.repairNewText = ""
        root.postDraftState = "IDLE"
        root.postDraftSourceText = ""
        root.postDraftGateReportSha256 = ""
        root.postDraftApplyingCandidate = false
    }

    function loadCurrentAuthoringBuffer() {
        if (root.liveAidBackend === null)
            return

        if (root.currentObjectProvenance !== "REAL_LOCAL_FILE")
            return

        var raw = root.liveAidBackend.loadSource(
            root.currentObjectId
        )
        var payload = JSON.parse(raw)

        if (payload.status !== "PASS") {
            root.editorLoaded = false
            root.liveAidState = "BLOCKED"
            root.liveAidDiagnostics = []
            root.liveAidEvidenceSummary =
                payload.message || "source load failed"
            return
        }

        root.editorLoaded = false
        root.editorBaseText = payload.source
        root.editorSourceName = payload.source_name
        root.editorLanguage = payload.language
        root.editorBaseSha256 = payload.source_sha256
        codeEditor.text = payload.source
        root.editorDirty = false
        root.editorLoaded = true
        root.liveAidState = "QUEUED"
        root.liveAidDiagnostics = []
        root.liveAidEvidenceSummary =
            "DISK SHA · " + payload.source_sha256
            + " · WRITE AUTHORITY NONE"
        root.preflightState = "NOT RUN"
        root.preflightSourceText = ""
        root.preflightReportSha256 = ""
        root.repairState = "IDLE"
        root.repairProposalId = ""
        root.repairSourceText = ""
        root.repairOldText = ""
        root.repairNewText = ""
        root.postDraftState = "IDLE"
        root.postDraftSourceText = ""
        root.postDraftGateReportSha256 = ""
        root.postDraftApplyingCandidate = false
        analysisTimer.restart()
    }

    function requestLiveAidAnalysis() {
        if (!root.editorLoaded)
            return

        if (root.liveAidBackend === null)
            return

        root.liveAidState = "RUNNING"
        root.liveAidBackend.analyze(
            root.currentObjectId,
            root.editorSourceName,
            codeEditor.text,
            root.editorLanguage
        )
    }

    function requestLiveAidPreflight() {
        if (!root.editorLoaded)
            return

        if (root.liveAidBackend === null)
            return

        if (root.preflightState === "RUNNING")
            return

        analysisTimer.stop()
        root.preflightSourceText = codeEditor.text
        root.preflightState = "RUNNING"
        root.liveAidState = "PREFLIGHT"
        root.liveAidDiagnostics = []
        root.liveAidEvidenceSummary =
            "QML GATE PREFLIGHT · RUNNING · "
            + "NO EXECUTION · NO SAVE"

        root.liveAidBackend.preflight(
            root.currentObjectId,
            root.editorSourceName,
            codeEditor.text,
            root.editorLanguage
        )
    }

    function requestLiveAidRepair() {
        if (!root.editorLoaded)
            return

        if (root.liveAidBackend === null)
            return

        if (root.preflightState !== "FAIL")
            return

        if (root.liveAidDiagnostics.length === 0)
            return

        if (root.repairState === "RUNNING")
            return

        root.repairSourceText = codeEditor.text
        root.repairState = "RUNNING"
        root.repairProposalId = ""
        root.repairOldText = ""
        root.repairNewText = ""
        root.liveAidState = "GENERATING"
        root.liveAidEvidenceSummary =
            "LOCAL AI REPAIR · GENERATING · "
            + "UNTRUSTED PROPOSAL ONLY · NO APPLY"

        root.liveAidBackend.requestRepair(
            root.currentObjectId,
            root.editorSourceName,
            codeEditor.text,
            root.editorLanguage
        )
    }

    function requestApplyRepair() {
        if (root.liveAidBackend === null)
            return

        if (root.repairState !== "READY")
            return

        if (root.repairProposalId.length === 0)
            return

        root.liveAidBackend.applyRepair(
            root.repairProposalId,
            root.currentObjectId,
            codeEditor.text
        )
    }


    function requestPostDraftAutomaticRepair() {
        if (!root.editorLoaded)
            return

        if (root.liveAidBackend === null)
            return

        if (root.editorLanguage !== "qml")
            return

        if (root.postDraftBusy)
            return

        analysisTimer.stop()

        root.postDraftSourceText = codeEditor.text
        root.postDraftGateReportSha256 = ""
        root.postDraftState = "VERIFYING"
        root.liveAidState = "VERIFYING"
        root.liveAidDiagnostics = []
        root.liveAidEvidenceSummary =
            "POST-DRAFT · DRAFT COMPLETE · VERIFYING · "
            + "AUTOMATIC PRIVATE-BUFFER REPAIR · "
            + "NO SAVE · NO EXECUTION"

        root.liveAidBackend.runPostDraftRepair(
            root.currentObjectId,
            root.editorSourceName,
            codeEditor.text,
            root.editorLanguage
        )
    }

    onLiveAidBackendChanged: {
        if (
            root.liveAidBackend !== null
            && root.currentObjectProvenance === "REAL_LOCAL_FILE"
        ) {
            Qt.callLater(root.loadCurrentAuthoringBuffer)
        }
    }

    property bool showDemoFixtures: false
    property bool showProductSourceTabs: false
    property real chatWidthRatio: 0.31
    property int telemetryWidth: 168
    property color accentColor: "#8a8a8a"
    property color frameBorder: "#6a6a6a"
    property int frameRadius: 4
    property bool showOpenTabInInput: false
    property bool showInnerEditorChrome: true
    property bool settingsOpen: false
    property bool chatBusy: false
    property string engineTarget: "LOCAL_QWEN"
    property string hostKind: "CODE"
    property string cryptoWalletLabel: "WALLET · DISCONNECTED"
    property int liveEpoch: 0

    function applyLiveReload() {
        root.liveEpoch = root.liveEpoch + 1
    }
    property int utilityHeight: 112
    property bool desktopShell: false
    property int nextInstanceSerial: 2
    property string siteRelativePath: "index.html"
    property string webPageUrl: ""
    property string browseUrl: "about:blank"
    property string browseBarText: ""
    property int sitePreviewNonce: 0
    property string siteImportStatus: "SITE · waiting for import"
    property bool sitePreviewRunning: false
    property string sitePreviewOrigin: ""
    property alias snippetModel: siteFileModel
    ListModel { id: siteFileModel }

    signal chatWidthRatioRequested(real value)
    signal telemetryWidthRequested(int value)
    signal accentColorRequested(color value)
    signal frameBorderRequested(color value)
    signal frameRadiusRequested(int value)
    signal demoVisibilityRequested(bool value)
    signal productSourceTabsRequested(bool value)
    signal showOpenTabInInputRequested(bool value)
    signal showInnerEditorChromeRequested(bool value)
    signal engineTargetRequested(string value)
    signal utilityHeightRequested(int value)
    signal desktopShellRequested(bool value)

    function openSettings() {
        root.settingsOpen = true
    }

    function closeSettings() {
        root.settingsOpen = false
    }

    Shortcut {
        sequence: "Esc"
        enabled: root.settingsOpen
        onActivated: root.closeSettings()
    }

    implicitWidth: 620
    implicitHeight: 620

    ListModel {
        id: workspaceObjects

        ListElement {
            objectId: "ws.file.scratch.1"
            title: "untitled"
            objectType: "CODE_FILE"
            provenanceClass: "REAL_UI_STATE"
            sourcePath: ""
            activityState: "IDLE"
        }
        ListElement {
            objectId: "ws.file.context-composer"
            title: "ContextComposer.qml"
            objectType: "CODE_FILE"
            provenanceClass: "REAL_LOCAL_FILE"
            sourcePath: "qml/components/ContextComposer.qml"
            activityState: "IDLE"
        }
        ListElement {
            objectId: "ws.file.grok-work-stream"
            title: "GrokWorkStream.qml"
            objectType: "CODE_FILE"
            provenanceClass: "REAL_LOCAL_FILE"
            sourcePath: "qml/components/GrokWorkStream.qml"
            activityState: "IDLE"
        }
        ListElement {
            objectId: "ws.file.chat-node"
            title: "ChatNode.qml"
            objectType: "CODE_FILE"
            provenanceClass: "REAL_LOCAL_FILE"
            sourcePath: "qml/components/ChatNode.qml"
            activityState: "IDLE"
        }
        ListElement {
            objectId: "ws.file.workspace-object-node"
            title: "WorkspaceObjectNode.qml"
            objectType: "CODE_FILE"
            provenanceClass: "REAL_LOCAL_FILE"
            sourcePath: "qml/components/WorkspaceObjectNode.qml"
            activityState: "IDLE"
        }
        ListElement {
            objectId: "ws.terminal.user"
            title: "Terminal"
            objectType: "USER_TERMINAL"
            provenanceClass: "REAL_UI_STATE"
            sourcePath: ""
            activityState: "IDLE"
        }
        ListElement {
            objectId: "ws.app.external"
            title: "External app"
            objectType: "EXTERNAL_APP"
            provenanceClass: "REAL_UI_STATE"
            sourcePath: ""
            activityState: "IDLE"
        }
        ListElement {
            objectId: "ws.web.stub"
            title: "Web"
            objectType: "WEBSITE"
            provenanceClass: "REAL_UI_STATE"
            sourcePath: "about:blank"
            activityState: "IDLE"
        }
        ListElement {
            objectId: "ws.site.current"
            title: "Site"
            objectType: "SITE_PROJECT"
            provenanceClass: "REAL_UI_STATE"
            sourcePath: "index.html"
            activityState: "IDLE"
        }
        ListElement {
            objectId: "ws.website.goldgoblins"
            title: "Website"
            objectType: "WEBSITE"
            provenanceClass: "SYNTHETIC_UI_FIXTURE"
            sourcePath: ""
            activityState: "IDLE"
        }
        ListElement {
            objectId: "ws.code.header-css"
            title: "header.css"
            objectType: "CODE_FILE"
            provenanceClass: "SYNTHETIC_UI_FIXTURE"
            sourcePath: ""
            activityState: "IDLE"
        }
        ListElement {
            objectId: "ws.document.invoice-pdf"
            title: "invoice.pdf"
            objectType: "PDF"
            provenanceClass: "SYNTHETIC_UI_FIXTURE"
            sourcePath: ""
            activityState: "IDLE"
        }
        ListElement {
            objectId: "ws.image.product"
            title: "product-image"
            objectType: "IMAGE"
            provenanceClass: "SYNTHETIC_UI_FIXTURE"
            sourcePath: ""
            activityState: "IDLE"
        }
    }

    function focusObject(objectId) {
        for (var i = 0; i < workspaceObjects.count; i++) {
            if (workspaceObjects.get(i).objectId === objectId) {
                activate(i)
                return true
            }
        }
        return false
    }

    function boundObjectActivityState() {
        if (root.currentObjectProvenance === "SYNTHETIC_UI_FIXTURE")
            return "IDLE"

        if (root.postDraftBusy) {
            if (
                root.postDraftState === "GENERATING"
                || root.postDraftState === "REPAIRING"
            )
                return "GENERATING"

            return "RUNNING"
        }

        if (root.repairState === "RUNNING")
            return "GENERATING"

        if (
            root.preflightState === "RUNNING"
            || root.liveAidState === "RUNNING"
            || root.liveAidState === "PREFLIGHT"
        )
            return "RUNNING"

        if (
            root.liveAidState === "GENERATING"
            || root.liveAidState === "VERIFYING"
        )
            return "GENERATING"

        if (root.liveAidState === "WAITING_FOR_USER")
            return "WAITING_FOR_USER"

        if (
            root.liveAidState === "BLOCKED"
            || root.preflightState === "BLOCKED"
            || root.repairState === "BLOCKED"
        )
            return "BLOCKED"

        if (root.preflightState === "FAIL")
            return "FAIL"

        if (root.preflightState === "PASS")
            return "PASS"

        if (root.liveAidState === "QUEUED")
            return "QUEUED"

        if (root.chatBusy)
            return root.engineTarget === "GROK_WORKER"
                ? "STREAMING"
                : "GENERATING"

        return "IDLE"
    }

    function syncObjectActivities() {
        for (var i = 0; i < workspaceObjects.count; i++) {
            var item = workspaceObjects.get(i)
            var nextState = "IDLE"

            if (item.objectId === root.currentObjectId)
                nextState = root.boundObjectActivityState()

            if (item.activityState !== nextState)
                workspaceObjects.setProperty(
                    i,
                    "activityState",
                    nextState
                )
        }
    }

    function hostKindForType(objectType) {
        if (objectType === "USER_TERMINAL")
            return "TERMINAL"
        if (objectType === "EXTERNAL_APP")
            return "EXTERNAL"
        if (objectType === "WEBSITE")
            return "WEB"
        if (objectType === "SITE_PROJECT")
            return "SITE"
        if (objectType === "CRYPTO_DESK")
            return "CRYPTO"
        if (objectType === "TMOG_DESK")
            return "TMOG"
        if (objectType === "DRAW_DESK" || objectType === "IMAGE")
            return "DRAW"
        if (objectType === "PDF")
            return "WEB"
        return "CODE"
    }

    function objectVisibleForKind(item, kind) {
        if (root.hostKindForType(item.objectType) !== kind)
            return false
        if (
            !root.showDemoFixtures
            && item.provenanceClass === "SYNTHETIC_UI_FIXTURE"
        )
            return false
        if (
            !root.showProductSourceTabs
            && item.provenanceClass === "REAL_LOCAL_FILE"
        )
            return false
        return true
    }

    function setHostKind(kind) {
        root.hostKind = kind
        if (kind === "CRYPTO" || kind === "TMOG" || kind === "MEDIA" || kind === "DRAW")
            return
        if (
            kind === "CODE"
            && root.currentObjectType === "SITE_PROJECT"
            && root.siteRelativePath.length > 0
        ) {
            root.activate(root.ensureSiteCodeObject(root.siteRelativePath))
            return
        }
        for (var i = 0; i < workspaceObjects.count; ++i) {
            var item = workspaceObjects.get(i)
            if (!root.objectVisibleForKind(item, kind))
                continue
            root.activate(i)
            return
        }
        if (kind === "CODE")
            root.spawnHostInstance()
    }

    function spawnHostInstance() {
        var kind = root.hostKind
        var serial = root.nextInstanceSerial
        root.nextInstanceSerial = serial + 1
        var objectId = ""
        var title = ""
        var objectType = "CODE_FILE"
        if (kind === "TERMINAL") {
            objectId = "ws.terminal.user." + serial
            title = "Terminal " + serial
            objectType = "USER_TERMINAL"
        } else if (kind === "WEB") {
            objectId = "ws.web.stub." + serial
            title = "Web " + serial
            objectType = "WEBSITE"
        } else if (kind === "EXTERNAL") {
            objectId = "ws.app.external." + serial
            title = "External app " + serial
            objectType = "EXTERNAL_APP"
        } else if (kind === "SITE") {
            objectId = "ws.site.current." + serial
            title = "Site " + serial
            objectType = "SITE_PROJECT"
        } else {
            objectId = "ws.file.scratch." + serial
            title = "untitled-" + serial
            objectType = "CODE_FILE"
        }
        workspaceObjects.append({
            "objectId": objectId,
            "title": title,
            "objectType": objectType,
            "provenanceClass": "REAL_UI_STATE",
            "sourcePath": kind === "WEB" ? "about:blank" : "",
            "activityState": "IDLE"
        })
        root.activate(workspaceObjects.count - 1)
    }

    function isSpawnedObject(objectId) {
        var id = String(objectId || "")
        return id.indexOf("ws.file.scratch.") === 0
            || id.indexOf("ws.terminal.user.") === 0
            || id.indexOf("ws.app.external.") === 0
            || id.indexOf("ws.web.stub.") === 0
            || id.indexOf("ws.site.current.") === 0
            || id.indexOf("ws.site.file.") === 0
    }

    function scratchHost() {
        var win = Window.window
        if (win && win.surfaceHost)
            return win.surfaceHost
        return null
    }

    function scratchFileName() {
        var name = String(root.currentObjectTitle || "untitled")
        name = name.replace(/[^A-Za-z0-9._-]+/g, "-")
        if (name.length === 0)
            name = "untitled"
        if (name.indexOf(".") < 0)
            name += ".txt"
        return name
    }

    function scratchNameFromUrl(url) {
        var raw = String(url || "").replace(/^file:\/\//, "")
        try {
            raw = decodeURIComponent(raw)
        } catch (e) {
        }
        var parts = raw.split("/")
        return parts[parts.length - 1] || ""
    }

    function saveScratchAs(fileName) {
        var name = String(fileName || "").replace(/[^A-Za-z0-9._-]+/g, "-")
        if (name.length === 0)
            return false
        if (root.currentObjectType !== "CODE_FILE")
            return false
        if (root.currentObjectProvenance !== "REAL_UI_STATE")
            return false
        var host = root.scratchHost()
        if (host === null)
            return false
        var saved = host.saveScratchFile(name, codeEditor.text)
        if (!saved || String(saved).length === 0)
            return false
        if (root.currentIndex >= 0)
            workspaceObjects.setProperty(root.currentIndex, "title", name)
        root.editorSourceName = name
        root.editorBaseText = codeEditor.text
        root.editorDirty = false
        root.liveAidEvidenceSummary = "SAVED · " + String(saved)
        return true
    }

    function saveScratchBuffer() {
        if (String(root.currentObjectId).indexOf("ws.site.file.") === 0)
            return root.saveSiteBuffer()
        return root.saveScratchAs(root.scratchFileName())
    }

    function filePathFromUrl(url) {
        var raw = String(url || "").replace(/^file:\/\//, "")
        try {
            raw = decodeURIComponent(raw)
        } catch (e) {
        }
        return raw
    }

    function openSaveAsDialog() {
        var host = root.scratchHost()
        var folder = "file:///home/GG/.local/state/goldgoblins/gg-ai-desktop/scratch"
        var name = root.scratchFileName()
        if (
            String(root.currentObjectId).indexOf("ws.site.file.") === 0
            && host !== null
        ) {
            folder = "file://" + String(host.siteRoot())
            if (String(root.siteRelativePath).length > 0)
                name = String(root.siteRelativePath)
        }
        scratchSaveDialog.currentFolder = folder
        scratchSaveDialog.selectedFile = folder + "/" + name
        scratchSaveDialog.open()
    }

    function applySaveAsUrl(url) {
        var path = root.filePathFromUrl(url)
        var host = root.scratchHost()
        if (host !== null) {
            var siteRoot = String(host.siteRoot())
            if (siteRoot.length > 0 && path.indexOf(siteRoot) === 0) {
                var rel = path.slice(siteRoot.length).replace(/^\//, "")
                if (rel.length === 0)
                    return false
                var saved = host.writeSiteFile(rel, codeEditor.text)
                if (!saved)
                    return false
                root.editorBaseText = codeEditor.text
                root.editorDirty = false
                root.liveAidEvidenceSummary = "SAVED AS · site:" + rel
                return true
            }
        }
        return root.saveScratchAs(root.scratchNameFromUrl(url))
    }

    function webTabCount() {
        var n = 0
        var i
        for (i = 0; i < workspaceObjects.count; ++i) {
            var item = workspaceObjects.get(i)
            if (
                item.objectType === "WEBSITE"
                && item.provenanceClass === "REAL_UI_STATE"
            )
                n += 1
        }
        return n
    }

    function resetWebTab(index) {
        if (index < 0 || index >= workspaceObjects.count)
            return
        workspaceObjects.setProperty(index, "sourcePath", "about:blank")
        workspaceObjects.setProperty(index, "title", "Web")
        if (index === root.currentIndex) {
            root.browseUrl = "about:blank"
            root.browseBarText = ""
        }
        root.activate(index)
    }

    function closeHostInstance(index) {
        if (index < 0 || index >= workspaceObjects.count)
            return
        var item = workspaceObjects.get(index)
        if (
            item.objectType === "WEBSITE"
            && item.provenanceClass === "REAL_UI_STATE"
        ) {
            if (
                item.objectId === "ws.web.stub"
                || root.webTabCount() <= 1
            ) {
                root.resetWebTab(index)
                return
            }
        } else if (!root.isSpawnedObject(item.objectId))
            return
        if (
            index === root.currentIndex
            && item.objectType === "CODE_FILE"
            && item.provenanceClass === "REAL_UI_STATE"
            && root.editorDirty
        )
            root.saveScratchBuffer()
        var host = root.scratchHost()
        if (
            host !== null
            && item.objectType === "USER_TERMINAL"
        )
            host.stopChatTerminal(item.objectId)
        var closedKind = root.hostKindForType(item.objectType)
        var wasCurrent = index === root.currentIndex
        workspaceObjects.remove(index)
        if (root.currentIndex > index)
            root.currentIndex -= 1
        if (!wasCurrent)
            return
        root.setHostKind(closedKind)
    }

    function refreshSiteFiles() {
        var host = root.scratchHost()
        if (host === null)
            return
        var raw = host.listSiteFiles()
        var rows = []
        try {
            rows = JSON.parse(raw)
        } catch (e) {
            rows = []
        }
        siteFileModel.clear()
        for (var i = 0; i < rows.length; ++i)
            siteFileModel.append(rows[i])
        if (
            !root.sitePreviewRunning
            && root.siteImportStatus.indexOf("IMPORT") !== 0
            && root.siteImportStatus.indexOf("PREVIEW") !== 0
            && rows.length > 0
        )
            root.siteImportStatus = "SITE · local · " + String(rows.length) + " listed"
        var preferred = host.preferredSiteFile
            ? host.preferredSiteFile()
            : ""
        if (root.siteRelativePath.length === 0 && preferred.length > 0)
            root.openSiteFile(preferred)
        else if (root.siteRelativePath.length === 0 && rows.length > 0)
            root.openSiteFile(rows[0].path)
    }

    function siteFileObjectId(relative) {
        return "ws.site.file." + String(relative || "")
    }

    function ensureSiteCodeObject(relative) {
        var objectId = root.siteFileObjectId(relative)
        for (var i = 0; i < workspaceObjects.count; ++i) {
            if (workspaceObjects.get(i).objectId === objectId)
                return i
        }
        workspaceObjects.append({
            "objectId": objectId,
            "title": relative,
            "objectType": "CODE_FILE",
            "provenanceClass": "REAL_UI_STATE",
            "sourcePath": relative,
            "activityState": "IDLE"
        })
        return workspaceObjects.count - 1
    }

    function chooseSnippet(relative) {
        root.ensureSiteCodeObject(relative)
        if (root.hostKind === "CODE")
            root.activate(root.ensureSiteCodeObject(relative))
        else
            root.openSiteFile(relative)
    }

    function openSiteFile(relative) {
        var host = root.scratchHost()
        if (host === null)
            return
        var body = host.readSiteFile(relative)
        root.siteRelativePath = relative
        root.currentObjectSourcePath = relative
        root.editorLoaded = false
        root.editorBaseText = body
        codeEditor.text = body
        root.editorDirty = false
        root.editorLoaded = true
        root.webPageUrl = host.siteFileUrl(relative)
        if (root.sitePreviewRunning)
            root.applySitePreviewUrl()
        if (host.watchLivePath && host.siteRoot)
            host.watchLivePath(host.siteRoot() + "/" + relative)
    }

    function rememberBrowse(index, href) {
        if (index < 0 || index >= workspaceObjects.count)
            return
        var item = workspaceObjects.get(index)
        if (item.objectType !== "WEBSITE")
            return
        workspaceObjects.setProperty(index, "sourcePath", href)
        if (index === root.currentIndex) {
            root.browseUrl = href
            root.browseBarText = href === "about:blank" ? "" : href
        }
    }

    function goBrowse(raw) {
        var host = root.scratchHost()
        if (host === null)
            return
        var next = host.normalizeBrowseUrl(raw)
        if (!next)
            return
        root.rememberBrowse(root.currentIndex, next)
    }

    function applySitePreviewUrl() {
        if (!root.sitePreviewRunning || root.sitePreviewOrigin.length === 0) {
            var host = root.scratchHost()
            if (host !== null && root.siteRelativePath.length > 0)
                root.webPageUrl = host.siteFileUrl(root.siteRelativePath)
            return
        }
        var rel = root.siteRelativePath
        if (
            rel === "index.php"
            || rel === "index.html"
            || rel.length === 0
        )
            rel = ""
        root.webPageUrl = root.sitePreviewOrigin + rel
        root.sitePreviewNonce = root.sitePreviewNonce + 1
    }

    function ensureSitePreview() {
        var host = root.scratchHost()
        if (host === null)
            return false
        if (root.sitePreviewRunning && root.sitePreviewOrigin.length > 0) {
            root.applySitePreviewUrl()
            return true
        }
        var existing = host.sitePreviewOrigin
            ? String(host.sitePreviewOrigin())
            : ""
        if (existing.length > 0) {
            root.sitePreviewOrigin = existing
            root.sitePreviewRunning = true
            root.siteImportStatus = "PREVIEW · localhost"
            root.applySitePreviewUrl()
            return true
        }
        root.siteImportStatus = "PREVIEW · starting"
        var raw = host.startSitePreview()
        var lines = String(raw).split("\n")
        var origin = lines[0] || ""
        var kind = lines.length > 1 ? lines[1] : "STATIC"
        if (origin.length === 0) {
            root.siteImportStatus = "FAIL: local preview did not start"
            return false
        }
        root.sitePreviewOrigin = origin
        root.sitePreviewRunning = true
        root.siteImportStatus = (
            kind === "PHP"
                ? "PREVIEW · localhost PHP"
                : "PREVIEW · localhost static · PHP not installed · WP will not execute"
        )
        root.applySitePreviewUrl()
        return true
    }

    function toggleSitePreview() {
        var host = root.scratchHost()
        if (host === null)
            return
        if (root.sitePreviewRunning) {
            host.stopSitePreview()
            root.sitePreviewRunning = false
            root.sitePreviewOrigin = ""
            root.siteImportStatus = "PREVIEW · stopped"
            root.applySitePreviewUrl()
            return
        }
        root.ensureSitePreview()
    }

    function importSiteSqlFromDialog(urlString) {
        var host = root.scratchHost()
        if (host === null)
            return
        root.siteImportStatus = "IMPORT SQL · starting"
        var result = host.importSiteSql(urlString)
        root.siteImportStatus = String(result)
        root.liveAidEvidenceSummary = String(result)
    }

    function importSiteFromDialog(urlString) {
        var host = root.scratchHost()
        if (host === null)
            return
        root.siteImportStatus = "IMPORT · starting"
        var result = host.importSite(urlString)
        root.siteImportStatus = String(result)
        root.refreshSiteFiles()
        if (String(result).indexOf("PASS") === 0) {
            var preview = host.preferredSiteFile()
            if (preview.length > 0)
                root.openSiteFile(preview)
            else if (siteFileModel.count > 0)
                root.openSiteFile(siteFileModel.get(0).path)
            root.sitePreviewNonce = root.sitePreviewNonce + 1
        }
        root.liveAidEvidenceSummary = String(result)
    }

    function saveSiteBuffer() {
        var host = root.scratchHost()
        if (host === null)
            return false
        var saved = host.writeSiteFile(
            root.siteRelativePath,
            codeEditor.text
        )
        if (!saved)
            return false
        root.editorBaseText = codeEditor.text
        root.editorDirty = false
        root.liveAidEvidenceSummary = "SAVED · site:" + root.siteRelativePath
        if (root.sitePreviewRunning) {
            root.sitePreviewNonce = root.sitePreviewNonce + 1
            root.siteImportStatus = "SAVED · " + root.siteRelativePath + " · preview reload"
        } else {
            root.webPageUrl = host.siteFileUrl(root.siteRelativePath)
            root.siteImportStatus = "SAVED · " + root.siteRelativePath
        }
        return true
    }

    function applyChatCodeToCurrent(source) {
        var body = String(source || "")
        if (body.length === 0)
            return false
        if (root.currentObjectType !== "CODE_FILE")
            return false
        if (root.currentObjectProvenance !== "REAL_UI_STATE")
            return false
        root.editorLoaded = true
        codeEditor.text = body
        root.editorDirty = body !== root.editorBaseText
        return true
    }

    function openScratchBuffer() {
        var host = root.scratchHost()
        var name = root.scratchFileName()
        var body = ""
        if (host !== null && host.readScratchFile)
            body = host.readScratchFile(name)
        root.editorLoaded = false
        root.editorBaseText = body
        root.editorSourceName = name
        root.editorLanguage = "text"
        root.editorBaseSha256 = ""
        codeEditor.text = body
        root.editorDirty = false
        root.editorLoaded = true
        root.liveAidState = "IDLE"
        root.liveAidDiagnostics = []
        root.liveAidEvidenceSummary = "SCRATCH · " + name
        if (host !== null && host.watchLivePath)
            host.watchLivePath(host.saveScratchFile(name, body))
    }

    function applyExternalFile(path, text, kind) {
        var p = String(path || "")
        var body = String(text || "")
        var k = String(kind || "")
        if (k === "site-dir") {
            root.refreshSiteFiles()
            if (
                root.currentObjectType === "CODE_FILE"
                && String(root.currentObjectId).indexOf("ws.site.file.") === 0
                && root.siteRelativePath.length > 0
            )
                root.openSiteFile(root.siteRelativePath)
            return
        }
        if (k === "scratch-dir") {
            if (
                root.currentObjectType === "CODE_FILE"
                && String(root.currentObjectId).indexOf("ws.file.scratch.") === 0
            )
                root.openScratchBuffer()
            return
        }
        if (
            k === "site"
            && p.length > 0
            && root.siteRelativePath.length > 0
            && p.indexOf(root.siteRelativePath) >= 0
        ) {
            root._applyingExternal = true
            root.editorLoaded = true
            codeEditor.text = body
            root.editorBaseText = body
            root.editorDirty = false
            root._applyingExternal = false
            if (root.sitePreviewRunning)
                root.sitePreviewNonce = root.sitePreviewNonce + 1
            return
        }
        if (
            k === "scratch"
            && root.currentObjectType === "CODE_FILE"
            && String(root.currentObjectId).indexOf("ws.file.scratch.") === 0
            && (
                p.indexOf(root.scratchFileName()) >= 0
                || p.indexOf("untitled.txt") >= 0
            )
        ) {
            root._applyingExternal = true
            root.editorLoaded = true
            codeEditor.text = body
            root.editorBaseText = body
            root.editorDirty = false
            root._applyingExternal = false
        }
    }

    function activate(index) {
        if (index < 0 || index >= workspaceObjects.count)
            return
        var item = workspaceObjects.get(index)
        if (
            root.currentIndex === index
            && root.currentObjectId === item.objectId
        ) {
            root.settingsOpen = false
            root.hostKind = root.hostKindForType(item.objectType)
            return
        }
        root.settingsOpen = false
        root.currentIndex = index
        root.currentObjectId = item.objectId
        root.currentObjectTitle = item.title
        root.currentObjectType = item.objectType
        root.currentObjectProvenance = item.provenanceClass
        root.currentObjectSourcePath = item.sourcePath
        root.hostKind = root.hostKindForType(item.objectType)
        root.activeObjectChanged(item.objectId, item.title)

        root.resetAuthoringBuffer()
        root.syncObjectActivities()

        if (
            item.objectType === "CODE_FILE"
            && item.provenanceClass === "REAL_UI_STATE"
        ) {
            if (String(item.sourcePath || "").length > 0)
                Qt.callLater(function() {
                    root.openSiteFile(item.sourcePath)
                })
            else
                Qt.callLater(root.openScratchBuffer)
            return
        }

        if (item.objectType === "SITE_PROJECT") {
            Qt.callLater(function() {
                root.refreshSiteFiles()
                var host = root.scratchHost()
                var preferred = host && host.preferredSiteFile
                    ? host.preferredSiteFile()
                    : ""
                var rel = preferred.length > 0
                    ? preferred
                    : (item.sourcePath.length > 0 ? item.sourcePath : "index.php")
                root.ensureSitePreview()
                root.openSiteFile(rel)
            })
            return
        }

        if (item.objectType === "WEBSITE") {
            var stored = String(item.sourcePath || "")
            if (stored.length === 0)
                stored = "about:blank"
            root.browseUrl = stored
            root.browseBarText = stored === "about:blank" ? "" : stored
            return
        }

        if (
            item.provenanceClass === "REAL_LOCAL_FILE"
            && root.liveAidBackend !== null
        ) {
            Qt.callLater(root.loadCurrentAuthoringBuffer)
        }
    }

    property bool _applyingExternal: false

    Component.onCompleted: {
        activate(0)
        Qt.callLater(root.refreshSiteFiles)
        var host = root.scratchHost()
        if (host !== null && host.watchDesktopWorkspace)
            host.watchDesktopWorkspace()
    }

    onLiveAidStateChanged: root.syncObjectActivities()
    onPreflightStateChanged: root.syncObjectActivities()
    onPostDraftStateChanged: root.syncObjectActivities()
    onRepairStateChanged: root.syncObjectActivities()
    onEditorDirtyChanged: root.syncObjectActivities()
    onCurrentObjectIdChanged: root.syncObjectActivities()
    onChatBusyChanged: root.syncObjectActivities()
    onEngineTargetChanged: root.syncObjectActivities()

    Timer {
        id: analysisTimer
        interval: 280
        repeat: false
        onTriggered: root.requestLiveAidAnalysis()
    }

    Timer {
        id: scratchLiveTimer
        interval: 220
        repeat: false
        onTriggered: {
            if (root._applyingExternal)
                return
            if (root.currentObjectType !== "CODE_FILE")
                return
            if (String(root.currentObjectId).indexOf("ws.file.scratch.") !== 0)
                return
            root.saveScratchBuffer()
        }
    }

    Connections {
        target: Window.window && Window.window.surfaceHost
            ? Window.window.surfaceHost
            : null
        ignoreUnknownSignals: true

        function onWorkspaceFileChanged(path, text, kind) {
            root.applyExternalFile(path, text, kind)
        }
    }

    Connections {
        target: root.liveAidBackend
        enabled: root.liveAidBackend !== null
        ignoreUnknownSignals: true

        function onResultReady(objectId, payloadJson) {
            if (objectId !== root.currentObjectId)
                return

            if (root.preflightState === "RUNNING")
                return

            var result = JSON.parse(payloadJson)
            root.liveAidState = result.status || "UNKNOWN"
            root.liveAidDiagnostics = result.diagnostics || []
            root.liveAidEvidenceSummary =
                "EXECUTION READY · "
                + String(result.execution_ready).toUpperCase()
                + " · ACTION " + (result.action_authority || "NONE")
                + " · NETWORK " + (result.network_authority || "NONE")
        }

        function onAnalysisFailed(objectId, message) {
            if (objectId !== root.currentObjectId)
                return

            root.liveAidState = "BLOCKED"
            root.liveAidDiagnostics = []
            root.liveAidEvidenceSummary =
                "LIVE AID BRIDGE ERROR · " + message
        }

        function onPreflightReady(objectId, payloadJson) {
            if (objectId !== root.currentObjectId)
                return

            var result = JSON.parse(payloadJson)

            if (codeEditor.text !== root.preflightSourceText) {
                root.preflightState = "STALE"
                root.preflightReportSha256 = ""
                root.repairState = "STALE"
                root.repairProposalId = ""
                root.repairOldText = ""
                root.repairNewText = ""
                root.liveAidState = "QUEUED"
                root.liveAidDiagnostics = []
                root.liveAidEvidenceSummary =
                    "PREFLIGHT RESULT STALE · "
                    + "BUFFER CHANGED DURING CHECK"
                analysisTimer.restart()
                return
            }

            root.preflightState = result.gate_status
            root.preflightReportSha256 =
                result.gate_report_sha256 || ""
            root.repairProposalId = ""
            root.repairSourceText = ""
            root.repairOldText = ""
            root.repairNewText = ""

            if (result.gate_status === "FAIL")
                root.repairState = "AVAILABLE"
            else
                root.repairState = "IDLE"

            root.liveAidState = result.status
            root.liveAidDiagnostics =
                result.diagnostics || []
            root.liveAidEvidenceSummary =
                "QML GATE " + result.gate_status
                + " · PROFILE BOUND · REPORT "
                + result.gate_report_sha256.substring(0, 12)
                + " · NO EXECUTION · DISK UNCHANGED"
        }

        function onPreflightFailed(objectId, message) {
            if (objectId !== root.currentObjectId)
                return

            if (codeEditor.text !== root.preflightSourceText) {
                root.preflightState = "STALE"
                root.preflightReportSha256 = ""
                root.repairState = "STALE"
                root.repairProposalId = ""
                root.repairOldText = ""
                root.repairNewText = ""
                root.liveAidState = "QUEUED"
                root.liveAidEvidenceSummary =
                    "PREFLIGHT FAILURE STALE · "
                    + "BUFFER CHANGED DURING CHECK"
                analysisTimer.restart()
                return
            }

            root.preflightState = "BLOCKED"
            root.preflightReportSha256 = ""
            root.repairState = "BLOCKED"
            root.repairProposalId = ""
            root.repairOldText = ""
            root.repairNewText = ""
            root.liveAidState = "BLOCKED"
            root.liveAidDiagnostics = []
            root.liveAidEvidenceSummary =
                "QML PREFLIGHT HARNESS ERROR · " + message
        }

        function onRepairReady(objectId, payloadJson) {
            if (objectId !== root.currentObjectId)
                return

            var result = JSON.parse(payloadJson)

            if (codeEditor.text !== root.repairSourceText) {
                root.repairState = "STALE"
                root.repairProposalId = ""
                root.repairOldText = ""
                root.repairNewText = ""
                root.liveAidState = "QUEUED"
                root.liveAidEvidenceSummary =
                    "AI REPAIR PROPOSAL STALE · "
                    + "BUFFER CHANGED DURING MODEL RUN"
                analysisTimer.restart()
                return
            }

            root.repairProposalId = result.proposal_id
            root.repairOldText = result.old_text
            root.repairNewText = result.new_text
            root.repairState = "READY"
            root.liveAidState = "WAITING_FOR_USER"
            root.liveAidEvidenceSummary =
                "AI PROPOSAL · UNTRUSTED · OLD: "
                + result.old_text
                + " → NEW: " + result.new_text
                + " · WHY " + result.why
                + " · APPLY REQUIRES CLICK"
        }

        function onRepairFailed(objectId, message) {
            if (objectId !== root.currentObjectId)
                return

            root.repairState = "BLOCKED"
            root.repairProposalId = ""
            root.repairOldText = ""
            root.repairNewText = ""
            root.liveAidState = "BLOCKED"
            root.liveAidEvidenceSummary =
                "AI REPAIR ERROR · " + message
        }

        function onRepairApplied(
            objectId,
            proposalId,
            candidateSource
        ) {
            if (objectId !== root.currentObjectId)
                return

            if (proposalId !== root.repairProposalId)
                return

            codeEditor.text = candidateSource

            root.repairState = "APPLIED"
            root.repairProposalId = ""
            root.repairOldText = ""
            root.repairNewText = ""
            root.preflightState = "STALE"
            root.preflightReportSha256 = ""
            root.liveAidState = "QUEUED"
            root.liveAidDiagnostics = []
            root.liveAidEvidenceSummary =
                "AI REPAIR APPLIED TO BUFFER ONLY · "
                + "PREFLIGHT REQUIRED · NO SAVE · NO EXECUTION"

            analysisTimer.restart()
        }

        function onPostDraftEvent(
            objectId,
            payloadJson
        ) {
            if (objectId !== root.currentObjectId)
                return

            if (root.postDraftState === "STALE")
                return

            if (codeEditor.text !== root.postDraftSourceText) {
                root.postDraftState = "STALE"
                root.liveAidState = "QUEUED"
                root.liveAidDiagnostics = []
                root.liveAidEvidenceSummary =
                    "POST-DRAFT RESULT STALE · "
                    + "BUFFER CHANGED DURING AUTOMATIC REPAIR · "
                    + "RESULT WILL NOT BE APPLIED"
                return
            }

            var event = JSON.parse(payloadJson)
            var name = event.event || "UNKNOWN"

            if (name === "DRAFT_COMPLETE") {
                root.postDraftState = "VERIFYING"
                root.liveAidState = "VERIFYING"
            } else if (name === "VERIFYING") {
                root.postDraftState = "VERIFYING"
                root.liveAidState = "VERIFYING"
            } else if (name === "REPAIRING") {
                root.postDraftState = "GENERATING"
                root.liveAidState = "GENERATING"
            } else if (name === "CANDIDATE_APPLIED_IN_MEMORY") {
                root.postDraftState = "REPAIRING"
                root.liveAidState = "REPAIRING"
            } else if (name === "PREFLIGHT_RESPONSE") {
                if (event.gate_status)
                    root.preflightState = event.gate_status

                if (event.gate_report_sha256) {
                    root.postDraftGateReportSha256 =
                        event.gate_report_sha256
                }
            } else if (name === "READY_TO_RUN") {
                root.postDraftState = "REPAIRING"
                root.liveAidState = "REPAIRING"
            } else if (name === "BLOCKED") {
                root.postDraftState = "BLOCKED"
                root.liveAidState = "BLOCKED"
            }

            root.liveAidEvidenceSummary =
                "POST-DRAFT · " + name
                + " · REPAIRS "
                + String(event.repair_attempts || 0)
                + " · MODEL DISPATCH "
                + String(event.model_dispatch_count || 0)
                + " · NO SAVE · NO EXECUTION"
        }

        function onPostDraftReady(
            objectId,
            payloadJson
        ) {
            if (objectId !== root.currentObjectId)
                return

            if (
                root.postDraftState === "STALE"
                || codeEditor.text !== root.postDraftSourceText
            ) {
                root.postDraftState = "STALE"
                root.liveAidState = "QUEUED"
                root.liveAidDiagnostics = []
                root.liveAidEvidenceSummary =
                    "POST-DRAFT VERIFIED RESULT DISCARDED · "
                    + "BUFFER CHANGED DURING RUN"
                analysisTimer.restart()
                return
            }

            var result = JSON.parse(payloadJson)

            if (
                result.state !== "READY_TO_RUN"
                || result.execution_ready !== true
            ) {
                root.postDraftState = "BLOCKED"
                root.liveAidState = "BLOCKED"
                root.liveAidEvidenceSummary =
                    "POST-DRAFT BLOCKED · "
                    + (result.blocked_fault_layer || "UNKNOWN")
                    + " · "
                    + (result.blocked_reason || "no ready result")
                return
            }

            root.postDraftApplyingCandidate = true
            codeEditor.text = result.source
            root.postDraftApplyingCandidate = false

            root.postDraftSourceText = result.source
            root.postDraftState = "READY_TO_RUN"

            root.preflightState = "PASS"
            root.preflightSourceText = result.source
            root.preflightReportSha256 =
                root.postDraftGateReportSha256

            root.repairState = "IDLE"
            root.repairProposalId = ""
            root.repairSourceText = ""
            root.repairOldText = ""
            root.repairNewText = ""

            root.liveAidState = "READY_TO_RUN"
            root.liveAidDiagnostics = []
            root.liveAidEvidenceSummary =
                "POST-DRAFT AUTO REPAIR · READY TO RUN · "
                + "REPAIRS "
                + String(result.repair_attempts)
                + " · MODEL DISPATCH "
                + String(result.model_dispatch_count)
                + " · BUFFER ONLY · DISK UNCHANGED · "
                + "NO EXECUTION"
        }

        function onPostDraftFailed(
            objectId,
            message
        ) {
            if (objectId !== root.currentObjectId)
                return

            if (
                root.postDraftState === "STALE"
                || codeEditor.text !== root.postDraftSourceText
            ) {
                root.postDraftState = "STALE"
                root.liveAidState = "QUEUED"
                root.liveAidEvidenceSummary =
                    "POST-DRAFT FAILURE STALE · "
                    + "BUFFER CHANGED DURING RUN"
                analysisTimer.restart()
                return
            }

            root.postDraftState = "BLOCKED"
            root.liveAidState = "BLOCKED"
            root.liveAidDiagnostics = []
            root.liveAidEvidenceSummary =
                "POST-DRAFT ASYNC ERROR · " + message
        }

    }

    Rectangle {
        z: 5
        anchors.left: tabs.left
        anchors.leftMargin: -6
        anchors.top: tabs.top
        width: tabs.width + 12
        height: 18
        color: "#161616"
        visible: tabs.width > 0
    }

    readonly property string frameKindLabel: root.settingsOpen
        ? "SETTINGS"
        : String(root.hostKind || "")
    readonly property int tabStripLeft:
        root.frameKindLabel.length > 0
            ? (20 + root.frameKindLabel.length * 8)
            : 14

    Row {
        id: tabs
        z: 6
        anchors.left: parent.left
        anchors.leftMargin: root.tabStripLeft
        anchors.top: parent.top
        anchors.topMargin: -8
        height: 18
        spacing: 0

        Repeater {
            model: workspaceObjects

            delegate: Item {
                id: tabButton

                required property int index
                required property string objectId
                required property string title
                required property string objectType
                required property string activityState
                required property string provenanceClass

                readonly property bool kindMatch:
                    root.hostKindForType(tabButton.objectType) === root.hostKind
                readonly property bool tabVisible:
                    tabButton.kindMatch
                    && (
                        root.showDemoFixtures
                        || tabButton.provenanceClass
                            !== "SYNTHETIC_UI_FIXTURE"
                    )
                    && (
                        root.showProductSourceTabs
                        || tabButton.provenanceClass
                            !== "REAL_LOCAL_FILE"
                    )
                readonly property bool tabCurrent:
                    tabButton.index === root.currentIndex

                visible: tabButton.tabVisible
                width: visible
                    ? sepText.implicitWidth
                        + tabText.implicitWidth
                        + closeText.implicitWidth
                    : 0
                height: 18

                Text {
                    id: sepText
                    text: " | "
                    height: 18
                    verticalAlignment: Text.AlignVCenter
                    visible: {
                        if (!tabButton.tabVisible)
                            return false
                        for (var i = 0; i < tabButton.index; ++i) {
                            var prev = workspaceObjects.get(i)
                            if (
                                !root.objectVisibleForKind(
                                    prev,
                                    root.hostKind
                                )
                            )
                                continue
                            return true
                        }
                        return false
                    }
                    color: "#a8b0b8"
                    font.family: "monospace"
                    font.pixelSize: 12
                }

                Text {
                    id: tabText
                    anchors.left: sepText.visible ? sepText.right : parent.left
                    height: 18
                    verticalAlignment: Text.AlignVCenter
                    text: tabButton.title
                    color: tabButton.tabCurrent ? "#d8dee9" : "#a8b0b8"
                    font.family: "monospace"
                    font.pixelSize: 12
                    font.bold: tabButton.tabCurrent
                }

                Text {
                    id: closeText
                    objectName: "workspaceCloseInstanceButton"
                    z: 12
                    anchors.left: tabText.right
                    width: visible ? 14 : 0
                    height: 18
                    verticalAlignment: Text.AlignVCenter
                    text: " ×"
                    color: "#c8a97e"
                    font.family: "monospace"
                    font.pixelSize: 12
                    visible: root.isSpawnedObject(tabButton.objectId)
                        || (
                            tabButton.objectType === "WEBSITE"
                            && tabButton.provenanceClass === "REAL_UI_STATE"
                        )

                    MouseArea {
                        anchors.fill: parent
                        z: 13
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.closeHostInstance(tabButton.index)
                    }
                }

                MouseArea {
                    z: 1
                    anchors.fill: parent
                    anchors.rightMargin: closeText.visible
                        ? closeText.width
                        : 0
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.activate(tabButton.index)
                }
            }
        }

        Item {
            objectName: "workspaceSpawnInstanceButton"
            visible: !root.settingsOpen
                && root.hostKind !== "CRYPTO"
                && root.hostKind !== "TMOG"
                && root.hostKind !== "MEDIA"
                && root.hostKind !== "DRAW"
            width: visible ? spawnTabRow.width : 0
            height: 18

            Row {
                id: spawnTabRow
                spacing: 0

                Text {
                    text: " | "
                    color: "#a8b0b8"
                    font.family: "monospace"
                    font.pixelSize: 12
                }

                Text {
                    text: "+"
                    color: "#c8cdd4"
                    font.family: "monospace"
                    font.pixelSize: 12
                }
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.spawnHostInstance()
            }
        }

        Item {
            visible: root.settingsOpen
            width: visible ? settingsTabRow.width : 0
            height: 18

            Row {
                id: settingsTabRow
                spacing: 0

                Text {
                    text: " | "
                    color: "#a8b0b8"
                    font.family: "monospace"
                    font.pixelSize: 12
                }

                Text {
                    text: "Settings"
                    color: "#d8dee9"
                    font.family: "monospace"
                    font.pixelSize: 12
                    font.bold: true
                }

                Text {
                    objectName: "settingsTabCloseButton"
                    text: " ×"
                    color: "#c8cdd4"
                    font.family: "monospace"
                    font.pixelSize: 12

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.closeSettings()
                    }
                }
            }
        }
    }

    Item {
        id: codeActions
        objectName: "workspaceSaveScratchRow"
        z: 6
        visible:
            !root.settingsOpen
            && root.hostKind === "CODE"
            && root.currentObjectProvenance === "REAL_UI_STATE"
            && root.currentObjectType === "CODE_FILE"
        anchors.right: parent.right
        anchors.rightMargin: 88
        anchors.top: parent.top
        anchors.topMargin: -8
        height: 18
        width: scratchSaveRow.implicitWidth + 12

        Rectangle {
            anchors.fill: parent
            color: "#161616"
        }

        Row {
            id: scratchSaveRow
            anchors.centerIn: parent
            spacing: 10

            Text {
                height: 18
                verticalAlignment: Text.AlignVCenter
                text: root.editorDirty ? "SAVE" : "SAVED"
                color: "#c8cdd4"
                font.family: "monospace"
                font.pixelSize: 12
                font.bold: true

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.saveScratchBuffer()
                }
            }

            Text {
                objectName: "workspaceSaveScratchButton"
                height: 18
                verticalAlignment: Text.AlignVCenter
                text: "SAVE AS"
                color: "#c8cdd4"
                font.family: "monospace"
                font.pixelSize: 12
                font.bold: true

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.openSaveAsDialog()
                }
            }
        }
    }

    GgFrame {
        id: workspaceFrame
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 8
        leftLegend: root.frameKindLabel
        rightLegend: root.chatBusy
            ? (
                root.engineTarget === "GROK_WORKER"
                    ? "STREAMING"
                    : "GENERATING"
            )
            : (root.hostKind === "CRYPTO"
                ? ((cryptoPane.item && cryptoPane.item.legend) || "TESTNET")
                : (
                    root.currentObjectTitle.length > 0
                        ? "@current"
                        : "@workspace"
                ))
        bottomLeftLegend: ""
        bottomRightLegend: root.editorDirty
            ? (
                root.currentObjectProvenance === "REAL_LOCAL_FILE"
                    ? "BUFFER · UNSAVED · DISK UNCHANGED"
                    : "BUFFER · UNSAVED"
            )
            : (
                root.hostKind === "CODE"
                    ? "BUFFER · DISK BASE"
                    : "DISK BASE"
            )
        backgroundColor: "#161616"
        borderColor: root.frameBorder
        radius: root.frameRadius

        Flow {
            id: objectNodeRail
            objectName: "workspaceObjectNodeRail"
            width: parent.width
            spacing: 8
            visible: false
            height: 0

            Repeater {
                model: workspaceObjects

                delegate: Item {
                    id: objectNodeWrap
                    objectName: "workspaceObjectNodeWrap"

                    required property int index
                    required property string objectId
                    required property string title
                    required property string objectType
                    required property string provenanceClass
                    required property string sourcePath
                    required property string activityState

                    width: 0
                    height: 0

                    WorkspaceObjectNode {
                        id: objectNode
                        width: objectNodeWrap.width
                        height: objectNodeWrap.height
                        objectId: objectNodeWrap.objectId
                        title: objectNodeWrap.title
                        objectType: objectNodeWrap.objectType
                        provenanceClass: objectNodeWrap.provenanceClass
                        sourcePath: objectNodeWrap.sourcePath
                        activityState: objectNodeWrap.activityState
                        current:
                            objectNodeWrap.index === root.currentIndex
                        editorDirty:
                            objectNode.current
                            && root.editorDirty
                            && objectNodeWrap.provenanceClass
                                === "REAL_LOCAL_FILE"
                        accentColor: root.accentColor
                        onActivated: function(value) {
                            root.focusObject(value)
                        }
                    }
                }
            }
        }

        Item {
            width: parent.width
            height: Math.max(
                160,
                root.height - 44
            )

            Row {
                id: authoringSurface
                anchors.fill: parent
                spacing: 10
                visible:
                    !root.settingsOpen
                    && root.hostKind !== "CRYPTO"
                    && root.hostKind !== "TMOG"
                    && root.hostKind !== "MEDIA"
                    && root.hostKind !== "DRAW"
                    && (
                        root.currentObjectProvenance === "REAL_LOCAL_FILE"
                        || (
                            root.currentObjectType === "CODE_FILE"
                            && root.currentObjectProvenance === "REAL_UI_STATE"
                        )
                    )

                Item {
                    id: codeHost
                    width: authoringSurface.width
                    height: authoringSurface.height

                    ScrollView {
                        id: codeScroll
                        objectName: "workspaceCodeScroll"
                        anchors.fill: parent
                        anchors.leftMargin: 2
                        anchors.rightMargin: 2
                        anchors.topMargin: 8
                        anchors.bottomMargin: 8
                        clip: true
                        ScrollBar.horizontal: GgScrollBar {}
                        ScrollBar.vertical: GgScrollBar {}

                        TextArea {
                            id: codeEditor
                            objectName: "workspaceCodeEditor"
                            enabled: root.editorLoaded
                            readOnly: false
                            selectByMouse: true
                            textFormat: TextEdit.PlainText
                            wrapMode: TextEdit.NoWrap
                            color: "#e6e6e6"
                            selectionColor: "#3a3a3a"
                            selectedTextColor: "#f2f2f2"
                            font.family: "monospace"
                            font.pixelSize: 12
                            leftPadding: 12
                            rightPadding: 12
                            topPadding: 8
                            bottomPadding: 12
                            implicitWidth: Math.max(
                                codeScroll.availableWidth,
                                contentWidth + 24
                            )
                            implicitHeight: Math.max(
                                codeScroll.availableHeight,
                                contentHeight + 20
                            )

                            background: Rectangle {
                                color: "#161616"
                                border.width: 0
                            }

                        onTextChanged: {
                            if (!root.editorLoaded)
                                return

                            root.editorDirty =
                                codeEditor.text !== root.editorBaseText
                            if (
                                !root._applyingExternal
                                && String(root.currentObjectId).indexOf(
                                    "ws.file.scratch."
                                ) === 0
                            )
                                scratchLiveTimer.restart()

                            if (root.postDraftApplyingCandidate)
                                return

                            if (root.postDraftBusy) {
                                root.postDraftState = "STALE"
                                root.liveAidState = "QUEUED"
                                root.liveAidEvidenceSummary =
                                    "POST-DRAFT STALE · "
                                    + "BUFFER CHANGED DURING RUN · "
                                    + "RESULT WILL NOT BE APPLIED"
                                return
                            }

                            if (
                                root.postDraftState !== "IDLE"
                                && root.postDraftState !== "STALE"
                            ) {
                                root.postDraftState = "STALE"
                                root.postDraftGateReportSha256 = ""
                            }

                            if (root.preflightState !== "RUNNING") {
                                root.preflightState = "STALE"
                                root.preflightReportSha256 = ""
                            }

                            if (
                                root.repairState !== "RUNNING"
                                && root.repairState !== "IDLE"
                            ) {
                                root.repairState = "STALE"
                                root.repairProposalId = ""
                                root.repairOldText = ""
                                root.repairNewText = ""
                            }

                            root.liveAidState = "QUEUED"
                            analysisTimer.restart()
                        }
                        }
                    }
                }
            }

            SettingsSurface {
                id: settingsSurface
                anchors.fill: parent
                anchors.margins: 10
                visible: root.settingsOpen
                chatWidthRatio: root.chatWidthRatio
                telemetryWidth: root.telemetryWidth
                accentColor: root.accentColor
                frameBorder: root.frameBorder
                frameRadius: root.frameRadius
                showDemoFixtures: root.showDemoFixtures
                showProductSourceTabs: root.showProductSourceTabs
                showOpenTabInInput: root.showOpenTabInInput
                showInnerEditorChrome: root.showInnerEditorChrome
                hostKind: root.hostKind
                engineTarget: root.engineTarget
                utilityHeight: root.utilityHeight
                desktopShell: root.desktopShell

                onChatWidthRatioChangedByUser: function(value) {
                    root.chatWidthRatioRequested(value)
                }

                onTelemetryWidthChangedByUser: function(value) {
                    root.telemetryWidthRequested(value)
                }

                onAccentColorChangedByUser: function(value) {
                    root.accentColorRequested(value)
                }

                onFrameBorderChangedByUser: function(value) {
                    root.frameBorderRequested(value)
                }

                onFrameRadiusChangedByUser: function(value) {
                    root.frameRadiusRequested(value)
                }

                onDemoVisibilityChangedByUser: function(value) {
                    root.demoVisibilityRequested(value)
                }

                onProductSourceTabsChangedByUser: function(value) {
                    root.showProductSourceTabs = value
                    root.productSourceTabsRequested(value)
                }

                onShowOpenTabInInputChangedByUser: function(value) {
                    root.showOpenTabInInputRequested(value)
                }

                onShowInnerEditorChromeChangedByUser: function(value) {
                    root.showInnerEditorChromeRequested(value)
                }

                onHostKindChangedByUser: function(value) {
                    root.setHostKind(value)
                }

                onSpawnInstanceRequested: root.spawnHostInstance()

                onEngineTargetChangedByUser: function(value) {
                    root.engineTargetRequested(value)
                }

                onUtilityHeightChangedByUser: function(value) {
                    root.utilityHeightRequested(value)
                }

                onDesktopShellChangedByUser: function(value) {
                    root.desktopShellRequested(value)
                }

                onCloseRequested: root.closeSettings()
            }

            Item {
                id: siteHost
                objectName: "workspaceSiteHost"
                anchors.fill: parent
                anchors.margins: 10
                visible:
                    !root.settingsOpen
                    && root.hostKind === "SITE"
                    && root.currentObjectType === "SITE_PROJECT"

                FileDialog {
                    id: siteZipDialog
                    fileMode: FileDialog.OpenFile
                    nameFilters: ["Zip (*.zip)"]
                    onAccepted: root.importSiteFromDialog(
                        String(siteZipDialog.selectedFile)
                    )
                }

                FileDialog {
                    id: siteSqlDialog
                    fileMode: FileDialog.OpenFile
                    nameFilters: ["SQL (*.sql)"]
                    onAccepted: root.importSiteSqlFromDialog(
                        String(siteSqlDialog.selectedFile)
                    )
                }

                FolderDialog {
                    id: siteFolderDialog
                    onAccepted: root.importSiteFromDialog(
                        String(siteFolderDialog.selectedFolder)
                    )
                }

                Connections {
                    target: Window.window && Window.window.surfaceHost
                        ? Window.window.surfaceHost
                        : null
                    ignoreUnknownSignals: true

                    function onSiteImportProgress(phase, current, total, extra) {
                        var line = String(phase)
                        if (Number(total) > 0)
                            line += " · " + String(current) + "/" + String(total)
                        if (String(extra).length > 0)
                            line += " · " + String(extra)
                        root.siteImportStatus = line
                    }
                }

                Text {
                    objectName: "workspaceSiteImportStatus"
                    z: 8
                    anchors.left: parent.left
                    anchors.right: siteImportBar.left
                    anchors.rightMargin: 12
                    anchors.top: parent.top
                    height: 18
                    text: root.siteImportStatus
                    color: root.siteImportStatus.indexOf("FAIL") === 0
                        ? "#c98989"
                        : "#8b949e"
                    font.family: "monospace"
                    font.pixelSize: 12
                    elide: Text.ElideMiddle
                }

                Row {
                    id: siteImportBar
                    objectName: "workspaceSiteImportBar"
                    z: 8
                    spacing: 12
                    anchors.top: parent.top
                    anchors.right: parent.right
                    height: 18

                    Text {
                        text: "EDIT IN CODE"
                        color: "#c8a97e"
                        font.family: "monospace"
                        font.pixelSize: 12
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.setHostKind("CODE")
                        }
                    }

                    Text {
                        text: root.sitePreviewRunning ? "STOP PREVIEW" : "PREVIEW"
                        color: root.sitePreviewRunning ? "#d8dee9" : "#c8a97e"
                        font.family: "monospace"
                        font.pixelSize: 12
                        font.bold: root.sitePreviewRunning
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.toggleSitePreview()
                        }
                    }

                    Text {
                        text: "IMPORT SQL"
                        color: "#c8a97e"
                        font.family: "monospace"
                        font.pixelSize: 12
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: siteSqlDialog.open()
                        }
                    }

                    Text {
                        text: "IMPORT ZIP"
                        color: "#c8a97e"
                        font.family: "monospace"
                        font.pixelSize: 12
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: siteZipDialog.open()
                        }
                    }

                    Text {
                        text: "IMPORT FOLDER"
                        color: "#c8a97e"
                        font.family: "monospace"
                        font.pixelSize: 12
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: siteFolderDialog.open()
                        }
                    }
                }

                WebPane {
                    anchors.fill: parent
                    anchors.topMargin: 22
                    pageUrl: root.webPageUrl
                    siteOnly: true
                    reloadNonce: root.sitePreviewNonce
                    wantEngine: siteHost.visible
                }
            }

            Loader {
                id: cryptoPane
                objectName: "workspaceCryptoPane"
                z: 20
                anchors.fill: parent
                anchors.bottomMargin: 18
                active: !root.settingsOpen && root.hostKind === "CRYPTO"
                visible: active
                sourceComponent: Component {
                    CryptoSurface {
                        objectName: "workspaceCryptoPane"
                        surfaceHost: root.scratchHost()
                        frameBorder: root.frameBorder
                        frameRadius: root.frameRadius
                        onWalletLabelChanged: function(label) {
                            root.cryptoWalletLabel = label
                            var win = Window.window
                            if (win)
                                win.cryptoStatusJson = cryptoPane.item
                                    ? cryptoPane.item.statusJson
                                    : win.cryptoStatusJson
                        }
                    }
                }
            }

            Loader {
                id: tmogPane
                objectName: "workspaceTmogPane"
                z: 20
                anchors.fill: parent
                active: !root.settingsOpen && root.hostKind === "TMOG"
                visible: active
                sourceComponent: Component {
                    TmogSurface {
                        objectName: "workspaceTmogPane"
                        surfaceHost: root.scratchHost()
                        frameBorder: root.frameBorder
                        frameRadius: root.frameRadius
                    }
                }
            }

            MediaSurface {
                id: mediaPane
                objectName: "workspaceMediaPane"
                z: 20
                anchors.fill: parent
                visible:
                    !root.settingsOpen
                    && root.hostKind === "MEDIA"
                surfaceHost: root.scratchHost()
                frameBorder: root.frameBorder
                frameRadius: root.frameRadius
            }

            Loader {
                id: drawPane
                objectName: "workspaceDrawPane"
                z: 20
                anchors.fill: parent
                active: !root.settingsOpen && root.hostKind === "DRAW"
                visible: active
                sourceComponent: Component {
                    DrawSurface {
                        objectName: "workspaceDrawPane"
                        surfaceHost: root.scratchHost()
                        frameBorder: root.frameBorder
                        frameRadius: root.frameRadius
                    }
                }
            }

            Item {
                id: webHost
                objectName: "workspaceWebHost"
                anchors.fill: parent
                anchors.margins: 10
                visible:
                    !root.settingsOpen
                    && root.hostKind === "WEB"
                    && root.currentObjectType === "WEBSITE"
                    && root.currentObjectProvenance === "REAL_UI_STATE"

                Repeater {
                    model: workspaceObjects

                    delegate: Item {
                        id: webTab
                        required property int index
                        required property string objectId
                        required property string objectType
                        required property string provenanceClass
                        required property string sourcePath

                        readonly property bool isWebTab:
                            webTab.objectType === "WEBSITE"
                            && webTab.provenanceClass === "REAL_UI_STATE"
                        readonly property bool isCurrent:
                            webTab.objectId === root.currentObjectId

                        anchors.fill: parent
                        visible: webTab.isWebTab
                        opacity: webTab.isCurrent ? 1 : 0
                        enabled: webTab.isCurrent
                        z: webTab.isCurrent ? 2 : 0

                        Column {
                            anchors.fill: parent
                            spacing: 6

                            GgField {
                                id: tabBrowseBar
                                objectName: "workspaceWebAddress"
                                width: parent.width
                                height: 26
                                text: webTab.sourcePath === "about:blank"
                                    ? ""
                                    : webTab.sourcePath
                                placeholderText: "https://"
                                onAccepted: root.goBrowse(tabBrowseBar.text)
                            }

                            Loader {
                                width: parent.width
                                height: parent.height - tabBrowseBar.height - 6
                                active: webTab.isWebTab
                                sourceComponent: Component {
                                    WebPane {
                                        anchors.fill: parent
                                        pageUrl: webTab.sourcePath.length > 0
                                            ? webTab.sourcePath
                                            : "about:blank"
                                        siteOnly: false
                                        wantEngine: webHost.visible && webTab.isCurrent
                                        onNavigated: function(href) {
                                            root.rememberBrowse(webTab.index, href)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Item {
                id: userTerminalHost
                anchors.fill: parent
                anchors.margins: 10
                visible:
                    !root.settingsOpen
                    && root.hostKind === "TERMINAL"
                    && root.currentObjectType === "USER_TERMINAL"

                WorkObject {
                    anchors.fill: parent
                    fillHost: true
                    objectType: "TERMINAL"
                    title: root.currentObjectTitle
                    terminalId: root.currentObjectId
                    provenanceClass: "REAL_UI_STATE"
                    activityState: "RUNNING"
                    bodyText: ""
                    contextReference: "@current"
                }
            }

            Column {
                anchors.centerIn: parent
                width: Math.min(parent.width - 60, 560)
                spacing: 12
                visible:
                    !root.settingsOpen
                    && root.hostKind === "EXTERNAL"
                    && root.currentObjectType === "EXTERNAL_APP"

                Text {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text: root.currentObjectTitle
                    color: "#e6edf3"
                    font.pixelSize: 22
                    font.bold: true
                }

                Text {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text: root.currentObjectType
                        + " · REAL_UI_STATE · HOSTING NOT AVAILABLE"
                    color: "#c8a97e"
                    font.family: "monospace"
                    font.pixelSize: 12
                }

                Text {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text:
                        "No X11/Wayland window embed yet. "
                        + "This is not a fake browser or game. "
                        + "The open program fills this workspace box when hosted."
                    color: "#c8cdd4"
                    wrapMode: Text.WordWrap
                    font.pixelSize: 12
                }
            }

            Column {
                anchors.centerIn: parent
                width: Math.min(parent.width - 60, 560)
                spacing: 12
                visible:
                    !root.settingsOpen
                    && root.hostKind !== "CRYPTO"
                    && root.hostKind !== "TMOG"
                    && root.hostKind !== "MEDIA"
                    && root.hostKind !== "DRAW"
                    && root.currentObjectProvenance === "SYNTHETIC_UI_FIXTURE"

                Text {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text: root.currentObjectTitle
                    color: "#e6edf3"
                    font.pixelSize: 22
                    font.bold: true
                }

                Text {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text: root.currentObjectType
                        + " · "
                        + root.currentObjectProvenance
                        + " · DEMO / SAMPLE"
                    color: "#c8a97e"
                    font.family: "monospace"
                    font.pixelSize: 12
                }

                Text {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text:
                        "Visual renderer/editor adapter is not connected "
                        + "for this SAMPLE object.\n"
                        + "Synthetic fixtures remain blocked from real "
                        + "@current context."
                    color: "#c8cdd4"
                    wrapMode: Text.WordWrap
                    font.pixelSize: 12
                }
            }
        }
    }

    Rectangle {
        z: 5
        anchors.left: hostKindFooter.left
        anchors.leftMargin: -6
        anchors.bottom: hostKindFooter.bottom
        width: hostKindFooter.width + 12
        height: 18
        color: "#161616"
        visible: hostKindFooter.width > 0
    }

    Row {
        id: hostKindFooter
        objectName: "workspaceHostKindSelector"
        z: 6
        anchors.left: parent.left
        anchors.leftMargin: 14
        anchors.bottom: workspaceFrame.bottom
        anchors.bottomMargin: -7
        height: 18
        spacing: 0

        Text {
            text: "CODE"
            color: root.hostKind === "CODE" ? "#d8dee9" : "#a8b0b8"
            font.family: "monospace"
            font.pixelSize: 12
            font.bold: root.hostKind === "CODE"

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.setHostKind("CODE")
            }
        }

        Text {
            text: " | "
            color: "#a8b0b8"
            font.family: "monospace"
            font.pixelSize: 12
        }

        Text {
            text: "TERMINAL"
            color: root.hostKind === "TERMINAL" ? "#d8dee9" : "#a8b0b8"
            font.family: "monospace"
            font.pixelSize: 12
            font.bold: root.hostKind === "TERMINAL"

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.setHostKind("TERMINAL")
            }
        }

        Text {
            text: " | "
            color: "#a8b0b8"
            font.family: "monospace"
            font.pixelSize: 12
        }

        Text {
            text: "WEB"
            color: root.hostKind === "WEB" ? "#d8dee9" : "#a8b0b8"
            font.family: "monospace"
            font.pixelSize: 12
            font.bold: root.hostKind === "WEB"

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.setHostKind("WEB")
            }
        }

        Text {
            text: " | "
            color: "#a8b0b8"
            font.family: "monospace"
            font.pixelSize: 12
        }

        Text {
            text: "EXTERNAL"
            color: root.hostKind === "EXTERNAL" ? "#d8dee9" : "#a8b0b8"
            font.family: "monospace"
            font.pixelSize: 12
            font.bold: root.hostKind === "EXTERNAL"

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.setHostKind("EXTERNAL")
            }
        }

        Text {
            text: " | "
            color: "#a8b0b8"
            font.family: "monospace"
            font.pixelSize: 12
        }

        Text {
            text: "SITE"
            color: root.hostKind === "SITE" ? "#d8dee9" : "#a8b0b8"
            font.family: "monospace"
            font.pixelSize: 12
            font.bold: root.hostKind === "SITE"

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.setHostKind("SITE")
            }
        }

        Text {
            text: " | "
            color: "#a8b0b8"
            font.family: "monospace"
            font.pixelSize: 12
        }

        Text {
            text: "CRYPTO"
            color: root.hostKind === "CRYPTO" ? "#d8dee9" : "#a8b0b8"
            font.family: "monospace"
            font.pixelSize: 12
            font.bold: root.hostKind === "CRYPTO"

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.setHostKind("CRYPTO")
            }
        }

        Text {
            text: " | "
            color: "#a8b0b8"
            font.family: "monospace"
            font.pixelSize: 12
        }

        Text {
            text: "TMOG"
            color: root.hostKind === "TMOG" ? "#d8dee9" : "#a8b0b8"
            font.family: "monospace"
            font.pixelSize: 12
            font.bold: root.hostKind === "TMOG"

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.setHostKind("TMOG")
            }
        }

        Text {
            text: " | "
            color: "#a8b0b8"
            font.family: "monospace"
            font.pixelSize: 12
        }

        Text {
            text: "MEDIA"
            color: root.hostKind === "MEDIA" ? "#d8dee9" : "#a8b0b8"
            font.family: "monospace"
            font.pixelSize: 12
            font.bold: root.hostKind === "MEDIA"

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.setHostKind("MEDIA")
            }
        }

        Text {
            text: " | "
            color: "#a8b0b8"
            font.family: "monospace"
            font.pixelSize: 12
        }

        Text {
            text: "DRAW"
            color: root.hostKind === "DRAW" ? "#d8dee9" : "#a8b0b8"
            font.family: "monospace"
            font.pixelSize: 12
            font.bold: root.hostKind === "DRAW"

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.setHostKind("DRAW")
            }
        }
    }

    FileDialog {
        id: scratchSaveDialog
        title: "SAVE AS"
        fileMode: FileDialog.SaveFile
        nameFilters: [
            "Text (*.txt)",
            "JavaScript (*.js)",
            "QML (*.qml)",
            "Python (*.py)",
            "JSON (*.json)",
            "HTML (*.html)",
            "CSS (*.css)",
            "PHP (*.php)",
            "All files (*)"
        ]
        defaultSuffix: "txt"
        currentFolder: "file:///home/GG/.local/state/goldgoblins/gg-ai-desktop/scratch"
        onAccepted: root.applySaveAsUrl(
            String(scratchSaveDialog.selectedFile)
        )
    }
}
