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
}
