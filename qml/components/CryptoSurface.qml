import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs

Item {
    id: root
    objectName: "workspaceCryptoPane"

    property var surfaceHost: null
    property color frameBorder: "#6a6a6a"
    property int frameRadius: 4
    property string statusJson: "{}"
    property string botTab: "trader"
    property string botTape: "live"
    property string page: "PORTFOLIO"
    readonly property var nav: [
        "PORTFOLIO",
        "TRADER",
        "BACKTEST",
        "SIGNAL",
        "ARB",
        "ACTIVITY"
    ]
    readonly property bool backtestRunning: String((root.status.backtest_job || {}).state || "") === "running"
    signal walletLabelChanged(string label)

    readonly property var status: {
        try {
            return JSON.parse(root.statusJson || "{}")
        } catch (err) {
            return {}
        }
    }

    readonly property var wallet: root.status.wallet || {}
    readonly property var holdings: root.status.holdings || []
    readonly property var ledger: {
        var rows = root.status.ledger || []
        var out = []
        var testnet = String(root.status.legend || "TESTNET") !== "MAINNET"
        for (var i = rows.length - 1; i >= 0; i--) {
            var row = rows[i] || {}
            var err = String(row.error || "")
            var hint = String(row.hint || "")
            if (testnet && (err === "MAINNET_NOT_ARMED"
                            || hint.indexOf("Mainnet stays locked") >= 0))
                continue
            out.push(row)
        }
        return out
    }
    readonly property var bot: root.status.bot || {}
    readonly property var trader: root.status.trader || {}
    readonly property var arb: root.status.arb || {}
    readonly property var lab: root.status.lab || {}
    readonly property string legend: String(root.status.legend || "TESTNET")
    readonly property bool connected: String(root.wallet.pubkey || "").length > 12
    readonly property var quote: root.status.quote || {}
    readonly property var liveChart: root.status.chart || {}
    readonly property var sparkChart: root.liveChart
    readonly property var botTapeChart: {
        if (root.botTape === "bt0") {
            var a = ((root.trader.backtest || {}).chart) || {}
            if (a.closes && a.closes.length > 1)
                return a
        }
        if (root.botTape === "bt1") {
            var b = ((root.trader.backtest_prev || {}).chart) || {}
            if (b.closes && b.closes.length > 1)
                return b
        }
        return root.liveChart
    }
    readonly property var closes: {
        var rows = (root.sparkChart || {}).closes
        if (rows && rows.length !== undefined && rows.length > 1)
            return rows
        rows = root.bot.closes
        if (rows && rows.length !== undefined)
            return rows
        return []
    }
    readonly property var chartTimes: {
        var rows = (root.sparkChart || {}).times
        if (rows && rows.length !== undefined)
            return rows
        return []
    }
    readonly property var tradeMarks: root.buildTradeMarks(root.sparkChart, false)
    readonly property var chartPoints: root.buildChartPoints(root.sparkChart)
    readonly property var chartMarkers: []
    readonly property bool chartHasTimes: root.chartTimes.length === root.closes.length
        && root.closes.length > 1
    readonly property var botPoints: root.buildChartPoints(root.botTapeChart)
    readonly property var botMarkers: root.buildChartMarkers(
        root.botTapeChart,
        root.botTape === "live"
            ? root.buildTradeMarks(root.botTapeChart, false)
            : root.buildTradeMarks(root.botTapeChart, true)
    )
    readonly property bool botHasTimes: {
        var c = (root.botTapeChart || {}).closes || []
        var t = (root.botTapeChart || {}).times || []
        return t.length === c.length && c.length > 1
    }
    readonly property var botEquity: {
        var rows = (root.botTapeChart || {}).equity || []
        var out = []
        var i
        if (!rows || !rows.length)
            return out
        for (i = 0; i < rows.length; i++) {
            var row = rows[i] || {}
            var ts = Number(row.time || row.ts || 0)
            var val = Number(row.value || row.sol || 0)
            if (ts > 0 && val > 0)
                out.push({ "time": ts, "value": val })
        }
        return out
    }

    function refresh() {
        if (!root.surfaceHost)
            return
        var raw = root.surfaceHost.cryptoStatus()
        if (raw === root.statusJson)
            return
        root.statusJson = raw
        var w = root.status.wallet || {}
        root.walletLabelChanged(String(w.label || "WALLET · DISCONNECTED"))
        if (root.surfaceHost.cryptoRefreshChart
                && (root.closes.length < 2
                    || root.chartTimes.length !== root.closes.length))
            Qt.callLater(root.pullChart)
    }

    function pullChart() {
        if (!root.surfaceHost || !root.surfaceHost.cryptoRefreshChart)
            return
        var raw = root.surfaceHost.cryptoRefreshChart()
        try {
            var parsed = JSON.parse(raw || "{}")
            if (!parsed.error)
                root.statusJson = raw
        } catch (err) {
            return
        }
        var w = root.status.wallet || {}
        root.walletLabelChanged(String(w.label || "WALLET · DISCONNECTED"))
    }

    function connectWatch() {
        if (!root.surfaceHost)
            return
        root.statusJson = root.surfaceHost.cryptoConnectWatch(pubkeyField.text)
        refresh()
    }

    function paperSignal() {
        if (!root.surfaceHost)
            return
        root.surfaceHost.cryptoIngestSignal(
            JSON.stringify({
                "side": "buy",
                "size_sol": 0.01,
                "symbol": "SOL",
                "source": "manual"
            })
        )
        refresh()
    }

    function shortKey(value) {
        var t = String(value || "")
        if (t.length < 12)
            return t.length ? t : "not connected"
        return t.substring(0, 4) + " ··· " + t.substring(t.length - 4)
    }

    function tokenColor(index) {
        var colors = ["#c8a97e", "#6aa8c8", "#8db89a", "#b6a6c8", "#c98989", "#d4c84a"]
        return colors[index % colors.length]
    }

    function lastClose() {
        if (root.closes.length === 0)
            return ""
        return String(root.closes[root.closes.length - 1])
    }

    function lotDollars(raw) {
        var px = Number(raw || 0)
        if (px > 10000)
            px = px / 1000000.0
        return px
    }

    function buildTradeMarks(chart, fromBacktest) {
        var rows = (chart || {}).closes || []
        var n = rows.length
        var out = []
        if (n < 2)
            return out
        var times = (chart || {}).times || []
        var lots = fromBacktest
            ? ((chart || {}).marks || [])
            : ((root.trader || {}).lots || [])
        var i
        var j
        var t0 = 0
        var t1 = 0
        if (times && times.length === n) {
            t0 = Number(times[0] || 0)
            t1 = Number(times[n - 1] || 0)
        }
        for (j = 0; j < lots.length; j++) {
            var lot = lots[j] || {}
            var side = String(lot.side || "")
            if (side !== "buy" && side !== "sell")
                continue
            var ts = Number(lot.ts || 0)
            if (!(t0 > 0 && t1 >= t0 && ts > 0))
                continue
            if (ts < t0 - 7200)
                continue
            var idx = 0
            for (i = 0; i < n; i++) {
                if (Number(times[i] || 0) <= ts)
                    idx = i
            }
            out.push({
                "i": idx,
                "side": side,
                "px": root.lotDollars(lot.price !== undefined ? lot.price : lot.px)
            })
        }
        return out
    }

    function buildChartPoints(chart) {
        var rows = (chart || {}).closes || []
        var times = (chart || {}).times || []
        var out = []
        var i
        if (!rows || rows.length < 2 || times.length !== rows.length)
            return out
        for (i = 0; i < rows.length; i++) {
            var ts = Number(times[i] || 0)
            var px = Number(rows[i] || 0)
            if (ts > 0 && px > 0)
                out.push({ "time": ts, "value": px })
        }
        return out
    }

    function buildChartMarkers(chart, marks) {
        var times = (chart || {}).times || []
        var out = []
        var i
        for (i = 0; i < marks.length; i++) {
            var m = marks[i] || {}
            var idx = Math.round(Number(m.i || 0))
            var ts = Number(times[idx] || 0)
            if (!(ts > 0))
                continue
            var buy = String(m.side || "") === "buy"
            out.push({
                "time": ts,
                "position": buy ? "belowBar" : "aboveBar",
                "color": buy ? "#8db89a" : "#c98989",
                "shape": buy ? "arrowUp" : "arrowDown"
            })
        }
        return out
    }

    Timer {
        interval: 20000
        running: root.visible
        repeat: true
        onTriggered: root.refresh()
    }

    Timer {
        interval: 1000
        running: root.visible && root.backtestRunning
        repeat: true
        onTriggered: {
            root.refresh()
            var st = String((root.status.backtest_job || {}).state || "")
            if (st === "done") {
                root.page = "BACKTEST"
                root.botTab = "trader"
                root.botTape = "bt0"
            }
        }
    }

    Timer {
        interval: 1000
        running: root.visible && String(root.lab.label || "") === "LAB STARTING"
        repeat: true
        onTriggered: root.refresh()
    }

    Timer {
        interval: 30000
        running: root.visible && root.bot.armed === true
        repeat: true
        onTriggered: {
            if (root.surfaceHost)
                root.statusJson = root.surfaceHost.cryptoTickBot()
            root.refresh()
        }
    }

    Timer {
        interval: 15000
        running: root.visible && root.trader.armed === true
        repeat: true
        onTriggered: {
            if (root.surfaceHost)
                root.statusJson = root.surfaceHost.cryptoTickTrader()
            root.refresh()
        }
    }

    onVisibleChanged: {
        if (visible)
            root.refresh()
    }

    FileDialog {
        id: keypairDialog
        title: "IMPORT SOLANA KEYPAIR"
        fileMode: FileDialog.OpenFile
        nameFilters: ["JSON (*.json)", "All files (*)"]
        onAccepted: {
            if (root.surfaceHost)
                root.surfaceHost.cryptoImportKeypair(
                    String(keypairDialog.selectedFile)
                )
            root.refresh()
        }
    }


    onPageChanged: {
        if (root.page === "SIGNAL")
            root.botTab = "signal"
        else if (root.page === "ARB")
            root.botTab = "arb"
        else
            root.botTab = "trader"
    }

    Item {
        anchors.fill: parent
        anchors.leftMargin: 6
        anchors.rightMargin: 6
        anchors.topMargin: 4
        anchors.bottomMargin: 6

        Item {
            id: topBar
            width: parent.width
            height: 20

            Row {
                spacing: 0
                Repeater {
                    model: root.nav
                    Text {
                        required property int index
                        required property string modelData
                        text: index > 0 ? ("  |  " + modelData) : modelData
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
            }

            Row {
                anchors.right: parent.right
                spacing: 12
                Text {
                    text: "TESTNET"
                    color: root.legend === "TESTNET" ? "#d8dee9" : "#a8b0b8"
                    font.family: "monospace"
                    font.pixelSize: 12
                    font.bold: root.legend === "TESTNET"
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (root.surfaceHost)
                                root.surfaceHost.cryptoSetNetwork("testnet")
                            root.refresh()
                        }
                    }
                }
                Text {
                    text: "MAINNET"
                    color: root.legend === "MAINNET" ? "#d8dee9" : "#a8b0b8"
                    font.family: "monospace"
                    font.pixelSize: 12
                    font.bold: root.legend === "MAINNET"
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (root.surfaceHost)
                                root.surfaceHost.cryptoSetNetwork("mainnet")
                            root.refresh()
                        }
                    }
                }
                Text {
                    text: root.status.signer ? "SIGNER ON DISK" : "WATCH ONLY"
                    color: root.status.signer ? "#8db89a" : "#c8cdd4"
                    font.family: "monospace"
                    font.pixelSize: 12
                }
                Text {
                    text: String(root.lab.label || (root.lab.healthy ? "LAB ON" : "LAB OFF"))
                    color: root.lab.healthy ? "#8db89a" : "#c8a97e"
                    font.family: "monospace"
                    font.pixelSize: 12
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (!root.surfaceHost)
                                return
                            root.statusJson = root.lab.running
                                ? root.surfaceHost.cryptoLabOff()
                                : root.surfaceHost.cryptoLabOn()
                            root.refresh()
                        }
                    }
                }
                Text {
                    text: "PROVEN " + String((root.status.proven || {}).label || "0/5")
                    color: (root.status.proven || {}).ready ? "#8db89a" : "#a8b0b8"
                    font.family: "monospace"
                    font.pixelSize: 12
                }
            }
        }

        Item {
            id: field
            anchors.top: topBar.bottom
            anchors.topMargin: 8
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom

            Column {
                id: portHead
                width: parent.width
                spacing: 4
                visible: root.page === "PORTFOLIO"
                Text {
                    text: root.connected ? root.shortKey(root.wallet.pubkey) : "no wallet"
                    color: "#c8cdd4"
                    font.family: "monospace"
                    font.pixelSize: 12
                }
                Text {
                    text: String(root.quote.usd || "")
                    visible: String(root.quote.usd || "").length > 0
                    color: "#e6e6e6"
                    font.family: "monospace"
                    font.pixelSize: 26
                    font.bold: true
                }
                Text {
                    text: String(root.quote.sek || "")
                    visible: String(root.quote.sek || "").length > 0
                    color: "#c8cdd4"
                    font.family: "monospace"
                    font.pixelSize: 13
                }
                Text {
                    text: String(root.wallet.balance_sol || "0") + " SOL"
                    color: String(root.quote.usd || "").length > 0 ? "#c8cdd4" : "#e6e6e6"
                    font.family: "monospace"
                    font.pixelSize: String(root.quote.usd || "").length > 0 ? 12 : 26
                    font.bold: String(root.quote.usd || "").length === 0
                }
                Text {
                    visible: root.lastClose().length > 0
                    text: "1 SOL  $" + root.lastClose()
                        + (String(root.quote.usd_sek || "") ? ("  ·  USDSEK " + String(root.quote.usd_sek)) : "")
                        + (String(root.quote.source || "") ? ("  ·  " + String(root.quote.source)) : "")
                    color: "#b6a6c8"
                    font.family: "monospace"
                    font.pixelSize: 12
                }
            }

            Column {
                id: btHead
                width: parent.width
                spacing: 4
                visible: root.page === "BACKTEST"
                Row {
                    spacing: 10
                    Text {
                        text: "LIVE"
                        color: root.botTape === "live" ? "#d8dee9" : "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        font.bold: root.botTape === "live"
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.botTape = "live"
                        }
                    }
                    Text {
                        visible: (((root.trader.backtest || {}).chart || {}).closes || []).length > 1
                        text: {
                            var t = String((root.trader.backtest || {}).ran_at || "")
                            return t ? ("BACKTEST 1  " + t) : "BACKTEST 1"
                        }
                        color: root.botTape === "bt0" ? "#d8dee9" : "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        font.bold: root.botTape === "bt0"
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.botTape = "bt0"
                        }
                    }
                    Text {
                        visible: (((root.trader.backtest_prev || {}).chart || {}).closes || []).length > 1
                        text: {
                            var t = String((root.trader.backtest_prev || {}).ran_at || "")
                            return t ? ("BACKTEST 2  " + t) : "BACKTEST 2"
                        }
                        color: root.botTape === "bt1" ? "#d8dee9" : "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        font.bold: root.botTape === "bt1"
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.botTape = "bt1"
                        }
                    }
                    Repeater {
                        model: (root.trader.books || []).length
                        Text {
                            text: String(((root.trader.books || [])[index] || {}).name || "")
                            color: String(((root.trader.books || [])[index] || {}).id || "")
                                   === String(root.trader.book || "gg")
                                   ? "#d8dee9" : "#5d6670"
                            font.family: "monospace"
                            font.pixelSize: 12
                            font.bold: String(((root.trader.books || [])[index] || {}).id || "")
                                       === String(root.trader.book || "gg")
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    var row = (root.trader.books || [])[index] || {}
                                    if (!root.surfaceHost || !root.surfaceHost.cryptoSetBook)
                                        return
                                    root.statusJson = root.surfaceHost.cryptoSetBook(String(row.id || "gg"))
                                }
                            }
                        }
                    }
                    Text {
                        text: root.backtestRunning ? "BACKTEST…" : "RUN BACKTEST"
                        color: root.backtestRunning ? "#c8a97e" : "#8db89a"
                        font.family: "monospace"
                        font.pixelSize: 12
                        font.bold: true
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (!root.surfaceHost || !root.surfaceHost.cryptoBacktestTrader)
                                    return
                                if (root.backtestRunning)
                                    return
                                root.botTape = "live"
                                root.statusJson = root.surfaceHost.cryptoBacktestTrader()
                            }
                        }
                    }
                }
                Text {
                    width: parent.width
                    visible: root.backtestRunning
                        || String((root.status.backtest_job || {}).state || "") === "error"
                    text: root.backtestRunning
                        ? String((root.status.backtest_job || {}).note || "BACKTEST…")
                        : String((root.status.backtest_job || {}).note || "backtest failed")
                    color: root.backtestRunning ? "#c8a97e" : "#c98989"
                    font.family: "monospace"
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
                Text {
                    width: parent.width
                    visible: String((root.trader.backtest || {}).tokens || "").length > 0
                    text: {
                        var bt = root.trader.backtest || {}
                        var best = bt.best_trade || {}
                        var worst = bt.worst_trade || {}
                        return String(bt.verdict || "")
                            + "  " + String(bt.fills || 0) + " fills"
                            + "  vault " + String(bt.banked_sol || "") + " SOL"
                            + "  win " + String(bt.win_rate || "0") + "%"
                            + "  avg " + String(bt.avg_fills_day || "") + "/d"
                            + (best.profit ? ("  best " + String(best.profit) + " SOL") : "")
                            + (worst.profit ? ("  worst " + String(worst.profit) + " SOL") : "")
                            + (bt.pnl_sol ? ("  pnl " + String(bt.pnl_sol) + " SOL") : "")
                            + (bt.range ? ("  " + String(bt.range)) : "")
                    }
                    color: String((root.trader.backtest || {}).verdict || "") === "GOOD"
                        ? "#8db89a"
                        : (String((root.trader.backtest || {}).verdict || "") === "WEAK"
                            ? "#c98989"
                            : "#c8a97e")
                    font.family: "monospace"
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
                Text {
                    width: parent.width
                    visible: ((root.trader.backtest || {}).weeks || []).length > 0
                        || ((root.trader.backtest || {}).years || []).length > 0
                    text: {
                        var bt = root.trader.backtest || {}
                        var start = String(bt.start_sol || "2.000000000")
                        var end = String(bt.equity_sol || bt.tokens || "")
                        var pnl = String(bt.pnl_sol || "")
                        var usd = String(bt.usd || "")
                        var parts = ["start " + start + " → " + end + " SOL  pnl " + pnl + " SOL"
                            + (usd ? ("  powder $" + usd) : "")]
                        var years = bt.years || []
                        var yp = []
                        var i
                        for (i = 0; i < years.length; i++) {
                            var y = years[i] || {}
                            yp.push(String(y.year || "") + " Δ" + String(y.pnl_sol || "") + " f" + String(y.fills || 0))
                        }
                        if (yp.length)
                            parts.push(yp.join("  ·  "))
                        var gaps = bt.gaps || []
                        var gp = []
                        for (i = 0; i < gaps.length; i++) {
                            var g = gaps[i] || {}
                            gp.push(String(g.from || "") + "…" + String(g.to || "") + " idle " + String(g.months || 0) + "mo")
                        }
                        if (gp.length)
                            parts.push("gaps " + gp.join("  ·  "))
                        var weeks = bt.weeks || []
                        var from = Math.max(0, weeks.length - 12)
                        var wp = []
                        for (i = from; i < weeks.length; i++) {
                            var w = weeks[i] || {}
                            wp.push(String(w.week || "") + " b" + String(w.buys || 0) + "/s" + String(w.sells || 0) + " Δ" + String(w.pnl_sol || "0"))
                        }
                        if (wp.length)
                            parts.push(wp.join("  ·  "))
                        return parts.join("\n")
                    }
                    color: "#a8b0b8"
                    font.family: "monospace"
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
            }

            Loader {
                id: tapeLoader
                active: root.visible
                    && ((root.page === "PORTFOLIO" && (root.chartHasTimes || root.closes.length > 1))
                        || (root.page === "BACKTEST" && root.botHasTimes))
                width: parent.width
                y: root.page === "BACKTEST" ? btHead.height + 6 : portHead.height + 6
                height: {
                    var bot = 0
                    if (root.page === "PORTFOLIO")
                        bot = portFoot.height + 8
                    return Math.max(80, field.height - y - bot)
                }
                sourceComponent: tapeComp
            }

            Component {
                id: tapeComp
                Item {
                    CryptoChart {
                        anchors.fill: parent
                        visible: (root.page === "PORTFOLIO" && root.chartHasTimes)
                            || (root.page === "BACKTEST" && root.botHasTimes)
                        points: root.page === "BACKTEST" ? root.botPoints : root.chartPoints
                        markers: root.page === "BACKTEST" ? root.botMarkers : root.chartMarkers
                        equity: root.botEquity
                    }
                    TmogSpark {
                        anchors.fill: parent
                        visible: root.page === "PORTFOLIO" && !root.chartHasTimes && root.closes.length > 1
                        values: root.closes
                        marks: []
                        fromZero: false
                        stroke: "#c98989"
                        fill: "#241818"
                        grid: "#1e1e1e"
                    }
                }
            }

            Column {
                id: portFoot
                width: parent.width
                anchors.bottom: parent.bottom
                spacing: 6
                visible: root.page === "PORTFOLIO"
                Text {
                    visible: root.closes.length > 1
                    text: String((root.sparkChart || {}).interval || "15m") + " live SOL"
                    color: "#a8b0b8"
                    font.family: "monospace"
                    font.pixelSize: 12
                }
                Row {
                    spacing: 8
                    width: parent.width
                    GgField {
                        id: pubkeyField
                        width: Math.max(120, parent.width - 80)
                        height: 26
                        placeholderText: "Solana pubkey"
                        text: String(root.wallet.pubkey || "")
                    }
                    Text {
                        text: "CONNECT"
                        color: "#c8a97e"
                        font.family: "monospace"
                        font.pixelSize: 12
                        font.bold: true
                        anchors.verticalCenter: parent.verticalCenter
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.connectWatch()
                        }
                    }
                }
                Row {
                    spacing: 12
                    Text {
                        text: "CREATE TEST WALLET"
                        color: "#c8a97e"
                        font.family: "monospace"
                        font.pixelSize: 12
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (root.surfaceHost)
                                    root.surfaceHost.cryptoCreateTestWallet()
                                root.refresh()
                            }
                        }
                    }
                    Text {
                        text: "AIRDROP 100 SOL"
                        color: "#8db89a"
                        font.family: "monospace"
                        font.pixelSize: 12
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (root.surfaceHost)
                                    root.surfaceHost.cryptoAirdrop()
                                root.refresh()
                            }
                        }
                    }
                    Text {
                        text: "IMPORT KEYPAIR"
                        color: "#c8a97e"
                        font.family: "monospace"
                        font.pixelSize: 12
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: keypairDialog.open()
                        }
                    }
                    Text {
                        text: "DISCONNECT"
                        color: "#c8cdd4"
                        font.family: "monospace"
                        font.pixelSize: 12
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (root.surfaceHost)
                                    root.surfaceHost.cryptoDisconnect()
                                root.refresh()
                            }
                        }
                    }
                }
                Text {
                    text: "ASSETS"
                    color: "#a8b0b8"
                    font.family: "monospace"
                    font.pixelSize: 12
                }
                Repeater {
                    model: Math.min(root.holdings.length, 6)
                    delegate: Row {
                        width: portFoot.width
                        spacing: 8
                        readonly property var row: root.holdings[index] || {}
                        Rectangle {
                            width: 8
                            height: 8
                            radius: 4
                            color: root.tokenColor(index)
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            width: 72
                            text: String(row.symbol || "")
                            color: "#d8dee9"
                            font.family: "monospace"
                            font.pixelSize: 12
                        }
                        Text {
                            text: {
                                var amt = String(row.display || "")
                                if (row.usd)
                                    return amt + "   " + String(row.usd)
                                return amt
                            }
                            color: "#c8cdd4"
                            font.family: "monospace"
                            font.pixelSize: 12
                        }
                    }
                }
                Text {
                    visible: root.holdings.length === 0
                    text: "No assets yet. Create a test wallet on lab."
                    color: "#a8b0b8"
                    font.family: "monospace"
                    font.pixelSize: 12
                }
            }

            Flickable {
                anchors.fill: parent
                visible: root.page === "TRADER"
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                contentHeight: traderCol.height
                Column {
                    id: traderCol
                    width: parent.width
                    spacing: 8
                    Text {
                        width: parent.width
                        text: {
                            var f = root.trader.flow || (root.trader.last || {}).flow || {}
                            var macro = String(root.trader.macro || (root.trader.last || {}).macro || root.trader.regime || "range")
                            var vote = String(root.trader.vote || (root.trader.last || {}).vote || "none")
                            return "MACRO " + macro.toUpperCase()
                                + "  1d " + String(f["1d"] || "-")
                                + "  4h " + String(f["4h"] || "-")
                                + "  8h " + String(f["8h"] || "-")
                                + "  vote " + vote.toUpperCase()
                                + "   float " + String(root.trader.usd || "0")
                                + "   tokens " + String(root.trader.tokens || "0")
                        }
                        color: "#d8dee9"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        width: parent.width
                        text: "vault " + String(root.trader.banked_sol || "0")
                            + "   day " + String(root.trader.trades_today || 0)
                            + "/" + String(root.trader.max_day || 34)
                            + "   open " + String(root.trader.open_lots || 0)
                        color: "#c8cdd4"
                        font.family: "monospace"
                        font.pixelSize: 12
                    }
                    Text {
                        width: parent.width
                        visible: {
                            var live = ((root.trader.day_book || {}).fills || []).length
                            var bt = ((root.trader.backtest || {}).day_book || {}).fills || []
                            return live > 0 || bt.length > 0
                        }
                        text: {
                            var book = root.trader.day_book || {}
                            if (!((book.fills || []).length))
                                book = (root.trader.backtest || {}).day_book || {}
                            var rows = book.fills || []
                            var parts = [String(book.day || "today") + "  " + String(book.n || rows.length) + "/34"]
                            var i
                            for (i = 0; i < rows.length; i++) {
                                var r = rows[i] || {}
                                parts.push(String(r.side || "").toUpperCase()
                                    + " " + String(r.horizon || "day")
                                    + " " + String(r.sol || "")
                                    + (r.pnl_sol ? ("  Δ" + String(r.pnl_sol)) : ""))
                            }
                            return parts.join("\n")
                        }
                        color: "#c8cdd4"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        width: parent.width
                        text: {
                            var o = root.trader.osc || (root.trader.last || {}).osc || {}
                            var h = root.trader.horizons || (root.trader.last || {}).horizons || {}
                            return "rsi 1m " + String(o["1m"] == null ? "-" : o["1m"])
                                + "  5m " + String(o["5m"] == null ? "-" : o["5m"])
                                + "  15m " + String(o["15m"] == null ? "-" : o["15m"])
                                + "  1h " + String(o["1h"] == null ? "-" : o["1h"])
                                + "  4h " + String(o["4h"] == null ? "-" : o["4h"])
                                + "  8h " + String(o["8h"] == null ? "-" : o["8h"])
                                + "  1d " + String(o["1d"] == null ? "-" : o["1d"])
                                + "  open " + String(h.spot || root.trader.open_lots || 0)
                        }
                        color: "#b6a6c8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        width: parent.width
                        visible: String((root.trader.last || {}).note || "").length > 0
                        text: String((root.trader.last || {}).action || "hold") + "  " + String((root.trader.last || {}).note || "")
                        color: "#c8a97e"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Row {
                        spacing: 14
                        Text {
                            text: root.trader.armed ? "TRADER OFF" : "ARM TRADER"
                            color: root.trader.armed ? "#c8a97e" : "#8db89a"
                            font.family: "monospace"
                            font.pixelSize: 12
                            font.bold: true
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (!root.surfaceHost)
                                        return
                                    root.statusJson = root.surfaceHost.cryptoArmTrader(!root.trader.armed)
                                    root.refresh()
                                }
                            }
                        }
                        Text {
                            text: "TICK TRADER"
                            color: "#c8a97e"
                            font.family: "monospace"
                            font.pixelSize: 12
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (root.surfaceHost)
                                        root.statusJson = root.surfaceHost.cryptoTickTrader()
                                    root.refresh()
                                }
                            }
                        }
                        Text {
                            text: root.backtestRunning ? "BACKTEST…" : "BACKTEST"
                            color: root.backtestRunning ? "#c8a97e" : "#8db89a"
                            font.family: "monospace"
                            font.pixelSize: 12
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (!root.surfaceHost || !root.surfaceHost.cryptoBacktestTrader)
                                        return
                                    if (root.backtestRunning)
                                        return
                                    root.page = "BACKTEST"
                                    root.botTape = "live"
                                    root.statusJson = root.surfaceHost.cryptoBacktestTrader()
                                }
                            }
                        }
                        Text {
                            text: "RESET"
                            color: "#c8cdd4"
                            font.family: "monospace"
                            font.pixelSize: 12
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (root.surfaceHost)
                                        root.statusJson = root.surfaceHost.cryptoResetTrader()
                                    root.refresh()
                                }
                            }
                        }
                    }
                    Text {
                        width: parent.width
                        text: "DCA: 1.00→1.10 keeps 1.02, harvests 0.08. Skip if fees > 10% of the clip."
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                }
            }

            Column {
                anchors.fill: parent
                visible: root.page === "SIGNAL"
                spacing: 8
                Text {
                    width: parent.width
                    text: String(root.bot.symbol || "SOLUSDT") + "  5m  ·  size " + String(root.bot.size_sol || "0.01") + " SOL"
                    color: "#d8dee9"
                    font.family: "monospace"
                    font.pixelSize: 12
                }
                Text {
                    width: parent.width
                    text: {
                        var last = root.bot.last || {}
                        var side = String(last.super || "none")
                        if (side === "none" && !last.buy_votes && !last.sell_votes)
                            return "NO SUPER"
                        var line = side.toUpperCase() + "   votes " + String(last.buy_votes || 0) + "/" + String(last.sell_votes || 0)
                        var rsi = last.rsi14
                        if (rsi !== undefined && rsi !== null && rsi !== "")
                            line += "   RSI " + Number(rsi).toFixed(1)
                        return line
                    }
                    color: String((root.bot.last || {}).super || "") === "buy"
                        ? "#8db89a"
                        : (String((root.bot.last || {}).super || "") === "sell" ? "#c98989" : "#8b949e")
                    font.family: "monospace"
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
                Text {
                    width: parent.width
                    visible: ((root.bot.last || {}).notes || []).length > 0
                    text: ((root.bot.last || {}).notes || []).join(" · ")
                    color: "#a8b0b8"
                    font.family: "monospace"
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
                Row {
                    spacing: 14
                    Text {
                        text: "EVAL SIGNALS"
                        color: "#c8a97e"
                        font.family: "monospace"
                        font.pixelSize: 12
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (root.surfaceHost)
                                    root.surfaceHost.cryptoEvalSignals()
                                root.refresh()
                            }
                        }
                    }
                    Text {
                        text: root.bot.armed ? "DISARM" : "ARM BOT"
                        color: root.bot.armed ? "#c8a97e" : "#8db89a"
                        font.family: "monospace"
                        font.pixelSize: 12
                        font.bold: true
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (!root.surfaceHost)
                                    return
                                root.statusJson = root.surfaceHost.cryptoArmBot(!root.bot.armed)
                                root.refresh()
                            }
                        }
                    }
                    Text {
                        text: "TEST BUY 0.01 SOL"
                        color: "#8db89a"
                        font.family: "monospace"
                        font.pixelSize: 12
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.paperSignal()
                        }
                    }
                }
                Text {
                    text: root.bot.armed
                        ? "Ticks every 30s. Lab fill on super buy/sell."
                        : (root.connected
                            ? "Strategy004 on SOLUSDT. EVAL then ARM for lab fills."
                            : "CREATE TEST WALLET, then AIRDROP 100 SOL.")
                    color: "#a8b0b8"
                    font.family: "monospace"
                    font.pixelSize: 12
                }
            }

            Column {
                anchors.fill: parent
                visible: root.page === "ARB"
                spacing: 8
                Text {
                    width: parent.width
                    text: "A " + String(root.arb.price_a || "—") + "    B " + String(root.arb.price_b || "—") + "    USDC/SOL"
                    color: "#d8dee9"
                    font.family: "monospace"
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
                Text {
                    width: parent.width
                    visible: String((root.status.arb_last || {}).txid || "").length > 0
                        || String((root.status.arb_last || {}).error || "").length > 0
                    text: {
                        var last = root.status.arb_last || {}
                        var line = String(last.txid || "")
                        if (last.profit)
                            line += "   profit " + String(last.profit)
                        if (last.error)
                            line += "   " + String(last.error)
                        return line
                    }
                    color: (root.status.arb_last || {}).error ? "#c98989" : "#8db89a"
                    font.family: "monospace"
                    font.pixelSize: 12
                    wrapMode: Text.WrapAnywhere
                }
                Row {
                    spacing: 14
                    Text {
                        text: "FLASH ARB"
                        color: "#8db89a"
                        font.family: "monospace"
                        font.pixelSize: 12
                        font.bold: true
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (root.surfaceHost)
                                    root.statusJson = root.surfaceHost.cryptoFlashArb()
                                root.refresh()
                            }
                        }
                    }
                    Text {
                        text: "RESET POOLS"
                        color: "#c8a97e"
                        font.family: "monospace"
                        font.pixelSize: 12
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (root.surfaceHost)
                                    root.statusJson = root.surfaceHost.cryptoFlashArbReset()
                                root.refresh()
                            }
                        }
                    }
                }
                Text {
                    text: "Atomic lab swap. Mainnet stays unarmed."
                    color: "#a8b0b8"
                    font.family: "monospace"
                    font.pixelSize: 12
                }
            }

            Flickable {
                anchors.fill: parent
                visible: root.page === "ACTIVITY"
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                contentHeight: ledCol.height
                Column {
                    id: ledCol
                    width: parent.width
                    spacing: 6
                    Text {
                        visible: root.ledger.length === 0
                        text: "No fills yet."
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                    }
                    Repeater {
                        model: root.ledger.length
                        delegate: Row {
                            width: ledCol.width
                            spacing: 10
                            readonly property var row: root.ledger[index] || {}
                            Text {
                                width: 64
                                text: String(row.side || "").toUpperCase()
                                color: row.error ? "#c98989" : (String(row.side || "") === "buy" ? "#8db89a" : "#c8a97e")
                                font.family: "monospace"
                                font.pixelSize: 12
                                font.bold: true
                            }
                            Text {
                                width: parent.width - 74
                                text: {
                                    var hint = String(row.hint || "")
                                    if (hint.length)
                                        return hint
                                    if (row.error)
                                        return String(row.error)
                                    var tx = String(row.txid || "")
                                    if (tx.length > 20)
                                        return tx.substring(0, 8) + "…" + tx.substring(tx.length - 6)
                                    return tx
                                }
                                color: row.error ? "#c98989" : "#c8cdd4"
                                font.family: "monospace"
                                font.pixelSize: 12
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }
            }
        }
    }
}
