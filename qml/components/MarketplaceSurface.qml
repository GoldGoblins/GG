import QtQuick
import QtQuick.Controls

Item {
    id: root
    objectName: "workspaceMarketplacePane"

    property var surfaceHost: null
    property color frameBorder: "#6a6a6a"
    property int frameRadius: 4
    property string statusJson: "{}"
    property string page: "CATALOG"
    property string draftCategory: "MATERIAL"
    property string draftMaterial: "UNKNOWN"
    property string formError: ""
    readonly property var nav: [
        "CATALOG",
        "CATEGORIES",
        "LIST",
        "PROVENANCE",
        "ACTIVITY"
    ]

    readonly property var status: {
        try {
            return JSON.parse(root.statusJson || "{}")
        } catch (err) {
            return {}
        }
    }

    readonly property var listings: {
        var rows = root.status.listings
        if (rows && rows.length !== undefined)
            return rows
        return []
    }
    readonly property var categories: {
        var rows = root.status.categories
        if (rows && rows.length !== undefined && rows.length > 0)
            return rows
        return [
            {"id": "MATERIAL", "label": "MATERIAL", "count": 0, "root_short": "empty"},
            {"id": "ITEM", "label": "ITEM", "count": 0, "root_short": "empty"},
            {"id": "ART", "label": "ART", "count": 0, "root_short": "empty"},
            {"id": "COLLECTIBLE", "label": "COLLECTIBLE", "count": 0, "root_short": "empty"},
            {"id": "DOCUMENT", "label": "DOCUMENT", "count": 0, "root_short": "empty"},
            {"id": "TOOL", "label": "TOOL", "count": 0, "root_short": "empty"},
            {"id": "COMPONENT", "label": "COMPONENT", "count": 0, "root_short": "empty"}
        ]
    }
    readonly property var ledger: {
        var rows = root.status.ledger
        if (rows && rows.length !== undefined)
            return rows
        return []
    }
    readonly property var filters: {
        var rows = root.status.filters
        if (rows && rows.length !== undefined && rows.length > 0)
            return rows
        return [
            "ALL",
            "MATERIAL",
            "ITEM",
            "ART",
            "COLLECTIBLE",
            "DOCUMENT",
            "TOOL",
            "COMPONENT"
        ]
    }
    readonly property var materials: {
        var rows = root.status.materials
        if (rows && rows.length !== undefined && rows.length > 0)
            return rows
        return [
            "GOLD",
            "SILVER",
            "COPPER",
            "WOOD",
            "STONE",
            "FABRIC",
            "METAL",
            "DIGITAL",
            "MIXED",
            "UNKNOWN"
        ]
    }
    readonly property var wallet: root.status.wallet || {}
    readonly property var merkle: root.status.merkle || {}
    readonly property var selected: root.status.selected || null
    readonly property var proof: root.status.proof || null
    readonly property string legend: String(root.status.legend || "TESTNET")
    readonly property string activeFilter: String(root.status.filter || "ALL")
    readonly property bool connected: root.wallet.connected === true

    function refresh() {
        if (!root.surfaceHost || !root.surfaceHost.marketplaceStatus)
            return
        var raw = root.surfaceHost.marketplaceStatus()
        if (raw === root.statusJson)
            return
        root.statusJson = raw
        root.formError = String(root.status.error || "")
    }

    function applyRaw(raw) {
        root.statusJson = String(raw || "{}")
        root.formError = String(root.status.error || "")
    }

    function setFilter(name) {
        if (!root.surfaceHost || !root.surfaceHost.marketplaceSetFilter)
            return
        root.applyRaw(root.surfaceHost.marketplaceSetFilter(name))
    }

    function selectRow(listingId) {
        if (!root.surfaceHost || !root.surfaceHost.marketplaceSelect)
            return
        root.applyRaw(root.surfaceHost.marketplaceSelect(listingId))
        root.page = "PROVENANCE"
    }

    function submitList() {
        if (!root.surfaceHost || !root.surfaceHost.marketplaceList)
            return
        root.applyRaw(
            root.surfaceHost.marketplaceList(
                JSON.stringify({
                    "title": titleField.text,
                    "category": root.draftCategory,
                    "material": root.draftMaterial,
                    "mint": mintField.text,
                    "price_sol": priceField.text,
                    "description": descField.text
                })
            )
        )
        if (!root.formError) {
            titleField.text = ""
            mintField.text = ""
            priceField.text = "0"
            descField.text = ""
            root.page = "PROVENANCE"
        }
    }

    function delistSelected() {
        if (!root.surfaceHost || !root.surfaceHost.marketplaceDelist)
            return
        if (!root.selected)
            return
        root.applyRaw(
            root.surfaceHost.marketplaceDelist(String(root.selected.id || ""))
        )
    }

    function buySelected() {
        if (!root.surfaceHost || !root.surfaceHost.marketplacePaperBuy)
            return
        if (!root.selected)
            return
        root.applyRaw(
            root.surfaceHost.marketplacePaperBuy(String(root.selected.id || ""))
        )
    }

    function shortHash(value) {
        var t = String(value || "")
        if (t.length < 12)
            return t.length ? t : "—"
        return t.substring(0, 8) + "…" + t.substring(t.length - 4)
    }

    function statusColor(value) {
        var s = String(value || "")
        if (s === "LISTED")
            return "#8db89a"
        if (s === "SOLD")
            return "#c8a97e"
        if (s === "DELISTED")
            return "#c98989"
        return "#a8b0b8"
    }

    Timer {
        interval: 4000
        running: root.visible
        repeat: true
        onTriggered: root.refresh()
    }

    onVisibleChanged: {
        if (visible)
            root.refresh()
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
                    text: root.legend
                    color: root.legend === "TESTNET" ? "#8db89a" : "#c8a97e"
                    font.family: "monospace"
                    font.pixelSize: 12
                    font.bold: true
                }
                Text {
                    text: root.connected
                        ? String(root.wallet.short || "")
                        : "WALLET OFF"
                    color: root.connected ? "#c8cdd4" : "#c8a97e"
                    font.family: "monospace"
                    font.pixelSize: 12
                }
                Text {
                    text: "MERKLE " + String(root.merkle.root_short || "—")
                    color: "#b6a6c8"
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
                id: catalogHead
                width: parent.width
                spacing: 6
                visible: root.page === "CATALOG"

                Flow {
                    width: parent.width
                    spacing: 10
                    Repeater {
                        model: root.filters
                        Text {
                            required property string modelData
                            text: modelData
                            color: root.activeFilter === modelData ? "#d8dee9" : "#5d6670"
                            font.family: "monospace"
                            font.pixelSize: 12
                            font.bold: root.activeFilter === modelData
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.setFilter(modelData)
                            }
                        }
                    }
                }

                Text {
                    text: String(root.status.visible_count || 0)
                        + " / "
                        + String(root.status.listing_count || 0)
                        + " listings · solana catalog"
                    color: "#a8b0b8"
                    font.family: "monospace"
                    font.pixelSize: 12
                }
            }

            Flickable {
                anchors.fill: parent
                anchors.topMargin: catalogHead.visible ? catalogHead.height + 6 : 0
                visible: root.page === "CATALOG"
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                contentHeight: catalogCol.height
                ScrollBar.vertical: GgScrollBar {}

                Column {
                    id: catalogCol
                    width: parent.width
                    spacing: 8

                    Text {
                        visible: root.listings.length === 0
                        width: parent.width
                        text: "No listings yet. Open LIST and register a material or item. Each listing hashes into the Solana catalog merkle tree."
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }

                    Repeater {
                        model: root.listings.length
                        delegate: Rectangle {
                            required property int index
                            width: catalogCol.width
                            height: Math.max(52, listingCol.height + 12)
                            color: root.selected && String(root.selected.id || "")
                                   === String((root.listings[index] || {}).id || "")
                                ? "#1a1a1a"
                                : "#121212"
                            border.width: 1
                            border.color: "#2a2a2a"
                            radius: 2

                            Column {
                                id: listingCol
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.leftMargin: 8
                                anchors.rightMargin: 8
                                spacing: 2

                                Row {
                                    spacing: 10
                                    Text {
                                        text: String((root.listings[index] || {}).title || "")
                                        color: "#e6e6e6"
                                        font.family: "monospace"
                                        font.pixelSize: 13
                                        font.bold: true
                                    }
                                    Text {
                                        text: String((root.listings[index] || {}).status || "")
                                        color: root.statusColor((root.listings[index] || {}).status)
                                        font.family: "monospace"
                                        font.pixelSize: 12
                                        font.bold: true
                                    }
                                    Text {
                                        text: String((root.listings[index] || {}).price_sol || "0") + " SOL"
                                        color: "#c8a97e"
                                        font.family: "monospace"
                                        font.pixelSize: 12
                                    }
                                }
                                Text {
                                    width: listingCol.width
                                    text: String((root.listings[index] || {}).category || "")
                                        + " · "
                                        + String((root.listings[index] || {}).material || "")
                                        + " · mint "
                                        + String((root.listings[index] || {}).mint_short || "UNBOUND")
                                        + " · "
                                        + String((root.listings[index] || {}).identity_short || "")
                                    color: "#a8b0b8"
                                    font.family: "monospace"
                                    font.pixelSize: 12
                                    wrapMode: Text.WordWrap
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.selectRow(String((root.listings[index] || {}).id || ""))
                            }
                        }
                    }
                }
            }

            Flickable {
                anchors.fill: parent
                visible: root.page === "CATEGORIES"
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                contentHeight: catCol.height
                ScrollBar.vertical: GgScrollBar {}

                Column {
                    id: catCol
                    width: parent.width
                    spacing: 8

                    Text {
                        width: parent.width
                        text: "Category subtrees under "
                            + String(root.merkle.domain || "MARKETPLACE")
                            + " / "
                            + String(root.merkle.scope || "solana.catalog")
                            + ". Root "
                            + root.shortHash(root.merkle.root_sha256)
                        color: "#c8cdd4"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }

                    Repeater {
                        model: root.categories.length
                        delegate: Rectangle {
                            required property int index
                            width: catCol.width
                            height: 44
                            color: "#121212"
                            border.width: 1
                            border.color: "#2a2a2a"
                            radius: 2

                            Row {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.leftMargin: 8
                                anchors.rightMargin: 8
                                spacing: 12

                                Text {
                                    width: 120
                                    text: String((root.categories[index] || {}).label || "")
                                    color: "#d8dee9"
                                    font.family: "monospace"
                                    font.pixelSize: 12
                                    font.bold: true
                                }
                                Text {
                                    width: 64
                                    text: String((root.categories[index] || {}).count || 0)
                                    color: "#c8a97e"
                                    font.family: "monospace"
                                    font.pixelSize: 12
                                }
                                Text {
                                    text: String((root.categories[index] || {}).root_short || "empty")
                                    color: "#b6a6c8"
                                    font.family: "monospace"
                                    font.pixelSize: 12
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    root.setFilter(String((root.categories[index] || {}).id || "ALL"))
                                    root.page = "CATALOG"
                                }
                            }
                        }
                    }
                }
            }

            Flickable {
                anchors.fill: parent
                visible: root.page === "LIST"
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                contentHeight: listCol.height
                ScrollBar.vertical: GgScrollBar {}

                Column {
                    id: listCol
                    width: parent.width
                    spacing: 8

                    Text {
                        width: parent.width
                        text: "Register a material or item. Optional mint binds it to a Solana NFT. Listing is paper/testnet until trade authority exists."
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        text: "TITLE"
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                    }
                    GgField {
                        id: titleField
                        width: Math.min(listCol.width, 520)
                        placeholderText: "item or material name"
                    }

                    Text {
                        text: "CATEGORY"
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                    }
                    Flow {
                        width: parent.width
                        spacing: 10
                        Repeater {
                            model: root.categories.length
                            Text {
                                required property int index
                                text: String((root.categories[index] || {}).id || "")
                                color: root.draftCategory
                                       === String((root.categories[index] || {}).id || "")
                                    ? "#d8dee9" : "#5d6670"
                                font.family: "monospace"
                                font.pixelSize: 12
                                font.bold: root.draftCategory
                                           === String((root.categories[index] || {}).id || "")
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.draftCategory = String(
                                        (root.categories[index] || {}).id || "MATERIAL"
                                    )
                                }
                            }
                        }
                    }

                    Text {
                        text: "MATERIAL"
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                    }
                    Flow {
                        width: parent.width
                        spacing: 10
                        Repeater {
                            model: root.materials
                            Text {
                                required property string modelData
                                text: modelData
                                color: root.draftMaterial === modelData ? "#d8dee9" : "#5d6670"
                                font.family: "monospace"
                                font.pixelSize: 12
                                font.bold: root.draftMaterial === modelData
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.draftMaterial = modelData
                                }
                            }
                        }
                    }

                    Text {
                        text: "SOLANA MINT (optional)"
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                    }
                    GgField {
                        id: mintField
                        width: Math.min(listCol.width, 520)
                        placeholderText: "base58 mint pubkey"
                    }

                    Text {
                        text: "PRICE SOL"
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                    }
                    GgField {
                        id: priceField
                        width: 160
                        text: "0"
                        placeholderText: "0"
                    }

                    Text {
                        text: "DESCRIPTION"
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                    }
                    GgField {
                        id: descField
                        width: Math.min(listCol.width, 520)
                        placeholderText: "what it is and where it came from"
                    }

                    Text {
                        visible: root.formError.length > 0
                        width: parent.width
                        text: root.formError
                        color: "#c98989"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }

                    GgButton {
                        text: "LIST ITEM"
                        onClicked: root.submitList()
                    }
                }
            }

            Flickable {
                anchors.fill: parent
                visible: root.page === "PROVENANCE"
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                contentHeight: proofCol.height
                ScrollBar.vertical: GgScrollBar {}

                Column {
                    id: proofCol
                    width: parent.width
                    spacing: 6

                    Text {
                        visible: root.selected === null
                        width: parent.width
                        text: "Select a listing in CATALOG to see its merkle path."
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        visible: root.selected !== null
                        text: String((root.selected || {}).title || "")
                        color: "#e6e6e6"
                        font.family: "monospace"
                        font.pixelSize: 18
                        font.bold: true
                    }
                    Text {
                        visible: root.selected !== null
                        text: String((root.selected || {}).category || "")
                            + " · "
                            + String((root.selected || {}).material || "")
                            + " · "
                            + String((root.selected || {}).status || "")
                            + " · "
                            + String((root.selected || {}).price_sol || "0")
                            + " SOL"
                        color: "#c8cdd4"
                        font.family: "monospace"
                        font.pixelSize: 12
                    }
                    Text {
                        visible: root.selected !== null
                        width: parent.width
                        text: String((root.selected || {}).description || "")
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        visible: root.selected !== null
                        width: parent.width
                        text: "identity  " + String((root.proof || {}).identity_sha256 || "")
                        color: "#b6a6c8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WrapAnywhere
                    }
                    Text {
                        visible: root.selected !== null
                        width: parent.width
                        text: "state     " + String((root.proof || {}).state_sha256 || "")
                        color: "#b6a6c8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WrapAnywhere
                    }
                    Text {
                        visible: root.selected !== null
                        width: parent.width
                        text: "category  "
                            + String((root.proof || {}).category || "")
                            + "  "
                            + String((root.proof || {}).category_root || "")
                        color: "#b6a6c8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WrapAnywhere
                    }
                    Text {
                        visible: root.selected !== null
                        width: parent.width
                        text: "catalog   " + String((root.proof || {}).catalog_root || "")
                        color: "#b6a6c8"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WrapAnywhere
                    }
                    Text {
                        visible: root.selected !== null
                        width: parent.width
                        text: "mint      "
                            + (String((root.selected || {}).mint || "") || "UNBOUND")
                        color: "#c8cdd4"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WrapAnywhere
                    }
                    Text {
                        visible: root.selected !== null
                        width: parent.width
                        text: "owner     "
                            + (String((root.selected || {}).owner || "") || "unowned")
                        color: "#c8cdd4"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WrapAnywhere
                    }

                    Row {
                        visible: root.selected !== null
                            && String((root.selected || {}).status || "") === "LISTED"
                        spacing: 10
                        GgButton {
                            text: "PAPER BUY"
                            onClicked: root.buySelected()
                        }
                        GgButton {
                            text: "DELIST"
                            onClicked: root.delistSelected()
                        }
                    }

                    Text {
                        visible: root.formError.length > 0 && root.page === "PROVENANCE"
                        width: parent.width
                        text: root.formError
                        color: "#c98989"
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                }
            }

            Flickable {
                anchors.fill: parent
                visible: root.page === "ACTIVITY"
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                contentHeight: actCol.height
                ScrollBar.vertical: GgScrollBar {}

                Column {
                    id: actCol
                    width: parent.width
                    spacing: 6

                    Text {
                        visible: root.ledger.length === 0
                        text: "No catalog events yet."
                        color: "#a8b0b8"
                        font.family: "monospace"
                        font.pixelSize: 12
                    }

                    Repeater {
                        model: root.ledger.length
                        delegate: Row {
                            required property int index
                            width: actCol.width
                            spacing: 10
                            readonly property var row: root.ledger[root.ledger.length - 1 - index] || {}

                            Text {
                                width: 64
                                text: String(row.kind || "")
                                color: String(row.kind || "") === "BUY"
                                    ? "#8db89a"
                                    : (String(row.kind || "") === "DELIST"
                                        ? "#c98989"
                                        : "#c8a97e")
                                font.family: "monospace"
                                font.pixelSize: 12
                                font.bold: true
                            }
                            Text {
                                width: parent.width - 74
                                text: String(row.listing_id || "")
                                    + "  "
                                    + String(row.txid || "PAPER")
                                    + "  "
                                    + root.shortHash(row.identity_sha256)
                                color: "#c8cdd4"
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
