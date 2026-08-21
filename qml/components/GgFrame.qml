import QtQuick

Item {
    id: root

    property string leftLegend: ""
    property string rightLegend: ""
    property string bottomLeftLegend: ""
    property string bottomRightLegend: ""
    property color backgroundColor: "#161616"
    property color borderColor: "#6a6a6a"
    property color leftLegendColor: "#d8dee9"
    property color rightLegendColor: "#8b949e"
    property int radius: 2
    property int padding: 14
    property int legendGap: 8

    default property alias contentData: content.data

    readonly property bool hasTopLegend:
        root.leftLegend.length > 0 || root.rightLegend.length > 0
    readonly property bool hasBottomLegend:
        root.bottomLeftLegend.length > 0 || root.bottomRightLegend.length > 0

    implicitWidth: 320
    implicitHeight: Math.max(
        44,
        content.implicitHeight
            + (root.hasTopLegend ? 22 : 10)
            + (root.hasBottomLegend ? 22 : 10)
            + root.padding
    )

    Rectangle {
        id: frame
        anchors.fill: parent
        radius: root.radius
        color: root.backgroundColor
        border.width: 1
        border.color: root.borderColor
    }

    Rectangle {
        id: leftLegendPlate
        visible: root.leftLegend.length > 0
        anchors.left: parent.left
        anchors.leftMargin: 12
        anchors.top: parent.top
        anchors.topMargin: -7
        height: 18
        width: leftLegendText.implicitWidth + 12
        color: root.backgroundColor

        Text {
            id: leftLegendText
            anchors.centerIn: parent
            text: root.leftLegend
            color: root.leftLegendColor
            font.family: "monospace"
            font.pixelSize: 10
            font.bold: true
        }
    }

    Rectangle {
        visible: root.rightLegend.length > 0
        anchors.right: parent.right
        anchors.rightMargin: 12
        anchors.top: parent.top
        anchors.topMargin: -7
        height: 18
        width: rightLegendText.implicitWidth + 12
        color: root.backgroundColor

        Text {
            id: rightLegendText
            anchors.centerIn: parent
            text: root.rightLegend
            color: root.rightLegendColor
            font.family: "monospace"
            font.pixelSize: 10
            font.bold: true
        }
    }

    Rectangle {
        visible: root.bottomLeftLegend.length > 0
        anchors.left: parent.left
        anchors.leftMargin: 12
        anchors.bottom: parent.bottom
        anchors.bottomMargin: -7
        height: 18
        width: bottomLeftLegendText.implicitWidth + 12
        color: root.backgroundColor

        Text {
            id: bottomLeftLegendText
            anchors.centerIn: parent
            text: root.bottomLeftLegend
            color: root.leftLegendColor
            font.family: "monospace"
            font.pixelSize: 10
            font.bold: true
        }
    }

    Rectangle {
        visible: root.bottomRightLegend.length > 0
        anchors.right: parent.right
        anchors.rightMargin: 12
        anchors.bottom: parent.bottom
        anchors.bottomMargin: -7
        height: 18
        width: bottomRightLegendText.implicitWidth + 12
        color: root.backgroundColor

        Text {
            id: bottomRightLegendText
            anchors.centerIn: parent
            text: root.bottomRightLegend
            color: root.rightLegendColor
            font.family: "monospace"
            font.pixelSize: 10
        }
    }

    Column {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: root.padding
        anchors.rightMargin: root.padding
        anchors.topMargin: root.hasTopLegend ? 22 : 10
        spacing: 8
    }
}
