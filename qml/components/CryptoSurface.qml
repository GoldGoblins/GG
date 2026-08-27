import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs

Item {
    id: root
    objectName: "workspaceCryptoPane"

    property var surfaceHost: null
    property color frameBorder: "#6a6a6a"
    property int frameRadius: 2
    property string statusJson: "{}"
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
    readonly property var ledger: root.status.ledger || []
    readonly property string legend: String(root.status.legend || "TESTNET")
    readonly property string rpc: String(root.status.rpc || "")

    function refresh() {
        if (!root.surfaceHost)
            return
        root.statusJson = root.surfaceHost.cryptoStatus()
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

    Timer {
        interval: 20000
        running: root.visible
        repeat: true
        onTriggered: root.refresh()
    }

    onVisibleChanged: {
        if (visible)
            root.refresh()
    }

    GgFrame {
        anchors.fill: parent
        anchors.margins: 10
        leftLegend: "CRYPTO"
        rightLegend: root.legend
        backgroundColor: "#161616"
        borderColor: root.frameBorder
        radius: root.frameRadius

        Column {
            width: parent.width
            spacing: 8

            Text {
                width: parent.width
                text: {
                    var lab = root.status.lab || {}
                    var node = String(lab.label || "LAB OFF")
                    if (root.legend === "MAINNET")
                        return "MAINNET · not armed · " + node
                    return "TESTNET · 127.0.0.1:8899 · " + node
                }
                color: "#8b949e"
                font.family: "monospace"
                font.pixelSize: 10
                wrapMode: Text.WordWrap
            }

            Row {
                spacing: 12
                Text {
                    text: "TESTNET"
                    color: root.legend === "TESTNET" ? "#d8dee9" : "#5d6670"
                    font.family: "monospace"
                    font.pixelSize: 10
                    font.bold: root.legend === "TESTNET"
                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            if (root.surfaceHost)
                                root.surfaceHost.cryptoSetNetwork("testnet")
                            root.refresh()
                        }
                    }
                }
                Text {
                    text: "MAINNET"
                    color: root.legend === "MAINNET" ? "#d8dee9" : "#5d6670"
                    font.family: "monospace"
                    font.pixelSize: 10
                    font.bold: root.legend === "MAINNET"
                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            if (root.surfaceHost)
                                root.surfaceHost.cryptoSetNetwork("mainnet")
                            root.refresh()
                        }
                    }
                }
                Text {
                    text: root.status.signer ? "SIGNER · ON DISK" : "SIGNER · NONE"
                    color: root.status.signer ? "#8db89a" : "#8b949e"
                    font.family: "monospace"
                    font.pixelSize: 10
                }
                Text {
                    text: "LAB ON"
                    color: (root.status.lab && root.status.lab.running)
                        ? "#5d6670"
                        : "#8db89a"
                    font.family: "monospace"
                    font.pixelSize: 10
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (root.surfaceHost)
                                root.statusJson = root.surfaceHost.cryptoLabOn()
                            root.refresh()
                        }
                    }
                }
                Text {
                    text: "LAB OFF"
                    color: (root.status.lab && root.status.lab.running)
                        ? "#c8a97e"
                        : "#5d6670"
                    font.family: "monospace"
                    font.pixelSize: 10
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (root.surfaceHost)
                                root.statusJson = root.surfaceHost.cryptoLabOff()
                            root.refresh()
                        }
                    }
                }
            }

            Row {
                spacing: 8
                width: parent.width

                TextField {
                    id: pubkeyField
                    width: Math.min(460, Math.max(180, parent.width - 90))
                    height: 26
                    placeholderText: "Solana pubkey"
                    text: String(root.wallet.pubkey || "")
                    color: "#e6e6e6"
                    font.family: "monospace"
                    font.pixelSize: 11
                    background: Rectangle {
                        color: "#161616"
                        border.color: root.frameBorder
                    }
                }

                Text {
                    text: "CONNECT"
                    color: "#c8a97e"
                    font.family: "monospace"
                    font.pixelSize: 10
                    anchors.verticalCenter: parent.verticalCenter
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.connectWatch()
                    }
                }
            }

            Row {
                spacing: 14
                Text {
                    text: "CREATE TEST WALLET"
                    color: "#c8a97e"
                    font.family: "monospace"
                    font.pixelSize: 10
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
                    text: "AIRDROP"
                    color: "#8db89a"
                    font.family: "monospace"
                    font.pixelSize: 10
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
                    font.pixelSize: 10
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: keypairDialog.open()
                    }
                }
                Text {
                    text: "TEST BUY 0.01 SOL"
                    color: "#8db89a"
                    font.family: "monospace"
                    font.pixelSize: 10
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.paperSignal()
                    }
                }
                Text {
                    text: "EVAL SIGNALS"
                    color: "#c8a97e"
                    font.family: "monospace"
                    font.pixelSize: 10
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
                    text: (root.status.trader && root.status.trader.armed)
                        ? "TRADER OFF"
                        : "ARM TRADER"
                    color: (root.status.trader && root.status.trader.armed)
                        ? "#c8a97e"
                        : "#8db89a"
                    font.family: "monospace"
                    font.pixelSize: 10
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (!root.surfaceHost)
                                return
                            var on = !(root.status.trader && root.status.trader.armed)
                            root.statusJson = root.surfaceHost.cryptoArmTrader(on)
                            root.refresh()
                        }
                    }
                }
                Text {
                    text: "TICK TRADER"
                    color: "#c8a97e"
                    font.family: "monospace"
                    font.pixelSize: 10
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
                    text: "FLASH ARB"
                    color: "#8db89a"
                    font.family: "monospace"
                    font.pixelSize: 10
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
                    font.pixelSize: 10
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
                Text {
                    text: (root.status.bot && root.status.bot.armed)
                        ? "ARM OFF"
                        : "ARM BOT"
                    color: (root.status.bot && root.status.bot.armed)
                        ? "#c8a97e"
                        : "#8b949e"
                    font.family: "monospace"
                    font.pixelSize: 10
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (!root.surfaceHost)
                                return
                            var on = !(root.status.bot && root.status.bot.armed)
                            root.statusJson = root.surfaceHost.cryptoArmBot(on)
                            root.refresh()
                        }
                    }
                }
            }

            Timer {
                interval: 30000
                running: root.visible && root.status.bot && root.status.bot.armed
                repeat: true
                onTriggered: {
                    if (root.surfaceHost)
                        root.statusJson = root.surfaceHost.cryptoTickBot()
                    root.refresh()
                }
            }

            Timer {
                interval: 120000
                running: root.visible && root.status.trader && root.status.trader.armed
                repeat: true
                onTriggered: {
                    if (root.surfaceHost)
                        root.statusJson = root.surfaceHost.cryptoTickTrader()
                    root.refresh()
                }
            }

            Text {
                width: parent.width
                text: {
                    var bot = root.status.bot || {}
                    var last = bot.last || {}
                    if (!last.super && last.super !== "none")
                        return "SIGNAL  —  Strategy004 (freqtrade) on SOLUSDT 5m. EVAL then ARM for lab fill."
                    var line = "SIGNAL  " + String(last.super || "none")
                        + "  votes " + String(last.buy_votes) + "/" + String(last.sell_votes)
                    if (last.rsi14 !== undefined && last.rsi14 !== null)
                        line += "  RSI " + String(last.rsi14)
                    var notes = last.notes || []
                    if (notes.length)
                        line += "\n" + notes.join(" · ")
                    if (bot.armed)
                        line += "\nARMED · ticks 30s · lab fill if super buy/sell"
                    return line
                }
                color: "#8b949e"
                font.family: "monospace"
                font.pixelSize: 9
                wrapMode: Text.WordWrap
            }

            Text {
                width: parent.width
                text: {
                    var t = root.status.trader || {}
                    var last = t.last || {}
                    var line = "TRADER  " + String(t.regime || "range")
                        + "  tokens " + String(t.tokens || "0")
                        + "  banked " + String(t.banked_sol || "0")
                        + "  cash " + String(t.usd || "0")
                        + "  day " + String(t.trades_today || 0) + "/" + String(t.max_day || 12)
                    if (last.note)
                        line += "\n" + String(last.action || "") + "  " + String(last.note)
                    return line
                }
                color: "#8b949e"
                font.family: "monospace"
                font.pixelSize: 9
                wrapMode: Text.WordWrap
            }

            Text {
                width: parent.width
                text: {
                    var arb = root.status.arb || {}
                    var last = root.status.arb_last || {}
                    var line = "ARB  A " + String(arb.price_a || "—")
                        + "  B " + String(arb.price_b || "—")
                        + "  USDC/SOL"
                    if (last.txid)
                        line += "\nLAST  " + String(last.txid)
                    if (last.profit)
                        line += "  profit " + String(last.profit)
                    if (last.error)
                        line += "  " + String(last.error)
                    if (last.hint)
                        line += "\n" + String(last.hint)
                    return line
                }
                color: "#8b949e"
                font.family: "monospace"
                font.pixelSize: 9
                wrapMode: Text.WordWrap
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

            Text {
                text: "HOLDINGS"
                color: "#6a6a6a"
                font.family: "monospace"
                font.pixelSize: 8
            }

            Flickable {
                width: parent.width
                height: 140
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                flickableDirection: Flickable.VerticalFlick
                contentWidth: width
                contentHeight: holdCol.height
                interactive: contentHeight > height

                Column {
                    id: holdCol
                    width: parent.width
                    spacing: 6

                    Text {
                        visible: root.holdings.length === 0
                        text: "NO HOLDINGS"
                        color: "#6a6a6a"
                        font.family: "monospace"
                        font.pixelSize: 10
                    }

                    Repeater {
                        model: root.holdings.length
                        delegate: Column {
                            width: holdCol.width
                            spacing: 1
                            readonly property var row: root.holdings[index] || {}
                            Text {
                                width: parent.width
                                text: String(row.symbol || "")
                                color: "#8b949e"
                                font.family: "monospace"
                                font.pixelSize: 8
                            }
                            Text {
                                width: parent.width
                                text: String(row.display || "")
                                color: "#d8dee9"
                                font.family: "monospace"
                                font.pixelSize: 12
                                wrapMode: Text.WrapAnywhere
                            }
                            Text {
                                width: parent.width
                                text: "dp " + String(row.decimals || "")
                                color: "#6a6a6a"
                                font.family: "monospace"
                                font.pixelSize: 8
                            }
                        }
                    }
                }

                ScrollBar.vertical: ScrollBar {
                    policy: ScrollBar.AsNeeded
                }
            }

            Text {
                text: "ACTIVITY"
                color: "#6a6a6a"
                font.family: "monospace"
                font.pixelSize: 8
            }

            Flickable {
                width: parent.width
                height: 160
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                flickableDirection: Flickable.VerticalFlick
                contentWidth: width
                contentHeight: ledCol.height
                interactive: contentHeight > height

                Column {
                    id: ledCol
                    width: parent.width
                    spacing: 6

                    Text {
                        visible: root.ledger.length === 0
                        text: "NO FILLS"
                        color: "#6a6a6a"
                        font.family: "monospace"
                        font.pixelSize: 10
                    }

                    Repeater {
                        model: root.ledger.length
                        delegate: Text {
                            width: ledCol.width
                            readonly property var row: root.ledger[index] || {}
                            text: {
                                var line = String(row.side || "")
                                    + "  " + String(row.txid || "")
                                if (row.error)
                                    line += "\n" + String(row.error)
                                return line
                            }
                            color: row.error ? "#b08080" : "#8b949e"
                            font.family: "monospace"
                            font.pixelSize: 9
                            wrapMode: Text.WrapAnywhere
                        }
                    }
                }

                ScrollBar.vertical: ScrollBar {
                    policy: ScrollBar.AsNeeded
                }
            }
        }
    }
}
