import QtQuick
import QtQuick.Controls.Basic as C
import FedoraGlass.Core

// Taking Fedora Glass off the PC: whether removing the package (dnf, apt or pacman) puts the original look back first,
// and a button that does both (Restore original, then removes the app after your password).
Card {
    id: root
    height: implicitHeight
    readonly property bool busy: Backend.removing

    Column {
        width: parent.width
        spacing: 6
        SectionTitle { text: "Removing Fedora Glass" }
        SwitchRow {
            objectName: "undoOnRemove"
            label: "Put my original look back"
            caption: "When Fedora Glass is removed, your desktop goes back to how it was before"
            tip: "On: removing Fedora Glass (here, or with " + Backend.removeCommand + ") first does what Restore original does. Off: the glass and themes stay after the app is gone. Saved straight away."
            checked: Backend.undoOnRemove
            onToggled: (on) => Backend.undoOnRemove = on
        }
        Item { width: 1; height: 6; visible: Backend.canRemoveApp }
        LgButton {
            objectName: "removeApp"
            visible: Backend.canRemoveApp
            kind: "danger"
            text: root.busy ? "Removing Fedora Glass…" : "Remove Fedora Glass…"
            iconName: "trash"
            leftPadding: 14
            busy: root.busy
            enabled: !Backend.busy && !root.busy
            tip: "Puts your original look back, then removes the app. Asks for your password."
            tipBelow: true
            onClicked: removeSheet.open()
        }
        Item { width: 1; height: 4 }
    }

    Sheet {
        id: removeSheet
        title: "Remove Fedora Glass?"
        subtitle: "Your original look comes back first, exactly as Restore original does. Then Fedora Glass is removed from your PC, which needs your password. Your Fedora Glass settings are kept, in case you install it again."
        iconName: "trash"
        iconColor: Theme.bad
        width: Math.min(520, (parent ? parent.width : 800) - 64)
        buttons: [
            LgButton { text: "Cancel"; kind: "secondary"; onClicked: removeSheet.close() },
            LgButton {
                objectName: "removeConfirm"
                text: "Remove"
                kind: "destructive"
                iconName: "trash"
                onClicked: { removeSheet.close(); Backend.removeApp() }
            }
        ]
        Item { width: 1; height: 1 }
    }

    Sheet {
        id: removedSheet
        title: "Fedora Glass is removed"
        subtitle: "Your original look is back. Restart your PC to finish, so GNOME lets go of the glass completely."
        iconName: "okCircle"
        iconColor: Theme.good
        width: Math.min(520, (parent ? parent.width : 800) - 64)
        closePolicy: C.Popup.NoAutoClose
        buttons: [ LgButton { text: "Close Fedora Glass"; kind: "primary"; onClicked: Qt.quit() } ]
        Item { width: 1; height: 1 }
    }

    Connections {
        target: Backend
        function onRemoveFinished(ok) { if (ok) removedSheet.open() }
    }
}
