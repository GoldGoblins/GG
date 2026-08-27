import QtQuick

Item {
    id: root
    property string leftLegend: ""
    property string rightLegend: ""
    property color borderColor: "#6a6a6a"
    property color fill: "#141414"
    default property alias body: inner.data

    Rectangle {
        anchors.fill: parent
        color: root.fill
        border.color: root.borderColor
        border.width: 1
        radius: 2
    }

    Rectangle {
        visible: root.leftLegend.length > 0
        anchors.left: parent.left
        anchors.leftMargin: 10
        anchors.top: parent.top
        anchors.topMargin: -7
        height: 16
        width: leftTxt.implicitWidth + 10
        color: root.fill
        Text {
            id: leftTxt
            anchors.centerIn: parent
            text: root.leftLegend
            color: "#d8dee9"
            font.family: "monospace"
            font.pixelSize: 9
            font.bold: true
        }
    }

    Rectangle {
        visible: root.rightLegend.length > 0
        anchors.right: parent.right
        anchors.rightMargin: 10
        anchors.top: parent.top
        anchors.topMargin: -7
        height: 16
        width: rightTxt.implicitWidth + 10
        color: root.fill
        Text {
            id: rightTxt
            anchors.centerIn: parent
            text: root.rightLegend
            color: "#8b949e"
            font.family: "monospace"
            font.pixelSize: 9
        }
    }

    Item {
        id: inner
        anchors.fill: parent
        anchors.leftMargin: 10
        anchors.rightMargin: 10
        anchors.topMargin: 14
        anchors.bottomMargin: 8
    }
}
