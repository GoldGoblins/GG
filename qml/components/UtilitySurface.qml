pragma ComponentBehavior: Bound

import QtQuick

Item {
    id: root

    objectName: "utilitySurface"

    property color accentColor: "#8a8a8a"
    property color frameBorder: "#6a6a6a"
    property int frameRadius: 2
    readonly property string capabilityState:
        "RESERVED_FOR_REAL_CAPABILITIES"

    property int surfaceHeight: 112
    implicitHeight: root.surfaceHeight

    GgFrame {
        anchors.fill: parent
        leftLegend: "MEDIA / UTILITIES"
        rightLegend: "INDEPENDENT SURFACE"
        backgroundColor: "#161616"
        borderColor: root.frameBorder
        radius: root.frameRadius
    }

    Text {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        text: "Reserved for real radio / VLC / TV / utility capabilities. "
            + "No fake controls are rendered before those capabilities exist."
        color: "#8b949e"
        wrapMode: Text.WordWrap
        font.pixelSize: 10
    }
}
