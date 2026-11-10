import QtQuick
import FedoraGlass.Core

// About: the version, a way to the release notes, and every keyboard shortcut.
// Opened with F1 (or ?) and from the app name in the header.
Sheet {
    id: sheet
    objectName: "aboutSheet"
    title: "Fedora Glass"
    subtitle: "Version " + Backend.version
    iconSource: typeof appIconUrl !== "undefined" ? appIconUrl : ""
    iconName: "info"
    width: Math.min(540, (parent ? parent.width : 800) - 64)

    readonly property url releasesUrl: "https://github.com/djshiye/fedora-glass/releases"
    readonly property var shortcuts: [
        { keys: ["Ctrl+Enter"], what: "Apply" },
        { keys: ["Ctrl+Z"], what: "Undo changes" },
        { keys: ["Ctrl+1", "Ctrl+2", "Ctrl+3"], what: "Look, Lock screen, Apps" },
        { keys: ["Tab", "Shift+Tab"], what: "Move to the next or previous control" },
        { keys: ["Arrow keys"], what: "Change a slider, or pick in a group" },
        { keys: ["Space", "Enter"], what: "Press the focused button" },
        { keys: ["Esc"], what: "Close a sheet like this one" },
        { keys: ["F1"], what: "Show this sheet" },
        { keys: ["Ctrl+W", "Ctrl+Q"], what: "Close Fedora Glass" }
    ]

    buttons: [
        LgButton {
            objectName: "aboutWhatsNew"
            text: "What's new"
            kind: "secondary"
            iconName: "sparkle"
            leftPadding: 16
            tip: "Opens the release notes in your web browser"
            onClicked: Qt.openUrlExternally(sheet.releasesUrl)
        },
        LgButton {
            objectName: "aboutClose"
            text: "Close"
            kind: "primary"
            onClicked: sheet.close()
        }
    ]

    Column {
        width: parent.width
        spacing: 12

        Text {
            text: "Keyboard shortcuts"
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
                        Accessible.name: modelData.keys.join(" or ") + ": " + modelData.what
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
