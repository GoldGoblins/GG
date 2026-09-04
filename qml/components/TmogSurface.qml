import QtQuick
import QtQuick.Controls

Item {
    id: root
    objectName: "workspaceTmogPane"

    property var surfaceHost: null
    property color frameBorder: "#6a6a6a"
    property int frameRadius: 4
    property string statusJson: "{}"
    property int selectedPid: -1
    property string page: "SUMMARY"
    property string perfKey: "CPU"
    readonly property var emptyHist: [0]
    readonly property int liveCap: 120
    property int liveTicks: 0
    property real liveCpu: 0
    property real liveMemUsed: 0
    property real liveMemTotal: 0
    property real liveTemp: 0
    property real liveLoad1: 0
    property real liveLoad5: 0
    property real liveLoad15: 0
    property int liveMhz: 0
    property int liveMhzMax: 0
    property int liveDiskRead: 0
    property int liveDiskWrite: 0
    property int liveNetRx: 0
    property int liveNetTx: 0
    property var liveCpuHist: []
    property var liveMemHist: []
    property var liveTempHist: []
    property var liveDiskHist: []
    property var liveNetHist: []
    property var liveCoreHists: []

    readonly property var nav: [
        "SUMMARY",
        "PERFORMANCE",
        "PROCESSES",
        "SYSTEM",
        "STARTUP",
        "USERS",
        "SERVICES",
        "FREQ",
        "CONNECTIONS",
        "APPS",
        "DISK"
    ]

    readonly property var status: {
        try {
            return JSON.parse(root.statusJson || "{}")
        } catch (err) {
            return {}
        }
    }

    readonly property var processes: {
        var rows = root.status.processes
        if (rows && rows.length !== undefined)
            return rows
        return []
    }

    readonly property var selected: {
        var i
        for (i = 0; i < root.processes.length; i++) {
            if (Number(root.processes[i].pid) === root.selectedPid)
                return root.processes[i]
        }
        return null
    }

    readonly property var energy: root.status.energy || {}

    function refresh() {
        if (!root.surfaceHost || !root.surfaceHost.tmogSnapshot)
            return
        var raw = root.surfaceHost.tmogSnapshot(root.page)
        if (raw === root.statusJson)
            return
        root.statusJson = raw
        if (root.liveCpuHist.length < 2) {
            try {
                var parsed = JSON.parse(raw)
                if (parsed.cpu_hist && parsed.cpu_hist.length)
                    root.liveCpuHist = parsed.cpu_hist.slice()
                if (parsed.mem_hist && parsed.mem_hist.length)
                    root.liveMemHist = parsed.mem_hist.slice()
                if (parsed.temp_hist && parsed.temp_hist.length)
                    root.liveTempHist = parsed.temp_hist.slice()
                if (parsed.disk_hist && parsed.disk_hist.length)
                    root.liveDiskHist = parsed.disk_hist.slice()
                if (parsed.net_hist && parsed.net_hist.length)
                    root.liveNetHist = parsed.net_hist.slice()
                root.liveCpu = Number(parsed.cpu_busy || 0)
                root.liveMemUsed = Number(parsed.mem_used_kb || 0)
                root.liveMemTotal = Number(parsed.mem_total_kb || 0)
                root.liveTemp = Number(parsed.temp_c || 0)
                root.liveMhz = Number(parsed.mhz || 0)
                root.liveMhzMax = Number(parsed.mhz_max || 0)
            } catch (err) {
            }
        }
    }

    function swallow() {
        if (!root.surfaceHost || !root.surfaceHost.startTmog)
            return
        root.surfaceHost.startTmog()
        root.refresh()
    }

    function hideEmbed() {
        if (root.surfaceHost && root.surfaceHost.hideTmog)
            root.surfaceHost.hideTmog()
    }

    function kib(value) {
        var amount = Number(value || 0)
        if (amount >= 1024 * 1024)
            return (amount / 1024 / 1024).toFixed(1) + "G"
        if (amount >= 1024)
            return (amount / 1024).toFixed(1) + "M"
        return String(Math.round(amount)) + "K"
    }

    function bps(value) {
        var amount = Number(value || 0)
        if (amount >= 1024 * 1024)
            return (amount / 1024 / 1024).toFixed(1) + " MB/s"
        if (amount >= 1024)
            return (amount / 1024).toFixed(1) + " KB/s"
        return String(Math.round(amount)) + " B/s"
    }

    function clock(seconds) {
        var s = Math.max(0, Number(seconds || 0))
        var h = Math.floor(s / 3600)
        var m = Math.floor((s % 3600) / 60)
        var r = Math.floor(s % 60)
        return String(h).padStart(2, "0") + ":"
            + String(m).padStart(2, "0") + ":"
            + String(r).padStart(2, "0")
    }

    function arr(name) {
        if (name === "cpu_hist")
            return root.liveCpuHist
        if (name === "mem_hist")
            return root.liveMemHist
        if (name === "temp_hist")
            return root.liveTempHist
        if (name === "disk_hist")
            return root.liveDiskHist
        if (name === "net_hist")
            return root.liveNetHist
        if (name === "core_hist")
            return root.liveCoreHists
        var rows = root.status[name]
        if (rows && rows.length !== undefined)
            return rows
        return []
    }

    function n(name, fallback) {
        var fb = fallback === undefined ? 0 : fallback
        if (name === "cpu_busy")
            return root.liveCpu
        if (name === "mem_used_kb")
            return root.liveMemUsed
        if (name === "mem_total_kb")
            return root.liveMemTotal || fb
        if (name === "temp_c")
            return root.liveTemp
        if (name === "load1")
            return root.liveLoad1
        if (name === "load5")
            return root.liveLoad5
        if (name === "load15")
            return root.liveLoad15
        if (name === "mhz")
            return root.liveMhz
        if (name === "mhz_max")
            return root.liveMhzMax
        if (name === "disk_read_bps")
            return root.liveDiskRead
        if (name === "disk_write_bps")
            return root.liveDiskWrite
        if (name === "net_rx_bps")
            return root.liveNetRx
        if (name === "net_tx_bps")
            return root.liveNetTx
        if (name === "disk_led")
            return Math.min(1, (root.liveDiskRead + root.liveDiskWrite) / (8 * 1024 * 1024))
        var v = root.status[name]
        if (v === undefined || v === null)
            return fb
        return Number(v)
    }

    function pushHist(hist, value) {
        var next = hist && hist.length !== undefined ? hist.slice() : []
        next.push(Number(value || 0))
        if (next.length > root.liveCap)
            next.splice(0, next.length - root.liveCap)
        return next
    }

    function applyPulse(payload) {
        var p = payload || {}
        root.liveCpu = Number(p.cpu_busy || 0)
        root.liveMemUsed = Number(p.mem_used_kb || 0)
        root.liveMemTotal = Number(p.mem_total_kb || 0)
        root.liveTemp = Number(p.temp_c || 0)
        root.liveLoad1 = Number(p.load1 || 0)
        root.liveLoad5 = Number(p.load5 || 0)
        root.liveLoad15 = Number(p.load15 || 0)
        root.liveMhz = Number(p.mhz || 0)
        root.liveMhzMax = Number(p.mhz_max || 0)
        root.liveDiskRead = Number(p.disk_read_bps || 0)
        root.liveDiskWrite = Number(p.disk_write_bps || 0)
        root.liveNetRx = Number(p.net_rx_bps || 0)
        root.liveNetTx = Number(p.net_tx_bps || 0)
        root.liveCpuHist = root.pushHist(root.liveCpuHist, root.liveCpu)
        root.liveMemHist = root.pushHist(
            root.liveMemHist,
            root.liveMemTotal ? (root.liveMemUsed / root.liveMemTotal * 100) : 0
        )
        root.liveTempHist = root.pushHist(root.liveTempHist, root.liveTemp)
        root.liveDiskHist = root.pushHist(
            root.liveDiskHist,
            (root.liveDiskRead + root.liveDiskWrite) / 1024.0
        )
        root.liveNetHist = root.pushHist(
            root.liveNetHist,
            (root.liveNetRx + root.liveNetTx) / 1024.0
        )
        var cores = p.cores || []
        var rows = root.liveCoreHists && root.liveCoreHists.length
            ? root.liveCoreHists.slice()
            : []
        var i
        for (i = 0; i < cores.length; i++)
            rows[i] = root.pushHist(rows[i] || [], cores[i])
        root.liveCoreHists = rows
    }

    function tick() {
        if (!root.surfaceHost || !root.surfaceHost.tmogPulse)
            return
        try {
            root.applyPulse(JSON.parse(root.surfaceHost.tmogPulse() || "{}"))
        } catch (err) {
        }
        root.liveTicks += 1
        if (root.liveTicks >= 60) {
            root.liveTicks = 0
            root.refresh()
        }
    }

    Timer {
        interval: 16
        running: root.visible
        repeat: true
        onTriggered: root.tick()
    }

    onPageChanged: {
        if (root.visible)
            root.refresh()
    }

    onVisibleChanged: {
        if (visible)
            root.refresh()
        else
            root.hideEmbed()
    }

    Component.onCompleted: root.refresh()

    Item {
        anchors.fill: parent
        anchors.leftMargin: 6
        anchors.rightMargin: 6
        anchors.topMargin: 4
        anchors.bottomMargin: 6

        Row {
            anchors.fill: parent
            spacing: 10

                Column {
                    id: navCol
                    width: 108
                    spacing: 3

                    Repeater {
                        model: root.nav
                        delegate: Text {
                            required property string modelData
                            width: navCol.width
                            text: modelData
                            color: root.page === modelData ? "#d8dee9" : "#a8b0b8"
                            font.family: "monospace"
                            font.pixelSize: 12
                            font.bold: root.page === modelData
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.page = modelData
                            }
                        }
                    }

                    Item { width: 1; height: 8 }

                    Text {
                        width: navCol.width
                        visible: root.status.appimage_found === true
                        text: "OPEN APPIMAGE"
                        color: "#c8a97e"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.swallow()
                        }
                    }
                }

                Rectangle {
                    width: 1
                    height: parent.height
                    color: "#2a2a2a"
                }

                Item {
                    id: field
                    width: parent.width - navCol.width - 11
                    height: parent.height

                    Loader {
                        anchors.fill: parent
                        active: root.page === "SUMMARY"
                        visible: active
                        sourceComponent: summaryPage
                    }

                    Component {
                        id: summaryPage
                        Item {
                            anchors.fill: parent

                        TmogCard {
                            id: barsCard
                            anchors.left: parent.left
                            anchors.top: parent.top
                            width: Math.max(92, parent.width * 0.14)
                            height: parent.height * 0.42
                            leftLegend: "CPU"
                            rightLegend: root.n("cpu_busy").toFixed(1) + "%"

                            Row {
                                anchors.fill: parent
                                spacing: 6

                                Repeater {
                                    model: 3
                                    delegate: Item {
                                        required property int index
                                        readonly property string barKey: index === 0
                                            ? "cpu_busy"
                                            : (index === 1 ? "mhz" : "temp_c")
                                        readonly property real barCap: index === 0
                                            ? 100
                                            : (index === 1 ? Math.max(1, root.n("mhz_max")) : 105)
                                        width: 22
                                        height: parent.height
                                        Rectangle {
                                            anchors.fill: parent
                                            color: "#1c1c1c"
                                            border.color: "#2a2a2a"
                                        }
                                        Rectangle {
                                            anchors.left: parent.left
                                            anchors.right: parent.right
                                            anchors.bottom: parent.bottom
                                            height: parent.height * Math.max(
                                                0.02,
                                                Math.min(1, root.n(barKey) / barCap)
                                            )
                                            color: "#8db89a"
                                        }
                                        Text {
                                            anchors.bottom: parent.bottom
                                            anchors.bottomMargin: 2
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            text: index === 0 ? "CPU" : (index === 1 ? "CLK" : "TMP")
                                            color: "#a8b0b8"
                                            font.family: "monospace"
                                            font.pixelSize: 7
                                            rotation: -90
                                            visible: false
                                        }
                                    }
                                }
                            }
                        }

                        TmogCard {
                            id: cpuCard
                            anchors.left: barsCard.right
                            anchors.leftMargin: 8
                            anchors.right: topCard.left
                            anchors.rightMargin: 8
                            anchors.top: parent.top
                            height: barsCard.height
                            leftLegend: "CPU OVERVIEW"
                            rightLegend: root.n("cpu_busy").toFixed(1) + "%"

                            TmogSpark {
                                anchors.fill: parent
                                values: root.arr("cpu_hist")
                                yMax: 100
                                stroke: "#8db89a"
                                fill: "#1c2a22"
                            }
                        }

                        TmogCard {
                            id: topCard
                            anchors.right: parent.right
                            anchors.top: parent.top
                            width: Math.max(180, parent.width * 0.28)
                            height: barsCard.height
                            leftLegend: "TOP CPU"
                            rightLegend: String(Math.min(8, root.processes.length))

                            Column {
                                anchors.fill: parent
                                spacing: 2
                                Repeater {
                                    model: root.processes.slice(0, 8)
                                    delegate: Text {
                                        required property var modelData
                                        width: parent.width
                                        text: String(modelData.pid)
                                            + "  " + String(modelData.cpu_pct) + "%"
                                            + "  " + root.kib(modelData.rss_kb)
                                            + "  " + String(modelData.comm || "")
                                        color: "#d8dee9"
                                        font.family: "monospace"
                                        font.pixelSize: 12
                                        elide: Text.ElideRight
                                    }
                                }
                            }
                        }

                        TmogCard {
                            id: memCard
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: barsCard.bottom
                            anchors.topMargin: 10
                            height: parent.height * 0.24
                            leftLegend: "MEMORY"
                            rightLegend: root.kib(root.n("mem_used_kb"))
                                + " / " + root.kib(root.n("mem_total_kb"))

                            Column {
                                anchors.fill: parent
                                spacing: 6
                                TmogMeter {
                                    width: parent.width
                                    ratio: root.n("mem_total_kb")
                                        ? root.n("mem_used_kb") / root.n("mem_total_kb")
                                        : 0
                                    onColor: "#b6a6c8"
                                    segments: 32
                                }
                                TmogSpark {
                                    width: parent.width
                                    height: parent.height - 22
                                    values: root.arr("mem_hist")
                                    yMax: 100
                                    stroke: "#b6a6c8"
                                    fill: "#241c28"
                                }
                            }
                        }

                        Row {
                            id: bottomRow
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: memCard.bottom
                            anchors.topMargin: 10
                            anchors.bottom: parent.bottom
                            spacing: 8

                            TmogCard {
                                width: (parent.width - 40) / 6
                                height: parent.height
                                leftLegend: "LOAD"
                                rightLegend: String(root.n("load1"))
                                Column {
                                    anchors.centerIn: parent
                                    spacing: 4
                                    Text {
                                        text: String(root.n("load1"))
                                        color: "#d8dee9"
                                        font.family: "monospace"
                                        font.pixelSize: 16
                                    }
                                    Text {
                                        text: String(root.n("load5")) + "  "
                                            + String(root.n("load15"))
                                        color: "#c8cdd4"
                                        font.family: "monospace"
                                        font.pixelSize: 12
                                    }
                                }
                            }
                            TmogCard {
                                width: (parent.width - 40) / 6
                                height: parent.height
                                leftLegend: "TASKS"
                                rightLegend: String(root.n("process_count"))
                                Column {
                                    anchors.centerIn: parent
                                    Text {
                                        text: String(root.n("tasks_running"))
                                            + " / " + String(root.n("process_count"))
                                        color: "#d8dee9"
                                        font.family: "monospace"
                                        font.pixelSize: 14
                                    }
                                    Text {
                                        text: "running / total"
                                        color: "#a8b0b8"
                                        font.family: "monospace"
                                        font.pixelSize: 12
                                    }
                                }
                            }
                            TmogCard {
                                width: (parent.width - 40) / 6
                                height: parent.height
                                leftLegend: "ENERGY"
                                rightLegend: root.energy.watts === undefined
                                    || root.energy.watts === null
                                    ? "—"
                                    : String(root.energy.watts) + " W"
                                Column {
                                    anchors.fill: parent
                                    spacing: 6
                                    TmogMeter {
                                        width: parent.width
                                        ratio: root.energy.battery_pct
                                            ? Number(root.energy.battery_pct) / 100
                                            : 0
                                        onColor: "#c8a97e"
                                    }
                                    Text {
                                        text: String(root.energy.source || "AC")
                                        color: "#c8cdd4"
                                        font.family: "monospace"
                                        font.pixelSize: 12
                                    }
                                    TmogSpark {
                                        width: parent.width
                                        height: parent.height - 36
                                        values: root.arr("temp_hist")
                                        stroke: "#c8a97e"
                                        fill: "#2a2418"
                                        yMax: 105
                                    }
                                }
                            }
                            TmogCard {
                                width: (parent.width - 40) / 6
                                height: parent.height
                                leftLegend: "THERMALS"
                                rightLegend: root.n("temp_c").toFixed(0) + " C"
                                Column {
                                    anchors.fill: parent
                                    spacing: 6
                                    TmogMeter {
                                        width: parent.width
                                        ratio: Math.min(1, root.n("temp_c") / 105)
                                        onColor: "#c8a97e"
                                    }
                                    TmogSpark {
                                        width: parent.width
                                        height: parent.height - 22
                                        values: root.arr("temp_hist")
                                        yMax: 105
                                        stroke: "#c8a97e"
                                        fill: "#2a2418"
                                    }
                                }
                            }
                            TmogCard {
                                width: (parent.width - 40) / 6
                                height: parent.height
                                leftLegend: "DISK"
                                rightLegend: root.bps(root.n("disk_read_bps"))
                                Column {
                                    anchors.fill: parent
                                    TmogSpark {
                                        width: parent.width
                                        height: parent.height
                                        values: root.arr("disk_hist")
                                        stroke: "#8db89a"
                                        fill: "#1c2a22"
                                    }
                                }
                            }
                            TmogCard {
                                width: (parent.width - 40) / 6
                                height: parent.height
                                leftLegend: "NETWORK"
                                rightLegend: root.bps(root.n("net_rx_bps") + root.n("net_tx_bps"))
                                Column {
                                    anchors.fill: parent
                                    TmogSpark {
                                        width: parent.width
                                        height: parent.height
                                        values: root.arr("net_hist")
                                        stroke: "#8a8a8a"
                                        fill: "#1c1c1c"
                                    }
                                }
                            }
                        }
                    }
                    }

                    Loader {
                        anchors.fill: parent
                        active: root.page === "PERFORMANCE"
                        visible: active
                        sourceComponent: performancePage
                    }

                    Component {
                        id: performancePage
                        Item {
                            anchors.fill: parent

                        Column {
                            id: perfNav
                            width: 148
                            anchors.left: parent.left
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            spacing: 6

                            Repeater {
                                model: [
                                    { "k": "CPU", "c": "#8db89a", "h": "cpu_hist" },
                                    { "k": "MEMORY", "c": "#b6a6c8", "h": "mem_hist" },
                                    { "k": "ENERGY", "c": "#c8a97e", "h": "temp_hist" },
                                    { "k": "THERMALS", "c": "#c8a97e", "h": "temp_hist" },
                                    { "k": "DISK", "c": "#8db89a", "h": "disk_hist" },
                                    { "k": "NETWORK", "c": "#8a8a8a", "h": "net_hist" }
                                ]
                                delegate: TmogCard {
                                    required property var modelData
                                    width: perfNav.width
                                    height: 52
                                    leftLegend: modelData.k
                                    borderColor: root.perfKey === modelData.k
                                        ? "#8b949e"
                                        : "#3a3a3a"
                                    TmogSpark {
                                        anchors.fill: parent
                                        values: root.arr(modelData.h)
                                        stroke: modelData.c
                                        fill: "#161616"
                                        yMax: modelData.k === "CPU" || modelData.k === "MEMORY"
                                            ? 100
                                            : 0
                                    }
                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: root.perfKey = modelData.k
                                    }
                                }
                            }
                        }

                        TmogCard {
                            anchors.left: perfNav.right
                            anchors.leftMargin: 10
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            leftLegend: root.perfKey
                            rightLegend: root.perfKey === "CPU"
                                ? root.n("cpu_busy").toFixed(1) + "%"
                                : (root.perfKey === "MEMORY"
                                    ? root.kib(root.n("mem_used_kb"))
                                    : (root.perfKey === "THERMALS"
                                        ? root.n("temp_c").toFixed(0) + " C"
                                        : (root.perfKey === "DISK"
                                            ? root.bps(root.n("disk_read_bps"))
                                            : (root.perfKey === "NETWORK"
                                                ? root.bps(root.n("net_rx_bps"))
                                                : (root.energy.watts == null
                                                    ? "—"
                                                    : String(root.energy.watts) + " W")))))

                            Column {
                                anchors.fill: parent
                                spacing: 8

                                TmogMeter {
                                    width: parent.width
                                    height: 16
                                    ratio: root.perfKey === "CPU"
                                        ? root.n("cpu_busy") / 100
                                        : (root.perfKey === "MEMORY"
                                            ? (root.n("mem_total_kb")
                                                ? root.n("mem_used_kb") / root.n("mem_total_kb")
                                                : 0)
                                            : (root.perfKey === "THERMALS"
                                                ? Math.min(1, root.n("temp_c") / 105)
                                                : 0.05))
                                    onColor: root.perfKey === "MEMORY"
                                        ? "#b6a6c8"
                                        : (root.perfKey === "THERMALS" || root.perfKey === "ENERGY"
                                            ? "#c8a97e"
                                            : "#8db89a")
                                    segments: 36
                                }

                                TmogSpark {
                                    width: parent.width
                                    height: root.perfKey === "CPU"
                                        ? Math.max(72, parent.height * 0.28)
                                        : Math.max(120, parent.height * 0.55)
                                    values: root.perfKey === "MEMORY"
                                        ? root.arr("mem_hist")
                                        : (root.perfKey === "THERMALS" || root.perfKey === "ENERGY"
                                            ? root.arr("temp_hist")
                                            : (root.perfKey === "DISK"
                                                ? root.arr("disk_hist")
                                                : (root.perfKey === "NETWORK"
                                                    ? root.arr("net_hist")
                                                    : root.arr("cpu_hist"))))
                                    yMax: root.perfKey === "CPU" || root.perfKey === "MEMORY"
                                        ? 100
                                        : (root.perfKey === "THERMALS" ? 105 : 0)
                                    stroke: root.perfKey === "MEMORY"
                                        ? "#b6a6c8"
                                        : (root.perfKey === "THERMALS" || root.perfKey === "ENERGY"
                                            ? "#c8a97e"
                                            : "#8db89a")
                                    fill: root.perfKey === "MEMORY"
                                        ? "#241c28"
                                        : (root.perfKey === "THERMALS" || root.perfKey === "ENERGY"
                                            ? "#2a2418"
                                            : "#1c2a22")
                                }

                                Flow {
                                    width: parent.width
                                    spacing: 6
                                    visible: root.perfKey === "CPU"
                                    Repeater {
                                        model: root.arr("cores")
                                        delegate: TmogCard {
                                            required property var modelData
                                            required property int index
                                            width: 92
                                            height: 56
                                            leftLegend: "CPU " + modelData.id
                                            rightLegend: String(modelData.pct) + "%"
                                            TmogSpark {
                                                anchors.fill: parent
                                                values: {
                                                    var all = root.arr("core_hist")
                                                    if (all && all.length > index)
                                                        return all[index]
                                                    return root.emptyHist
                                                }
                                                yMax: 100
                                                stroke: "#8db89a"
                                                fill: "#1c2a22"
                                            }
                                        }
                                    }
                                }

                                Text {
                                    width: parent.width
                                    wrapMode: Text.WordWrap
                                    color: "#c8cdd4"
                                    font.family: "monospace"
                                    font.pixelSize: 12
                                    text: root.perfKey === "CPU"
                                        ? (root.status.cpu_model || "")
                                            + "\n" + root.arr("cores").length + " logical   "
                                            + root.n("mhz") + " MHz   up "
                                            + root.clock(root.n("uptime_s"))
                                            + "   threads " + String(root.n("process_count"))
                                        : (root.perfKey === "MEMORY"
                                            ? "capacity " + root.kib(root.n("mem_total_kb"))
                                                + "   used " + root.kib(root.n("mem_used_kb"))
                                                + "   avail " + root.kib(root.n("mem_avail_kb"))
                                                + "   cached " + root.kib(root.n("mem_cached_kb"))
                                                + "\nswap " + root.kib(root.n("swap_used_kb"))
                                                + "   buffers " + root.kib(root.n("mem_buffers_kb"))
                                                + "   shared " + root.kib(root.n("mem_shared_kb"))
                                                + "   slab " + root.kib(root.n("mem_slab_kb"))
                                            : (root.perfKey === "THERMALS"
                                                ? "whole machine  " + root.n("temp_c").toFixed(1) + " C"
                                                : (root.perfKey === "DISK"
                                                    ? "read " + root.bps(root.n("disk_read_bps"))
                                                        + "   write " + root.bps(root.n("disk_write_bps"))
                                                    : (root.perfKey === "NETWORK"
                                                        ? String(root.status.net_iface || "—")
                                                            + "   ↓ " + root.bps(root.n("net_rx_bps"))
                                                            + "   ↑ " + root.bps(root.n("net_tx_bps"))
                                                        : String(root.energy.source || "AC")
                                                            + (root.energy.watts == null
                                                                ? "   power unavailable"
                                                                : "   " + String(root.energy.watts) + " W")))))
                                }
                            }
                        }
                    }
                    }

                    Loader {
                        anchors.fill: parent
                        active: root.page !== "SUMMARY" && root.page !== "PERFORMANCE"
                        visible: active
                        sourceComponent: listPage
                    }

                    Component {
                        id: listPage
                    Flickable {
                        anchors.fill: parent
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        contentWidth: width
                        contentHeight: listBody.height
                        flickableDirection: Flickable.VerticalFlick

                        Column {
                            id: listBody
                            width: parent.width
                            spacing: 8

                            TmogCard {
                                width: parent.width
                                height: Math.max(180, root.processes.length * 16 + 36)
                                visible: root.page === "PROCESSES"
                                leftLegend: "PROCESSES"
                                rightLegend: String(root.n("process_count"))
                                    + (
                                        root.n("tombstones") > 0
                                            ? (" · " + String(root.n("tombstones")) + " GONE")
                                            : ""
                                    )
                                Column {
                                    width: parent.width
                                    spacing: 3
                                    Text {
                                        width: parent.width
                                        text: "NAME            PID     STATUS      USER        CPU    RSS     THR"
                                        color: "#a8b0b8"
                                        font.family: "monospace"
                                        font.pixelSize: 12
                                    }
                                    Repeater {
                                        model: root.processes
                                        delegate: Text {
                                            required property var modelData
                                            width: listBody.width - 8
                                            text: String(modelData.comm || "").padEnd(14, " ").slice(0, 14)
                                                + " " + String(modelData.pid).padStart(6, " ")
                                                + "  " + String(modelData.status || "").padEnd(11, " ").slice(0, 11)
                                                + " " + String(modelData.user || "").padEnd(10, " ").slice(0, 10)
                                                + " " + String(modelData.cpu_pct).padStart(5, " ") + "%"
                                                + " " + root.kib(modelData.rss_kb).padStart(7, " ")
                                                + " " + String(modelData.threads).padStart(4, " ")
                                            color: modelData.tombstone
                                                ? "#c98989"
                                                : (
                                                    Number(modelData.pid) === root.selectedPid
                                                        ? "#e6edf3"
                                                        : "#c8cdd4"
                                                )
                                            font.family: "monospace"
                                            font.pixelSize: 12
                                            elide: Text.ElideRight
                                            MouseArea {
                                                anchors.fill: parent
                                                onClicked: root.selectedPid = Number(modelData.pid)
                                            }
                                        }
                                    }
                                    Text {
                                        width: parent.width
                                        visible: root.selected !== null
                                        text: root.selected
                                            ? "#" + root.selected.pid + "  "
                                                + (root.selected.cmdline || "")
                                            : ""
                                        color: "#c8a97e"
                                        font.family: "monospace"
                                        font.pixelSize: 12
                                        wrapMode: Text.WrapAnywhere
                                    }
                                }
                            }

                            TmogCard {
                                width: parent.width
                                height: 160
                                visible: root.page === "SYSTEM"
                                leftLegend: "SYSTEM"
                                Text {
                                    width: parent.width
                                    text: "HOST  " + (root.status.hostname || "—")
                                        + "\nKERNEL  " + (root.status.kernel || "—")
                                        + "\nCPU  " + (root.status.cpu_model || "—")
                                        + "\nCORES  " + root.arr("cores").length
                                        + "\nUP  " + root.clock(root.n("uptime_s"))
                                    color: "#d8dee9"
                                    font.family: "monospace"
                                    font.pixelSize: 12
                                    wrapMode: Text.WordWrap
                                }
                            }

                            Repeater {
                                model: root.page === "USERS" ? root.arr("users") : []
                                delegate: Text {
                                    required property var modelData
                                    text: String(modelData.name) + "   " + String(modelData.procs)
                                    color: "#d8dee9"
                                    font.family: "monospace"
                                    font.pixelSize: 12
                                }
                            }
                            Repeater {
                                model: root.page === "CONNECTIONS" ? root.arr("connections") : []
                                delegate: Text {
                                    required property var modelData
                                    width: listBody.width
                                    text: String(modelData.state) + "  "
                                        + String(modelData.local) + " → " + String(modelData.remote)
                                    color: "#c8cdd4"
                                    font.family: "monospace"
                                    font.pixelSize: 12
                                    elide: Text.ElideRight
                                }
                            }
                            TmogCard {
                                width: parent.width
                                height: 28
                                visible: root.page === "DISK"
                                leftLegend: "BLINKENDISK"
                                rightLegend: root.bps(root.n("disk_read_bps") + root.n("disk_write_bps"))
                                Rectangle {
                                    width: parent.width
                                    height: 8
                                    color: "#1a1a1a"
                                    radius: 2
                                    Rectangle {
                                        width: Math.max(4, parent.width * Math.min(1, root.n("disk_led")))
                                        height: parent.height
                                        color: root.n("disk_led") > 0.04 ? "#e05050" : "#3a3a3a"
                                        radius: 2
                                    }
                                }
                            }
                            Repeater {
                                model: root.page === "DISK" ? root.arr("mounts") : []
                                delegate: TmogCard {
                                    required property var modelData
                                    width: listBody.width
                                    height: 52
                                    leftLegend: String(modelData.path)
                                    rightLegend: String(modelData.fstype)
                                    TmogMeter {
                                        width: parent.width
                                        ratio: Number(modelData.total)
                                            ? Number(modelData.used) / Number(modelData.total)
                                            : 0
                                        onColor: "#8db89a"
                                    }
                                }
                            }
                            Repeater {
                                model: root.page === "FREQ" ? root.arr("cores") : []
                                delegate: Text {
                                    required property var modelData
                                    text: "CPU " + modelData.id + "  "
                                        + modelData.mhz + " MHz  " + modelData.pct + "%"
                                    color: "#8db89a"
                                    font.family: "monospace"
                                    font.pixelSize: 12
                                }
                            }
                            Repeater {
                                model: root.page === "STARTUP" ? root.arr("startup") : []
                                delegate: Text {
                                    required property var modelData
                                    text: String(modelData)
                                    color: "#d8dee9"
                                    font.family: "monospace"
                                    font.pixelSize: 12
                                }
                            }
                            Repeater {
                                model: root.page === "APPS" ? root.arr("apps") : []
                                delegate: Text {
                                    required property var modelData
                                    text: String(modelData)
                                    color: "#c8cdd4"
                                    font.family: "monospace"
                                    font.pixelSize: 12
                                }
                            }
                            Repeater {
                                model: root.page === "SERVICES" ? root.arr("services") : []
                                delegate: Text {
                                    required property var modelData
                                    text: String(modelData)
                                    color: "#c8cdd4"
                                    font.family: "monospace"
                                    font.pixelSize: 12
                                }
                            }
                        }
                    }
                    }
                }
            }
        }

    Item {
        id: hole
        objectName: "workspaceTmogHole"
        enabled: false
        anchors.fill: parent
        anchors.margins: 12
        anchors.topMargin: 86
        anchors.bottomMargin: 18
    }
}
