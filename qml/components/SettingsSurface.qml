pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls

Item {
    id: root

    objectName: "workspaceSettingsSurface"

    property real chatWidthRatio: 0.31
    property int telemetryWidth: 168
    property color accentColor: "#8a8a8a"
    property color frameBorder: "#6a6a6a"
    property int frameRadius: 2
    property bool showDemoFixtures: false
    property bool showProductSourceTabs: false
    property bool showOpenTabInInput: false
    property bool showInnerEditorChrome: true
    property string hostKind: "CODE"
    property string engineTarget: "LOCAL_QWEN"
    property int utilityHeight: 112
    readonly property string themeId: "obsidian-ledger-standard"

    signal chatWidthRatioChangedByUser(real value)
    signal telemetryWidthChangedByUser(int value)
    signal accentColorChangedByUser(color value)
    signal frameBorderChangedByUser(color value)
    signal frameRadiusChangedByUser(int value)
    signal demoVisibilityChangedByUser(bool value)
    signal productSourceTabsChangedByUser(bool value)
    signal showOpenTabInInputChangedByUser(bool value)
    signal showInnerEditorChromeChangedByUser(bool value)
    signal hostKindChangedByUser(string value)
    signal spawnInstanceRequested()
    signal engineTargetChangedByUser(string value)
    signal utilityHeightChangedByUser(int value)
    signal closeRequested()

    implicitWidth: 620
    implicitHeight: 560

    GgFrame {
        id: settingsChrome
        anchors.fill: parent
        leftLegend: "SETTINGS"
        rightLegend: "OBSIDIAN / LEDGER STANDARD"
        backgroundColor: "#161616"
        borderColor: root.frameBorder
        radius: root.frameRadius
    }

    Flickable {
        id: settingsFlick
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 14
        anchors.topMargin: 22
        anchors.bottomMargin: 14
        clip: true
        contentWidth: width
        contentHeight: modulesColumn.implicitHeight
        flickableDirection: Flickable.VerticalFlick
        boundsBehavior: Flickable.StopAtBounds

        ScrollBar.vertical: ScrollBar {}

        Column {
            id: modulesColumn
            width: settingsFlick.width
            spacing: 10

            Text {
                width: parent.width
                text: "Settings modules are separated by concern. "
                    + "Only controls with real alpha wiring are interactive."
                color: "#8b949e"
                wrapMode: Text.WordWrap
                font.pixelSize: 11
            }

            SettingsAppearanceModule {
                width: parent.width
                accentColor: root.accentColor
                frameBorder: root.frameBorder
                frameRadius: root.frameRadius

                onAccentColorChangedByUser: function(value) {
                    root.accentColorChangedByUser(value)
                }

                onFrameBorderChangedByUser: function(value) {
                    root.frameBorderChangedByUser(value)
                }

                onFrameRadiusChangedByUser: function(value) {
                    root.frameRadiusChangedByUser(value)
                }
            }

            SettingsLayoutModule {
                width: parent.width
                chatWidthRatio: root.chatWidthRatio
                telemetryWidth: root.telemetryWidth
                utilityHeight: root.utilityHeight

                onChatWidthRatioChangedByUser: function(value) {
                    root.chatWidthRatioChangedByUser(value)
                }

                onTelemetryWidthChangedByUser: function(value) {
                    root.telemetryWidthChangedByUser(value)
                }

                onUtilityHeightChangedByUser: function(value) {
                    root.utilityHeightChangedByUser(value)
                }
            }

            SettingsChatModule {
                width: parent.width
                showOpenTabInInput: root.showOpenTabInInput
                engineTarget: root.engineTarget

                onShowOpenTabInInputChangedByUser: function(value) {
                    root.showOpenTabInInputChangedByUser(value)
                }

                onEngineTargetChangedByUser: function(value) {
                    root.engineTargetChangedByUser(value)
                }
            }

            SettingsWorkspaceModule {
                width: parent.width
                showInnerEditorChrome: root.showInnerEditorChrome
                hostKind: root.hostKind

                onShowInnerEditorChromeChangedByUser: function(value) {
                    root.showInnerEditorChromeChangedByUser(value)
                }

                onHostKindChangedByUser: function(value) {
                    root.hostKindChangedByUser(value)
                }

                onSpawnInstanceRequested: root.spawnInstanceRequested()
            }

            SettingsActivityModule {
                width: parent.width
            }

            SettingsDeveloperModule {
                width: parent.width
                showDemoFixtures: root.showDemoFixtures
                showProductSourceTabs: root.showProductSourceTabs

                onDemoVisibilityChangedByUser: function(value) {
                    root.demoVisibilityChangedByUser(value)
                }

                onProductSourceTabsChangedByUser: function(value) {
                    root.productSourceTabsChangedByUser(value)
                }
            }

            SettingsExtensionsModule {
                width: parent.width
            }

            Row {
                width: parent.width
                height: 44
                spacing: 8

                Button {
                    text: "Reset standard layout"
                    onClicked: {
                        root.chatWidthRatioChangedByUser(0.31)
                        root.telemetryWidthChangedByUser(168)
                        root.accentColorChangedByUser("#8a8a8a")
                        root.frameBorderChangedByUser("#6a6a6a")
                        root.frameRadiusChangedByUser(2)
                        root.demoVisibilityChangedByUser(false)
                        root.productSourceTabsChangedByUser(false)
                        root.showOpenTabInInputChangedByUser(false)
                        root.showInnerEditorChromeChangedByUser(true)
                        root.hostKindChangedByUser("CODE")
                        root.engineTargetChangedByUser("LOCAL_QWEN")
                        root.utilityHeightChangedByUser(112)
                    }
                }

                Button {
                    text: "Close settings"
                    onClicked: root.closeRequested()
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "theme-id · " + root.themeId
                    color: "#6e7681"
                    font.family: "monospace"
                    font.pixelSize: 9
                }
            }

            Item {
                width: 1
                height: 6
            }
        }
    }
}
