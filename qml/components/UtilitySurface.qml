pragma ComponentBehavior: Bound

import QtQuick

Item {
    id: root

    objectName: "utilitySurface"

    property color accentColor: "#8a8a8a"
    property color frameBorder: "#6a6a6a"
    property int frameRadius: 4
    property int surfaceHeight: 112
    property var surfaceHost: null
    property string statusJson: "{}"
    signal surfaceRequested(string kind)
    readonly property string capabilityState: "REAL_LOCAL_MEDIA"

    implicitHeight: root.surfaceHeight

    readonly property var status: {
        try {
            return JSON.parse(root.statusJson || "{}")
        } catch (err) {
            return {}
        }
    }

    readonly property string mode: String(root.status.mode || "MUSIC")
    readonly property bool playing: root.status.playing === true
    readonly property bool paused: root.status.paused === true
    readonly property string nowTitle: String((root.status.now || {}).title || "")
    readonly property string nowArtist: String((root.status.now || {}).artist || "")
    readonly property int volume: Number(root.status.volume || 70)
    readonly property var spectrum: {
        var rows = root.status.spectrum
        if (rows && rows.length !== undefined)
            return rows
        return []
    }
    readonly property var eqBands: {
        var rows = root.status.eq_bands
        if (rows && rows.length !== undefined)
            return rows
        return [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    }
    readonly property real duration: Number(root.status.duration || 0)
    readonly property real position: Number(root.status.position || 0)
    readonly property bool seekable: root.duration > 0.5
    readonly property real progress: {
        if (!root.seekable)
            return 0
        return Math.max(0, Math.min(1, root.position / root.duration))
    }
    property string meterClock: "00:00"
    property string meterLength: "00:00"
    readonly property int spectrumBars: 120
    readonly property int spectrumSegs: 18
    readonly property int peakHoldTicks: 5
    readonly property bool liveMeters: root.playing || root.paused
    readonly property bool hasSpectrum: root.spectrum.length > 0

    function pullLiveRaw() {
        if (!root.surfaceHost)
            return ""
        var raw = ""
        if (root.surfaceHost.mediaLiveStatus)
            raw = root.surfaceHost.mediaLiveStatus()
        if (!raw || raw === "{}")
            return ""
        return raw
    }

    function chromeBlob(parsed) {
        return JSON.stringify({
            "mode": String(parsed.mode || "MUSIC"),
            "playing": parsed.playing === true,
            "paused": parsed.paused === true,
            "now": parsed.now || {},
            "volume": Number(parsed.volume || 0),
            "duration": Number(parsed.duration || 0),
            "eq_preset": String(parsed.eq_preset || "Flat"),
            "eq_bands": parsed.eq_bands || [],
            "player": String(parsed.player || ""),
            "shuffle": parsed.shuffle === true,
            "repeat": String(parsed.repeat || "off")
        })
    }

    function applyChrome(parsed) {
        var blob = root.chromeBlob(parsed)
        if (blob !== root.statusJson)
            root.statusJson = blob
    }

    function refresh() {
        var raw = root.pullLiveRaw()
        if (!raw)
            return
        root.refreshMeters(raw)
    }

    function refreshMeters(raw) {
        var text = raw || root.pullLiveRaw()
        if (!text)
            return
        var parsed
        try {
            parsed = JSON.parse(text)
        } catch (err) {
            return
        }
        root.applyChrome(parsed)
        var spec = parsed.spectrum
        if (!spec || spec.length === undefined)
            spec = []
        if (spectrumCanvas)
            spectrumCanvas.levels = spec
        var clock = String(parsed.clock || "00:00")
        var length = String(parsed.length || "00:00")
        if (clock !== root.meterClock)
            root.meterClock = clock
        if (length !== root.meterLength)
            root.meterLength = length
        if (spectrumCanvas)
            spectrumCanvas.requestPaint()
    }

    function setMode(mode) {
        if (!root.surfaceHost)
            return
        root.surfaceRequested("MEDIA")
        root.statusJson = root.surfaceHost.mediaSetMode(mode)
        if (mode === "FETCH" && root.surfaceHost.mediaStartFetch)
            root.statusJson = root.surfaceHost.mediaStartFetch()
        root.refresh()
    }

    function playPause() {
        if (!root.surfaceHost)
            return
        root.surfaceRequested("MEDIA")
        if (root.playing)
            root.statusJson = root.surfaceHost.mediaPause()
        else if (root.paused)
            root.statusJson = root.surfaceHost.mediaPause()
        else
            root.statusJson = root.surfaceHost.mediaSkip(0)
        root.refresh()
    }

    function stop() {
        if (!root.surfaceHost)
            return
        root.statusJson = root.surfaceHost.mediaStop()
        root.refresh()
    }

    function skip(delta) {
        if (!root.surfaceHost)
            return
        root.surfaceRequested("MEDIA")
        root.statusJson = root.surfaceHost.mediaSkip(delta)
        root.refresh()
    }

    function bumpVolume(delta) {
        if (!root.surfaceHost)
            return
        root.statusJson = root.surfaceHost.mediaSetVolume(root.volume + delta)
        root.refresh()
    }

    function cycleEq() {
        if (!root.surfaceHost || !root.surfaceHost.mediaSetEqPreset)
            return
        root.statusJson = root.surfaceHost.mediaSetEqPreset("cycle")
        root.refresh()
    }

    function flattenEq() {
        if (!root.surfaceHost || !root.surfaceHost.mediaSetEqPreset)
            return
        root.statusJson = root.surfaceHost.mediaSetEqPreset("Flat")
        root.refresh()
    }

    function setEqFromY(index, y, height) {
        if (!root.surfaceHost || !root.surfaceHost.mediaSetEqBand)
            return
        var span = Math.max(1, Number(height))
        var db = 12 - (Number(y) / span) * 24
        if (db > 12)
            db = 12
        if (db < -12)
            db = -12
        root.statusJson = root.surfaceHost.mediaSetEqBand(index, db)
        root.refresh()
    }

    function seekAt(x, width) {
        if (!root.surfaceHost || !root.surfaceHost.mediaSeek)
            return
        if (!root.seekable)
            return
        var frac = Math.max(0, Math.min(1, Number(x) / Math.max(1, Number(width))))
        root.statusJson = root.surfaceHost.mediaSeek(frac * root.duration)
        root.refresh()
    }

    function toolMark(name) {
        var tools = root.status.tools || {}
        var row = tools[name] || {}
        return name.toUpperCase() + (row.present ? " ON" : " OFF")
    }

    function bandAt(index) {
        var rows = spectrumCanvas ? spectrumCanvas.levels : root.spectrum
        if (!rows || rows.length === 0)
            return 0
        if (index < rows.length)
            return Number(rows[index] || 0)
        return 0
    }

    function ledColor(frac) {
        if (frac < 0.32)
            return "#4eb8b0"
        if (frac < 0.52)
            return "#7cc86a"
        if (frac < 0.72)
            return "#d4c84a"
        if (frac < 0.88)
            return "#e09040"
        return "#e05050"
    }

    function eqAt(index) {
        var rows = root.eqBands
        if (!rows || index >= rows.length)
            return 0
        return Number(rows[index] || 0)
    }

    Connections {
        target: root.surfaceHost
        ignoreUnknownSignals: true
        function onMediaStateChanged() {
            root.refresh()
        }
    }

    Timer {
        interval: 50
        running: root.liveMeters
        repeat: true
        onTriggered: root.refreshMeters()
    }

    Timer {
        interval: 400
        running: !root.liveMeters
        repeat: true
        onTriggered: root.refresh()
    }

    Component.onCompleted: root.refresh()

    Item {
        anchors.fill: parent

        Rectangle {
            anchors.fill: parent
            color: "#161616"
            border.color: root.frameBorder
            border.width: 1
            radius: root.frameRadius
        }

        Item {
            id: utilHeader
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.leftMargin: 10
            anchors.rightMargin: 10
            anchors.topMargin: 6
            height: 16

            Text {
                anchors.left: parent.left
                height: 16
                verticalAlignment: Text.AlignVCenter
                text: "MEDIA / UTILITIES"
                color: "#e6edf3"
                font.family: "monospace"
                font.pixelSize: 12
                font.bold: true
            }
            Text {
                anchors.right: parent.right
                height: 16
                verticalAlignment: Text.AlignVCenter
                text: root.playing ? "LIVE · " + root.mode : root.mode
                color: "#c8cdd4"
                font.family: "monospace"
                font.pixelSize: 12
            }
        }

        Item {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: utilHeader.bottom
            anchors.bottom: parent.bottom
            anchors.leftMargin: 10
            anchors.rightMargin: 10
            anchors.topMargin: 6
            anchors.bottomMargin: 8

            Row {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: timeline.top
                anchors.bottomMargin: 4
                spacing: 10

                Column {
                    width: 248
                    spacing: 4

                    Row {
                        objectName: "utilityModeRow"
                        spacing: 8

                        Repeater {
                            model: ["MUSIC", "RADIO", "TV", "GAME", "FETCH"]
                            delegate: Text {
                                required property string modelData
                                text: modelData
                                color: root.mode === modelData ? "#d8dee9" : "#a8b0b8"
                                font.family: "monospace"
                                font.pixelSize: 12
                                font.bold: root.mode === modelData
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.setMode(modelData)
                                }
                            }
                        }
                    }

                    Row {
                        objectName: "utilityTransport"
                        spacing: 10

                        Text {
                            text: "|<"
                            color: "#c8a97e"
                            font.family: "monospace"
                            font.pixelSize: 12
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.skip(-1)
                            }
                        }
                        Text {
                            text: root.playing ? "PAUSE" : "PLAY"
                            color: "#d8dee9"
                            font.family: "monospace"
                            font.pixelSize: 12
                            font.bold: true
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.playPause()
                            }
                        }
                        Text {
                            text: ">|"
                            color: "#c8a97e"
                            font.family: "monospace"
                            font.pixelSize: 12
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.skip(1)
                            }
                        }
                        Text {
                            text: "STOP"
                            color: "#c8cdd4"
                            font.family: "monospace"
                            font.pixelSize: 12
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.stop()
                            }
                        }
                        Text {
                            text: "VOL " + String(root.volume)
                            color: "#c8cdd4"
                            font.family: "monospace"
                            font.pixelSize: 12
                            MouseArea {
                                anchors.fill: parent
                                acceptedButtons: Qt.LeftButton | Qt.RightButton
                                cursorShape: Qt.PointingHandCursor
                                onClicked: function(event) {
                                    root.bumpVolume(event.button === Qt.RightButton ? -5 : 5)
                                }
                            }
                        }
                    }

                    Text {
                        objectName: "utilityNow"
                        width: parent.width
                        text: root.nowTitle.length > 0
                            ? root.nowTitle
                            : "NOW · idle"
                        color: root.playing ? "#d8dee9" : "#c8cdd4"
                        font.family: "monospace"
                        font.pixelSize: 12
                        font.bold: root.playing
                        elide: Text.ElideRight
                    }

                    Text {
                        width: parent.width
                        text: {
                            var who = root.nowArtist.length > 0
                                ? root.nowArtist + " · "
                                : ""
                            return who + root.meterClock + " / " + root.meterLength
                        }
                        color: "#c8cdd4"
                        font.family: "monospace"
                        font.pixelSize: 12
                        elide: Text.ElideRight
                    }
                }

                Column {
                    width: Math.max(
                        120,
                        parent.width - 248 - 132 - 20
                    )
                    height: parent.height
                    spacing: 4

                    Row {
                        width: parent.width
                        spacing: 10
                        Text {
                            text: "SPECTRUM"
                            color: "#a8b0b8"
                            font.family: "monospace"
                            font.pixelSize: 12
                        }
                        Text {
                            text: String(root.status.player || "")
                            color: root.playing ? "#8db89a" : "#a8b0b8"
                            font.family: "monospace"
                            font.pixelSize: 12
                        }
                        Text {
                            text: (root.status.shuffle ? "SHUF" : "")
                                + (String(root.status.repeat || "off") !== "off"
                                    && String(root.status.repeat || "off") !== "Off"
                                    ? "  REP" : "")
                            color: "#c8a97e"
                            font.family: "monospace"
                            font.pixelSize: 12
                        }
                    }

                    Canvas {
                        id: spectrumCanvas
                        objectName: "utilitySpectrum"
                        width: parent.width
                        height: 44
                        property var levels: []
                        property var peaks: []
                        property var holds: []
                        onWidthChanged: requestPaint()
                        onHeightChanged: requestPaint()
                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.reset()
                            var cols = root.spectrumBars
                            var segs = root.spectrumSegs
                            var w = width
                            var h = height
                            if (w < 2 || h < 2)
                                return
                            var gapX = 1
                            var gapY = 1
                            var colW = Math.max(1, Math.floor((w - (cols - 1) * gapX) / cols))
                            var blockH = Math.max(1, Math.floor((h - (segs - 1) * gapY) / segs))
                            var usedH = segs * blockH + (segs - 1) * gapY
                            var yBase = h - usedH
                            var rows = spectrumCanvas.levels
                            var peaks = spectrumCanvas.peaks
                            var holds = spectrumCanvas.holds
                            if (!peaks || peaks.length !== cols) {
                                peaks = []
                                holds = []
                                var p
                                for (p = 0; p < cols; p++) {
                                    peaks.push(0)
                                    holds.push(0)
                                }
                                spectrumCanvas.peaks = peaks
                                spectrumCanvas.holds = holds
                            }
                            var x = 0
                            var i
                            var s
                            var step = 1 / Math.max(1, segs)
                            for (i = 0; i < cols; i++) {
                                var level = 0
                                if (root.playing && rows && i < rows.length)
                                    level = Math.min(1, Number(rows[i] || 0))
                                var peak = Number(peaks[i] || 0)
                                var hold = Number(holds[i] || 0)
                                if (level >= peak) {
                                    peak = level
                                    hold = root.peakHoldTicks
                                } else if (!root.playing) {
                                    hold = 0
                                    peak = Math.max(0, peak - step * 2)
                                } else if (hold > 0) {
                                    hold -= 1
                                } else {
                                    peak = Math.max(level, peak - step)
                                }
                                peaks[i] = peak
                                holds[i] = hold
                                var lit = Math.round(level * segs)
                                var peakSeg = Math.round(peak * segs) - 1
                                if (peak > 0 && peakSeg < 0)
                                    peakSeg = 0
                                for (s = 0; s < segs; s++) {
                                    var on = s < lit
                                    var isPeak = peak > 0.02 && s === peakSeg
                                    if (!on && !isPeak)
                                        continue
                                    var y = yBase + (segs - 1 - s) * (blockH + gapY)
                                    var frac = segs <= 1 ? 0 : s / (segs - 1)
                                    if (isPeak && !on)
                                        ctx.fillStyle = "#f0e6c0"
                                    else
                                        ctx.fillStyle = root.ledColor(frac)
                                    ctx.fillRect(x, y, colW, blockH)
                                }
                                x += colW + gapX
                                if (x >= w)
                                    break
                            }
                        }
                    }
                }

                Column {
                    width: 132
                    height: parent.height
                    spacing: 4

                    Text {
                        width: parent.width
                        text: "EQ · " + String(root.status.eq_preset || "Flat")
                        color: "#c8a97e"
                        font.family: "monospace"
                        font.pixelSize: 12
                        elide: Text.ElideRight
                        MouseArea {
                            anchors.fill: parent
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            cursorShape: Qt.PointingHandCursor
                            onClicked: function(event) {
                                if (event.button === Qt.RightButton)
                                    root.flattenEq()
                                else
                                    root.cycleEq()
                            }
                        }
                    }

                    Row {
                        id: eqRow
                        objectName: "utilityEq"
                        width: parent.width
                        height: 50
                        spacing: 2

                        Repeater {
                            model: 10
                            delegate: Item {
                                id: eqBand
                                required property int index
                                width: Math.max(8, (eqRow.width - 18) / 10)
                                height: eqRow.height

                                Rectangle {
                                    anchors.fill: parent
                                    color: "#141414"
                                }

                                Rectangle {
                                    width: parent.width
                                    height: 1
                                    y: parent.height / 2
                                    color: "#2a2a2a"
                                }

                                Rectangle {
                                    width: parent.width - 2
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    height: Math.max(
                                        2,
                                        parent.height * Math.abs(root.eqAt(eqBand.index)) / 12 * 0.5
                                    )
                                    y: root.eqAt(eqBand.index) >= 0
                                        ? parent.height / 2 - height
                                        : parent.height / 2
                                    color: root.eqAt(eqBand.index) >= 0 ? "#8db89a" : "#c8a97e"
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    preventStealing: true
                                    onPressed: function(event) {
                                        root.setEqFromY(
                                            eqBand.index,
                                            event.y,
                                            eqBand.height
                                        )
                                    }
                                    onPositionChanged: function(event) {
                                        if (pressed)
                                            root.setEqFromY(
                                                eqBand.index,
                                                event.y,
                                                eqBand.height
                                            )
                                    }
                                    onDoubleClicked: root.setEqFromY(
                                        eqBand.index,
                                        eqBand.height / 2,
                                        eqBand.height
                                    )
                                }
                            }
                        }
                    }

                }
            }

            Item {
                id: timeline
                objectName: "utilityTimeline"
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: root.seekable ? 10 : 0
                visible: root.seekable

                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width
                    height: 4
                    radius: 2
                    color: "#1a1a1a"
                    border.color: "#2a2a2a"
                    border.width: 1
                }

                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: root.seekable
                        ? Math.max(0, parent.width * root.progress)
                        : 0
                    height: 4
                    radius: 2
                    color: "#c8a97e"
                    visible: root.seekable
                }

                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    x: Math.max(
                        0,
                        Math.min(parent.width - 8, parent.width * root.progress - 4)
                    )
                    width: 8
                    height: 8
                    radius: 4
                    color: "#d8dee9"
                    visible: root.seekable
                }

                MouseArea {
                    anchors.fill: parent
                    enabled: root.seekable
                    cursorShape: root.seekable
                        ? Qt.PointingHandCursor
                        : Qt.ArrowCursor
                    preventStealing: true
                    onPressed: function(event) {
                        root.seekAt(event.x, timeline.width)
                    }
                    onPositionChanged: function(event) {
                        if (pressed)
                            root.seekAt(event.x, timeline.width)
                    }
                }
            }
        }
    }
}
