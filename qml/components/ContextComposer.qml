pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls

Item {
    id: root

    signal submitRequested(
        string text,
        string contextReference,
        string workspaceObjectId
    )
    signal stopRequested()
    signal assignmentSetRequested(
        string participant,
        string creatorActor
    )
    signal assignmentClearRequested()
    signal engineTargetRequested(string value)

    property string contextReference: "@current"
    property string workspaceObjectId: ""
    property string workspaceObjectTitle: ""
    property string bridgeState: "NOT CONNECTED"
    property bool busy: false
    property string activeTaskId: ""
    property bool assignmentExpanded: false
    property string engineTarget: "LOCAL_QWEN"
    property color frameBorder: "#6a6a6a"
    property int frameRadius: 2
    property bool showOpenTab: false

    implicitHeight: root.engineTarget === "GROK_TUI"
        ? 22
        : (root.assignmentExpanded ? 160 : 96)
    implicitWidth: 720

    function submit() {
        var value = input.text.trim()
        if (value.length === 0)
            return
        var wasBusy = root.busy
        root.submitRequested(
            value,
            root.contextReference,
            root.workspaceObjectId
        )
        if (
            !wasBusy
            || root.engineTarget === "GROK_WORKER"
            || root.engineTarget === "GROK_TUI"
        )
            input.text = ""
    }

    readonly property bool canSend: input.text.trim().length > 0
    readonly property string engineLabel:
        root.engineTarget === "GROK_TUI"
            ? "GROK TUI"
            : (
                root.engineTarget === "GROK_WORKER"
                    ? "GROK WORKER"
                    : "LOCAL QWEN"
            )

    GgFrame {
        id: inputFrame
        visible: root.engineTarget !== "GROK_TUI"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: engineFooter.top
        anchors.bottomMargin: 16
        leftLegend: root.showOpenTab
            && root.workspaceObjectTitle.length > 0
                ? "INPUT · " + root.workspaceObjectTitle
                : "INPUT"
        rightLegend: root.busy
            ? root.engineLabel + " · RUNNING " + root.activeTaskId
            : root.engineLabel + " · BRIDGE " + root.bridgeState
        bottomLeftLegend: ""
        bottomRightLegend: ""
        backgroundColor: "#161616"
        borderColor: root.frameBorder
        radius: root.frameRadius

        Column {
            width: parent.width
            spacing: 6

            Row {
                width: parent.width
                height: visible ? 28 : 0
                spacing: 8
                visible: root.assignmentExpanded

                ComboBox {
                    id: participantSelector
                    objectName: "orchestratorParticipantSelector"
                    width: 240
                    height: 28
                    currentIndex: -1
                    model: [
                        "GG-AI-installator",
                        "GG-Agentarkitekt-agentskapare",
                        "GG-Content-Studio",
                        "GG-Marknadsföring",
                        "GG-Metaarkitekt-gptskapare",
                        "GG-Webmaster",
                        "GG-idekompassen"
                    ]
                    displayText: currentIndex >= 0
                        ? currentText
                        : "Explicit participant…"
                }

                TextField {
                    id: creatorActorInput
                    objectName: "orchestratorCreatorActorInput"
                    width: parent.width
                        - participantSelector.width
                        - assignmentButton.width
                        - clearAssignmentButton.width
                        - 24
                    height: 28
                    placeholderText: "Explicit creator actor"
                    selectByMouse: true
                }

                Text {
                    id: assignmentButton
                    objectName: "orchestratorAssignmentSetButton"
                    text: "Assign"
                    height: 28
                    verticalAlignment: Text.AlignVCenter
                    color: participantSelector.currentIndex >= 0
                        && creatorActorInput.text.trim().length > 0
                        ? "#d8dee9"
                        : "#5d6670"
                    font.family: "monospace"
                    font.pixelSize: 10
                    font.bold: participantSelector.currentIndex >= 0
                        && creatorActorInput.text.trim().length > 0

                    MouseArea {
                        anchors.fill: parent
                        enabled: participantSelector.currentIndex >= 0
                            && creatorActorInput.text.trim().length > 0
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.assignmentSetRequested(
                            participantSelector.currentText,
                            creatorActorInput.text.trim()
                        )
                    }
                }

                Text {
                    id: clearAssignmentButton
                    objectName: "orchestratorAssignmentClearButton"
                    text: "Clear"
                    height: 28
                    verticalAlignment: Text.AlignVCenter
                    color: "#d8dee9"
                    font.family: "monospace"
                    font.pixelSize: 10
                    font.bold: true

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            participantSelector.currentIndex = -1
                            creatorActorInput.text = ""
                            root.assignmentClearRequested()
                        }
                    }
                }
            }

            Row {
                width: parent.width
                spacing: 8

                Text {
                    text: ">"
                    color: "#8b949e"
                    font.family: "monospace"
                    font.pixelSize: 13
                    verticalAlignment: Text.AlignVCenter
                    height: 22
                }

                TextArea {
                    id: input
                    width: parent.width - 18
                    height: 22
                    enabled: true
                    focus: true
                    placeholderText: ""
                    color: "#e6edf3"
                    wrapMode: TextEdit.NoWrap
                    selectByMouse: true
                    font.family: "monospace"
                    font.pixelSize: 13
                    leftPadding: 0
                    rightPadding: 0
                    topPadding: 2
                    bottomPadding: 0

                    background: Rectangle {
                        color: "transparent"
                        border.width: 0
                    }

                    Keys.onPressed: function(event) {
                        if (
                            (
                                event.key === Qt.Key_Return
                                || event.key === Qt.Key_Enter
                            )
                            && !(event.modifiers & Qt.ShiftModifier)
                        ) {
                            root.submit()
                            event.accepted = true
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        z: 5
        anchors.left: peopleRow.left
        anchors.leftMargin: -6
        anchors.bottom: peopleRow.bottom
        width: peopleRow.width + 12
        height: 18
        color: "#161616"
        visible: peopleRow.width > 0 && root.engineTarget !== "GROK_TUI"
    }

    Row {
        id: peopleRow
        z: 6
        anchors.left: inputFrame.left
        anchors.leftMargin: 14
        anchors.bottom: inputFrame.bottom
        anchors.bottomMargin: -7
        height: 18
        spacing: 0
        visible: root.engineTarget !== "GROK_TUI"
        Text {
            id: assignmentOptionsButton
            objectName: "orchestratorAssignmentOptionsButton"
            text: root.assignmentExpanded
                ? "People · close"
                : "People"
            color: "#d8dee9"
            font.family: "monospace"
            font.pixelSize: 10
            font.bold: true

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked:
                    root.assignmentExpanded = !root.assignmentExpanded
            }
        }
    }

    Rectangle {
        z: 5
        anchors.left: sendRow.left
        anchors.leftMargin: -6
        anchors.bottom: sendRow.bottom
        width: sendRow.width + 12
        height: 18
        color: "#161616"
        visible: sendRow.width > 0 && root.engineTarget !== "GROK_TUI"
    }

    Row {
        id: sendRow
        z: 6
        anchors.right: inputFrame.right
        anchors.rightMargin: 14
        anchors.bottom: inputFrame.bottom
        anchors.bottomMargin: -7
        height: 18
        spacing: 0
        visible: root.engineTarget !== "GROK_TUI"
        Text {
            id: sendButton
            text: "Send"
            visible: !root.busy
            color: root.canSend ? "#d8dee9" : "#5d6670"
            font.family: "monospace"
            font.pixelSize: 10
            font.bold: root.canSend

            MouseArea {
                anchors.fill: parent
                enabled: root.canSend
                cursorShape: root.canSend
                    ? Qt.PointingHandCursor
                    : Qt.ArrowCursor
                onClicked: root.submit()
            }
        }

        Text {
            id: stopButton
            text: "Stop"
            visible: root.busy
            enabled: root.busy
            color: root.busy ? "#d8dee9" : "#5d6670"
            font.family: "monospace"
            font.pixelSize: 10
            font.bold: root.busy

            MouseArea {
                anchors.fill: parent
                enabled: root.busy
                cursorShape: Qt.PointingHandCursor
                onClicked: root.stopRequested()
            }
        }
    }

    Row {
        id: engineFooter
        objectName: "engineTargetSelector"
        anchors.left: parent.left
        anchors.leftMargin: 14
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 2
        height: 16
        spacing: 0

        Text {
            id: qwenEngineTarget
            text: "QWEN"
            color: root.engineTarget === "LOCAL_QWEN"
                ? "#d8dee9"
                : "#5d6670"
            font.family: "monospace"
            font.pixelSize: 10
            font.bold: root.engineTarget === "LOCAL_QWEN"

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.engineTargetRequested("LOCAL_QWEN")
            }
        }

        Text {
            text: " | "
            color: "#5d6670"
            font.family: "monospace"
            font.pixelSize: 10
        }

        Text {
            id: grokEngineTarget
            text: "GROK"
            color: root.engineTarget === "GROK_WORKER"
                ? "#d8dee9"
                : "#5d6670"
            font.family: "monospace"
            font.pixelSize: 10
            font.bold: root.engineTarget === "GROK_WORKER"

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.engineTargetRequested("GROK_WORKER")
            }
        }

        Text {
            text: " | "
            color: "#5d6670"
            font.family: "monospace"
            font.pixelSize: 10
        }

        Text {
            id: grokTuiEngineTarget
            text: "GROK TUI"
            color: root.engineTarget === "GROK_TUI"
                ? "#d8dee9"
                : "#5d6670"
            font.family: "monospace"
            font.pixelSize: 10
            font.bold: root.engineTarget === "GROK_TUI"

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.engineTargetRequested("GROK_TUI")
            }
        }
    }
}
