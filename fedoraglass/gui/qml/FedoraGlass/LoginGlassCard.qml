import QtQuick
import QtQuick.Controls.Basic as C
import FedoraGlass.Core

// The glass login screen (GDM), through the root helper fedora-glass-login. It changes
// only when you turn it on (your password), and on Apply while it is on. The sliders here
// move the preview only, like everywhere else in the app.
Card {
    id: root
    readonly property string state_: Backend.glassLoginState
    readonly property bool busy: state_ === "busy"
    readonly property bool on: Backend.glassLoginOn
    // Not available and not on: only the title and why.
    readonly property bool offered: Backend.glassLoginCanTurnOn || root.on || root.busy
    signal touched()        // a control here changed: the preview shows the login screen
    height: implicitHeight

    component Choice: Column {
        property string label: ""
        property alias model: seg.model
        property alias value: seg.value
        property alias fit: seg.fit
        signal picked(var v)
        width: parent.width
        spacing: 8
        Text { text: parent.label; color: parent.enabled ? Theme.text : Theme.textFaint; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
        Segmented {
            id: seg
            width: parent.width
            enabled: parent.enabled
            onActivated: (v) => parent.picked(v)
            Accessible.name: parent.label
        }
    }
    component Divider: Rectangle { width: parent.width; height: 1; color: Theme.divider }
    component Faint: Text {
        width: parent.width
        wrapMode: Text.WordWrap
        color: Theme.textFaint
        font.pixelSize: Theme.fsSmall
        visible: text.length > 0
    }

    Column {
        width: parent.width
        spacing: 14

        Column {
            width: parent.width
            spacing: 6
            SectionTitle {
                objectName: "loginGlassTitle"
                text: qsTr("Login screen")
                resetKeys: ["login_match_lock", "login_blur", "login_dim", "login_tint", "login_card", "login_clock",
                            "login_picture", "login_battery", "login_message"]
                resetTip: qsTr("Put the login screen's settings back to their defaults")
            }
            Row {
                width: parent.width
                spacing: 8
                Item {
                    width: 10
                    height: 17
                    Spinner {
                        visible: root.busy
                        size: 14
                        color: Theme.textDim
                        anchors.centerIn: parent
                    }
                    Rectangle {
                        objectName: "loginGlassDot"
                        visible: !root.busy
                        anchors.centerIn: parent
                        width: 8; height: 8; radius: 4
                        color: root.state_ === "on" ? Theme.good
                             : root.state_ === "trial" ? Theme.accentText
                             : root.state_ === "behind" || root.state_ === "stopped" ? Theme.warn
                             : Theme.textFaint
                    }
                }
                Text {
                    id: statusText
                    objectName: "loginGlassStatus"
                    width: parent.width - 18
                    wrapMode: Text.WordWrap
                    text: Backend.glassLoginStatus
                    color: Theme.textDim
                    font.pixelSize: Theme.fsSmall + 1
                    Accessible.role: Accessible.StaticText
                    Accessible.name: qsTr("Login screen: %1").arg(text)
                }
            }
        }

        Faint {
            objectName: "loginGlassReplaces"
            visible: Backend.glassLoginReplacesPainted && !root.on && root.offered
            text: qsTr("Turning this on replaces the glass that is painted on your login screen now.")
        }

        Flow {
            width: parent.width
            spacing: 10
            visible: root.offered
            LgButton {
                objectName: "loginGlassToggle"
                kind: root.on ? "secondary" : "primary"
                enabled: !root.busy && (root.on || Backend.glassLoginCanTurnOn)
                busy: root.busy
                iconName: root.on ? "" : "lock"
                text: root.on ? qsTr("Turn off") : qsTr("Turn on glass login screen")
                tip: root.on ? qsTr("Asks for your password, then puts GNOME's own login screen back.")
                             : qsTr("Asks for your password, then turns on the glass login screen with the look you applied last.")
                tipBelow: true
                onClicked: root.on ? Backend.turnOffGlassLogin() : Backend.turnOnGlassLogin()
            }
            LgButton {
                objectName: "loginSeeNow"
                visible: root.on
                kind: "flat"
                enabled: !root.busy
                iconName: "eye"
                leftPadding: 14
                text: qsTr("See it now")
                tip: qsTr("Locks your screen and opens the login screen next to your session. Your apps stay open; log in again to come back.")
                tipBelow: true
                onClicked: Backend.seeLoginScreen()
            }
            LgButton {
                objectName: "loginUseGlow"
                visible: Backend.glassLoginPictureFailed && !root.busy
                kind: "secondary"
                iconName: "sparkle"
                leftPadding: 14
                text: qsTr("Use Glow instead")
                tip: qsTr("A soft glow in your colours instead of your wallpaper. Asks for your password.")
                tipBelow: true
                onClicked: Backend.useGlowForLogin()
            }
        }

        Faint {
            objectName: "loginGlassNote"
            text: Backend.loginGlassNote
            color: Backend.loginGlassFailed ? Theme.bad : Theme.textFaint
        }
        Faint {
            objectName: "loginSeeNote"
            text: Backend.glassLoginSeeNote
        }
        Faint {
            // The buttons use the applied look, never unapplied slider values.
            objectName: "loginGlassBehind"
            visible: Backend.loginGlassBehind && !root.busy && root.offered
            text: root.on ? qsTr("Apply brings your newest changes to the login screen too.")
                          : qsTr("It starts with the look you applied last. Apply first to bring your newest changes along.")
        }

        Column {
            width: parent.width
            spacing: 14
            visible: root.offered

            Divider {}
            SwitchRow {
                objectName: "loginMatchLock"
                label: qsTr("Match my lock screen")
                caption: qsTr("The same glass, clock, battery and message as your lock screen")
                tip: qsTr("The login screen takes the frost, darken, tint, clock, glass card, battery and message of your lock screen. Off lets you set them here.")
                checked: Backend.loginMatchLock
                onToggled: (v) => { Backend.loginMatchLock = v; root.touched() }
            }

            // Its own settings: the same controls and words as the lock screen's above.
            Column {
                objectName: "loginOwn"
                width: parent.width
                spacing: 16
                topPadding: 2
                bottomPadding: 2
                visible: !Backend.loginMatchLock

                LabeledSlider {
                    objectName: "loginBlur"
                    label: qsTr("Frost")
                    from: 10; to: 100; stepSize: 1
                    value: Backend.loginBlur
                    defaultValue: Backend.defaults.login_blur
                    format: (v) => qsTr("%1 px").arg(Math.round(v))
                    onMoved: (v) => { Backend.loginBlur = Math.round(v); root.touched() }
                    tip: qsTr("How frosted the glass is. Left shows more of your wallpaper's shapes; right turns it into soft colour.")
                }
                LabeledSlider {
                    objectName: "loginDim"
                    label: qsTr("Darken")
                    from: 0; to: 0.65
                    value: Backend.loginDim
                    defaultValue: Backend.defaults.login_dim
                    onMoved: (v) => { Backend.loginDim = v; root.touched() }
                    tip: qsTr("How much darker the glass is than the picture behind it. A bright picture is always darkened enough to keep the white text readable.")
                }
                LabeledSlider {
                    objectName: "loginTint"
                    label: qsTr("Tint")
                    value: Backend.loginTint
                    defaultValue: Backend.defaults.login_tint
                    onMoved: (v) => { Backend.loginTint = v; root.touched() }
                    tip: qsTr("How much of your glass tint colour washes over the login screen. Left keeps the picture's own colours.")
                }
                Choice {
                    objectName: "loginClock"
                    label: qsTr("Clock")
                    value: Backend.loginClock
                    model: [{ value: "gnome", label: "GNOME", tip: qsTr("Only GNOME's small clock in the top bar") },
                            { value: "bold", label: qsTr("Bold"), tip: qsTr("Large, heavy numbers at the top of the screen") },
                            { value: "thin", label: qsTr("Thin"), tip: qsTr("Large, light numbers at the top of the screen") }]
                    onPicked: (v) => { Backend.loginClock = v; root.touched() }
                }
                SwitchRow {
                    objectName: "loginCardSwitch"
                    label: qsTr("Glass card behind the password")
                    caption: qsTr("Your picture, name and password field sit on their own pane")
                    tip: qsTr("Puts a pane of glass behind your picture, name and password field.")
                    checked: Backend.loginCard
                    onToggled: (v) => { Backend.loginCard = v; root.touched() }
                }
                SwitchRow {
                    objectName: "loginBattery"
                    label: qsTr("Battery")
                    caption: Backend.hasBattery ? qsTr("Shows your battery level under the clock")
                                                : qsTr("This PC has no battery, so nothing shows")
                    tip: qsTr("Shows your battery level and a charging sign on the login screen.")
                    checked: Backend.loginBattery
                    onToggled: (v) => { Backend.loginBattery = v; root.touched() }
                }
                Column {
                    width: parent.width
                    spacing: 8
                    Item {
                        width: parent.width
                        height: msgLabel.height
                        Text { id: msgLabel; text: qsTr("Message"); color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
                        Text {
                            anchors.right: parent.right
                            visible: msgField.activeFocus || msgField.text.length > Backend.lockMessageMax - 20
                            text: qsTr("%1 / %2").arg(msgField.text.length).arg(Backend.lockMessageMax)
                            color: Theme.textFaint
                            font.pixelSize: Theme.fsSmall
                            font.features: { "tnum": 1 }
                        }
                    }
                    C.TextField {
                        id: msgField
                        objectName: "loginMessage"
                        width: parent.width
                        height: 40
                        leftPadding: 14
                        rightPadding: 14
                        color: Theme.text
                        placeholderText: qsTr("For example: If found, please call 555 0100")
                        placeholderTextColor: Theme.textFaint
                        selectionColor: Theme.alpha(Theme.accent, 0.4)
                        selectedTextColor: Theme.text
                        font.pixelSize: Theme.fsBody
                        maximumLength: Backend.lockMessageMax
                        Accessible.name: qsTr("Login screen message")
                        background: Rectangle {
                            radius: Theme.rS
                            color: Theme.well
                            border.width: msgField.activeFocus ? 2 : 1
                            border.color: msgField.activeFocus ? Theme.alpha(Theme.accent, 0.85) : Theme.border
                        }
                        // Set once, and again only when it changes from elsewhere (Reset):
                        // typing a space must not be tidied away mid-word.
                        Component.onCompleted: text = Backend.loginMessage
                        onTextEdited: { Backend.loginMessage = text; root.touched() }
                        onEditingFinished: text = Backend.loginMessage
                        Connections {
                            target: Backend
                            function onSettingsChanged() {
                                if (!msgField.activeFocus && msgField.text !== Backend.loginMessage)
                                    msgField.text = Backend.loginMessage
                            }
                        }
                        HoverHandler { id: msgHover }
                        LgToolTip {
                            shown: msgHover.hovered && !msgField.activeFocus
                            text: qsTr("A short line on the login screen, such as how to return your laptop if it's lost. Anyone at this PC can read it.")
                        }
                    }
                }
            }

            Divider {}
            Column {
                width: parent.width
                spacing: 6
                Choice {
                    objectName: "loginPicture"
                    label: qsTr("Picture")
                    fit: true
                    value: Backend.loginPicture
                    model: [{ value: "wallpaper", label: qsTr("My wallpaper"), tip: qsTr("A copy of your dark-style wallpaper, under the glass") },
                            { value: "system", label: qsTr("System picture"), tip: qsTr("The picture the login screen has without Fedora Glass, under the glass") },
                            { value: "glow", label: qsTr("Glow"), tip: qsTr("A soft glow in your tint and accent colours") }]
                    onPicked: (v) => { Backend.loginPicture = v; root.touched() }
                }
                Faint {
                    objectName: "loginPictureNote"
                    visible: Backend.loginPicture === "wallpaper"
                    text: qsTr("Your wallpaper is copied to the login screen, where anyone at this PC can see it.")
                }
            }
        }

        Fold {
            objectName: "loginSafe"
            visible: root.offered
            card: false
            divider: true
            title: qsTr("How it stays safe")
            Column {
                width: parent.width
                spacing: 8
                Repeater {
                    model: [qsTr("It is on trial until you log in once with it."),
                            qsTr("If the login screen ever has trouble with it, it turns itself off at the next start."),
                            qsTr("You can always turn it off from a text console (Ctrl+Alt+F3) with: sudo fedora-glass login-screen off")]
                    delegate: Row {
                        required property string modelData
                        width: parent.width
                        spacing: 10
                        Rectangle { y: 7; width: 5; height: 5; radius: 2.5; color: Theme.textFaint }
                        Text {
                            width: parent.width - 15
                            wrapMode: Text.WordWrap
                            text: parent.modelData
                            color: Theme.textDim
                            font.pixelSize: Theme.fsSmall + 1
                        }
                    }
                }
            }
        }
    }
}
