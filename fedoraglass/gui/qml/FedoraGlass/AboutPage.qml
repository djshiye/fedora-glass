import QtQuick
import QtQuick.Window
import FedoraGlass.Core

// About and restore: the version and what's new, the keyboard shortcuts, putting the
// original look back, and taking Fedora Glass off the PC.
SettingsPage {
    id: page
    objectName: "aboutPage"
    pageId: "about"
    hasSide: false
    maxColumn: 720

    Card {
        width: parent.width
        height: implicitHeight
        Item {
            width: parent.width
            height: 64
            Image {
                id: appIcon
                width: 56; height: 56
                anchors.verticalCenter: parent.verticalCenter
                source: typeof appIconUrl !== "undefined" ? appIconUrl : ""
                sourceSize: Qt.size(112, 112)
                smooth: true
                visible: status === Image.Ready
            }
            Icon {
                visible: !appIcon.visible
                anchors.centerIn: appIcon
                name: "sparkle"
                size: 32
                color: Theme.accentText
            }
            Column {
                anchors.left: appIcon.right
                anchors.leftMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                spacing: 3
                Text { text: "Fedora Glass"; color: Theme.text; font.pixelSize: 20; font.weight: Font.DemiBold }
                Text {
                    objectName: "aboutVersion"
                    text: "Version " + Backend.version
                    color: Theme.textDim
                    font.pixelSize: Theme.fsBody
                    font.features: { "tnum": 1 }
                }
            }
            Row {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8
                LgButton {
                    objectName: "shortcutsButton"
                    kind: "flat"
                    implicitHeight: 34
                    leftPadding: 12; rightPadding: 14
                    text: "Keyboard shortcuts"
                    iconName: "keyboard"
                    tip: "Every keyboard shortcut in the app (F1)"
                    onClicked: if (Window.window) Window.window.openAbout()
                }
                LgButton {
                    objectName: "aboutWhatsNew"
                    kind: "secondary"
                    implicitHeight: 34
                    leftPadding: 12; rightPadding: 14
                    text: "What's new"
                    iconName: "sparkle"
                    tip: "Opens the release notes in your web browser"
                    onClicked: Qt.openUrlExternally("https://github.com/djshiye/fedora-glass/releases")
                }
            }
        }
    }

    Card {
        objectName: "restoreCard"
        width: parent.width
        height: implicitHeight
        Item {
            width: parent.width
            height: Math.max(restoreText.height, restore.height)
            Column {
                id: restoreText
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - restore.width - 16
                spacing: 3
                Text { text: "Restore your original look"; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.DemiBold }
                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: Backend.hasBackup
                          ? "Every file and setting Fedora Glass changed goes back to how it was before your first Apply. Your Fedora Glass settings are kept."
                          : "Nothing to restore yet: Fedora Glass hasn't changed anything on your desktop."
                    color: Theme.textFaint
                    font.pixelSize: Theme.fsSmall
                }
            }
            LgButton {
                id: restore
                objectName: "restoreOriginal"
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                kind: "danger"
                implicitHeight: 36
                leftPadding: 14; rightPadding: 16
                text: "Restore original…"
                iconName: "undo"
                enabled: !Backend.busy && Backend.hasBackup
                tip: Backend.hasBackup ? "Put back every file and setting as it was before Fedora Glass"
                                       : "Nothing to restore: Fedora Glass hasn't changed anything yet"
                onClicked: if (Window.window) Window.window.openRestore()
            }
        }
    }

    RemoveCard { width: parent.width }
}
