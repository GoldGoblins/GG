pragma ComponentBehavior: Bound

import QtQuick

FocusScope {
    id: root
    objectName: "grokTuiHost"
    clip: true

    property var surfaceHost: null

    onVisibleChanged: {
        if (visible)
            root.forceActiveFocus()
    }

    Item {
        objectName: "grokTuiPrompt"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 30
        height: 38
        enabled: false
    }
}
