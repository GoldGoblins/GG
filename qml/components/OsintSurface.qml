import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    objectName: "workspaceOsintPane"

    property var surfaceHost: null
    property color frameBorder: "#6a6a6a"
    property int frameRadius: 4
    readonly property color ink: "#e6edf3"
    readonly property color text: "#c8cdd4"
    readonly property color muted: "#7f8993"
    readonly property color panel: "#181818"
    readonly property color panelRaised: "#202020"
    readonly property color selectedPanel: "#34383d"
    readonly property color ledgerGold: "#c8a97e"
    readonly property color ledgerGreen: "#8db89a"
    readonly property color signalBlue: "#7fa9c4"
    readonly property color signalRed: "#c98989"
    readonly property color signalViolet: "#b6a6c8"
    property string statusJson: "{}"
    property string page: "OVERVIEW"
    property bool sidebarCollapsed: false
    property bool fetchBusy: false
    property var payload: ({})
    property var selectedEvent: null
    property bool navMode: false
    property string navDraft: ""
    property var navPlaces: []
    property string navMeta: ""

    readonly property var nav: [
        "OVERVIEW",
        "MAP",
        "FLIGHTS",
        "SEISMIC",
        "FIRES",
        "SPACE",
        "NEWS",
        "CONFLICT",
        "CAMERAS",
        "SOURCES",
        "RECON"
    ]

    function applyRaw(raw) {
        if (!raw)
            return
        try {
            var parsed = JSON.parse(String(raw))
            root.statusJson = String(raw)
            root.payload = parsed
            root.fetchBusy = false
        } catch (err) {
            root.fetchBusy = false
        }
    }

    function refresh() {
        if (!root.surfaceHost)
            return
        if (root.surfaceHost.osintSnapshot)
            root.applyRaw(root.surfaceHost.osintSnapshot(root.page))
        if (root.surfaceHost.osintRefresh) {
            var queued = root.surfaceHost.osintRefresh(root.page)
            if (queued)
                root.fetchBusy = true
        }
    }

    function rows(name) {
        var value = root.payload[name]
        return value && value.length !== undefined ? value : []
    }

    function count(name) {
        var counts = root.payload.counts || {}
        return Number(counts[name] || 0)
    }

    function history(name) {
        var values = (root.payload.histories || {})[name]
        return values && values.length !== undefined && values.length
            ? values
            : [0]
    }

    function navLabel(value) {
        var labels = {
            "OVERVIEW": "Overview",
            "MAP": "Event Map",
            "FLIGHTS": "Flights",
            "SEISMIC": "Seismic",
            "FIRES": "Fires",
            "SPACE": "Space Weather",
            "NEWS": "News",
            "CONFLICT": "Conflict watch",
            "CAMERAS": "ALPR pins",
            "SOURCES": "Sources",
            "RECON": "Recon boundary"
        }
        return labels[String(value || "")] || String(value || "")
    }

    function navIcon(value) {
        var icons = {
            "OVERVIEW": "⌂",
            "MAP": "◎",
            "FLIGHTS": "✈",
            "SEISMIC": "∿",
            "FIRES": "◆",
            "SPACE": "✦",
            "NEWS": "▤",
            "CONFLICT": "◇",
            "CAMERAS": "▣",
            "SOURCES": "▦",
            "RECON": "⌁"
        }
        return icons[String(value || "")] || "·"
    }

    function number(value, decimals) {
        var n = Number(value)
        if (!isFinite(n))
            return "—"
        return n.toFixed(decimals === undefined ? 0 : decimals)
    }

    function shortTime(value) {
        var s = String(value || "")
        if (!s)
            return "—"
        if (s.indexOf("T") >= 0)
            return s.replace("T", " ").replace("Z", "").slice(0, 19)
        return s.slice(0, 24)
    }

    function statusText() {
        if (root.fetchBusy)
            return "FETCHING"
        return String(root.payload.status || "READY")
    }

    function statusColor() {
        var value = statusText()
        if (value === "LIVE")
            return root.ledgerGreen
        if (value === "DEGRADED")
            return root.ledgerGold
        if (value === "OFFLINE")
            return root.signalRed
        if (value === "FETCHING")
            return root.signalBlue
        return root.muted
    }

    function markerColor(kind) {
        if (kind === "aircraft")
            return root.signalBlue
        if (kind === "earthquakes")
            return root.ledgerGold
        if (kind === "fires")
            return root.signalRed
        if (kind === "conflicts")
            return root.signalViolet
        if (kind === "cameras")
            return "#6ec4d8"
        if (kind === "gdelt" || kind === "news")
            return "#7fa9c4"
        return root.text
    }

    function mapPoints() {
        var result = []
        function add(items, kind, limit) {
            var values = items || []
            var cap = Math.min(values.length, limit)
            for (var i = 0; i < cap; i++) {
                var item = values[i] || {}
                if (item.lat === undefined || item.lon === undefined)
                    continue
                result.push({
                    lat: Number(item.lat),
                    lon: Number(item.lon),
                    kind: kind,
                    label: String(item.callsign || item.place || item.title || item.label || kind),
                    color: root.markerColor(kind),
                    heading: Number(item.heading || 0),
                    speed_mps: Number(item.speed_mps || 0),
                    alt_m: Number(item.alt_m || 0),
                    on_ground: Boolean(item.on_ground),
                    magnitude: Number(item.magnitude || 0),
                    severity: Number(item.severity || 0)
                })
            }
        }
        add(root.rows("aircraft"), "aircraft", 160)
        add(root.rows("earthquakes"), "earthquakes", 80)
        add(root.rows("fires"), "fires", 80)
        add(root.rows("conflicts"), "conflicts", 40)
        add(root.rows("gdelt"), "gdelt", 40)
        return result
    }

    function streamRows() {
        var values = root.payload.stream
        if (values && values.length)
            return values
        return root.rows("news").slice(0, 7)
    }

    function focusGlobe(item) {
        root.navMode = false
        overviewGlobe.setNavOpen(false)
        root.selectedEvent = item
        if (item && item.lat !== undefined && item.lon !== undefined)
            overviewGlobe.focusPoint(item.lat, item.lon, 5.4)
    }

    function openNav() {
        root.navMode = true
        root.selectedEvent = null
        overviewGlobe.setNavOpen(true)
    }

    function commitNavPlace() {
        var place = String(root.navDraft || "").trim()
        if (!place)
            return false
        if (root.navPlaces.length >= 26)
            return false
        var next = root.navPlaces.slice()
        if (next.length >= 2)
            next.splice(next.length - 1, 0, place)
        else
            next.push(place)
        root.navPlaces = next
        root.navDraft = ""
        return true
    }

    function removeNavPlace(index) {
        var next = []
        for (var i = 0; i < root.navPlaces.length; i++) {
            if (i !== index)
                next.push(root.navPlaces[i])
        }
        root.navPlaces = next
    }

    function moveNavPlace(fromIndex, toIndex) {
        var from = Number(fromIndex)
        var to = Number(toIndex)
        if (from === to || from < 0 || to < 0)
            return
        if (from >= root.navPlaces.length || to >= root.navPlaces.length)
            return
        var next = root.navPlaces.slice()
        var item = next.splice(from, 1)[0]
        next.splice(to, 0, item)
        root.navPlaces = next
    }

    function runNavRoute() {
        root.commitNavPlace()
        if (root.navPlaces.length < 2) {
            root.navMeta = "Add at least two places, then ROUTE."
            return
        }
        var places = root.navPlaces
        var gps = null
        if (String(places[0]).toLowerCase() === "gps" && overviewGlobe.gpsFix)
            gps = overviewGlobe.gpsFix
        root.navMeta = "ROUTING…"
        var raw = "{}"
        if (root.surfaceHost && root.surfaceHost.osintPlanRoute)
            raw = root.surfaceHost.osintPlanRoute(JSON.stringify({
                "places": places,
                "gps": gps
            }))
        var result = {}
        try {
            result = JSON.parse(String(raw || "{}"))
        } catch (err) {
            result = {}
        }
        if (!result.ok) {
            root.navMeta = String(result.error || "Routing unavailable.")
            return
        }
        var km = (Number(result.distance_m || 0) / 1000).toFixed(1)
        var min = Math.round(Number(result.duration_s || 0) / 60)
        root.navMeta = km + " km · " + min + " min · " + places.length + " places"
        overviewGlobe.applyRoute(raw)
    }

    function clearNav() {
        root.navDraft = ""
        root.navPlaces = []
        root.navMeta = ""
        overviewGlobe.clearRoute()
    }

    function paintMap(ctx, width, height) {
        ctx.clearRect(0, 0, width, height)
        ctx.fillStyle = "#111315"
        ctx.fillRect(0, 0, width, height)
        ctx.strokeStyle = "#25292d"
        ctx.lineWidth = 1
        for (var longitude = -180; longitude <= 180; longitude += 30) {
            var gx = (longitude + 180) / 360 * width
            ctx.beginPath()
            ctx.moveTo(gx, 0)
            ctx.lineTo(gx, height)
            ctx.stroke()
        }
        for (var latitude = -60; latitude <= 90; latitude += 30) {
            var gy = (90 - latitude) / 180 * height
            ctx.beginPath()
            ctx.moveTo(0, gy)
            ctx.lineTo(width, gy)
            ctx.stroke()
        }
        ctx.strokeStyle = "#394047"
        ctx.beginPath()
        ctx.moveTo(width / 2, 0)
        ctx.lineTo(width / 2, height)
        ctx.moveTo(0, height / 2)
        ctx.lineTo(width, height / 2)
        ctx.stroke()

        var points = root.mapPoints()
        for (var i = 0; i < points.length; i++) {
            var point = points[i]
            var x = (point.lon + 180) / 360 * width
            var y = (90 - point.lat) / 180 * height
            if (x < -8 || x > width + 8 || y < -8 || y > height + 8)
                continue
            var radius = point.kind === "conflicts" ? 4 : 2.5
            ctx.globalAlpha = point.kind === "conflicts" ? 0.75 : 0.88
            ctx.fillStyle = point.color
            ctx.beginPath()
            ctx.arc(x, y, radius, 0, Math.PI * 2)
            ctx.fill()
            if (point.kind === "conflicts") {
                ctx.globalAlpha = 0.22
                ctx.beginPath()
                ctx.arc(x, y, 10, 0, Math.PI * 2)
                ctx.strokeStyle = point.color
                ctx.stroke()
            }
        }
        ctx.globalAlpha = 1
        ctx.fillStyle = "#6c757d"
        ctx.font = "10px monospace"
        ctx.fillText("90N", 6, 12)
        ctx.fillText("0", 6, height / 2 - 4)
        ctx.fillText("60S", 6, height - 6)
        ctx.fillText("GLOBAL PUBLIC FEEDS · POINTS ONLY", 14, height - 8)
    }

    function copyText(value) {
        if (root.surfaceHost && root.surfaceHost.osintCopy)
            root.surfaceHost.osintCopy(String(value || ""))
    }

    onPageChanged: {
        if (root.visible)
            root.refresh()
    }

    onVisibleChanged: {
        if (visible)
            root.refresh()
    }

    Connections {
        target: root.surfaceHost
        ignoreUnknownSignals: true
        function onOsintUpdated(raw) {
            root.applyRaw(raw)
        }
    }

    Connections {
        target: overviewGlobe
        ignoreUnknownSignals: true
        function onNavOpenChanged() {
            if (overviewGlobe.navOpen)
                root.openNav()
            else if (!root.selectedEvent)
                root.navMode = false
        }
        function onLastPickChanged() {
            if (overviewGlobe.lastPick)
                root.focusGlobe(overviewGlobe.lastPick)
        }
        function onRouteMetaChanged() {
            if (overviewGlobe.routeMeta)
                root.navMeta = overviewGlobe.routeMeta
        }
        function onGpsFixChanged() {
            if (overviewGlobe.gpsFix)
                root.navMeta = overviewGlobe.routeMeta
        }
    }

    Timer {
        interval: 90000
        repeat: true
        running: root.visible
        onTriggered: root.refresh()
    }

    Component.onCompleted: root.refresh()

    Rectangle {
        anchors.fill: parent
        anchors.leftMargin: 8
        anchors.rightMargin: 12
        anchors.topMargin: 8
        anchors.bottomMargin: 10
        color: "#161616"
        border.color: "#333333"
        border.width: 1
    }

    Rectangle {
        id: sidebar
        anchors.left: parent.left
        anchors.leftMargin: 8
        anchors.top: parent.top
        anchors.topMargin: 8
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 10
        width: root.sidebarCollapsed ? 48 : Math.max(168, Math.min(205, parent.width * 0.18))
        color: root.panel
        border.color: "#333333"
        border.width: 1

        Behavior on width {
            NumberAnimation { duration: 150; easing.type: Easing.OutCubic }
        }

        Column {
            id: navColumn
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: sidebarFooter.top
            anchors.margins: 10
            spacing: 3

            Item {
                width: navColumn.width
                height: 30
                Text {
                    anchors.centerIn: parent
                    text: "☰"
                    color: root.ink
                    font.family: "monospace"
                    font.pixelSize: 19
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.sidebarCollapsed = !root.sidebarCollapsed
                }
            }

            Repeater {
                model: root.nav
                delegate: Item {
                    required property string modelData
                    width: navColumn.width
                    height: 29
                    Rectangle {
                        anchors.fill: parent
                        radius: 3
                        color: root.page === modelData
                            ? root.selectedPanel
                            : (navHit.containsMouse ? "#2a2a2a" : "transparent")
                    }
                    Text {
                        visible: !root.sidebarCollapsed
                        anchors.left: parent.left
                        anchors.leftMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.navIcon(modelData)
                        color: root.page === modelData ? root.ledgerGold : root.muted
                        font.family: "monospace"
                        font.pixelSize: 14
                    }
                    Text {
                        visible: !root.sidebarCollapsed
                        anchors.left: parent.left
                        anchors.leftMargin: 38
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.navLabel(modelData)
                        color: root.page === modelData ? root.ink : root.text
                        font.family: "monospace"
                        font.pixelSize: 12
                        font.bold: root.page === modelData
                        elide: Text.ElideRight
                    }
                    Text {
                        visible: root.sidebarCollapsed
                        anchors.centerIn: parent
                        text: root.navIcon(modelData)
                        color: root.page === modelData ? root.ledgerGold : root.muted
                        font.family: "monospace"
                        font.pixelSize: 14
                    }
                    MouseArea {
                        id: navHit
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.page = modelData
                    }
                }
            }
        }

        Item {
            id: sidebarFooter
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: root.sidebarCollapsed ? 50 : 82
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: 1
                color: "#3a3a3a"
            }
            Text {
                visible: !root.sidebarCollapsed
                anchors.left: parent.left
                anchors.leftMargin: 14
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 43
                text: "OSINT"
                color: root.ledgerGold
                font.family: "monospace"
                font.pixelSize: 17
                font.bold: true
                font.letterSpacing: 1.1
            }
            Text {
                visible: !root.sidebarCollapsed
                anchors.left: parent.left
                anchors.leftMargin: 14
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 14
                text: "PUBLIC · READ ONLY"
                color: root.muted
                font.family: "monospace"
                font.pixelSize: 10
            }
            Text {
                visible: root.sidebarCollapsed
                anchors.centerIn: parent
                text: "⌁"
                color: root.ledgerGold
                font.pixelSize: 17
            }
        }
    }

    Rectangle {
        id: navSeparator
        anchors.left: sidebar.right
        anchors.leftMargin: 12
        anchors.top: sidebar.top
        anchors.bottom: sidebar.bottom
        width: 1
        color: "#3a3a3a"
    }

    Item {
        id: mainArea
        anchors.left: navSeparator.right
        anchors.leftMargin: 18
        anchors.right: parent.right
        anchors.rightMargin: 12
        anchors.top: parent.top
        anchors.topMargin: 8
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 10

        Item {
            id: header
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 54

            Text {
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.topMargin: 4
                text: "GG / OSIRIS · NATIVE · PUBLIC READ ONLY"
                color: root.muted
                font.family: "monospace"
                font.pixelSize: 9
            }
            Text {
                anchors.left: parent.left
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 5
                text: root.navLabel(root.page).toUpperCase()
                color: root.ink
                font.family: "monospace"
                font.pixelSize: 18
            }

            Rectangle {
                id: sourceStatus
                anchors.right: refreshButton.left
                anchors.rightMargin: 14
                anchors.verticalCenter: parent.verticalCenter
                width: sourceStatusLabel.implicitWidth + 22
                height: 27
                color: "#181b1f"
                border.color: "#3c444d"
                border.width: 1
                radius: 3
                Text {
                    id: sourceStatusLabel
                    anchors.centerIn: parent
                    text: root.statusText()
                        + " · "
                        + String(root.payload.healthy_sources || 0)
                        + "/"
                        + String(root.payload.source_count || 0)
                    color: root.statusColor()
                    font.family: "monospace"
                    font.pixelSize: 10
                }
            }

            Rectangle {
                id: refreshButton
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                width: refreshLabel.implicitWidth + 24
                height: 27
                color: refreshHit.pressed ? "#20262d" : "#181b1f"
                border.color: refreshHit.containsMouse ? root.ledgerGold : "#3c444d"
                border.width: 1
                radius: 3
                Text {
                    id: refreshLabel
                    anchors.centerIn: parent
                    text: root.fetchBusy ? "…  FETCHING" : "↻  REFRESH"
                    color: root.text
                    font.family: "monospace"
                    font.pixelSize: 10
                }
                MouseArea {
                    id: refreshHit
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.refresh()
                }
            }
        }

        StackLayout {
            id: pages
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: header.bottom
            anchors.bottom: parent.bottom
            currentIndex: Math.max(0, root.nav.indexOf(root.page))

            Item {
                id: overviewPage
                objectName: "osintOverviewPage"

                Row {
                    id: metricRow
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    height: 78
                    spacing: 8

                    Repeater {
                        model: [
                            {key: "aircraft", label: "AIRCRAFT", color: root.signalBlue},
                            {key: "earthquakes", label: "EARTHQUAKES", color: root.ledgerGold},
                            {key: "fires", label: "FIRES", color: root.signalRed},
                            {key: "satellites", label: "SATELLITES", color: root.signalViolet},
                            {key: "news", label: "NEWS", color: root.text}
                        ]
                        delegate: TmogCard {
                            required property var modelData
                            width: (metricRow.width - 32) / 5
                            height: metricRow.height
                            leftLegend: String(modelData.label)
                            borderColor: root.frameBorder
                            fill: root.panel
                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 5
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 5
                                text: root.number(root.count(String(modelData.key)))
                                color: modelData.color
                                font.family: "monospace"
                                font.pixelSize: 22
                            }
                            Text {
                                anchors.right: parent.right
                                anchors.rightMargin: 5
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 7
                                text: root.statusText()
                                color: root.muted
                                font.family: "monospace"
                                font.pixelSize: 9
                            }
                        }
                    }
                }

                Row {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: metricRow.bottom
                    anchors.topMargin: 10
                    anchors.bottom: parent.bottom
                    spacing: 10

                    TmogCard {
                        id: overviewMapCard
                        width: parent.width * 0.66
                        height: parent.height
                        leftLegend: "MAP · GLOBAL POINTS"
                        rightLegend: String(root.payload.focus && root.payload.focus.label || "GLOBAL")
                        borderColor: root.frameBorder
                        fill: root.panel
                        Item {
                            id: overviewGlobeSlot
                            anchors.fill: parent
                            OsintGlobe {
                                id: overviewGlobe
                                parent: root.page === "MAP" ? mapGlobeSlot : overviewGlobeSlot
                                anchors.fill: parent
                                visible: root.page === "OVERVIEW" || root.page === "MAP"
                                points: root.mapPoints()
                                muted: root.muted
                                signalBlue: root.signalBlue
                                ledgerGold: root.ledgerGold
                                panel: root.panel
                            }
                        }
                    }

                    TmogCard {
                        id: intelCard
                        width: parent.width * 0.34 - 10
                        height: parent.height
                        leftLegend: "INTELLIGENCE STREAM"
                        rightLegend: root.navMode ? "NAV" : (root.selectedEvent ? "DETAIL" : "SELECT")
                        borderColor: root.frameBorder
                        fill: root.panel
                        ListView {
                            id: overviewNewsList
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.bottom: detailPane.top
                            clip: true
                            spacing: 4
                            model: root.streamRows()
                            delegate: Item {
                                required property var modelData
                                width: overviewNewsList.width
                                height: 50
                                Rectangle {
                                    anchors.fill: parent
                                    color: root.selectedEvent && root.selectedEvent.id === modelData.id
                                        ? "#2a323c"
                                        : (newsHit.containsMouse ? "#20262d" : "transparent")
                                    border.color: "#2c3035"
                                    border.width: 1
                                }
                                Text {
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.leftMargin: 7
                                    anchors.rightMargin: 7
                                    anchors.topMargin: 5
                                    text: String(modelData.title || "UNTITLED")
                                    color: root.text
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                    elide: Text.ElideRight
                                }
                                Text {
                                    anchors.left: parent.left
                                    anchors.bottom: parent.bottom
                                    anchors.leftMargin: 7
                                    anchors.bottomMargin: 5
                                    text: String(modelData.kind || "news").toUpperCase()
                                        + " · "
                                        + (modelData.lat !== undefined ? "MAP PIN" : "NO GEO")
                                        + " · "
                                        + root.shortTime(modelData.time || modelData.published)
                                    color: Number(modelData.risk_score || 0) >= 7 ? root.signalRed : root.muted
                                    font.family: "monospace"
                                    font.pixelSize: 9
                                }
                                MouseArea {
                                    id: newsHit
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.focusGlobe(modelData)
                                }
                            }
                        }
                        Item {
                            id: detailPane
                            objectName: "osintSharedPane"
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: (root.navMode || root.selectedEvent)
                                ? Math.min(root.navMode ? 360 : 248, parent.height * 0.72)
                                : 36
                            Rectangle {
                                anchors.fill: parent
                                color: root.navMode ? "#1a1a1a" : "#181818"
                                border.color: "#4a4a4a"
                                border.width: 1
                            }
                            Text {
                                visible: !root.navMode && !root.selectedEvent
                                anchors.centerIn: parent
                                text: "SELECT A ROW  ·  OR NAV"
                                color: root.muted
                                font.family: "monospace"
                                font.pixelSize: 9
                            }
                            Column {
                                visible: root.navMode
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 5
                                Text {
                                    width: parent.width
                                    text: root.navMeta !== ""
                                        ? root.navMeta
                                        : "TYPE A PLACE + ENTER · FIRST START · LAST END · DRAG TO REORDER"
                                    color: root.muted
                                    wrapMode: Text.WordWrap
                                    font.family: "monospace"
                                    font.pixelSize: 9
                                }
                                ListView {
                                    id: navPlaceList
                                    width: parent.width
                                    height: Math.min(25 * Math.max(root.navPlaces.length, 0), 175)
                                    clip: true
                                    visible: root.navPlaces.length > 0
                                    model: root.navPlaces
                                    spacing: 3
                                    delegate: Item {
                                        id: placeRow
                                        required property string modelData
                                        required property int index
                                        width: navPlaceList.width
                                        height: 22
                                        z: placeDrag.drag.active ? 2 : 0
                                        Rectangle {
                                            id: placeChip
                                            width: parent.width
                                            height: 22
                                            color: placeDrag.drag.active ? "#2a2a2a" : "#202020"
                                            border.color: "#5a5a5a"
                                            border.width: 1
                                            Text {
                                                anchors.left: parent.left
                                                anchors.leftMargin: 8
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: "⋮⋮  " + placeRow.modelData
                                                color: root.text
                                                font.family: "monospace"
                                                font.pixelSize: 10
                                            }
                                            Text {
                                                anchors.right: parent.right
                                                anchors.rightMargin: 8
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: "✕"
                                                color: root.muted
                                                font.family: "monospace"
                                                font.pixelSize: 10
                                            }
                                            MouseArea {
                                                id: placeDrag
                                                anchors.fill: parent
                                                anchors.rightMargin: 22
                                                hoverEnabled: true
                                                cursorShape: Qt.OpenHandCursor
                                                drag.target: placeChip
                                                drag.axis: Drag.YAxis
                                                onReleased: {
                                                    var localY = placeChip.mapToItem(navPlaceList.contentItem, 0, placeChip.height / 2).y
                                                    var target = Math.round(localY / 25)
                                                    if (target < 0)
                                                        target = 0
                                                    if (target > root.navPlaces.length - 1)
                                                        target = root.navPlaces.length - 1
                                                    root.moveNavPlace(placeRow.index, target)
                                                    placeChip.x = 0
                                                    placeChip.y = 0
                                                }
                                            }
                                            MouseArea {
                                                anchors.right: parent.right
                                                width: 22
                                                height: parent.height
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: root.removeNavPlace(placeRow.index)
                                            }
                                        }
                                    }
                                }
                                GgField {
                                    id: navDraftField
                                    width: parent.width
                                    placeholderText: root.navPlaces.length < 1
                                        ? "START  (enter)"
                                        : (root.navPlaces.length === 1 ? "END  (enter)" : "NEXT PLACE  (enter · goes between)")
                                    text: root.navDraft
                                    onTextChanged: root.navDraft = text
                                    Keys.onReturnPressed: root.commitNavPlace()
                                    Keys.onEnterPressed: root.commitNavPlace()
                                }
                                Row {
                                    spacing: 6
                                    Repeater {
                                        model: [
                                            {label: "GPS", action: "gps"},
                                            {label: "ADD", action: "stop"},
                                            {label: "ROUTE", action: "route"},
                                            {label: "CLEAR", action: "clear"}
                                        ]
                                        delegate: Rectangle {
                                            required property var modelData
                                            width: navBtnLabel.implicitWidth + 12
                                            height: 22
                                            color: navBtnHit.containsMouse ? "#2a2a2a" : "#202020"
                                            border.color: navBtnHit.containsMouse ? "#8a8a8a" : "#5a5a5a"
                                            border.width: 1
                                            Text {
                                                id: navBtnLabel
                                                anchors.centerIn: parent
                                                text: modelData.label
                                                color: root.text
                                                font.family: "monospace"
                                                font.pixelSize: 9
                                            }
                                            MouseArea {
                                                id: navBtnHit
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: {
                                                    if (modelData.action === "gps") {
                                                        if (root.navPlaces.length === 0
                                                                || String(root.navPlaces[0]).toLowerCase() !== "gps")
                                                            root.navPlaces = ["GPS"].concat(root.navPlaces)
                                                        overviewGlobe.locateGps()
                                                    } else if (modelData.action === "stop") {
                                                        root.commitNavPlace()
                                                    } else if (modelData.action === "route") {
                                                        root.runNavRoute()
                                                    } else {
                                                        root.clearNav()
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            Column {
                                visible: !root.navMode && root.selectedEvent
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 5
                                Text {
                                    width: parent.width
                                    text: root.selectedEvent ? String(root.selectedEvent.title || "") : ""
                                    color: root.ink
                                    wrapMode: Text.WordWrap
                                    font.family: "monospace"
                                    font.pixelSize: 11
                                }
                                Text {
                                    width: parent.width
                                    text: root.selectedEvent
                                        ? String(root.selectedEvent.source || "")
                                            + " · "
                                            + String(root.selectedEvent.kind || "")
                                            + (root.selectedEvent.lat !== undefined
                                                ? " · " + root.number(root.selectedEvent.lat, 2)
                                                    + ", " + root.number(root.selectedEvent.lon, 2)
                                                : "")
                                        : ""
                                    color: root.ledgerGold
                                    font.family: "monospace"
                                    font.pixelSize: 9
                                }
                                Text {
                                    width: parent.width
                                    text: root.selectedEvent ? String(root.selectedEvent.summary || "") : ""
                                    color: root.text
                                    wrapMode: Text.WordWrap
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                }
                                Text {
                                    width: parent.width
                                    text: root.selectedEvent && root.selectedEvent.url
                                        ? "CLICK COPIES SOURCE URL"
                                        : ""
                                    color: root.muted
                                    font.family: "monospace"
                                    font.pixelSize: 9
                                }
                            }
                            MouseArea {
                                visible: !root.navMode && root.selectedEvent
                                anchors.fill: parent
                                onClicked: {
                                    if (root.selectedEvent && root.selectedEvent.url)
                                        root.copyText(root.selectedEvent.url)
                                }
                            }
                        }
                    }
                }
            }

            Item {
                id: mapPage
                objectName: "osintMapPage"
                Row {
                    anchors.fill: parent
                    spacing: 10
                    TmogCard {
                        width: parent.width * 0.75
                        height: parent.height
                        leftLegend: "EVENT MAP"
                        rightLegend: root.number(root.mapPoints().length) + " POINTS"
                        borderColor: root.frameBorder
                        fill: root.panel
                        Item {
                            id: mapGlobeSlot
                            anchors.fill: parent
                        }
                        Item {
                            anchors.fill: parent
                            Row {
                                anchors.left: parent.left
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 10
                                anchors.leftMargin: 10
                                spacing: 12
                                Repeater {
                                    model: [
                                        {label: "AIRCRAFT", color: root.signalBlue},
                                        {label: "SEISMIC", color: root.ledgerGold},
                                        {label: "FIRES", color: root.signalRed},
                                        {label: "WATCHLIST", color: root.signalViolet},
                                        {label: "ALPR PINS", color: "#6ec4d8"}
                                    ]
                                    delegate: Row {
                                        required property var modelData
                                        spacing: 5
                                        Rectangle {
                                            width: 7
                                            height: 7
                                            radius: 4
                                            anchors.verticalCenter: parent.verticalCenter
                                            color: modelData.color
                                        }
                                        Text {
                                            text: modelData.label
                                            color: root.muted
                                            font.family: "monospace"
                                            font.pixelSize: 9
                                        }
                                    }
                                }
                            }
                        }
                    }
                    TmogCard {
                        width: parent.width * 0.25 - 10
                        height: parent.height
                        leftLegend: "LAYER COUNTS"
                        borderColor: root.frameBorder
                        fill: root.panel
                        Column {
                            anchors.fill: parent
                            spacing: 8
                            Repeater {
                                model: [
                                    {key: "aircraft", label: "AIRCRAFT"},
                                    {key: "earthquakes", label: "SEISMIC"},
                                    {key: "fires", label: "FIRES"},
                                    {key: "satellites", label: "SATELLITES"},
                                    {key: "news", label: "NEWS"},
                                    {key: "conflicts", label: "WATCHLIST"},
                                    {key: "cameras", label: "ALPR PINS"}
                                ]
                                delegate: Item {
                                    required property var modelData
                                    width: parent.width
                                    height: 23
                                    Text {
                                        anchors.left: parent.left
                                        text: modelData.label
                                        color: root.muted
                                        font.family: "monospace"
                                        font.pixelSize: 10
                                    }
                                    Text {
                                        anchors.right: parent.right
                                        text: root.number(root.count(modelData.key))
                                        color: root.ink
                                        font.family: "monospace"
                                        font.pixelSize: 11
                                    }
                                    Rectangle {
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.bottom: parent.bottom
                                        height: 1
                                        color: "#2c3035"
                                    }
                                }
                            }
                            Text {
                                width: parent.width
                                text: "MapLibre 3D globe with OpenFreeMap dark tiles, local land fallback, and bounded public feed points."
                                color: root.muted
                                wrapMode: Text.WordWrap
                                font.family: "monospace"
                                font.pixelSize: 9
                            }
                        }
                    }
                }
            }

            Item {
                id: flightsPage
                objectName: "osintFlightsPage"
                Column {
                    anchors.fill: parent
                    spacing: 10
                    Row {
                        width: parent.width
                        height: 100
                        spacing: 10
                        TmogCard {
                            width: parent.width * 0.33 - 7
                            height: parent.height
                            leftLegend: "AIRCRAFT"
                            borderColor: root.frameBorder
                            fill: root.panel
                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 6
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 7
                                text: root.number(root.count("aircraft"))
                                color: root.signalBlue
                                font.family: "monospace"
                                font.pixelSize: 25
                            }
                        }
                        TmogCard {
                            width: parent.width * 0.67 - 3
                            height: parent.height
                            leftLegend: "FLIGHT SNAPSHOT"
                            rightLegend: String(root.payload.focus && root.payload.focus.label || "REGION")
                            borderColor: root.frameBorder
                            fill: root.panel
                            TmogSpark {
                                anchors.fill: parent
                                values: root.history("aircraft")
                                stroke: root.signalBlue
                                fill: "#192631"
                                yMax: 0
                            }
                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 6
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 5
                                text: "OPEN SKY · POSITION SNAPSHOT"
                                color: root.muted
                                font.family: "monospace"
                                font.pixelSize: 9
                            }
                        }
                    }
                    TmogCard {
                        width: parent.width
                        height: parent.height - 110
                        leftLegend: "AIRCRAFT TABLE"
                        rightLegend: "COPY CALLSIGN / ID"
                        borderColor: root.frameBorder
                        fill: root.panel
                        ListView {
                            id: aircraftList
                            anchors.fill: parent
                            clip: true
                            model: root.rows("aircraft")
                            delegate: Item {
                                required property var modelData
                                required property int index
                                width: aircraftList.width
                                height: 27
                                Rectangle {
                                    anchors.fill: parent
                                    color: rowHit.containsMouse ? "#20262d" : (index % 2 ? "#171717" : "transparent")
                                }
                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 6
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: parent.width * 0.23
                                    text: String(modelData.callsign || modelData.id || "UNKNOWN")
                                    color: root.ink
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                    elide: Text.ElideRight
                                }
                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: parent.width * 0.25
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: parent.width * 0.21
                                    text: String(modelData.country || "—")
                                    color: root.text
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                    elide: Text.ElideRight
                                }
                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: parent.width * 0.48
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: parent.width * 0.18
                                    text: root.number(modelData.lat, 2) + " / " + root.number(modelData.lon, 2)
                                    color: root.signalBlue
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                }
                                Text {
                                    anchors.right: parent.right
                                    anchors.rightMargin: 8
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: root.number(modelData.alt_m) + "m"
                                    color: root.muted
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                }
                                MouseArea {
                                    id: rowHit
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.copyText(modelData.callsign || modelData.id)
                                }
                            }
                        }
                    }
                }
            }

            Item {
                id: seismicPage
                objectName: "osintSeismicPage"
                Row {
                    anchors.fill: parent
                    spacing: 10
                    TmogCard {
                        width: parent.width * 0.36
                        height: parent.height
                        leftLegend: "SEISMIC ACTIVITY"
                        rightLegend: "M2.5+ · 24H"
                        borderColor: root.frameBorder
                        fill: root.panel
                        TmogSpark {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.bottom: summaryText.top
                            values: root.history("earthquakes")
                            stroke: root.ledgerGold
                            fill: "#2b2418"
                        }
                        Text {
                            id: summaryText
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 8
                            text: root.number(root.count("earthquakes")) + " events in USGS feed"
                            color: root.text
                            font.family: "monospace"
                            font.pixelSize: 10
                        }
                    }
                    TmogCard {
                        width: parent.width * 0.64 - 10
                        height: parent.height
                        leftLegend: "EARTHQUAKES"
                        rightLegend: "USGS"
                        borderColor: root.frameBorder
                        fill: root.panel
                        ListView {
                            id: quakeList
                            anchors.fill: parent
                            clip: true
                            model: root.rows("earthquakes")
                            delegate: Item {
                                required property var modelData
                                width: quakeList.width
                                height: 32
                                Rectangle {
                                    anchors.fill: parent
                                    color: quakeHit.containsMouse ? "#20262d" : "transparent"
                                    border.color: "#2c3035"
                                    border.width: 1
                                }
                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 7
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "M" + root.number(modelData.magnitude, 1)
                                    color: root.ledgerGold
                                    font.family: "monospace"
                                    font.pixelSize: 12
                                }
                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 52
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: String(modelData.place || "UNKNOWN LOCATION")
                                    color: root.text
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                    elide: Text.ElideRight
                                }
                                Text {
                                    anchors.right: parent.right
                                    anchors.rightMargin: 7
                                    anchors.bottom: parent.bottom
                                    anchors.bottomMargin: 3
                                    text: root.number(modelData.depth_km, 0) + "km · " + root.shortTime(modelData.time)
                                    color: root.muted
                                    font.family: "monospace"
                                    font.pixelSize: 8
                                }
                                MouseArea {
                                    id: quakeHit
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.copyText(modelData.url)
                                }
                            }
                        }
                    }
                }
            }

            Item {
                id: firesPage
                objectName: "osintFiresPage"
                Row {
                    anchors.fill: parent
                    spacing: 10
                    TmogCard {
                        width: parent.width * 0.34
                        height: parent.height
                        leftLegend: "FIRES / EVENTS"
                        rightLegend: "NASA EONET"
                        borderColor: root.frameBorder
                        fill: root.panel
                        Column {
                            anchors.fill: parent
                            spacing: 10
                            Text {
                                text: root.number(root.count("fires"))
                                color: root.signalRed
                                font.family: "monospace"
                                font.pixelSize: 28
                            }
                            TmogMeter {
                                width: parent.width
                                ratio: Math.min(1, root.count("fires") / 100)
                                segments: 22
                                onColor: root.signalRed
                            }
                            Text {
                                width: parent.width
                                text: "Open EONET wildfire and volcano events with coordinates."
                                color: root.text
                                wrapMode: Text.WordWrap
                                font.family: "monospace"
                                font.pixelSize: 10
                            }
                        }
                    }
                    TmogCard {
                        width: parent.width * 0.66 - 10
                        height: parent.height
                        leftLegend: "ACTIVE EVENTS"
                        borderColor: root.frameBorder
                        fill: root.panel
                        ListView {
                            id: firesList
                            anchors.fill: parent
                            clip: true
                            model: root.rows("fires")
                            delegate: Item {
                                required property var modelData
                                width: firesList.width
                                height: 38
                                Rectangle {
                                    anchors.fill: parent
                                    color: fireHit.containsMouse ? "#20262d" : "transparent"
                                    border.color: "#2c3035"
                                    border.width: 1
                                }
                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 7
                                    anchors.top: parent.top
                                    anchors.topMargin: 5
                                    anchors.right: parent.right
                                    text: String(modelData.title || "EVENT")
                                    color: root.text
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                    elide: Text.ElideRight
                                }
                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 7
                                    anchors.bottom: parent.bottom
                                    anchors.bottomMargin: 5
                                    text: String(modelData.category || "EVENT") + " · " + root.number(modelData.lat, 2) + "," + root.number(modelData.lon, 2)
                                    color: root.signalRed
                                    font.family: "monospace"
                                    font.pixelSize: 9
                                }
                                MouseArea {
                                    id: fireHit
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.copyText(modelData.url)
                                }
                            }
                        }
                    }
                }
            }

            Item {
                id: spacePage
                objectName: "osintSpacePage"
                Column {
                    anchors.fill: parent
                    spacing: 10
                    Row {
                        width: parent.width
                        height: 112
                        spacing: 10
                        TmogCard {
                            width: parent.width * 0.34
                            height: parent.height
                            leftLegend: "SOLAR WEATHER"
                            rightLegend: "NOAA SWPC"
                            borderColor: root.frameBorder
                            fill: root.panel
                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 7
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 7
                                text: "KP " + root.number(root.payload.solar && root.payload.solar.kp_index, 1)
                                color: root.ledgerGold
                                font.family: "monospace"
                                font.pixelSize: 22
                            }
                            Text {
                                anchors.right: parent.right
                                anchors.rightMargin: 7
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 10
                                text: String(root.payload.solar && root.payload.solar.storm_level || "UNKNOWN")
                                color: root.text
                                font.family: "monospace"
                                font.pixelSize: 10
                            }
                        }
                        TmogCard {
                            width: parent.width * 0.66 - 10
                            height: parent.height
                            leftLegend: "STATION CATALOG"
                            rightLegend: "CELESTRAK"
                            borderColor: root.frameBorder
                            fill: root.panel
                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 7
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 8
                                text: root.number(root.count("satellites")) + " tracked station objects"
                                color: root.signalViolet
                                font.family: "monospace"
                                font.pixelSize: 15
                            }
                        }
                    }
                    TmogCard {
                        width: parent.width
                        height: parent.height - 122
                        leftLegend: "SATELLITES"
                        rightLegend: "NORAD / STATIONS"
                        borderColor: root.frameBorder
                        fill: root.panel
                        ListView {
                            id: satelliteList
                            anchors.fill: parent
                            clip: true
                            model: root.rows("satellites")
                            delegate: Item {
                                required property var modelData
                                required property int index
                                width: satelliteList.width
                                height: 26
                                Rectangle {
                                    anchors.fill: parent
                                    color: satelliteHit.containsMouse ? "#20262d" : (index % 2 ? "#171717" : "transparent")
                                }
                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 7
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: parent.width * 0.55
                                    text: String(modelData.name || "UNKNOWN")
                                    color: root.text
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                    elide: Text.ElideRight
                                }
                                Text {
                                    anchors.right: parent.right
                                    anchors.rightMargin: 7
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "NORAD " + String(modelData.norad || "—") + " · INC " + root.number(modelData.inclination, 1) + "°"
                                    color: root.signalViolet
                                    font.family: "monospace"
                                    font.pixelSize: 9
                                }
                                MouseArea {
                                    id: satelliteHit
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.copyText(modelData.name)
                                }
                            }
                        }
                    }
                }
            }

            Item {
                id: newsPage
                objectName: "osintNewsPage"
                TmogCard {
                    anchors.fill: parent
                    leftLegend: "WORLD NEWS"
                    rightLegend: "BBC WORLD · RISK HEURISTIC"
                    borderColor: root.frameBorder
                    fill: root.panel
                    ListView {
                        id: newsList
                        anchors.fill: parent
                        clip: true
                        spacing: 5
                        model: root.rows("news")
                        delegate: Item {
                            required property var modelData
                            width: newsList.width
                            height: 58
                            Rectangle {
                                anchors.fill: parent
                                color: newsPageHit.containsMouse ? "#20262d" : "#171717"
                                border.color: "#2c3035"
                                border.width: 1
                            }
                            Text {
                                anchors.left: parent.left
                                anchors.right: riskLabel.left
                                anchors.top: parent.top
                                anchors.leftMargin: 8
                                anchors.rightMargin: 8
                                anchors.topMargin: 7
                                text: String(modelData.title || "UNTITLED")
                                color: root.ink
                                font.family: "monospace"
                                font.pixelSize: 11
                                elide: Text.ElideRight
                            }
                            Text {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                anchors.leftMargin: 8
                                anchors.rightMargin: 8
                                anchors.bottomMargin: 7
                                text: String(modelData.source || "SOURCE") + " · " + root.shortTime(modelData.published)
                                color: root.muted
                                font.family: "monospace"
                                font.pixelSize: 9
                                elide: Text.ElideRight
                            }
                            Text {
                                id: riskLabel
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.rightMargin: 8
                                anchors.topMargin: 7
                                text: "R" + String(modelData.risk_score || 1)
                                color: Number(modelData.risk_score || 0) >= 7 ? root.signalRed : root.ledgerGold
                                font.family: "monospace"
                                font.pixelSize: 10
                            }
                            MouseArea {
                                id: newsPageHit
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.copyText(modelData.url)
                            }
                        }
                    }
                }
            }

            Item {
                id: conflictPage
                objectName: "osintConflictPage"
                Row {
                    anchors.fill: parent
                    spacing: 10
                    TmogCard {
                        width: parent.width * 0.48
                        height: parent.height
                        leftLegend: "REFERENCE WATCHLIST"
                        rightLegend: "NOT LIVE VERIFIED"
                        borderColor: root.frameBorder
                        fill: root.panel
                        ListView {
                            id: conflictList
                            anchors.fill: parent
                            clip: true
                            model: root.rows("conflicts")
                            delegate: Item {
                                required property var modelData
                                width: conflictList.width
                                height: 29
                                Rectangle {
                                    anchors.fill: parent
                                    color: conflictHit.containsMouse ? "#20262d" : "transparent"
                                }
                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 7
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 7
                                    height: 7
                                    radius: 4
                                    color: Number(modelData.severity || 0) >= 4 ? root.signalRed : root.signalViolet
                                }
                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 22
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: String(modelData.label || "ZONE")
                                    color: root.text
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                }
                                Text {
                                    anchors.right: parent.right
                                    anchors.rightMargin: 8
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "S" + String(modelData.severity || "—")
                                    color: root.muted
                                    font.family: "monospace"
                                    font.pixelSize: 9
                                }
                                MouseArea {
                                    id: conflictHit
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.copyText(modelData.label)
                                }
                            }
                        }
                    }
                    TmogCard {
                        width: parent.width * 0.52 - 10
                        height: parent.height
                        leftLegend: "INTERPRETATION"
                        borderColor: root.frameBorder
                        fill: root.panel
                        Column {
                            anchors.fill: parent
                            spacing: 14
                            Text {
                                width: parent.width
                                text: "OSIRIS REFERENCE LAYER"
                                color: root.signalViolet
                                font.family: "monospace"
                                font.pixelSize: 15
                            }
                            Text {
                                width: parent.width
                                text: "The locations are a stable orientation layer for the map. They are not presented as a live incident feed and do not replace source verification."
                                color: root.text
                                wrapMode: Text.WordWrap
                                font.family: "monospace"
                                font.pixelSize: 11
                            }
                            TmogRail {
                                leftLegend: "SOURCE"
                                rightLegend: "OSIRIS / README"
                            }
                            Text {
                                width: parent.width
                                text: "Use NEWS, USGS, NASA and the source panel for current evidence."
                                color: root.muted
                                wrapMode: Text.WordWrap
                                font.family: "monospace"
                                font.pixelSize: 10
                            }
                        }
                    }
                }
            }

            Item {
                id: camerasPage
                objectName: "osintCamerasPage"
                Column {
                    anchors.fill: parent
                    spacing: 10
                    TmogCard {
                        width: parent.width
                        height: 78
                        leftLegend: "ALPR LOCATION PINS"
                        rightLegend: "OSM / DEFLOCK SAMPLE"
                        borderColor: root.frameBorder
                        fill: root.panel
                        Text {
                            anchors.left: parent.left
                            anchors.leftMargin: 6
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 8
                            text: root.number(root.count("cameras")) + " sampled pins · locations only · no live video"
                            color: "#6ec4d8"
                            font.family: "monospace"
                            font.pixelSize: 13
                        }
                    }
                    TmogCard {
                        width: parent.width
                        height: parent.height - 88
                        leftLegend: "PUBLIC OSM PINS"
                        rightLegend: "COPY OSM URL"
                        borderColor: root.frameBorder
                        fill: root.panel
                        ListView {
                            id: cameraList
                            anchors.fill: parent
                            clip: true
                            model: root.rows("cameras")
                            delegate: Item {
                                required property var modelData
                                required property int index
                                width: cameraList.width
                                height: 27
                                Rectangle {
                                    anchors.fill: parent
                                    color: camHit.containsMouse ? "#20262d" : (index % 2 ? "#171717" : "transparent")
                                }
                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 6
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: parent.width * 0.38
                                    text: String(modelData.brand || modelData.label || "ALPR")
                                    color: root.ink
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                    elide: Text.ElideRight
                                }
                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: parent.width * 0.42
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: root.number(modelData.lat, 2) + " / " + root.number(modelData.lon, 2)
                                    color: "#6ec4d8"
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                }
                                Text {
                                    anchors.right: parent.right
                                    anchors.rightMargin: 8
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: String(modelData.zone || "PIN")
                                    color: root.muted
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                }
                                MouseArea {
                                    id: camHit
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.copyText(modelData.url)
                                }
                            }
                        }
                    }
                }
            }

            Item {
                id: sourcesPage
                objectName: "osintSourcesPage"
                TmogCard {
                    anchors.fill: parent
                    leftLegend: "SOURCE HEALTH"
                    rightLegend: String(root.payload.generated_at || "NOT FETCHED")
                    borderColor: root.frameBorder
                    fill: root.panel
                    Column {
                        anchors.fill: parent
                        spacing: 5
                        Repeater {
                            model: root.rows("sources")
                            delegate: Item {
                                required property var modelData
                                width: parent.width
                                height: 44
                                Rectangle {
                                    anchors.fill: parent
                                    color: sourceHit.containsMouse ? "#20262d" : "#171717"
                                    border.color: "#2c3035"
                                    border.width: 1
                                }
                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 8
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 7
                                    height: 7
                                    radius: 4
                                    color: String(modelData.status || "IDLE") === "OK"
                                        ? root.ledgerGreen
                                        : (String(modelData.status || "") === "REFERENCE"
                                            ? root.signalViolet
                                            : (String(modelData.status || "") === "ERROR" ? root.signalRed : root.muted))
                                }
                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 24
                                    anchors.top: parent.top
                                    anchors.topMargin: 6
                                    text: String(modelData.label || "SOURCE") + " · " + String(modelData.provider || "")
                                    color: root.ink
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                }
                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 24
                                    anchors.bottom: parent.bottom
                                    anchors.bottomMargin: 6
                                    text: String(modelData.status || "IDLE") + " · " + String(modelData.count || 0) + " rows"
                                    color: root.muted
                                    font.family: "monospace"
                                    font.pixelSize: 9
                                }
                                Text {
                                    anchors.right: parent.right
                                    anchors.rightMargin: 8
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "COPY URL"
                                    color: root.ledgerGold
                                    font.family: "monospace"
                                    font.pixelSize: 9
                                }
                                MouseArea {
                                    id: sourceHit
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.copyText(modelData.url)
                                }
                            }
                        }
                    }
                }
            }

            Item {
                id: reconPage
                objectName: "osintReconPage"
                Row {
                    anchors.fill: parent
                    spacing: 10
                    TmogCard {
                        width: parent.width * 0.55
                        height: parent.height
                        leftLegend: "RECON BOUNDARY"
                        rightLegend: "SAFE MODE"
                        borderColor: root.frameBorder
                        fill: root.panel
                        Column {
                            anchors.fill: parent
                            spacing: 14
                            Text {
                                width: parent.width
                                text: "PUBLIC READ-ONLY RECON"
                                color: root.ledgerGreen
                                font.family: "monospace"
                                font.pixelSize: 16
                            }
                            Text {
                                width: parent.width
                                text: "The native surface implements the observation side of OSIRIS: fixed public feeds, source health, event mapping and copyable references."
                                color: root.text
                                wrapMode: Text.WordWrap
                                font.family: "monospace"
                                font.pixelSize: 11
                            }
                            TmogRail {
                                leftLegend: "ENABLED"
                                rightLegend: "PUBLIC FEEDS"
                            }
                            Repeater {
                                model: root.payload.recon && root.payload.recon.available || []
                                delegate: Text {
                                    required property string modelData
                                    width: parent.width
                                    text: "✓  " + modelData
                                    color: root.ledgerGreen
                                    font.family: "monospace"
                                    font.pixelSize: 10
                                }
                            }
                        }
                    }
                    TmogCard {
                        width: parent.width * 0.45 - 10
                        height: parent.height
                        leftLegend: "NOT ENABLED"
                        rightLegend: "AUTHORIZATION REQUIRED"
                        borderColor: root.frameBorder
                        fill: root.panel
                        Column {
                            anchors.fill: parent
                            spacing: 10
                            Repeater {
                                model: root.payload.recon && root.payload.recon.not_enabled || []
                                delegate: Item {
                                    required property string modelData
                                    width: parent.width
                                    height: 27
                                    Text {
                                        anchors.left: parent.left
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "—  " + modelData
                                        color: root.muted
                                        font.family: "monospace"
                                        font.pixelSize: 10
                                    }
                                    Rectangle {
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.bottom: parent.bottom
                                        height: 1
                                        color: "#2c3035"
                                    }
                                }
                            }
                            Text {
                                width: parent.width
                                text: "No user-supplied target, URL or credential is accepted by this surface."
                                color: root.ledgerGold
                                wrapMode: Text.WordWrap
                                font.family: "monospace"
                                font.pixelSize: 10
                            }
                        }
                    }
                }
            }
        }
    }
}
