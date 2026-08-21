pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Window
import QtWebEngine

Item {
    id: root
    objectName: "webPane"

    property url pageUrl: ""
    property string loadState: "IDLE"
    property bool siteOnly: false
    property int reloadNonce: 0
    signal navigated(string href)

    function reload() {
        view.reload()
    }

    onReloadNonceChanged: view.reload()

    WebEngineView {
        id: view
        anchors.fill: parent
        url: root.pageUrl

        onUrlChanged: {
            var href = String(view.url)
            if (href.length > 0 && href !== String(root.pageUrl))
                root.navigated(href)
        }

        onLoadingChanged: function(loadRequest) {
            var status = Number(loadRequest.status)
            if (status === WebEngineView.LoadStartedStatus)
                root.loadState = "LOADING"
            else if (status === WebEngineView.LoadSucceededStatus)
                root.loadState = "PASS"
            else if (status === WebEngineView.LoadFailedStatus)
                root.loadState = "FAIL"
        }

        onNavigationRequested: function(request) {
            var win = Window.window
            var host = win && win.surfaceHost ? win.surfaceHost : null
            var target = String(request.url)
            var allowed = false
            if (host !== null)
                allowed = root.siteOnly
                    ? host.urlAllowed(target)
                    : host.browseUrlAllowed(target)
            if (!allowed) {
                request.reject()
                root.loadState = "BLOCKED"
                return
            }
            request.accept()
        }
    }

    Text {
        visible: root.loadState === "FAIL" || root.loadState === "BLOCKED"
        anchors.centerIn: parent
        width: parent.width - 40
        horizontalAlignment: Text.AlignHCenter
        text: root.loadState === "BLOCKED"
            ? (
                root.siteOnly
                    ? "URL is outside the local SITE root."
                    : "This address cannot be opened here."
            )
            : "WebEngine could not load this page."
        color: "#c8a97e"
        wrapMode: Text.WordWrap
        font.family: "monospace"
        font.pixelSize: 12
    }
}
