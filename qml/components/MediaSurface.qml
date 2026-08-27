import QtQuick

Item {
    id: root
    objectName: "workspaceMediaPane"

    property var surfaceHost: null
    property color frameBorder: "#6a6a6a"
    property int frameRadius: 2
    property string statusJson: "{}"
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
        if (rows && rows.length !== undefined)
            return rows
        return []
    }

    readonly property string mode: String(root.status.mode || "MUSIC")
    readonly property bool screenOn: String(root.status.screen || "") === "EMBED"
    readonly property var now: root.status.now || {}
    readonly property bool showDisplay:
        root.mode === "TV"
        || root.mode === "GAME"
        || root.mode === "FETCH"
        || root.screenOn
    readonly property bool listCollapsed:
        root.screenOn
        && (root.mode === "GAME" || root.mode === "FETCH")

    function refresh() {
        if (!root.surfaceHost || !root.surfaceHost.mediaStatus)
            return
        root.statusJson = root.surfaceHost.mediaStatus()
        var title = String((root.status.now || {}).title || root.status.legend || "MEDIA")
        root.nowPlayingChanged(title)
    }

    function setMode(mode) {
        if (!root.surfaceHost)
            return
        root.statusJson = root.surfaceHost.mediaSetMode(mode)
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
        root.statusJson = root.surfaceHost.mediaStartFetch()
        root.refresh()
    }

    function search(query) {
        if (!root.surfaceHost || !root.surfaceHost.mediaSearch)
            return
        root.statusJson = root.surfaceHost.mediaSearch(query)
        root.refresh()
    }

    Timer {
        interval: 2000
        running: root.visible
        repeat: true
        onTriggered: root.refresh()
    }

    onVisibleChanged: {
        if (visible)
            root.refresh()
        else if (root.surfaceHost && root.surfaceHost.hideMedia)
            root.surfaceHost.hideMedia()
    }

    GgFrame {
        id: mediaFrame
        anchors.fill: parent
        anchors.margins: 10
        leftLegend: "MEDIA"
        rightLegend: root.showDisplay ? "SCREEN · " + root.mode : root.mode
        backgroundColor: "#161616"
        borderColor: root.frameBorder
        radius: root.frameRadius

        Item {
            width: parent.width
            height: Math.max(180, root.height - 52)

            Column {
                id: chrome
                width: parent.width
                spacing: 8

                Row {
                    spacing: 12
                    Repeater {
                        model: ["MUSIC", "RADIO", "TV", "GAME", "FETCH"]
                        delegate: Text {
                            required property string modelData
                            text: modelData
                            color: root.mode === modelData ? "#d8dee9" : "#5d6670"
                            font.family: "monospace"
                            font.pixelSize: 10
                            font.bold: root.mode === modelData
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.setMode(modelData)
                            }
                        }
                    }
                }

                Text {
                    width: parent.width
                    text: {
                        if (root.mode === "FETCH")
                            return String((root.status.fetch || {}).detail || "FETCH")
                        if (root.mode === "MUSIC")
                            return "cliamp plays in the strip. Workspace is the playlist."
                        if (root.mode === "RADIO")
                            return "Radio Browser through cliamp. Search a station or paste a stream URL."
                        if (root.mode === "TV")
                            return "Channels on the left. The workspace box is the screen."
                        return "Pick a ROM. The workspace box becomes the console screen."
                    }
                    color: "#8b949e"
                    wrapMode: Text.WordWrap
                    font.pixelSize: 10
                }

                Row {
                    spacing: 12
                    visible: !!(root.status.tools && root.status.tools.cliamp && root.status.tools.cliamp.present)
                        && (root.mode === "MUSIC" || root.mode === "RADIO")
                    Text {
                        text: "OPEN CLIAMP"
                        color: "#c8a97e"
                        font.family: "monospace"
                        font.pixelSize: 10
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
                    visible: root.mode === "RADIO" || root.mode === "TV" || root.mode === "MUSIC"

                    TextInput {
                        id: searchBox
                        objectName: "workspaceMediaSearch"
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        color: "#e6e6e6"
                        font.family: "monospace"
                        font.pixelSize: 11
                        clip: true
                        onAccepted: root.search(searchBox.text)
                    }

                    Text {
                        anchors.fill: searchBox
                        text: root.mode === "RADIO"
                            ? "search radio or paste URL"
                            : (root.mode === "TV"
                                ? "search TV / paste URL / youtube"
                                : "search local tracks")
                        color: "#5d6670"
                        font.family: "monospace"
                        font.pixelSize: 11
                        verticalAlignment: Text.AlignVCenter
                        visible: searchBox.text.length === 0 && !searchBox.activeFocus
                    }
                }

                Row {
                    spacing: 12
                    visible: root.mode === "FETCH"
                    Text {
                        text: (root.status.fetch && root.status.fetch.present)
                            ? "OPEN TORLINK"
                            : "TORLINK MISSING"
                        color: (root.status.fetch && root.status.fetch.present)
                            ? "#c8a97e"
                            : "#8b949e"
                        font.family: "monospace"
                        font.pixelSize: 10
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            enabled: !!(root.status.fetch && root.status.fetch.present)
                            onClicked: root.openFetch()
                        }
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
                        font.pixelSize: 11
                        elide: Text.ElideMiddle
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.playItem(String(modelData.id || ""))
                        }
                    }

                    Text {
                        visible: catalogList.count === 0 && root.mode !== "FETCH" && catalogList.visible
                        anchors.centerIn: parent
                        width: parent.width - 16
                        horizontalAlignment: Text.AlignHCenter
                        text: root.mode === "GAME"
                            ? "No local ROMs under ~/ROMs, ~/Spel or media/library."
                            : "No local files in this mode yet."
                        color: "#8b949e"
                        wrapMode: Text.WordWrap
                        font.pixelSize: 11
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

                    Text {
                        anchors.centerIn: parent
                        visible: !root.screenOn
                        text: root.mode === "TV"
                            ? "SCREEN"
                            : (root.mode === "GAME" ? "CONSOLE" : "DISPLAY")
                        color: "#3a3a3a"
                        font.family: "monospace"
                        font.pixelSize: 18
                        font.bold: true
                    }
                }
            }
        }
    }
}
