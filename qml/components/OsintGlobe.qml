import QtQuick
import QtQuick.Window
import QtWebEngine

Item {
    id: root
    objectName: "osintGlobe"
    clip: true
    property var points: []
    property color muted: "#7f8993"
    property color signalBlue: "#7fa9c4"
    property color ledgerGold: "#c8a97e"
    property color panel: "#111315"
    readonly property int pointCount: (points || []).length
    property var savedView: null
    property var lastPick: null
    property bool navOpen: false
    property string routeMeta: ""
    property var gpsFix: null
    function push() {
        if (browser.item && browser.item.ready)
            browser.item.runJavaScript("window.setOsintPoints(" + JSON.stringify(root.points || []) + ")")
    }
    function focusPoint(lat, lon, zoom) {
        if (!browser.item || !browser.item.ready)
            return
        browser.item.runJavaScript(
            "window.focusOsintPoint && window.focusOsintPoint("
            + JSON.stringify({
                "lat": Number(lat),
                "lon": Number(lon),
                "zoom": Number(zoom === undefined ? 5.2 : zoom)
            })
            + ")"
        )
    }
    function applyRoute(raw) {
        if (!browser.item || !browser.item.ready)
            return
        browser.item.runJavaScript(
            "window.setOsintRoute && window.setOsintRoute(" + String(raw || "{}") + ")"
        )
    }
    function locateGps() {
        if (browser.item && browser.item.ready)
            browser.item.runJavaScript("window.locateOsintGps && window.locateOsintGps()")
    }
    function clearRoute() {
        if (browser.item && browser.item.ready)
            browser.item.runJavaScript("window.clearOsintRoute && window.clearOsintRoute()")
    }
    function setNavOpen(on) {
        navOpen = !!on
        if (browser.item && browser.item.ready)
            browser.item.runJavaScript("window.osintNavOpen = " + (on ? "true" : "false"))
    }
    onPointsChanged: Qt.callLater(root.push)
    Rectangle { anchors.fill: parent; color: "#05070c" }
    Loader {
        id: browser
        anchors.fill: parent
        active: root.Window.window !== null
        sourceComponent: Component {
            WebEngineView {
                property bool ready: false
                backgroundColor: "#05070c"
                url: Qt.resolvedUrl("../osint-map/index.html")
                settings.javascriptEnabled: true
                settings.javascriptCanOpenWindows: false
                settings.localContentCanAccessRemoteUrls: true
                settings.localContentCanAccessFileUrls: true
                settings.webGLEnabled: true
                settings.accelerated2dCanvasEnabled: true
                settings.errorPageEnabled: false
                settings.pluginsEnabled: false
                onLoadingChanged: function(request) {
                    ready = request.status === WebEngineView.LoadSucceededStatus
                    if (ready) {
                        root.push()
                        if (root.savedView)
                            runJavaScript("window.restoreOsintView(" + JSON.stringify(root.savedView) + ")")
                    }
                }
                onNavigationRequested: function(request) {
                    var href = String(request.url)
                    var allowed = String(Qt.resolvedUrl("../osint-map/index.html"))
                    if (href === allowed || href.indexOf(allowed + "?") === 0)
                        request.accept()
                    else
                        request.reject()
                }
                onNewWindowRequested: function(request) { }
                onContextMenuRequested: function(request) { request.accepted = true }
                onFeaturePermissionRequested: function(securityOrigin, feature) {
                    if (feature === WebEngineView.Geolocation)
                        grantFeaturePermission(securityOrigin, feature, true)
                    else
                        grantFeaturePermission(securityOrigin, feature, false)
                }
                onPermissionRequested: function(permission) {
                    permission.grant()
                }
            }
        }
    }
    Timer {
        interval: 2500
        running: browser.item !== null
        repeat: true
        onTriggered: {
            if (browser.item && browser.item.ready) {
                browser.item.runJavaScript("window.getOsintView && window.getOsintView()", function(value) {
                    if (value) root.savedView = value
                })
                browser.item.runJavaScript(
                    "({nav: !!window.osintNavOpen, pick: window.getOsintPick && window.getOsintPick(), meta: window.osintRouteMeta || '', gps: window.osintGps || null})",
                    function(value) {
                        if (!value)
                            return
                        root.navOpen = !!value.nav
                        root.routeMeta = String(value.meta || "")
                        if (value.gps)
                            root.gpsFix = value.gps
                        if (value.pick)
                            root.lastPick = value.pick
                    }
                )
            }
        }
    }
}
