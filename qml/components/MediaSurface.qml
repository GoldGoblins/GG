import QtQuick
import QtMultimedia

Item {
    id: root
    objectName: "workspaceMediaPane"

    property var surfaceHost: null
    property color frameBorder: "#6a6a6a"
    property int frameRadius: 4
    property string statusJson: "{}"
    property var catalogItems: []
    property string lastPlayUrl: ""
    property string playerError: ""
    property bool playerReady: false
    property real _clockStamp: 0
    signal nowPlayingChanged(string label)

    readonly property var status: {
        try {
            return JSON.parse(root.statusJson || "{}")
        } catch (err) {
            return {}
        }
    }

    readonly property var items: {
        var rows = root.status.items
        if (rows !== undefined && rows !== null && rows.length !== undefined)
            return rows
        return root.catalogItems
    }

    readonly property string mode: String(root.status.mode || "MUSIC")
    readonly property bool screenOn: String(root.status.screen || "") === "EMBED"
    readonly property var now: root.status.now || {}
    readonly property bool qmlVideo: String(root.status.backend || "") === "qml"
    readonly property bool libretro: String(root.status.backend || "") === "libretro"
    readonly property bool showDisplay:
        root.mode === "TV"
        || root.mode === "GAME"
        || root.mode === "FETCH"
        || root.screenOn
        || root.qmlVideo
    readonly property bool listCollapsed:
        root.screenOn
        && root.mode === "GAME"

    function applyStatus(raw) {
        var text = String(raw || "")
        if (text === root.statusJson)
            return
        root.statusJson = text
        root.rememberCatalog()
        var title = String((root.status.now || {}).title || root.status.legend || "MEDIA")
        root.nowPlayingChanged(title)
    }

    function refresh() {
        if (!root.surfaceHost || !root.surfaceHost.mediaStatus)
            return
        root.applyStatus(root.surfaceHost.mediaStatus())
    }

    function refreshLive() {
        if (!root.surfaceHost)
            return
        if (root.surfaceHost.mediaLiveStatus)
            root.applyStatus(root.surfaceHost.mediaLiveStatus())
        else if (root.surfaceHost.mediaStatus)
            root.applyStatus(root.surfaceHost.mediaStatus())
    }

    function rememberCatalog() {
        var rows = root.status.items
        if (rows !== undefined && rows !== null && rows.length !== undefined)
            root.catalogItems = rows
    }

    function setMode(mode) {
        if (!root.surfaceHost)
            return
        root.statusJson = root.surfaceHost.mediaSetMode(mode)
        if (mode === "FETCH")
            root.openFetch()
        else
            root.refresh()
    }

    function playItem(itemId) {
        if (!root.surfaceHost)
            return
        root.statusJson = root.surfaceHost.mediaPlay(itemId)
        root.refresh()
    }

    function openCliamp() {
        if (!root.surfaceHost)
            return
        root.statusJson = root.surfaceHost.mediaStartCliamp()
        root.refresh()
    }

    function openFetch() {
        if (!root.surfaceHost)
            return
        var raw = root.surfaceHost.mediaStartFetch()
        try {
            var parsed = JSON.parse(raw || "{}")
            if (parsed.error) {
                root.playerError = String(parsed.error)
                root.refresh()
                return
            }
            root.playerError = ""
            root.statusJson = raw
        } catch (err) {
            root.playerError = String(err)
        }
        root.refresh()
    }

    function search(query) {
        if (!root.surfaceHost || !root.surfaceHost.mediaSearch)
            return
        root.statusJson = root.surfaceHost.mediaSearch(query)
        root.refresh()
    }

    function toMediaUrl(raw) {
        var s = String(raw || "")
        if (!s)
            return ""
        if (s.indexOf("://") >= 0)
            return s
        if (s.charAt(0) === "/")
            return "file://" + s
        return s
    }

    function syncPlayer() {
        if (!root.playerReady)
            return
        if (!root.qmlVideo) {
            root.lastPlayUrl = ""
            holePlayer.stop()
            holePlayer.source = ""
            if (root.mode !== "FETCH")
                root.playerError = ""
            return
        }
        var url = root.toMediaUrl(String((root.status.now || {}).source || ""))
        holeAudio.volume = Math.max(0, Math.min(1, Number(root.status.volume || 70) / 100))
        if (url !== root.lastPlayUrl) {
            root.lastPlayUrl = url
            root.playerError = ""
            holePlayer.source = url
            if (root.status.paused === true)
                holePlayer.pause()
            else if (url)
                holePlayer.play()
            return
        }
        if (root.status.paused === true) {
            if (holePlayer.playbackState !== MediaPlayer.PausedState)
                holePlayer.pause()
            return
        }
        if (!url)
            return
        if (holePlayer.playbackState === MediaPlayer.StoppedState)
            holePlayer.play()
    }

    onLibretroChanged: {
        if (root.libretro)
            hole.forceActiveFocus()
    }

    onStatusJsonChanged: {
        root.rememberCatalog()
        root.syncPlayer()
    }

    Component.onCompleted: {
        root.playerReady = true
        root.syncPlayer()
    }

    function reportClock() {
        if (!root.qmlVideo || !root.surfaceHost || !root.surfaceHost.mediaReportClock)
            return
        var now = Date.now()
        if (now - root._clockStamp < 250)
            return
        root._clockStamp = now
        var pos = Number(holePlayer.position || 0) / 1000
        var dur = Number(holePlayer.duration || 0) / 1000
        if (!(pos >= 0))
            pos = 0
        if (!(dur >= 0))
            dur = 0
        root.surfaceHost.mediaReportClock(pos, dur)
    }

    Connections {
        target: root.surfaceHost
        ignoreUnknownSignals: true
        function onMediaStateChanged() {
            if (!root.visible)
                return
            var prev = root.mode
            root.refreshLive()
            if (root.mode !== prev)
                root.refresh()
        }
        function onMediaSeekChanged(seconds) {
            if (!root.qmlVideo || !root.playerReady)
                return
            holePlayer.position = Math.max(0, Number(seconds) * 1000)
        }
    }

    Timer {
        interval: 5000
        running: root.visible
        repeat: true
        onTriggered: root.refreshLive()
    }

    onVisibleChanged: {
        if (visible) {
            root.refresh()
            if (root.mode === "FETCH")
                root.openFetch()
        } else if (root.surfaceHost && root.surfaceHost.hideMedia)
            root.surfaceHost.hideMedia()
    }

    Item {
        id: mediaFrame
        anchors.fill: parent
        anchors.leftMargin: 6
        anchors.rightMargin: 6
        anchors.topMargin: 4
        anchors.bottomMargin: 6

        Column {
            id: chrome
            width: parent.width
            spacing: 6

                Item {
                    width: parent.width
                    height: 18

                    Row {
                        spacing: 12
                        Repeater {
                            model: ["MUSIC", "RADIO", "TV", "GAME", "FETCH"]
                            delegate: Text {
                                required property string modelData
                                text: modelData
                                color: root.mode === modelData ? "#d8dee9" : "#a8b0b8"
                                font.family: "monospace"
                                font.pixelSize: 12
                                font.bold: root.mode === modelData
                                verticalAlignment: Text.AlignVCenter
                                height: 18
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.setMode(modelData)
                                }
                            }
                        }
                    }

                    Text {
                        anchors.right: parent.right
                        height: 18
                        verticalAlignment: Text.AlignVCenter
                        text: root.showDisplay ? "SCREEN · " + root.mode : root.mode
                        color: "#c8cdd4"
                        font.family: "monospace"
                        font.pixelSize: 12
                    }
                }

                Text {
                    width: parent.width
                    text: {
                        if (root.mode === "FETCH")
                            return String((root.status.fetch || {}).detail || "Torrent search TUI in the workspace. Finished files on the left.")
                        if (root.mode === "MUSIC")
                            return "cliamp plays in the strip. Workspace is the playlist."
                        if (root.mode === "RADIO")
                            return "Radio Browser through cliamp. Search a station or paste a stream URL."
                        if (root.mode === "TV")
                            return "Channels on the left. The workspace box is the screen."
                        if (root.mode === "GAME") {
                            var cores = root.status.cores || {}
                            var on = []
                            var names = ["nes", "snes", "n64", "gb", "gba", "genesis", "ps1"]
                            var i
                            for (i = 0; i < names.length; i++) {
                                var row = cores[names[i]] || {}
                                if (row.present)
                                    on.push(row.label || names[i])
                            }
                            if (on.length === 0)
                                return "No emulator binary on PATH yet."
                            return "Ready: " + on.join(" · ") + ". Homebrew Hub on the left. Own dumps go in ~/ROMs/<system>."
                        }
                        return "Pick a ROM. The workspace box becomes the console screen."
                    }
                    color: "#c8cdd4"
                    wrapMode: Text.WordWrap
                    font.pixelSize: 12
                }

                Row {
                    spacing: 12
                    visible: !!(root.status.tools && root.status.tools.cliamp && root.status.tools.cliamp.present)
                        && (root.mode === "MUSIC" || root.mode === "RADIO")
                    Text {
                        text: "OPEN CLIAMP"
                        color: "#c8a97e"
                        font.family: "monospace"
                        font.pixelSize: 12
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.openCliamp()
                        }
                    }
                }

                Rectangle {
                    width: parent.width
                    height: 24
                    color: "#121212"
                    border.color: root.frameBorder
                    border.width: 1
                    visible: root.mode === "RADIO" || root.mode === "TV" || root.mode === "MUSIC" || root.mode === "GAME" || root.mode === "FETCH"

                    TextInput {
                        id: searchBox
                        objectName: "workspaceMediaSearch"
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        color: "#e6e6e6"
                        font.family: "monospace"
                        font.pixelSize: 12
                        clip: true
                        onAccepted: root.search(searchBox.text)
                    }

                    Text {
                        anchors.fill: searchBox
                        text: root.mode === "RADIO"
                            ? "search radio or paste URL"
                            : (root.mode === "TV"
                                ? "search TV / paste URL / youtube"
                                : (root.mode === "GAME"
                                    ? "search homebrew or local ROM"
                                    : (root.mode === "FETCH"
                                        ? "search finished downloads"
                                        : "search local tracks")))
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        verticalAlignment: Text.AlignVCenter
                        visible: searchBox.text.length === 0 && !searchBox.activeFocus
                    }
                }

                Row {
                    spacing: 12
                    visible: root.mode === "FETCH"
                    Text {
                        text: {
                            var fetch = root.status.fetch || {}
                            if (!fetch.present)
                                return String(fetch.label || "TORLINK MISSING")
                            if (fetch.running)
                                return "REATTACH TORLINK"
                            return "OPEN TORLINK"
                        }
                        color: (root.status.fetch && root.status.fetch.present)
                            ? "#c8a97e"
                            : "#8b949e"
                        font.family: "monospace"
                        font.pixelSize: 12
                        font.bold: true
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            enabled: !!(root.status.fetch && root.status.fetch.present)
                            onClicked: root.openFetch()
                        }
                    }
                    Text {
                        visible: !!(root.status.fetch && root.status.fetch.files)
                        text: "FILES 127.0.0.1:9160"
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                    }
                }
            }

            Row {
                id: stage
                objectName: "workspaceMediaStage"
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: chrome.bottom
                anchors.topMargin: 8
                anchors.bottom: parent.bottom
                spacing: 8

                ListView {
                    id: catalogList
                    objectName: "workspaceMediaCatalog"
                    width: root.listCollapsed
                        ? 0
                        : (root.showDisplay
                            ? Math.min(240, Math.max(140, stage.width * 0.32))
                            : stage.width)
                    height: parent.height
                    visible: width > 8
                    clip: true
                    spacing: 2
                    model: root.items

                    delegate: Text {
                        required property var modelData
                        width: catalogList.width
                        height: 16
                        verticalAlignment: Text.AlignVCenter
                        text: {
                            var row = modelData
                            var mark = String(root.now.id || "") === String(row.id) ? "▶ " : "  "
                            var extra = row.system_label ? (" · " + row.system_label) : ""
                            return mark + String(row.title || row.source || "") + extra
                        }
                        color: String(root.now.id || "") === String(modelData.id)
                            ? "#d8dee9"
                            : "#8b949e"
                        font.family: "monospace"
                        font.pixelSize: 12
                        elide: Text.ElideMiddle
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.playItem(String(modelData.id || ""))
                        }
                    }

                    Text {
                        visible: catalogList.count === 0 && catalogList.visible
                        anchors.centerIn: parent
                        width: parent.width - 16
                        horizontalAlignment: Text.AlignHCenter
                        text: root.mode === "GAME"
                            ? "No games yet. Search Homebrew Hub or drop files in ~/ROMs."
                            : (root.mode === "FETCH"
                                ? "No finished downloads yet. Search in the TUI, press d to download. Files land in ~/Downloads/torlink."
                                : "No local files in this mode yet.")
                        color: "#c8cdd4"
                        wrapMode: Text.WordWrap
                        font.pixelSize: 12
                    }
                }

                Item {
                    id: hole
                    objectName: "workspaceMediaHole"
                    width: root.showDisplay
                        ? Math.max(16, stage.width - catalogList.width - (catalogList.visible ? 8 : 0))
                        : 0
                    height: parent.height
                    visible: root.showDisplay
                    clip: true

                    Rectangle {
                        anchors.fill: parent
                        color: "#0a0a0a"
                        border.color: root.frameBorder
                        border.width: 1
                    }

                    VideoOutput {
                        id: holeVideo
                        objectName: "workspaceMediaVideo"
                        anchors.fill: parent
                        anchors.margins: 1
                        fillMode: VideoOutput.PreserveAspectFit
                        visible: root.qmlVideo
                    }

                    Image {
                        id: holeFrame
                        objectName: "workspaceMediaFrame"
                        anchors.fill: parent
                        anchors.margins: 1
                        fillMode: Image.PreserveAspectFit
                        cache: false
                        asynchronous: false
                        visible: root.libretro
                        source: {
                            if (!root.libretro || !root.surfaceHost)
                                return ""
                            return "image://console/" + String(root.surfaceHost.mediaFrameSeq || 0)
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        enabled: root.libretro
                        hoverEnabled: true
                        onClicked: hole.forceActiveFocus()
                    }

                    Keys.onPressed: function(event) {
                        if (!root.libretro || !root.surfaceHost || !root.surfaceHost.mediaGameKey)
                            return
                        root.surfaceHost.mediaGameKey(event.key, true)
                        event.accepted = true
                    }
                    Keys.onReleased: function(event) {
                        if (!root.libretro || !root.surfaceHost || !root.surfaceHost.mediaGameKey)
                            return
                        root.surfaceHost.mediaGameKey(event.key, false)
                        event.accepted = true
                    }
                    focus: root.libretro

                    AudioOutput {
                        id: holeAudio
                    }

                    MediaPlayer {
                        id: holePlayer
                        videoOutput: holeVideo
                        audioOutput: holeAudio
                        onErrorOccurred: function(error, errorString) {
                            root.playerError = String(errorString || "VIDEO ERROR")
                        }
                        onMediaStatusChanged: {
                            if (!root.qmlVideo || root.status.paused === true)
                                return
                            if (holePlayer.mediaStatus === MediaPlayer.EndOfMedia && root.lastPlayUrl)
                                holePlayer.play()
                        }
                        onPositionChanged: root.reportClock()
                        onDurationChanged: root.reportClock()
                    }

                    Text {
                        anchors.centerIn: parent
                        visible: !root.qmlVideo && !root.libretro && !root.screenOn
                        width: parent.width - 24
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                        text: root.mode === "TV"
                            ? "SCREEN"
                            : (root.mode === "GAME"
                                ? "CONSOLE"
                                : (root.mode === "FETCH"
                                    ? "TORLINK"
                                    : "DISPLAY"))
                        color: "#3a3a3a"
                        font.family: "monospace"
                        font.pixelSize: 18
                        font.bold: true
                    }

                    Text {
                        id: holeError
                        objectName: "workspaceMediaVideoError"
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        anchors.margins: 8
                        text: root.playerError || String(root.status.embed_error || "")
                        visible: text.length > 0
                        color: "#c8a97e"
                        wrapMode: Text.WordWrap
                        horizontalAlignment: Text.AlignHCenter
                        font.family: "monospace"
                        font.pixelSize: 12
                    }
                }
            }
        }
    }
