pragma ComponentBehavior: Bound

import QtQuick

FocusScope {
    id: root
    objectName: "grokTuiHost"
    clip: true
    focus: true
    Keys.priority: Keys.BeforeItem

    Keys.onPressed: function(event) {
        var paste = (
            event.key === Qt.Key_V
            && (event.modifiers & Qt.ControlModifier)
        ) || (
            event.key === Qt.Key_Insert
            && (event.modifiers & Qt.ShiftModifier)
        )
        if (!paste)
            return
        if (root.surfaceHost && root.surfaceHost.pasteChatTerminal)
            root.surfaceHost.pasteChatTerminal(root.terminalId)
        event.accepted = true
    }

    property var surfaceHost: null
    // Both engines use the same terminal surface and input styling.  The
    // identity only selects which PTY receives paste/shortcut events.
    property string terminalId: "ws.tui.grok"
    property int scrollOffset: 0
    property int scrollMaximum: 0
    property int scrollPage: 1

    function applyScrollMetrics(offset, maximum, page) {
        root.scrollOffset = Math.max(0, Number(offset) || 0)
        root.scrollMaximum = Math.max(0, Number(maximum) || 0)
        root.scrollPage = Math.max(1, Number(page) || 1)
    }

    function scrollFromBar(y) {
        if (root.scrollMaximum <= 0)
            return
        var track = Math.max(1, root.height)
        var thumb = Math.max(24, track * root.scrollPage /
            (root.scrollMaximum + root.scrollPage))
        var travel = Math.max(1, track - thumb)
        var ratio = Math.max(0, Math.min(1, (y - thumb / 2) / travel))
        if (root.surfaceHost && root.surfaceHost.scrollChatTerminalTo)
            root.surfaceHost.scrollChatTerminalTo(
                root.terminalId,
                Math.round(ratio * root.scrollMaximum)
            )
    }

    Connections {
        target: root.surfaceHost
        function onTerminalScrollChanged(id, offset, maximum, page) {
            if (id === root.terminalId)
                root.applyScrollMetrics(offset, maximum, page)
        }
    }

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

    // QQuickPaintedItem normally receives wheel events itself, but a QML
    // FocusScope can win the event-routing race depending on which child was
    // created first.  This transparent proxy keeps wheel scrolling reliable
    // without participating in ordinary clicks or drag-selection.
    MouseArea {
        objectName: "grokTuiWheelProxy"
        anchors.fill: parent
        z: 1000
        acceptedButtons: Qt.NoButton
        propagateComposedEvents: true
        onWheel: function(wheel) {
            if (!root.surfaceHost || !root.surfaceHost.scrollChatTerminal)
                return
            var handled = root.surfaceHost.scrollChatTerminal(
                root.terminalId,
                wheel.angleDelta.y
            )
            wheel.accepted = Boolean(handled)
        }
    }

    // TerminalGrid is intentionally not a Flickable, so expose its bounded
    // inline history with the same visible grab handle as the rest of the UI.
    Rectangle {
        id: terminalScrollBar
        objectName: "grokTuiScrollBar"
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        width: 9
        z: 1100
        color: "#1b1e22"
        opacity: root.scrollMaximum > 0 ? 0.9 : 0.35
        visible: true

        Rectangle {
            id: terminalScrollThumb
            x: 2
            width: parent.width - 4
            height: Math.max(
                24,
                parent.height * root.scrollPage /
                    (root.scrollMaximum + root.scrollPage)
            )
            y: (parent.height - height) *
                (root.scrollMaximum > 0
                    ? root.scrollOffset / root.scrollMaximum
                    : 0)
            radius: 2
            visible: root.scrollMaximum > 0
            color: terminalScrollMouse.pressed
                ? "#c8cdd4"
                : (terminalScrollMouse.containsMouse ? "#a8b0b8" : "#707780")
            opacity: terminalScrollMouse.pressed || terminalScrollMouse.containsMouse
                ? 1.0 : 0.82
        }

        MouseArea {
            id: terminalScrollMouse
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton
            enabled: root.scrollMaximum > 0
            hoverEnabled: true
            onPressed: function(mouse) {
                root.scrollFromBar(mouse.y)
            }
            onPositionChanged: function(mouse) {
                if (pressed)
                    root.scrollFromBar(mouse.y)
            }
            onWheel: function(wheel) {
                if (!root.surfaceHost || !root.surfaceHost.scrollChatTerminal)
                    return
                var handled = root.surfaceHost.scrollChatTerminal(
                    root.terminalId,
                    wheel.angleDelta.y
                )
                wheel.accepted = Boolean(handled)
            }
        }
    }
}
