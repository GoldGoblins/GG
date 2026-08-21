pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls

Item {
    id: root

    property real chatWidthRatio: 0.31
    property int telemetryWidth: 168
    property int utilityHeight: 112

    signal chatWidthRatioChangedByUser(real value)
    signal telemetryWidthChangedByUser(int value)
    signal utilityHeightChangedByUser(int value)

    implicitHeight: 248

    GgFrame {
        anchors.fill: parent
        leftLegend: "LAYOUT"
        rightLegend: "LIVE"
        backgroundColor: "#161616"
        borderColor: "#6a6a6a"
    }

    Column {
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 14
        anchors.topMargin: 22
        anchors.bottomMargin: 12
        spacing: 7

        Text {
            text: "Chat width · "
                + Math.round(root.chatWidthRatio * 100)
                + "%"
            color: "#d8dee9"
            font.family: "monospace"
            font.pixelSize: 10
        }

        Slider {
            id: chatSlider
            width: parent.width
            from: 0.24
            to: 0.42
            stepSize: 0.01
            value: root.chatWidthRatio

            onMoved:
                root.chatWidthRatioChangedByUser(
                    chatSlider.value
                )
        }

        Text {
            text: "Telemetry width · "
                + String(root.telemetryWidth)
                + " px"
            color: "#d8dee9"
            font.family: "monospace"
            font.pixelSize: 10
        }

        Slider {
            id: telemetrySlider
            width: parent.width
            from: 140
            to: 260
            stepSize: 4
            value: root.telemetryWidth

            onMoved:
                root.telemetryWidthChangedByUser(
                    Math.round(telemetrySlider.value)
                )
        }

        Text {
            text: "Media / Utilities height · "
                + String(root.utilityHeight)
                + " px"
            color: "#d8dee9"
            font.family: "monospace"
            font.pixelSize: 10
        }

        Slider {
            id: utilitySlider
            width: parent.width
            from: 72
            to: 180
            stepSize: 4
            value: root.utilityHeight

            onMoved:
                root.utilityHeightChangedByUser(
                    Math.round(utilitySlider.value)
                )
        }

        Text {
            width: parent.width
            text: "Center Workspace keeps the remaining width. "
                + "Media / Utilities is a separate sibling surface."
            color: "#8b949e"
            wrapMode: Text.WordWrap
            font.pixelSize: 10
        }
    }
}
