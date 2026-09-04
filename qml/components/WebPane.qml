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
    property bool wantEngine: false
    property bool engineArmed: false
    signal navigated(string href)

    readonly property bool engineActive: true

    onWantEngineChanged: {
        if (root.wantEngine)
            root.engineArmed = true
    }
    Component.onCompleted: {
        if (root.wantEngine)
            root.engineArmed = true
    }

    function hrefAllowed(target) {
        var href = String(target || "")
        if (href === "about:blank" || href.indexOf("about:blank") === 0)
            return true
        if (root.siteOnly)
            return false
        if (
            href.indexOf("https://") === 0
            || href.indexOf("http://") === 0
        )
            return true
        return false
    }

    function reload() {
        if (engineLoader.item)
            engineLoader.item.reload()
    }

    function goBack() {
        if (engineLoader.item)
            engineLoader.item.goBack()
    }

    function currentHref() {
        if (engineLoader.item)
            return String(engineLoader.item.url || root.pageUrl || "")
        return String(root.pageUrl || "")
    }

    function runPageScript(script, done) {
        if (!engineLoader.item || !engineLoader.item.runJavaScript) {
            done("")
            return
        }
        engineLoader.item.runJavaScript(script, done)
    }

    onReloadNonceChanged: root.reload()

    Loader {
        id: engineLoader
        anchors.fill: parent
        active: root.engineArmed
        sourceComponent: webEngineComp
    }

    Component {
        id: webEngineComp
        WebEngineView {
        id: view
        anchors.fill: parent
        url: root.pageUrl
        backgroundColor: "#161616"
        settings.javascriptEnabled: true
        settings.localContentCanAccessFileUrls: true

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
            var target = String(request.url)
            if (root.hrefAllowed(target)) {
                request.accept()
                return
            }
            var win = Window.window
            var host = win && win.surfaceHost ? win.surfaceHost : null
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
    }

    BufferMark {
        objectName: "webPaneBuffer"
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 8
        active: root.loadState === "LOADING"
        cell: 6
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
