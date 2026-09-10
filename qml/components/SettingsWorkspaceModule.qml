pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls

Item {
    id: root

    property bool showInnerEditorChrome: true
    property string hostKind: "CODE"
    signal showInnerEditorChromeChangedByUser(bool value)
    signal hostKindChangedByUser(string value)
    signal spawnInstanceRequested()

    implicitHeight: 208

    GgFrame {
        anchors.fill: parent
        leftLegend: "WORKSPACE"
        rightLegend: "NAMED SURFACES"
        backgroundColor: "#161616"
        borderColor: "#6a6a6a"
    }

    Column {
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 14
        anchors.topMargin: 22
        anchors.bottomMargin: 12
        spacing: 8

        Text {
            text: "Host"
            color: "#d8dee9"
            font.family: "monospace"
            font.pixelSize: 12
        }

        Row {
            spacing: 0
            height: 18

            Repeater {
                model: ["CODE", "TERMINAL", "WEB", "EXTERNAL", "SITE", "CRYPTO", "MARKETPLACE", "TMOG", "OSINT", "QIP", "MEDIA", "DRAW", "GAME_ENGINE", "NODES", "FLOW"]

                delegate: Text {
                    required property string modelData
                    required property int index
                    text: (index === 0 ? "" : " | ")
                        + (modelData === "GAME_ENGINE" ? "GAME ENGINE" : modelData)
                    color: root.hostKind === modelData
                        ? "#d8dee9"
                        : "#5d6670"
                    font.family: "monospace"
                    font.pixelSize: 12
                    font.bold: root.hostKind === modelData

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.hostKindChangedByUser(modelData)
                    }
                }
            }
        }

        Row {
            spacing: 10

            GgCheck {
                id: innerChromeBox
                text: "Show inner CODE frame"
                checked: root.showInnerEditorChrome
                onToggled:
                    root.showInnerEditorChromeChangedByUser(
                        innerChromeBox.checked
                    )
            }

            GgButton {
                text: "New tab +"
                onClicked: root.spawnInstanceRequested()
            }
        }

        Text {
            width: parent.width
            text: "Same as the workspace footer and top tabs. "
                + "WEB is your browser in this box. SITE is the local "
                + "WordPress copy (files + MariaDB 3307). PREVIEW runs "
                + "PHP on 127.0.0.1 only. After you approve the requested "
                + "task in chat, network, production and one.com actions "
                + "can use the visible operator flow. EXTERNAL "
                + "stays honest until a "
                + "window embed exists. MEDIA is playlists, radio, TV "
                + "and older-console games; the bottom strip is the player. "
                + "DRAW hosts Krita, GIMP, Inkscape or darktable in this box "
                + "when they are on PATH, plus a small sketch pad. OSINT is "
                + "the native OSIRIS public-feed dashboard; its RECON page "
                + "stays read-only and target-free. QIP is a local-only WASM "
                + "component lab; host imports and I/O stay blocked. GAME ENGINE "
                + "is a separate local Quick3D playground with fixed-step "
                + "simulation, bounded pools and deterministic replay. NODES is "
                + "the Geometry Nodes-style editor for agent and information "
                + "streams: blocks, edge ports, and wires on the machine graph."
            color: "#8a8a8a"
            wrapMode: Text.WordWrap
            font.pixelSize: 12
        }
    }
}
