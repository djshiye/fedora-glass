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

    // One Apply back (and forward again): the look applied before the last Apply.
    Card {
        objectName: "previousCard"
        visible: Backend.hasPrevious
        width: parent.width
        height: visible ? implicitHeight : 0
        Item {
            width: parent.width
            height: Math.max(previousText.height, previousButton.height)
            Column {
                id: previousText
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - previousButton.width - 16
                spacing: 3
                Text {
                    objectName: "previousTitle"
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: Backend.previousIsForward ? "Go forward to the look you went back from"
                                                    : "Go back to the look before your last Apply"
                    color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.DemiBold
                }
                Text {
                    objectName: "previousWhen"
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: (Backend.previousWhen ? "It was applied " + Backend.previousWhen + ". " : "")
                          + (Backend.previousIsForward ? "One click applies it again."
                                                       : "One click applies it again, and you can come forward after.")
                    color: Theme.textFaint
                    font.pixelSize: Theme.fsSmall
                }
            }
            LgButton {
                id: previousButton
                objectName: "goToPrevious"
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                kind: "secondary"
                implicitHeight: 36
                leftPadding: 14; rightPadding: 16
                text: Backend.previousIsForward ? "Go forward" : "Go back"
                iconName: Backend.previousIsForward ? "forward" : "back"
                enabled: !Backend.busy
                tip: Backend.previousIsForward ? "Apply the look you had before you went back"
                                               : "Apply the look you had before your last Apply"
                onClicked: Backend.dirty ? stepSheet.open() : Backend.goToPrevious()
            }
        }
    }
    Sheet {
        id: stepSheet
        objectName: "previousSheet"
        title: Backend.previousIsForward ? "Go forward and drop your changes?" : "Go back and drop your changes?"
        subtitle: "You changed the look but haven't applied it. Going " + (Backend.previousIsForward ? "forward" : "back")
                  + " applies the earlier look in their place, and those changes are lost."
        iconName: "info"
        width: Math.min(520, (parent ? parent.width : 800) - 64)
        buttons: [
            LgButton { text: "Cancel"; kind: "secondary"; onClicked: stepSheet.close() },
            LgButton {
                text: Backend.previousIsForward ? "Go forward" : "Go back"
                kind: "primary"
                onClicked: { stepSheet.close(); Backend.goToPrevious() }
            }
        ]
        Item { width: 1; height: 1 }
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
