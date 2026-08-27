pragma ComponentBehavior: Bound

import QtQuick

Item {
    id: root

    objectName: "utilitySurface"

    property color accentColor: "#8a8a8a"
    property color frameBorder: "#6a6a6a"
    property int frameRadius: 2
    property int surfaceHeight: 112
    property var surfaceHost: null
    property string statusJson: "{}"
    signal surfaceRequested(string kind)
    readonly property string capabilityState: "REAL_LOCAL_MEDIA"

    implicitHeight: root.surfaceHeight

    readonly property var status: {
        try {
            return JSON.parse(root.statusJson || "{}")
        } catch (err) {
            return {}
        }
    }

    readonly property string mode: String(root.status.mode || "MUSIC")
    readonly property bool playing: root.status.playing === true
    readonly property string nowTitle: String((root.status.now || {}).title || "")
    readonly property int volume: Number(root.status.volume || 70)

    function refresh() {
        if (!root.surfaceHost || !root.surfaceHost.mediaStatus)
            return
        root.statusJson = root.surfaceHost.mediaStatus()
    }

    function setMode(mode) {
        if (!root.surfaceHost)
            return
        root.surfaceRequested("MEDIA")
        root.statusJson = root.surfaceHost.mediaSetMode(mode)
        root.refresh()
    }

    function playPause() {
        if (!root.surfaceHost)
            return
        root.surfaceRequested("MEDIA")
        if (root.playing)
            root.statusJson = root.surfaceHost.mediaPause()
        else if (root.nowTitle.length > 0)
            root.statusJson = root.surfaceHost.mediaPause()
        else
            root.statusJson = root.surfaceHost.mediaSkip(0)
        root.refresh()
    }

    function stop() {
        if (!root.surfaceHost)
            return
        root.statusJson = root.surfaceHost.mediaStop()
        root.refresh()
    }

    function skip(delta) {
        if (!root.surfaceHost)
            return
        root.surfaceRequested("MEDIA")
        root.statusJson = root.surfaceHost.mediaSkip(delta)
        root.refresh()
    }

    function bumpVolume(delta) {
        if (!root.surfaceHost)
            return
        root.statusJson = root.surfaceHost.mediaSetVolume(root.volume + delta)
        root.refresh()
    }

    function toolMark(name) {
        var tools = root.status.tools || {}
        var row = tools[name] || {}
        return name.toUpperCase() + (row.present ? " ON" : " OFF")
    }

    Timer {
        interval: 2000
        running: true
        repeat: true
        onTriggered: root.refresh()
    }

    Component.onCompleted: root.refresh()

    GgFrame {
        anchors.fill: parent
        leftLegend: "MEDIA / UTILITIES"
        rightLegend: root.mode
        backgroundColor: "#161616"
        borderColor: root.frameBorder
        radius: root.frameRadius

        Column {
            width: parent.width
            spacing: 6

            Row {
                objectName: "utilityModeRow"
                spacing: 10

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

            Row {
                objectName: "utilityTransport"
                spacing: 14

                Text {
                    text: "|<"
                    color: "#c8a97e"
                    font.family: "monospace"
                    font.pixelSize: 12
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.skip(-1)
                    }
                }
                Text {
                    text: root.playing ? "PAUSE" : "PLAY"
                    color: "#d8dee9"
                    font.family: "monospace"
                    font.pixelSize: 12
                    font.bold: true
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.playPause()
                    }
                }
                Text {
                    text: ">|"
                    color: "#c8a97e"
                    font.family: "monospace"
                    font.pixelSize: 12
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.skip(1)
                    }
                }
                Text {
                    text: "STOP"
                    color: "#8b949e"
                    font.family: "monospace"
                    font.pixelSize: 12
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.stop()
                    }
                }
                Text {
                    text: "VOL " + String(root.volume)
                    color: "#8b949e"
                    font.family: "monospace"
                    font.pixelSize: 10
                    MouseArea {
                        anchors.fill: parent
                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                        cursorShape: Qt.PointingHandCursor
                        onClicked: function(event) {
                            root.bumpVolume(event.button === Qt.RightButton ? -5 : 5)
                        }
                    }
                }
                Text {
                    width: Math.max(80, root.width - 360)
                    text: root.nowTitle.length > 0
                        ? ("NOW · " + root.nowTitle)
                        : "NOW · idle"
                    color: "#8b949e"
                    font.family: "monospace"
                    font.pixelSize: 10
                    elide: Text.ElideMiddle
                }
            }

            Text {
                objectName: "utilityToolLine"
                width: parent.width
                text: root.toolMark("vlc")
                    + " · "
                    + root.toolMark("cliamp")
                    + " · "
                    + root.toolMark("torlink")
                    + " · "
                    + root.toolMark("yt-dlp")
                    + " · "
                    + root.toolMark("retroarch")
                color: "#5d6670"
                font.family: "monospace"
                font.pixelSize: 10
                elide: Text.ElideRight
            }
        }
    }
}
