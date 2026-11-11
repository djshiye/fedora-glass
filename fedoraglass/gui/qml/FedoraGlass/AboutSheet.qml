import QtQuick
import FedoraGlass.Core

// About: the version, a way to the release notes, and every keyboard shortcut.
// Opened with F1 (or ?) and from the app name in the header.
Sheet {
    id: sheet
    objectName: "aboutSheet"
    title: "Fedora Glass"
    subtitle: qsTr("Version %1").arg(Backend.version)
    iconSource: typeof appIconUrl !== "undefined" ? appIconUrl : ""
    iconName: "info"
    width: Math.min(540, (parent ? parent.width : 800) - 64)

    readonly property url releasesUrl: "https://github.com/djshiye/fedora-glass/releases"
    readonly property var shortcuts: [
        { keys: ["Ctrl+Enter"], what: qsTr("Apply") },
        { keys: ["Ctrl+Z"], what: qsTr("Undo changes") },
        { keys: ["Ctrl+F", "/"], what: qsTr("Search settings") },
        { keys: ["Ctrl+1 … 9"], what: qsTr("Go to a page, in sidebar order") },
        { keys: ["Tab", "Shift+Tab"], what: qsTr("Move to the next or previous control") },
        { keys: [qsTr("Arrow keys")], what: qsTr("Change a slider, or pick in a group") },
        { keys: ["Space", "Enter"], what: qsTr("Press the focused button") },
        { keys: ["Esc"], what: qsTr("Close a sheet like this one") },
        { keys: ["F1"], what: qsTr("Show this sheet") },
        { keys: ["Ctrl+W", "Ctrl+Q"], what: qsTr("Close Fedora Glass") }
    ]

    buttons: [
        LgButton {
            objectName: "aboutWhatsNew"
            text: qsTr("What's new")
            kind: "secondary"
            iconName: "sparkle"
            leftPadding: 16
            tip: qsTr("Opens the release notes in your web browser")
            onClicked: Qt.openUrlExternally(sheet.releasesUrl)
        },
        LgButton {
            objectName: "aboutClose"
            text: qsTr("Close")
            kind: "primary"
            onClicked: sheet.close()
        }
    ]

    Column {
        width: parent.width
        spacing: 12

        Text {
            text: qsTr("Keyboard shortcuts")
            color: Theme.text
            font.pixelSize: Theme.fsBody
            font.weight: Font.DemiBold
        }
        Rectangle {
            width: parent.width
            height: list.height + 20
            radius: Theme.rM
            color: Theme.well
            border.width: 1
            border.color: Theme.border

            Column {
                id: list
                x: 14; y: 10
                width: parent.width - 28
                spacing: 0
                Repeater {
                    model: sheet.shortcuts
                    delegate: Item {
                        id: line
                        required property var modelData
                        required property int index
                        width: list.width
                        height: 36
                        Accessible.role: Accessible.StaticText
                        Accessible.name: qsTr("%1: %2").arg(modelData.keys.length > 1 ? qsTr("%1 or %2").arg(modelData.keys[0]).arg(modelData.keys[1]) : modelData.keys[0]).arg(modelData.what)
                        Rectangle {
                            visible: line.index > 0
                            width: parent.width; height: 1
                            color: Theme.divider
                        }
                        Row {
                            id: keyRow
                            anchors.verticalCenter: parent.verticalCenter
                            width: 172
                            spacing: 6
                            Repeater {
                                model: line.modelData.keys
                                delegate: Rectangle {
                                    required property string modelData
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: cap.implicitWidth + 14
                                    height: 24
                                    radius: 6
                                    color: Theme.surfaceHi
                                    border.width: 1
                                    border.color: Theme.border
                                    Text {
                                        id: cap
                                        anchors.centerIn: parent
                                        text: parent.modelData
                                        color: Theme.text
                                        font.pixelSize: 12
                                        font.weight: Font.Medium
                                    }
                                }
                            }
                        }
                        Text {
                            anchors.left: keyRow.right
                            anchors.leftMargin: 12
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            text: line.modelData.what
                            color: Theme.textDim
                            font.pixelSize: Theme.fsBody
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }
    }
}
