pragma ComponentBehavior: Bound

import QtQuick

Item {
    id: root

    implicitHeight: 112

    GgFrame {
        anchors.fill: parent
        leftLegend: "EXTENSIONS"
        rightLegend: "FOUNDATION ONLY"
        backgroundColor: "#161616"
        borderColor: "#6a6a6a"
    }

    Text {
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 14
        anchors.topMargin: 22
        anchors.bottomMargin: 12
        text: "Future themes and visual modules can integrate here. "
            + "A1.2 grants no arbitrary QML, Python, shell, network or "
            + "capability execution."
        color: "#c8cdd4"
        wrapMode: Text.WordWrap
        font.pixelSize: 12
    }
}
