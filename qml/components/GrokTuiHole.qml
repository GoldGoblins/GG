pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Window
import QtWebEngine
import QtWebChannel

Item {
    id: root
    objectName: "grokTuiHost"

    property var surfaceHost: null

    WebChannel {
        id: tuiChannel
        registeredObjects: [hostProxy]
    }

    QtObject {
        id: hostProxy
        WebChannel.id: "host"

        signal grokTuiChunk(string b64)

        function grokTuiWrite(data) {
            if (root.surfaceHost)
                root.surfaceHost.grokTuiWrite(data)
        }

        function grokTuiReady() {
            if (root.surfaceHost)
                root.surfaceHost.startGrokTui("ws.tui.grok")
        }

        function grokTuiResize(cols, rows) {
            if (root.surfaceHost)
                root.surfaceHost.grokTuiResize(cols, rows)
        }
    }

    Connections {
        target: root.surfaceHost
        function onGrokTuiChunk(b64) {
            hostProxy.grokTuiChunk(b64)
        }
    }

    WebEngineView {
        id: view
        anchors.fill: parent
        anchors.margins: 2
        url: Qt.resolvedUrl("../terminal-hole/index.html")
        webChannel: tuiChannel
        settings.localContentCanAccessFileUrls: true
        settings.javascriptEnabled: true
        backgroundColor: "#161616"
        focus: root.visible

        onNavigationRequested: function(request) {
            var href = String(request.url)
            if (href.indexOf("file:") === 0)
                request.accept()
            else
                request.reject()
        }
    }

    onVisibleChanged: {
        if (visible)
            view.forceActiveFocus()
    }
}
