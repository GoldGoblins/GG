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
        "ACTIVITY",
        "FACTORY",
        "DESK",
        "POLY"
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
    readonly property var polymarket: root.status.polymarket || {}
    readonly property var polyResult: root.polymarket.result || {}
    readonly property bool polyRunning: String(root.polymarket.state || "") === "running"
    readonly property var strategyFactory: root.status.strategy_factory || {}
    readonly property var strategyFactoryJob: root.status.strategy_factory_job || {}
    readonly property var strategyFactoryResult: root.strategyFactory
    readonly property bool strategyFactoryRunning:
        String(root.strategyFactoryJob.state || "") === "running"
    readonly property var desk: root.status.desk || {}
    readonly property var deskJob: root.status.desk_job || {}
    readonly property bool deskRunning: String(root.deskJob.state || "") === "running"
    property string polyPreset: "SUMMARY"
    property string polyDate: root.utcDate()
    property string polyHour: root.utcHour()
    property string polySlug: ""
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

    function twoDigits(value) {
        var number = Number(value)
        return number < 10 ? "0" + String(number) : String(number)
    }

    function utcDate() {
        var now = new Date()
        return String(now.getUTCFullYear()) + "-"
            + twoDigits(now.getUTCMonth() + 1) + "-"
            + twoDigits(now.getUTCDate())
    }

    function utcHour() {
        return twoDigits(new Date().getUTCHours())
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

    function runPolymarketQuery() {
        if (!root.surfaceHost || !root.surfaceHost.cryptoPolymarketQuery)
            return
        root.statusJson = root.surfaceHost.cryptoPolymarketQuery(
            root.polyPreset,
            polyDateField.text,
            polyHourField.text,
            polySlugField.text
        )
    }

    function pollPolymarketQuery() {
        if (!root.surfaceHost || !root.surfaceHost.cryptoPolymarketStatus)
            return
        root.statusJson = root.surfaceHost.cryptoPolymarketStatus()
    }

    function resetPolymarketQuery() {
        if (!root.surfaceHost || !root.surfaceHost.cryptoPolymarketReset)
            return
        root.statusJson = root.surfaceHost.cryptoPolymarketReset()
    }

    function factoryRolesText() {
        var roles = (root.strategyFactoryResult.orchestration || {}).roles || []
        var out = []
        for (var i = 0; i < roles.length; i++) {
            var role = roles[i] || {}
            out.push(String(role.id || "ROLE") + "=" + String(role.state || "—"))
        }
        return out.join("  ·  ")
    }

    function factoryGraveyardText() {
        var rows = root.strategyFactoryResult.graveyard || []
        var out = []
        for (var i = 0; i < rows.length; i++) {
            var row = rows[i] || {}
            out.push(String(row.id || "ID") + "=" + String(row.verdict || "—"))
        }
        return out.join("  ·  ")
    }

    function factoryAutoresearchText() {
        var steps = ((root.strategyFactoryResult.autoresearch || {}).steps) || []
        var out = []
        for (var i = 0; i < steps.length; i++) {
            var step = steps[i] || {}
            out.push(String(step.mutation || "STEP")
                     + " " + String(step.decision || "—")
                     + " sharpe " + String(step.test_sharpe || "—"))
        }
        return out.join("  ·  ")
    }

    function factoryMetric(row) {
        var item = row || {}
        var ret = item.return_pct !== undefined ? item.return_pct : "—"
        var drawdown = item.max_drawdown_pct !== undefined
            ? item.max_drawdown_pct : "—"
        var trades = item.trades !== undefined ? item.trades : "—"
        var wins = item.win_rate_pct !== undefined ? item.win_rate_pct : "—"
        return "ret " + String(ret) + "%"
            + "  maxDD " + String(drawdown) + "%"
            + "  trades " + String(trades)
            + "  win " + String(wins) + "%"
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
        running: root.visible && root.page === "POLY" && root.polyRunning
        repeat: true
        onTriggered: root.pollPolymarketQuery()
    }

    Timer {
        interval: 1000
        running: root.visible && root.page === "FACTORY"
            && root.strategyFactoryRunning
        repeat: true
        onTriggered: root.refresh()
    }

    Timer {
        interval: 1000
        running: root.visible && root.page === "DESK" && root.deskRunning
        repeat: true
        onTriggered: root.refresh()
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
                BufferMark {
                    objectName: "cryptoBuffer"
                    anchors.verticalCenter: parent.verticalCenter
                    active: root.backtestRunning
                        || String(root.lab.label || "") === "LAB STARTING"
                        || root.strategyFactoryRunning
                    cell: 5
                }
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
                        var currency = String(bt.quote_currency || "SOL")
                        return String(bt.verdict || "")
                            + "  " + String(bt.fills || 0) + " fills"
                            + "  vault " + String(bt.banked_sol || "") + " SOL"
                            + "  win " + String(bt.win_rate || "0") + "%"
                            + "  avg " + String(bt.avg_fills_day || "") + "/d"
                            + (best.profit ? ("  best " + String(best.profit) + " " + currency) : "")
                            + (worst.profit ? ("  worst " + String(worst.profit) + " " + currency) : "")
                            + (bt.pnl_usd
                                ? ("  pnl " + String(bt.pnl_usd) + " USD")
                                : (bt.pnl_sol ? ("  pnl " + String(bt.pnl_sol) + " SOL") : ""))
                            + (bt.max_drawdown_usd
                                ? ("  maxDD " + String(bt.max_drawdown_usd) + " USD") : "")
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
                        var startUsd = String(bt.start_usd || "")
                        var endUsd = String(bt.end_usd || "")
                        var pnlUsd = String(bt.pnl_usd || "")
                        var usd = String(bt.usd || "")
                        var headline = startUsd
                            ? ("start $" + startUsd + " → $" + endUsd + " USD  pnl " + pnlUsd
                                + (bt.return_pct !== undefined ? (" (" + String(bt.return_pct) + "%)") : ""))
                            : ("start " + start + " → " + end + " SOL  pnl " + pnl + " SOL")
                        if (bt.max_drawdown_usd)
                            headline += "  maxDD $" + String(bt.max_drawdown_usd)
                        if (usd)
                            headline += "  powder $" + usd
                        var parts = [headline]
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
                id: factoryScroll
                anchors.fill: parent
                visible: root.page === "FACTORY"
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                contentHeight: factoryCol.height
                ScrollBar.vertical: GgScrollBar {}

                Column {
                    id: factoryCol
                    width: factoryScroll.width
                    height: childrenRect.height
                    spacing: 8

                    Text {
                        text: "STRATEGY FACTORY"
                        color: "#d8dee9"
                        font.family: "monospace"
                        font.pixelSize: 16
                    }
                    Text {
                        text: "ECC LOOP  ·  BOUNDED WORKERS  ·  PAPER ONLY"
                        color: "#b6a6c8"
                        font.family: "monospace"
                        font.pixelSize: 12
                    }
                    Text {
                        width: factoryCol.width
                        text: "Hypothesis → backtest → validation → paper review. "
                            + "This surface never places orders and never arms a wallet."
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Row {
                        spacing: 14
                        Text {
                            text: root.strategyFactoryRunning ? "RUNNING…" : "RUN FACTORY"
                            color: root.strategyFactoryRunning ? "#c8a97e" : "#8db89a"
                            font.family: "monospace"
                            font.pixelSize: 12
                            font.bold: true
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (root.strategyFactoryRunning
                                            || !root.surfaceHost
                                            || !root.surfaceHost.cryptoStrategyFactory)
                                        return
                                    root.statusJson = root.surfaceHost.cryptoStrategyFactory()
                                }
                            }
                        }
                        Text {
                            text: "RESET"
                            color: "#c8a97e"
                            font.family: "monospace"
                            font.pixelSize: 12
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (!root.surfaceHost
                                            || !root.surfaceHost.cryptoStrategyFactoryReset)
                                        return
                                    root.statusJson = root.surfaceHost.cryptoStrategyFactoryReset()
                                }
                            }
                        }
                    }
                    Text {
                        width: factoryCol.width
                        text: "STATE · "
                            + String(root.strategyFactoryJob.state || "idle").toUpperCase()
                            + "  ·  " + String(root.strategyFactoryJob.note || root.strategyFactoryResult.note || "")
                        color: root.strategyFactoryRunning ? "#c8a97e" : "#c8cdd4"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        width: factoryCol.width
                        visible: root.strategyFactoryResult.source !== undefined
                        text: {
                            var source = root.strategyFactoryResult.source || {}
                            var split = root.strategyFactoryResult.split || {}
                            return "SOURCE · " + String(source.symbol || "SOLUSDT")
                                + "  " + String(source.interval || "—")
                                + "  " + String(source.bars || 0) + " bars"
                                + "  friction " + String(source.fee_bps || 0)
                                + "+" + String(source.slippage_bps || 0) + " bps"
                                + "\nSPLIT · train " + String(split.train_pct || 60)
                                + "%  validate " + String(split.validation_pct || 20)
                                + "%  test " + String(split.test_pct || 20) + "%"
                        }
                        color: "#8fa8a0"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        width: factoryCol.width
                        text: "ROLES · " + root.factoryRolesText()
                            + "\nGATES · " + (((root.strategyFactoryResult.orchestration || {}).gates || []).join("  ·  "))
                        color: "#7f8994"
                        font.family: "monospace"
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                    Repeater {
                        model: (root.strategyFactoryResult.candidates || []).length
                        delegate: Rectangle {
                            required property int index
                            width: factoryCol.width
                            height: candidateBody.implicitHeight + 16
                            color: "#121212"
                            border.width: 1
                            border.color: "#4c4c4c"
                            radius: 2

                            Column {
                                id: candidateBody
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 4
                                readonly property var row:
                                    (root.strategyFactoryResult.candidates || [])[index] || {}
                                Text {
                                    width: candidateBody.width
                                    text: String(candidateBody.row.label || candidateBody.row.id || "CANDIDATE")
                                        + "  [" + String(candidateBody.row.verdict || "—") + "]"
                                    color: String(candidateBody.row.verdict || "") === "PASS"
                                        ? "#8db89a"
                                        : (String(candidateBody.row.verdict || "") === "REJECT"
                                            ? "#c98989" : "#c8a97e")
                                    font.family: "monospace"
                                    font.pixelSize: 12
                                    font.bold: true
                                }
                                Text {
                                    width: candidateBody.width
                                    text: String(candidateBody.row.hypothesis || "")
                                    color: "#a8b0b8"
                                    font.family: "monospace"
                                    font.pixelSize: 11
                                    wrapMode: Text.WordWrap
                                }
                                Text {
                                    width: candidateBody.width
                                    text: "TRAIN  " + root.factoryMetric(candidateBody.row.train)
                                        + "\nVALID  " + root.factoryMetric(candidateBody.row.validation)
                                        + "\nTEST   " + root.factoryMetric(candidateBody.row.test)
                                    color: "#c8cdd4"
                                    font.family: "monospace"
                                    font.pixelSize: 11
                                    wrapMode: Text.WordWrap
                                }
                                Text {
                                    width: candidateBody.width
                                    text: String(candidateBody.row.gate_reason || "")
                                    color: "#7f8994"
                                    font.family: "monospace"
                                    font.pixelSize: 11
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }
                    }
                    Text {
                        width: factoryCol.width
                        visible: (root.strategyFactoryResult.candidates || []).length === 0
                        text: "No factory result yet. Run the bounded local research loop."
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        width: factoryCol.width
                        visible: ((root.strategyFactoryResult.graveyard || []).length > 0)
                        text: "GRAVEYARD · negative results kept · "
                            + String((root.strategyFactoryResult.graveyard || []).length)
                            + "  ·  " + root.factoryGraveyardText()
                        color: "#c98989"
                        font.family: "monospace"
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        width: factoryCol.width
                        visible: (root.strategyFactoryResult.autoresearch || {}).steps !== undefined
                        text: "AUTORESEARCH · KEEP/REVERT  best buffer "
                            + String((root.strategyFactoryResult.autoresearch || {}).best_buffer_bps || "—")
                            + "  sharpe "
                            + String((root.strategyFactoryResult.autoresearch || {}).best_test_sharpe || "—")
                            + "\n" + root.factoryAutoresearchText()
                        color: "#8fa8a0"
                        font.family: "monospace"
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                }
            }

            Flickable {
                id: deskScroll
                anchors.fill: parent
                visible: root.page === "DESK"
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                contentHeight: deskCol.height
                ScrollBar.vertical: GgScrollBar {}

                Column {
                    id: deskCol
                    width: deskScroll.width
                    height: childrenRect.height
                    spacing: 8

                    Text {
                        text: "PAPER DESK"
                        color: "#d8dee9"
                        font.family: "monospace"
                        font.pixelSize: 16
                    }
                    Text {
                        text: "SIX SEATS  ·  FRONT MAN IN CODE  ·  MAINNET NOT ARMED"
                        color: "#b6a6c8"
                        font.family: "monospace"
                        font.pixelSize: 12
                    }
                    Text {
                        width: deskCol.width
                        text: "456 volume-leads-price. 067 crowd spike. 218 vol size. "
                            + "240 invalidation. 001 reports only. Front Man is a hard veto, not a prompt."
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Row {
                        spacing: 14
                        Text {
                            text: root.deskRunning ? "RUNNING…" : "SIT THE DESK"
                            color: root.deskRunning ? "#c8a97e" : "#8db89a"
                            font.family: "monospace"
                            font.pixelSize: 12
                            font.bold: true
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (root.deskRunning
                                            || !root.surfaceHost
                                            || !root.surfaceHost.cryptoDesk)
                                        return
                                    root.statusJson = root.surfaceHost.cryptoDesk()
                                }
                            }
                        }
                        Text {
                            text: "RESET"
                            color: "#c8a97e"
                            font.family: "monospace"
                            font.pixelSize: 12
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (!root.surfaceHost || !root.surfaceHost.cryptoDeskReset)
                                        return
                                    root.statusJson = root.surfaceHost.cryptoDeskReset()
                                }
                            }
                        }
                    }
                    Text {
                        width: deskCol.width
                        text: "STATE · " + String(root.deskJob.state || "idle").toUpperCase()
                            + "  ·  LIGHT "
                            + String((root.desk.front_man || {}).light || "RED")
                            + "  ·  trades " + String(root.desk.trades || 0)
                            + "  ·  equity " + String(root.desk.equity_pct || 0) + "%"
                            + "  ·  red lights " + String(root.desk.red_lights || 0)
                        color: String((root.desk.front_man || {}).light || "") === "GREEN"
                            ? "#8db89a" : "#c98989"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        width: deskCol.width
                        text: "VOL · HMM "
                            + String(((root.desk.vol || {}).hmm || {}).last_state || "UNKNOWN")
                            + "  GARCH σ "
                            + String(((root.desk.vol || {}).garch || {}).last_sigma || "—")
                            + "  size " + String((root.desk.vol || {}).size_scale || "—")
                        color: "#8fa8a0"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Repeater {
                        model: (root.desk.seats || []).length
                        delegate: Rectangle {
                            required property int index
                            width: deskCol.width
                            height: seatBody.implicitHeight + 14
                            color: "#121212"
                            border.width: 1
                            border.color: "#4c4c4c"
                            radius: 2
                            Column {
                                id: seatBody
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 2
                                readonly property var row:
                                    (root.desk.seats || [])[index] || {}
                                Text {
                                    width: seatBody.width
                                    text: String(seatBody.row.id || "SEAT")
                                        + "  " + String(seatBody.row.job || "")
                                        + "  [" + String(seatBody.row.vote || "—") + "]"
                                    color: "#c8cdd4"
                                    font.family: "monospace"
                                    font.pixelSize: 12
                                    font.bold: true
                                }
                                Text {
                                    width: seatBody.width
                                    text: JSON.stringify(seatBody.row)
                                    color: "#7f8994"
                                    font.family: "monospace"
                                    font.pixelSize: 11
                                    wrapMode: Text.WordWrap
                                    elide: Text.ElideRight
                                    maximumLineCount: 2
                                }
                            }
                        }
                    }
                    Text {
                        width: deskCol.width
                        visible: ((root.desk.front_man || {}).reasons || []).length > 0
                        text: "FRONT MAN · "
                            + ((root.desk.front_man || {}).reasons || []).join("  ·  ")
                        color: "#c98989"
                        font.family: "monospace"
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        width: deskCol.width
                        visible: (root.desk.seats || []).length === 0
                        text: "No sitting yet. Paper only. Kill switch is in code."
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                }
            }

            Flickable {
                id: polyScroll
                anchors.fill: parent
                visible: root.page === "POLY"
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                contentHeight: polyCol.height
                ScrollBar.vertical: GgScrollBar {}

                Column {
                    id: polyCol
                    width: polyScroll.width
                    height: childrenRect.height
                    spacing: 8

                    Text {
                        text: "POLYMARKET RESEARCH"
                        color: "#d8dee9"
                        font.family: "monospace"
                        font.pixelSize: 16
                    }
                    Text {
                        text: "PENDULUMFLOW V3  ·  REMOTE PARQUET  ·  READ ONLY"
                        color: "#b6a6c8"
                        font.family: "monospace"
                        font.pixelSize: 12
                    }
                    Text {
                        width: polyCol.width
                        text: "One UTC hour per query. No wallet, order placement or automatic archive sync is connected."
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }

                    Row {
                        width: polyCol.width
                        spacing: 8
                        Text {
                            text: "UTC"
                            color: "#a8b0b8"
                            font.family: "monospace"
                            font.pixelSize: 12
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        GgField {
                            id: polyDateField
                            width: 112
                            height: 26
                            placeholderText: "YYYY-MM-DD"
                            text: root.polyDate
                        }
                        GgField {
                            id: polyHourField
                            width: 54
                            height: 26
                            placeholderText: "HH"
                            text: root.polyHour
                        }
                    }

                    Row {
                        width: polyCol.width
                        spacing: 12
                        Text {
                            text: "SUMMARY"
                            color: root.polyPreset === "SUMMARY" ? "#d8dee9" : "#a8b0b8"
                            font.family: "monospace"
                            font.pixelSize: 12
                            font.bold: root.polyPreset === "SUMMARY"
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.polyPreset = "SUMMARY"
                            }
                        }
                        Text {
                            text: "TRADES"
                            color: root.polyPreset === "TRADES" ? "#d8dee9" : "#a8b0b8"
                            font.family: "monospace"
                            font.pixelSize: 12
                            font.bold: root.polyPreset === "TRADES"
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.polyPreset = "TRADES"
                            }
                        }
                        Text {
                            text: "TOUCH"
                            color: root.polyPreset === "TOUCH" ? "#d8dee9" : "#a8b0b8"
                            font.family: "monospace"
                            font.pixelSize: 12
                            font.bold: root.polyPreset === "TOUCH"
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.polyPreset = "TOUCH"
                            }
                        }
                        Text {
                            text: "SCAN"
                            color: root.polyPreset === "SCAN" ? "#d8dee9" : "#a8b0b8"
                            font.family: "monospace"
                            font.pixelSize: 12
                            font.bold: root.polyPreset === "SCAN"
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.polyPreset = "SCAN"
                            }
                        }
                    }

                    Row {
                        width: polyCol.width
                        spacing: 8
                        Text {
                            text: "SLUG"
                            color: root.polyPreset === "TOUCH" ? "#c8cdd4" : "#5d6670"
                            font.family: "monospace"
                            font.pixelSize: 12
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        GgField {
                            id: polySlugField
                            width: Math.max(120, polyCol.width - 58)
                            height: 26
                            enabled: root.polyPreset === "TOUCH"
                            placeholderText: "market slug for TOUCH / optional otherwise"
                            text: root.polySlug
                        }
                    }

                    Row {
                        spacing: 14
                        Text {
                            text: root.polyRunning ? "READING…" : "RUN QUERY"
                            color: root.polyRunning ? "#c8a97e" : "#8db89a"
                            font.family: "monospace"
                            font.pixelSize: 12
                            font.bold: true
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.runPolymarketQuery()
                            }
                        }
                        Text {
                            text: "RESET"
                            color: "#c8a97e"
                            font.family: "monospace"
                            font.pixelSize: 12
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.resetPolymarketQuery()
                            }
                        }
                    }

                    Text {
                        width: polyCol.width
                        text: {
                            var state = String(root.polymarket.state || "IDLE").toUpperCase()
                            var mode = String(root.polymarket.preset || root.polyPreset || "SUMMARY")
                            return "STATE · " + state + "  ·  " + mode
                        }
                        color: root.polyRunning ? "#c8a97e" : "#c8cdd4"
                        font.family: "monospace"
                        font.pixelSize: 12
                    }
                    Text {
                        width: polyCol.width
                        text: String(root.polymarket.note || "")
                        visible: text.length > 0
                        color: String(root.polymarket.state || "") === "error" ? "#c98989" : "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        width: polyCol.width
                        text: "ARCHIVE · " + String(root.polymarket.url || "")
                        visible: String(root.polymarket.url || "").length > 0
                        color: "#8fa8a0"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WrapAnywhere
                    }
                    Text {
                        width: polyCol.width
                        text: "SQL PREVIEW\n" + String(root.polymarket.sql || "")
                        visible: String(root.polymarket.sql || "").length > 0
                        color: "#7f8994"
                        font.family: "monospace"
                        font.pixelSize: 11
                        wrapMode: Text.WrapAnywhere
                    }
                    Text {
                        width: polyCol.width
                        text: ((root.polyResult || {}).lines || []).join("\n")
                        visible: ((root.polyResult || {}).lines || []).length > 0
                        color: "#c8cdd4"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WrapAnywhere
                    }
                    Text {
                        width: polyCol.width
                        visible: !root.polyRunning
                            && ((root.polyResult || {}).lines || []).length === 0
                            && String(root.polymarket.state || "") !== "error"
                        text: "No result yet. SUMMARY and TRADES need only a UTC hour; TOUCH also needs a market slug."
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        width: polyCol.width
                        text: "POLY_DATA · " + String((root.polymarket.poly_data || {}).state || "OPTIONAL")
                            + "\n" + String((root.polymarket.poly_data || {}).note || "")
                        color: "#7f8994"
                        font.family: "monospace"
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
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
