import QtQuick
import QtQuick.Controls.Basic as C
import QtQuick.Effects
import FedoraGlass.Core

// Lock and login: the glass, the clock and what sits under it, the unlock animation and
// the login screen. The page keeps its own small lock-screen preview in the side column.
SettingsPage {
    id: page
    objectName: "lockPage"
    pageId: "lock"
    property alias previewMode: preview.mode
    readonly property bool weatherMissing: Backend.weatherState === "no-app" || Backend.weatherState === "no-place"
    readonly property string weatherWhy: Backend.weatherState === "no-app" ? qsTr("Weather needs the GNOME Weather app, so nothing shows yet.")
                                       : Backend.weatherState === "no-place" ? qsTr("Choose a place in GNOME Weather, so weather has something to show.")
                                       : ""

    component Choice: Column {
        property string label: ""
        property alias model: seg.model
        property alias value: seg.value
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

    // The unlock animation, played on the preview with the chosen curve and time.
    SequentialAnimation {
        id: unlockAnim
        NumberAnimation {
            id: slideOut
            target: preview; property: "slide"; from: 0; to: 1
            duration: Backend.lockSlide === "gnome" ? 250 : Backend.lockSlideMs
            easing.type: Backend.lockSlide === "spring" ? Easing.BezierSpline
                       : Backend.lockSlide === "smooth" ? Easing.OutCubic : Easing.OutQuad
            // lock.js springCurve(): the glass gathers itself (dips), then lifts away.
            easing.bezierCurve: [0.3, -0.5 * Backend.lockBounce, 0.2, 1, 1, 1]
        }
        PauseAnimation { duration: 900 }
        NumberAnimation { target: preview; property: "opacity"; to: 0; duration: 1 }
        PropertyAction { target: preview; property: "slide"; value: 0 }
        NumberAnimation { target: preview; property: "opacity"; to: 1; duration: Theme.slow }
    }

    Timer {
        id: focusMessage
        interval: Theme.slow + 60
        onTriggered: msgField.forceActiveFocus()
    }

    // ================================================================ left
    Card {
        width: parent.width
        height: implicitHeight
        padding: 0
        Column {
            x: 20
            width: parent.width - 40
            topPadding: 8
            bottomPadding: 8
            // The way back to the defaults, shown only while something here has changed.
            SectionTitle {
                objectName: "lockGlassReset"
                visible: changed
                height: visible ? implicitHeight + 8 : 0
                text: qsTr("Lock screen")
                resetKeys: ["lock_glass", "lock_blur", "lock_clock"]
            }
            SwitchRow {
                objectName: "lockGlass"
                label: qsTr("Glass lock screen")
                caption: Backend.reduceTransparency ? qsTr("Off while Reduce transparency is on")
                                                    : qsTr("Only your wallpaper shows through, never your windows")
                tip: qsTr("Turns the lock screen into one sheet of frosted glass over your wallpaper. When you unlock, the sheet slides up and your desktop appears underneath. Off gives you GNOME's own lock screen; your widgets stay.")
                implicitHeight: 60
                checked: Backend.lockGlass
                onToggled: (v) => Backend.lockGlass = v
            }
            Divider {}
            Item {
                width: parent.width
                height: blurSlider.height + 28
                LabeledSlider {
                    id: blurSlider
                    objectName: "lockBlur"
                    y: 14
                    enabled: preview.glass
                    label: qsTr("Frost")
                    from: 10; to: 100; stepSize: 1
                    value: Backend.lockBlur
                    defaultValue: Backend.defaults.lock_blur
                    format: (v) => qsTr("%1 px").arg(Math.round(v))
                    onMoved: (v) => Backend.lockBlur = Math.round(v)
                    tip: qsTr("How frosted the glass is. Left shows more of your wallpaper's shapes; right turns it into soft colour, which keeps the clock calm on a busy picture.")
                }
            }
            Divider {}
            Item {
                width: parent.width
                height: clockChoice.height + 28
                Choice {
                    id: clockChoice
                    objectName: "lockClock"
                    y: 14
                    enabled: preview.glass
                    label: qsTr("Clock")
                    value: Backend.lockClock
                    model: [{ value: "gnome", label: "GNOME", tip: qsTr("GNOME's own clock") },
                            { value: "bold", label: qsTr("Bold"), tip: qsTr("Large, heavy numbers that stand out on the glass") },
                            { value: "thin", label: qsTr("Thin"), tip: qsTr("Large, light numbers for a quieter look") }]
                    onPicked: (v) => { Backend.lockClock = v; preview.mode = "rest" }
                }
            }
        }
    }

    Card {
        width: parent.width
        height: implicitHeight
        Column {
            width: parent.width
            spacing: 12
            SectionTitle {
                text: qsTr("Under the clock")
                caption: qsTr("Anyone can see these")
                resetKeys: ["lock_widget_battery", "lock_widget_weather", "lock_greeting", "lock_hide_notifications"]
                resetTip: qsTr("Put these back to their defaults")
            }
            Flow {
                width: parent.width
                spacing: 8
                ToggleChip {
                    objectName: "lockWidgetBattery"
                    text: qsTr("Battery")
                    on: Backend.lockWidgetBattery
                    tip: Backend.hasBattery ? qsTr("Shows your battery level and a charging sign.")
                                            : qsTr("Shows your battery level and a charging sign. This PC has no battery, so nothing shows.")
                    onSwitched: (v) => { Backend.lockWidgetBattery = v; preview.mode = "rest" }
                }
                ToggleChip {
                    objectName: "lockWidgetWeather"
                    text: qsTr("Weather")
                    on: Backend.lockWidgetWeather
                    tip: page.weatherMissing ? qsTr("%1 Shows the current temperature and sky for the place set in GNOME Weather (the same weather as in the calendar menu).").arg(page.weatherWhy)
                                             : qsTr("Shows the current temperature and sky for the place set in GNOME Weather (the same weather as in the calendar menu).")
                    onSwitched: (v) => { Backend.lockWidgetWeather = v; preview.mode = "rest" }
                }
                ToggleChip {
                    objectName: "lockGreeting"
                    text: qsTr("Greeting")
                    on: Backend.lockGreeting
                    tip: qsTr("“Good morning” above the clock, changing through the day. It never shows your name.")
                    onSwitched: (v) => { Backend.lockGreeting = v; preview.mode = "rest" }
                }
                ToggleChip {
                    objectName: "lockMessageChip"
                    text: qsTr("Message")
                    on: Backend.lockMessage.length > 0
                    tip: qsTr("A short line under the clock, such as how to return your laptop if it's lost. Anyone who sees your screen can read it.")
                    onSwitched: (v) => {
                        if (v) {
                            more.expanded = true
                            focusMessage.restart()
                        } else {
                            Backend.lockMessage = ""
                            msgField.text = ""
                        }
                        preview.mode = "rest"
                    }
                }
                ToggleChip {
                    objectName: "lockHideNotifications"
                    text: qsTr("Hide notifications")
                    on: Backend.lockHideNotifications
                    tip: qsTr("Hides GNOME's notifications and music controls while the screen is locked. They're all still there when you unlock. GNOME's own notification settings aren't changed.")
                    onSwitched: (v) => { Backend.lockHideNotifications = v; preview.mode = "rest" }
                }
            }
            Text {
                objectName: "lockWeatherNote"
                visible: Backend.lockWidgetWeather && page.weatherMissing
                width: parent.width
                wrapMode: Text.WordWrap
                text: page.weatherWhy
                color: Theme.textFaint
                font.pixelSize: Theme.fsSmall
            }
        }
    }

    Fold {
        id: more
        objectName: "lockMore"
        title: qsTr("More lock screen options")
        summary: qsTr("Darken, tint, clock position, unlock animation")
        Column {
            width: parent.width
            spacing: 16

            SectionTitle {
                group: true
                text: qsTr("Glass")
                resetKeys: ["lock_dim", "lock_tint", "lock_card", "lock_clock_position"]
            }
            LabeledSlider {
                objectName: "lockDim"
                enabled: preview.glass
                label: qsTr("Darken")
                from: 0; to: 0.65
                value: Backend.lockDim
                defaultValue: Backend.defaults.lock_dim
                onMoved: (v) => Backend.lockDim = v
                tip: qsTr("How much darker the glass is than your wallpaper. A bright wallpaper is always darkened enough to keep the white clock readable.")
            }
            LabeledSlider {
                objectName: "lockTint"
                enabled: preview.glass
                label: qsTr("Tint")
                value: Backend.lockTint
                defaultValue: Backend.defaults.lock_tint
                onMoved: (v) => Backend.lockTint = v
                tip: qsTr("How much of your glass tint colour washes over the lock screen. Left keeps your wallpaper's own colours.")
            }
            SwitchRow {
                objectName: "lockCard"
                enabled: preview.glass
                label: qsTr("Glass card behind the password")
                caption: qsTr("Your picture, name and password field sit on their own pane")
                tip: qsTr("Puts a pane of glass behind your picture, name and password field when you start typing.")
                checked: Backend.lockCard
                onToggled: (v) => { Backend.lockCard = v; preview.mode = "prompt" }
            }
            Choice {
                objectName: "lockClockPosition"
                enabled: preview.glass
                label: qsTr("Clock position")
                value: Backend.lockClockPosition
                model: [{ value: "gnome", label: "GNOME", tip: qsTr("Where GNOME puts it, about a third of the way down") },
                        { value: "top", label: qsTr("Top"), tip: qsTr("Near the top of the screen, with more wallpaper below. The password appears there too.") },
                        { value: "middle", label: qsTr("Middle"), tip: qsTr("In the middle of the screen. The password appears there too.") }]
                onPicked: (v) => { Backend.lockClockPosition = v; preview.mode = "rest" }
            }

            SectionTitle {
                group: true
                text: qsTr("Weather and message")
                resetKeys: ["lock_weather_place", "lock_message", "lock_widget_style"]
            }
            SwitchRow {
                objectName: "lockWeatherPlace"
                enabled: Backend.lockWidgetWeather
                label: qsTr("Name the place for weather")
                caption: qsTr("Shows your town next to the weather")
                tip: qsTr("Adds the place name to the weather. Off keeps where you live off your lock screen.")
                checked: Backend.lockWeatherPlace
                onToggled: (v) => { Backend.lockWeatherPlace = v; preview.mode = "rest" }
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
                    objectName: "lockMessage"
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
                    Accessible.name: qsTr("Lock screen message")
                    background: Rectangle {
                        radius: Theme.rS
                        color: Theme.well
                        border.width: msgField.activeFocus ? 2 : 1
                        border.color: msgField.activeFocus ? Theme.alpha(Theme.accent, 0.85) : Theme.border
                    }
                    // Set once, and again only when it changes from elsewhere (Reset):
                    // typing a space must not be tidied away mid-word.
                    Component.onCompleted: text = Backend.lockMessage
                    onTextEdited: { Backend.lockMessage = text; preview.mode = "rest" }
                    onEditingFinished: text = Backend.lockMessage
                    Connections {
                        target: Backend
                        function onSettingsChanged() {
                            if (!msgField.activeFocus && msgField.text !== Backend.lockMessage)
                                msgField.text = Backend.lockMessage
                        }
                    }
                    HoverHandler { id: msgHover }
                    LgToolTip {
                        shown: msgHover.hovered && !msgField.activeFocus
                        text: qsTr("A short line under the clock, such as how to return your laptop if it's lost. Anyone who sees your screen can read it.")
                    }
                }
            }
            Choice {
                objectName: "lockWidgetStyle"
                label: qsTr("Look")
                value: Backend.lockWidgetStyle
                model: [{ value: "chips", label: qsTr("Glass"), tip: qsTr("Each widget sits on its own small pane of glass") },
                        { value: "plain", label: qsTr("Text only"), tip: qsTr("Just the icons and text, straight on the lock screen") }]
                onPicked: (v) => { Backend.lockWidgetStyle = v; preview.mode = "rest" }
            }

            SectionTitle {
                group: true
                text: qsTr("Unlock")
                resetKeys: ["lock_slide", "lock_slide_ms", "lock_bounce"]
            }
            Choice {
                objectName: "lockSlide"
                enabled: preview.glass
                label: qsTr("Unlock animation")
                value: Backend.lockSlide
                model: [{ value: "gnome", label: "GNOME", tip: qsTr("GNOME's own quick slide") },
                        { value: "smooth", label: qsTr("Smooth"), tip: qsTr("The glass glides up and slows as it leaves") },
                        { value: "spring", label: qsTr("Spring"), tip: qsTr("The glass gathers itself, then lifts away quickly") }]
                onPicked: (v) => Backend.lockSlide = v
            }
            LabeledSlider {
                objectName: "lockSlideMs"
                enabled: preview.glass && Backend.lockSlide !== "gnome"
                label: qsTr("Slide time")
                from: 250; to: 1200; stepSize: 10
                value: Backend.lockSlideMs
                defaultValue: Backend.defaults.lock_slide_ms
                format: (v) => qsTr("%1 s").arg((v / 1000).toFixed(2))
                onMoved: (v) => Backend.lockSlideMs = Math.round(v)
                tip: qsTr("How long the glass takes to slide away when you unlock. Reduce animation in GNOME's settings makes it instant.")
            }
            LabeledSlider {
                objectName: "lockBounce"
                enabled: preview.glass && Backend.lockSlide === "spring"
                label: qsTr("Bounce")
                value: Backend.lockBounce
                defaultValue: Backend.defaults.lock_bounce
                onMoved: (v) => Backend.lockBounce = v
                tip: qsTr("How much the glass gathers itself before it lifts away, like a spring letting go. Left lifts straight off; right gives a small dip first.")
            }
        }
    }

    LoginScreenCard {
        objectName: "loginCard"
        width: parent.width
    }

    // ================================================================ right: preview
    side: [
        Item {
            id: previewBox
            // A whole lock screen, as big as the page allows: the buttons and the line
            // under it still fit beside the cards, or above them in a narrow window.
            width: Math.min(parent.width, Math.round((page.stacked ? page.previewH - 48 : page.height - 150) * 16 / 9))
            height: Math.round(width * 9 / 16)

            RectangularShadow {
                anchors.fill: parent
                radius: Theme.rM
                blur: 28
                offset.y: 8
                color: Qt.rgba(0, 0, 0, Theme.dark ? 0.5 : 0.22)
            }
            LockPreview {
                id: preview
                objectName: "lockPreview"
                anchors.fill: parent
                layer.enabled: true
                layer.smooth: true
                layer.effect: MultiEffect {
                    maskEnabled: true
                    maskSource: previewMask
                    maskThresholdMin: 0.5
                    maskSpreadAtMin: 1.0
                }
            }
            Rectangle {
                id: previewMask
                anchors.fill: parent
                radius: Theme.rM
                visible: false
                layer.enabled: true
                layer.smooth: true
            }

            // Which moment of the lock screen to show, floating on the preview.
            Rectangle {
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.margins: 12
                width: modeSeg.width + 8
                height: modeSeg.height + 8
                radius: height / 2
                color: Qt.rgba(0.08, 0.085, 0.11, 0.55)
                Segmented {
                    id: modeSeg
                    objectName: "lockPreviewMode"
                    anchors.centerIn: parent
                    width: 230
                    compact: true
                    onWallpaper: true
                    model: [{ value: "rest", label: qsTr("Clock"), tip: qsTr("The lock screen as it waits, with the clock and your widgets") },
                            { value: "prompt", label: qsTr("Password"), tip: qsTr("The lock screen once you start typing your password") }]
                    value: preview.mode
                    onActivated: (v) => preview.mode = v
                    Accessible.name: qsTr("Preview")
                }
            }
        },
        Row {
            spacing: 8
            LgButton {
                objectName: "playUnlock"
                kind: "secondary"
                text: qsTr("Play unlock")
                iconName: "run"
                leftPadding: 14
                enabled: !unlockAnim.running
                tip: qsTr("Shows the unlock animation on the preview, with the time and bounce you picked")
                onClicked: { preview.mode = "rest"; unlockAnim.restart() }
            }
            LgButton {
                objectName: "lockNow"
                kind: "secondary"
                text: Backend.dirty ? qsTr("Apply and lock") : qsTr("Lock now")
                iconName: "lock"
                leftPadding: 14
                enabled: !Backend.busy
                tip: Backend.dirty ? qsTr("Applies your changes, then locks your screen so you can see them for real.")
                                   : qsTr("Locks your screen so you can see it for real. Your password unlocks it as usual.")
                onClicked: Backend.dirty ? Backend.applyAndLock() : Backend.lockScreenNow()
            }
        },
        Text {
            objectName: "lockStatus"
            width: parent.width
            wrapMode: Text.WordWrap
            text: qsTr("Changes show after Apply, the next time you lock.")
            color: Theme.textFaint
            font.pixelSize: Theme.fsSmall
        }
    ]
}
