import QtQuick
import QtWebEngine

Item {
    id: root
    objectName: "cryptoTape"
    property var points: []
    property var markers: []
    property var equity: []

    property string lastPayload: ""

    function payloadJson() {
        return JSON.stringify({
            "points": root.points || [],
            "markers": root.markers || [],
            "equity": root.equity || []
        })
    }

    function push() {
        if (!engineLoader.item)
            return
        var raw = root.payloadJson()
        if (raw === root.lastPayload)
            return
        root.lastPayload = raw
        engineLoader.item.runJavaScript(
            "window.setTape && window.setTape(" + raw + ")"
        )
    }

    onPointsChanged: Qt.callLater(root.push)
    onMarkersChanged: Qt.callLater(root.push)
    onEquityChanged: Qt.callLater(root.push)
    onVisibleChanged: {
        if (visible)
            Qt.callLater(root.push)
    }

    Loader {
        id: engineLoader
        anchors.fill: parent
        active: true
        visible: root.visible && root.width > 8 && root.height > 8
        sourceComponent: tapeEngine
    }

    Component {
        id: tapeEngine
        WebEngineView {
            backgroundColor: "#161616"
            url: Qt.resolvedUrl("../crypto-hole/index.html")
            settings.javascriptEnabled: true
            settings.localContentCanAccessFileUrls: true
            onLoadingChanged: function(loadRequest) {
                if (Number(loadRequest.status) === WebEngineView.LoadSucceededStatus)
                    Qt.callLater(root.push)
            }
            onNavigationRequested: function(request) {
                var href = String(request.url)
                if (href.indexOf("file:") === 0)
                    request.accept()
                else
                    request.reject()
            }
        }
    }
}
