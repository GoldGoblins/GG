import QtQuick

Row {
    id: root
    property string status: "IDLE"
    property int diagnosticCount: 0
    property int unresolvedCount: 0
    spacing: 8

    Text {
        text: "LIVE AID · " + root.status
        color: "#8b949e"
        font.family: "monospace"
        font.pixelSize: 9
        font.bold: true
    }
    Text {
        text: "diagnostics " + root.diagnosticCount + " · unresolved " + root.unresolvedCount
        color: "#7d8590"
        font.family: "monospace"
        font.pixelSize: 9
    }
}
