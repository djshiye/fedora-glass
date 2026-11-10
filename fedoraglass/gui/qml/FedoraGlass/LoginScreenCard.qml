import QtQuick
import FedoraGlass.Core

// Glass on the login screen (GDM). Opt in: it changes a system file, so it asks for
// your password, and one button puts the normal login screen back.
Card {
    id: root
    readonly property string state_: Backend.loginGlass
    readonly property bool busy: state_ === "busy"
    height: implicitHeight
    visible: state_ !== "unavailable"

    Column {
        width: parent.width
        spacing: 10
        Item {
            width: parent.width
            height: heads.height
            Column {
                id: heads
                width: parent.width
                spacing: 2
                Text { text: "Glass login screen"; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: "Needs your password once. Apply keeps it up to date."
                    color: Theme.textFaint
                    font.pixelSize: Theme.fsSmall
                }
            }
            HoverHandler { id: headHover }
            LgToolTip {
                shown: headHover.hovered
                below: true
                text: "The login screen can't see your wallpaper, so it gets a soft glow in your tint colour with glass panes for your name and password. It changes a system file, so your password is needed, also when Apply updates it. GNOME updates put the normal login screen back by themselves."
            }
        }
        Text {
            objectName: "loginGlassStatus"
            width: parent.width
            wrapMode: Text.WordWrap
            color: Theme.textDim
            font.pixelSize: Theme.fsSmall + 1
            text: root.state_ === "on" && Backend.loginGlassStale
                  ? "The login screen still has an older look. Apply brings it up to date; it asks for your password."
                : root.state_ === "on" ? "Glass is on the login screen, in your tint and accent colours. Apply keeps it up to date."
                : root.state_ === "undone" ? "A GNOME update put the normal login screen back. Turn the glass on again to bring it back."
                : root.busy ? "Waiting for your password…"
                : "The login screen you see after a restart is GNOME's own."
        }
        Flow {
            width: parent.width
            spacing: 10
            LgButton {
                objectName: "loginGlassOn"
                kind: root.state_ === "on" ? "secondary" : "primary"
                enabled: !root.busy
                busy: root.busy
                text: root.state_ === "on" ? (Backend.loginGlassStale ? "Update it now" : "Update to my colours") : "Use glass on the login screen"
                tip: "Asks for your password, then puts glass on the login screen in the colours you have now."
                tipBelow: true
                onClicked: Backend.turnOnLoginGlass()
            }
            LgButton {
                objectName: "loginGlassOff"
                visible: root.state_ === "on"
                kind: "flat"
                enabled: !root.busy
                text: "Put the normal login screen back"
                tip: "Asks for your password, then puts GNOME's own login screen back exactly as it was."
                tipBelow: true
                onClicked: Backend.turnOffLoginGlass()
            }
        }
        Text {
            objectName: "loginGlassNote"
            visible: text.length > 0
            width: parent.width
            wrapMode: Text.WordWrap
            color: Theme.textFaint
            font.pixelSize: Theme.fsSmall
            text: Backend.loginGlassNote
        }
    }
}
