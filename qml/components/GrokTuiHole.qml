pragma ComponentBehavior: Bound

import QtQuick

FocusScope {
    id: root
    objectName: "grokTuiHost"

    property var surfaceHost: null

    onVisibleChanged: {
        if (visible)
            root.forceActiveFocus()
    }
}
