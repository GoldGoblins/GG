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
            + "Give instructions directly in the chat. If an operation "
            + "needs confirmation, answer ja or nej there; the app then "
            + "continues with the task you described."
        color: "#c8cdd4"
        wrapMode: Text.WordWrap
        font.pixelSize: 12
    }
}
