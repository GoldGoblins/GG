import QtQuick
import QtQuick.Window
import QtWebEngine

Item {
    id: root
    objectName: "osintGlobe"
    clip: true
    property var points: []
    property var catalogCounts: ({})
    property color muted: "#7f8993"
    property color signalBlue: "#7fa9c4"
    property color ledgerGold: "#c8a97e"
    property color panel: "#111315"
    readonly property int pointCount: (points || []).length
    property var savedView: null
    property var lastPick: null
    property int lastPickSeq: 0
    property bool navOpen: false
    property bool mapReady: false
    property string routeMeta: ""
    property string savedRoute: ""
    property var gpsFix: null
    signal viewportChanged(var view)
    function applySavedState() {
        if (!browser.item || !browser.item.ready)
            return
        root.push()
        if (root.savedView)
            browser.item.runJavaScript("window.restoreOsintView(" + JSON.stringify(root.savedView) + ")")
        if (root.savedRoute)
            browser.item.runJavaScript("window.setOsintRoute && window.setOsintRoute(" + String(root.savedRoute) + ")")
    }
    function push() {
        if (browser.item && browser.item.ready)
            browser.item.runJavaScript(
                "window.setOsintPoints(" + JSON.stringify(root.points || []) + ","
                + JSON.stringify(root.catalogCounts || {}) + ")"
            )
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
    function sampleViewport() {
        if (!browser.item || !browser.item.ready)
            return
        browser.item.runJavaScript(
            "window.getOsintView && window.getOsintView()",
            function(value) {
                if (value)
                    root.viewportChanged(value)
            }
        )
    }
    function showPopup(item) {
        if (!browser.item || !browser.item.ready || !item)
            return
        browser.item.runJavaScript(
            "window.showOsintPopup && window.showOsintPopup("
            + JSON.stringify(item)
            + ")"
        )
    }
    function setProjection(mode) {
        if (!browser.item || !browser.item.ready)
            return
        browser.item.runJavaScript(
            "window.setOsintProjection && window.setOsintProjection("
            + JSON.stringify(String(mode || "globe"))
            + ")"
        )
    }
    function resetView() {
        if (browser.item && browser.item.ready)
            browser.item.runJavaScript("window.resetOsintView && window.resetOsintView()")
    }
    onPointsChanged: Qt.callLater(root.push)
    Rectangle { anchors.fill: parent; color: "#05070c" }
    Loader {
        id: browser
        anchors.fill: parent
        active: root.Window.window !== null
        sourceComponent: Component {
            WebEngineView {
                objectName: "osintMapWebEngine"
                property bool pageReady: false
                property bool ready: false
                function syncMapReady() {
                    if (!pageReady)
                        return
                    runJavaScript("Boolean(window.osintMapReady)", function(value) {
                        var next = Boolean(value)
                        if (next === ready)
                            return
                        ready = next
                        root.mapReady = next
                        if (next)
                            root.applySavedState()
                    })
                }
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
                onLoadingChanged: function(request) {
                    pageReady = request.status === WebEngineView.LoadSucceededStatus
                    ready = false
                    root.mapReady = false
                    if (pageReady)
                        syncMapReady()
                }
            }
        }
    }
    Timer {
        interval: 250
        running: browser.item !== null && browser.item.pageReady && !browser.item.ready
        repeat: true
        onTriggered: browser.item.syncMapReady()
    }
    Timer {
        interval: 750
        running: browser.item !== null
        repeat: true
        onTriggered: root.sampleViewport()
    }
    Timer {
        interval: 2500
        running: browser.item !== null
        repeat: true
        onTriggered: {
            if (browser.item && browser.item.ready) {
                browser.item.runJavaScript("window.getOsintView && window.getOsintView()", function(value) {
                    if (value) {
                        root.savedView = value
                        root.viewportChanged(value)
                    }
                })
                browser.item.runJavaScript(
                    "({nav: !!window.osintNavOpen, pick: window.takeOsintPick && window.takeOsintPick(), meta: window.osintRouteMeta || '', gps: window.osintGps || null, route: window.osintRoutePayload || null})",
                    function(value) {
                        if (!value)
                            return
                        root.navOpen = !!value.nav
                        root.routeMeta = String(value.meta || "")
                        if (value.gps)
                            root.gpsFix = value.gps
                        if (value.route)
                            root.savedRoute = JSON.stringify(value.route)
                        var pick = value.pick
                        if (pick && Number(pick.seq) !== root.lastPickSeq) {
                            root.lastPickSeq = Number(pick.seq)
                            root.lastPick = pick
                        }
                    }
                )
            }
        }
    }
}
