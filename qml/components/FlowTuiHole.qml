pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls

FocusScope {
    id: root
    objectName: "flowTuiHost"
    clip: true
    focus: visible

    property var surfaceHost: null
    property string statusJson: "{}"
    property string draft: ""

    readonly property var status: {
        try {
            return JSON.parse(root.statusJson || "{}")
        } catch (err) {
            return {}
        }
    }
    readonly property var grok: root.status.grok || {}
    readonly property var gpt: root.status.gpt || {}
    readonly property var merge: root.status.merge || {}
    readonly property var reflect: root.status.reflect || {}
    readonly property var transcript: root.status.transcript || []
    readonly property string mergeLight: String(root.merge.light || root.merge.status || "IDLE")

    function applyRaw(raw) {
        if (raw === undefined || raw === null)
            return
        root.statusJson = String(raw)
    }

    function refresh() {
        if (root.surfaceHost && root.surfaceHost.flowTuiStatus)
            root.applyRaw(root.surfaceHost.flowTuiStatus())
    }

    function submit() {
        var value = String(root.draft || "").trim()
        if (!value.length || !root.surfaceHost || !root.surfaceHost.flowTuiSubmit)
            return
        root.applyRaw(root.surfaceHost.flowTuiSubmit(value))
        root.draft = ""
        input.text = ""
        Qt.callLater(function() { input.forceActiveFocus() })
    }

    function resetBoard() {
        if (root.surfaceHost && root.surfaceHost.flowTuiReset)
            root.applyRaw(root.surfaceHost.flowTuiReset())
        Qt.callLater(function() { input.forceActiveFocus() })
    }

    Component.onCompleted: root.refresh()
    onVisibleChanged: {
        if (visible) {
            root.refresh()
            Qt.callLater(function() { input.forceActiveFocus() })
        }
    }

    Rectangle {
        anchors.fill: parent
        color: "#161616"
    }

    Text {
        id: flowTitle
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        anchors.topMargin: 6
        text: "FLOW TUI  ·  TWO MOTORS  ·  ONE HOUSE"
        color: "#d8dee9"
        font.family: "monospace"
        font.pixelSize: 14
        font.bold: true
    }
    Text {
        id: flowHint
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: flowTitle.bottom
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        anchors.topMargin: 4
        text: String(root.status.hint || "Shared ask. GROK TUI and GPTUI tabs stay as they were.")
        color: "#a8b0b8"
        font.family: "monospace"
        font.pixelSize: 11
        wrapMode: Text.WordWrap
    }

    Row {
        id: inputBar
        objectName: "flowTuiInputBar"
        z: 8
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        anchors.bottomMargin: 6
        spacing: 8
        height: 28

        GgField {
            id: input
            objectName: "flowTuiPrompt"
            width: Math.max(80, parent.width - 90)
            placeholderText: "shared ask for both motors"
            text: root.draft
            onTextChanged: root.draft = text
            Keys.onReturnPressed: root.submit()
        }
        Text {
            text: "RUN"
            color: "#8db89a"
            font.family: "monospace"
            font.pixelSize: 12
            font.bold: true
            anchors.verticalCenter: parent.verticalCenter
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.submit()
            }
        }
        Text {
            text: "RESET"
            color: "#c8a97e"
            font.family: "monospace"
            font.pixelSize: 12
            font.bold: true
            anchors.verticalCenter: parent.verticalCenter
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.resetBoard()
            }
        }
    }

    Item {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: flowHint.bottom
        anchors.bottom: inputBar.top
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        anchors.topMargin: 8
        anchors.bottomMargin: 8

        Row {
            id: motorRow
            spacing: 8
            width: parent.width
            height: Math.min(160, Math.max(88, parent.height * 0.42))

            Rectangle {
                width: (parent.width - 8) / 2
                height: parent.height
                color: "#121212"
                border.color: "#6a6a6a"
                border.width: 1
                radius: 3
                Column {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 4
                    Text {
                        text: "GROK TUI"
                        color: "#c8a97e"
                        font.family: "monospace"
                        font.pixelSize: 12
                        font.bold: true
                    }
                    Repeater {
                        model: root.grok.jobs || []
                        delegate: Text {
                            required property string modelData
                            width: parent.width
                            text: "· " + modelData
                            color: "#c8cdd4"
                            font.family: "monospace"
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                    }
                    Text {
                        visible: !(root.grok.jobs || []).length
                        text: "house · qml · memory · plan"
                        color: "#7f8994"
                        font.family: "monospace"
                        font.pixelSize: 11
                    }
                }
            }

            Rectangle {
                width: (parent.width - 8) / 2
                height: parent.height
                color: "#121212"
                border.color: "#6a6a6a"
                border.width: 1
                radius: 3
                Column {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 4
                    Text {
                        text: "GPTUI"
                        color: "#8db89a"
                        font.family: "monospace"
                        font.pixelSize: 12
                        font.bold: true
                    }
                    Repeater {
                        model: root.gpt.jobs || []
                        delegate: Text {
                            required property string modelData
                            width: parent.width
                            text: "· " + modelData
                            color: "#c8cdd4"
                            font.family: "monospace"
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                    }
                    Text {
                        visible: !(root.gpt.jobs || []).length
                        text: "tests · isolated files · build"
                        color: "#7f8994"
                        font.family: "monospace"
                        font.pixelSize: 11
                    }
                }
            }
        }

        Rectangle {
            id: mergeBox
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: motorRow.bottom
            anchors.topMargin: 8
            height: 48
            color: "#121212"
            border.color: root.mergeLight === "GO" || root.mergeLight === "READY"
                ? "#8db89a"
                : (root.mergeLight === "HOLD" ? "#c98989" : "#6a6a6a")
            border.width: 1
            radius: 3
            Column {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 2
                Text {
                    text: "MERGE  " + String(root.merge.status || "IDLE")
                    color: "#d8dee9"
                    font.family: "monospace"
                    font.pixelSize: 11
                    font.bold: true
                }
                Text {
                    width: parent.width
                    text: String(root.merge.note || "")
                    color: "#a8b0b8"
                    font.family: "monospace"
                    font.pixelSize: 11
                    elide: Text.ElideRight
                }
            }
        }

        Text {
            id: reflectLine
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: mergeBox.bottom
            anchors.topMargin: 6
            text: "REFLECT  " + String(root.reflect.body || "after reconverge")
            color: "#b6a6c8"
            font.family: "monospace"
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }

        Flickable {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: reflectLine.bottom
            anchors.bottom: parent.bottom
            anchors.topMargin: 6
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            contentHeight: logCol.height
            ScrollBar.vertical: GgScrollBar {}
            Column {
                id: logCol
                width: parent.width
                spacing: 3
                Repeater {
                    model: root.transcript
                    delegate: Text {
                        required property var modelData
                        width: logCol.width
                        text: String(modelData.role || "") + "  " + String(modelData.text || "")
                        color: String(modelData.role || "") === "YOU" ? "#d8dee9" : "#8fa8a0"
                        font.family: "monospace"
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }
    }
}
