import QtQuick
import QtQuick.Controls.Basic as C
import QtQuick.Effects
import LiquidGlass.Core

// The Lock screen tab: a live miniature of the lock screen on the left, everything
// about it on the right (the glass, the clock, the widgets, privacy, the unlock
// animation, and the login screen).
Item {
    id: page
    readonly property real sideW: width >= 1180 ? 400 : 360
    property alias previewMode: preview.mode

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
    component Note: Text {
        width: parent.width
        wrapMode: Text.WordWrap
        color: Theme.textFaint
        font.pixelSize: Theme.fsSmall
    }

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

    // ================================================================ left: preview
    Item {
        id: left
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.right: side.left
        anchors.rightMargin: 24

        Item {
            id: previewBox
            readonly property real maxH: left.height - hero.height - 16
            width: Math.min(left.width, maxH * 16 / 9)
            height: width * 9 / 16
            anchors.horizontalCenter: parent.horizontalCenter

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
                    model: [{ value: "rest", label: "Clock", tip: "The lock screen as it waits, with the clock and your widgets" },
                            { value: "prompt", label: "Password", tip: "The lock screen once you start typing your password" }]
                    value: preview.mode
                    onActivated: (v) => preview.mode = v
                    Accessible.name: "Preview"
                }
            }
        }

        Card {
            id: hero
            anchors.top: previewBox.bottom
            anchors.topMargin: 16
            width: parent.width
            height: implicitHeight
            padding: 20

            Item {
                width: parent.width
                height: Math.max(heroText.height, heroButtons.height)
                Column {
                    id: heroText
                    width: parent.width - heroButtons.width - 20
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 4
                    Text { text: "Lock screen"; color: Theme.text; font.pixelSize: 17; font.weight: Font.Bold }
                    Text {
                        objectName: "lockStatus"
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: "Only your wallpaper shows through the glass, never your windows. Changes show the next time you lock."
                        color: Theme.textDim
                        font.pixelSize: 13
                    }
                }
                Row {
                    id: heroButtons
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 8
                    LgButton {
                        objectName: "playUnlock"
                        kind: "secondary"
                        text: "Play unlock"
                        iconName: "run"
                        leftPadding: 14
                        enabled: !unlockAnim.running
                        tip: "Shows the unlock animation on the preview, with the time and bounce you picked"
                        onClicked: { preview.mode = "rest"; unlockAnim.restart() }
                    }
                    LgButton {
                        objectName: "lockNow"
                        kind: "primary"
                        text: "Lock now"
                        iconName: "lock"
                        leftPadding: 14
                        tip: "Locks your screen so you can see it for real. Your password unlocks it as usual."
                        onClicked: Backend.lockScreenNow()
                    }
                }
            }
        }
    }

    // ================================================================ right: options
    Flickable {
        id: side
        objectName: "lockOptions"
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.rightMargin: -12
        width: page.sideW + 12
        contentHeight: opts.height + 8
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        C.ScrollBar.vertical: LgScrollBar {}

        Column {
            id: opts
            width: page.sideW
            spacing: 16

            // ---------------------------------------------------------- glass
            Card {
                width: parent.width
                height: implicitHeight
                Column {
                    width: parent.width
                    spacing: 16
                    SectionTitle { text: "Glass" }
                    SwitchRow {
                        objectName: "lockGlass"
                        label: "Glass lock screen"
                        caption: Backend.reduceTransparency ? "Off while Reduce transparency is on"
                                                            : "A sheet of frosted glass that slides up into your desktop"
                        tip: "Turns the lock screen into one sheet of frosted glass over your wallpaper. When you unlock, the sheet slides up and your desktop appears underneath. Off gives you GNOME's own lock screen; your widgets stay."
                        checked: Backend.lockGlass
                        onToggled: (v) => Backend.lockGlass = v
                    }
                    LabeledSlider {
                        objectName: "lockBlur"
                        enabled: preview.glass
                        label: "Frost"
                        from: 10; to: 100; stepSize: 1
                        value: Backend.lockBlur
                        format: (v) => Math.round(v) + " px"
                        onMoved: (v) => Backend.lockBlur = Math.round(v)
                        tip: "How frosted the glass is. Left shows more of your wallpaper's shapes; right turns it into soft colour, which keeps the clock calm on a busy picture."
                    }
                    LabeledSlider {
                        objectName: "lockDim"
                        enabled: preview.glass
                        label: "Darken"
                        from: 0; to: 0.65
                        value: Backend.lockDim
                        onMoved: (v) => Backend.lockDim = v
                        tip: "How much darker the glass is than your wallpaper. A bright wallpaper is always darkened enough to keep the white clock readable."
                    }
                    LabeledSlider {
                        objectName: "lockTint"
                        enabled: preview.glass
                        label: "Tint"
                        value: Backend.lockTint
                        onMoved: (v) => Backend.lockTint = v
                        tip: "How much of your glass tint colour washes over the lock screen. Left keeps your wallpaper's own colours."
                    }
                    SwitchRow {
                        objectName: "lockCard"
                        enabled: preview.glass
                        label: "Glass card behind the password"
                        caption: "Your picture, name and password field sit on their own pane"
                        tip: "Puts a pane of glass behind your picture, name and password field when you start typing."
                        checked: Backend.lockCard
                        onToggled: (v) => { Backend.lockCard = v; preview.mode = "prompt" }
                    }
                }
            }

            // ---------------------------------------------------------- clock
            Card {
                width: parent.width
                height: implicitHeight
                Column {
                    width: parent.width
                    spacing: 16
                    SectionTitle { text: "Clock" }
                    Choice {
                        objectName: "lockClock"
                        enabled: preview.glass
                        label: "Style"
                        value: Backend.lockClock
                        model: [{ value: "gnome", label: "GNOME", tip: "GNOME's own clock" },
                                { value: "bold", label: "Bold", tip: "Large, heavy numbers that stand out on the glass" },
                                { value: "thin", label: "Thin", tip: "Large, light numbers for a quieter look" }]
                        onPicked: (v) => { Backend.lockClock = v; preview.mode = "rest" }
                    }
                    Choice {
                        objectName: "lockClockPosition"
                        enabled: preview.glass
                        label: "Position"
                        value: Backend.lockClockPosition
                        model: [{ value: "gnome", label: "GNOME", tip: "Where GNOME puts it, about a third of the way down" },
                                { value: "top", label: "Top", tip: "Near the top of the screen, with more wallpaper below. The password appears there too." },
                                { value: "middle", label: "Middle", tip: "In the middle of the screen. The password appears there too." }]
                        onPicked: (v) => { Backend.lockClockPosition = v; preview.mode = "rest" }
                    }
                    SwitchRow {
                        objectName: "lockGreeting"
                        label: "Greeting"
                        caption: "“Good morning” above the clock, changing through the day"
                        tip: "A friendly line above the clock that follows the time of day. It never shows your name."
                        checked: Backend.lockGreeting
                        onToggled: (v) => { Backend.lockGreeting = v; preview.mode = "rest" }
                    }
                }
            }

            // ---------------------------------------------------------- widgets
            Card {
                width: parent.width
                height: implicitHeight
                Column {
                    width: parent.width
                    spacing: 16
                    SectionTitle { text: "Widgets" }
                    Note {
                        text: "Under the clock, for anyone to see. Only the battery is on to start with; switch on only what you're happy to show."
                    }
                    SwitchRow {
                        objectName: "lockWidgetBattery"
                        label: "Battery"
                        caption: Backend.hasBattery ? "How full it is, and whether it's charging"
                                                    : "This PC has no battery, so nothing shows"
                        tip: "Shows your battery level and a charging sign. On a PC without a battery nothing shows."
                        checked: Backend.lockWidgetBattery
                        onToggled: (v) => { Backend.lockWidgetBattery = v; preview.mode = "rest" }
                    }
                    SwitchRow {
                        objectName: "lockWidgetWeather"
                        label: "Weather"
                        caption: Backend.weatherState === "no-app" ? "Needs the GNOME Weather app, so nothing shows yet"
                               : Backend.weatherState === "no-place" ? "Choose a place in GNOME Weather, so it has something to show"
                               : "Now, from GNOME Weather"
                        tip: "Shows the current temperature and sky for the place set in GNOME Weather (the same weather as in the calendar menu). Needs the Weather app with a place chosen. Nothing shows when there is no weather."
                        checked: Backend.lockWidgetWeather
                        onToggled: (v) => { Backend.lockWidgetWeather = v; preview.mode = "rest" }
                    }
                    SwitchRow {
                        objectName: "lockWeatherPlace"
                        enabled: Backend.lockWidgetWeather
                        x: 16
                        width: parent.width - 16
                        label: "Name the place"
                        caption: "Shows your town next to the weather"
                        tip: "Adds the place name to the weather. Off keeps where you live off your lock screen."
                        checked: Backend.lockWeatherPlace
                        onToggled: (v) => { Backend.lockWeatherPlace = v; preview.mode = "rest" }
                    }
                    Column {
                        width: parent.width
                        spacing: 8
                        Item {
                            width: parent.width
                            height: msgLabel.height
                            Text { id: msgLabel; text: "Message"; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
                            Text {
                                anchors.right: parent.right
                                visible: msgField.activeFocus || msgField.text.length > Backend.lockMessageMax - 20
                                text: msgField.text.length + " / " + Backend.lockMessageMax
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
                            placeholderText: "For example: If found, please call 555 0100"
                            placeholderTextColor: Theme.textFaint
                            selectionColor: Theme.alpha(Theme.accent, 0.4)
                            selectedTextColor: Theme.text
                            font.pixelSize: Theme.fsBody
                            maximumLength: Backend.lockMessageMax
                            Accessible.name: "Lock screen message"
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
                                text: "A short line under the clock, such as how to return your laptop if it's lost. Anyone who sees your screen can read it."
                            }
                        }
                    }
                    Choice {
                        objectName: "lockWidgetStyle"
                        label: "Look"
                        value: Backend.lockWidgetStyle
                        model: [{ value: "chips", label: "Glass", tip: "Each widget sits on its own small pane of glass" },
                                { value: "plain", label: "Text only", tip: "Just the icons and text, straight on the lock screen" }]
                        onPicked: (v) => { Backend.lockWidgetStyle = v; preview.mode = "rest" }
                    }
                }
            }

            // ---------------------------------------------------------- privacy
            Card {
                width: parent.width
                height: implicitHeight
                Column {
                    width: parent.width
                    spacing: 16
                    SectionTitle { text: "Privacy" }
                    SwitchRow {
                        objectName: "lockHideNotifications"
                        label: "Hide notifications and music"
                        caption: "Nothing from your apps under the clock"
                        tip: "Hides GNOME's notifications and music controls while the screen is locked. They're all still there when you unlock. GNOME's own notification settings aren't changed."
                        checked: Backend.lockHideNotifications
                        onToggled: (v) => { Backend.lockHideNotifications = v; preview.mode = "rest" }
                    }
                }
            }

            // ---------------------------------------------------------- unlock
            Card {
                width: parent.width
                height: implicitHeight
                Column {
                    width: parent.width
                    spacing: 16
                    SectionTitle { text: "Unlock" }
                    Choice {
                        objectName: "lockSlide"
                        enabled: preview.glass
                        label: "Animation"
                        value: Backend.lockSlide
                        model: [{ value: "gnome", label: "GNOME", tip: "GNOME's own quick slide" },
                                { value: "smooth", label: "Smooth", tip: "The glass glides up and slows as it leaves" },
                                { value: "spring", label: "Spring", tip: "The glass gathers itself, then lifts away quickly" }]
                        onPicked: (v) => Backend.lockSlide = v
                    }
                    LabeledSlider {
                        objectName: "lockSlideMs"
                        enabled: preview.glass && Backend.lockSlide !== "gnome"
                        label: "Slide time"
                        from: 250; to: 1200; stepSize: 10
                        value: Backend.lockSlideMs
                        format: (v) => (v / 1000).toFixed(2) + " s"
                        onMoved: (v) => Backend.lockSlideMs = Math.round(v)
                        tip: "How long the glass takes to slide away when you unlock. Reduce animation in GNOME's settings makes it instant."
                    }
                    LabeledSlider {
                        objectName: "lockBounce"
                        enabled: preview.glass && Backend.lockSlide === "spring"
                        label: "Bounce"
                        value: Backend.lockBounce
                        onMoved: (v) => Backend.lockBounce = v
                        tip: "How much the glass gathers itself before it lifts away, like a spring letting go. Left lifts straight off; right gives a small dip first."
                    }
                }
            }

            LoginScreenCard { width: parent.width }
        }
    }
    Rectangle {
        anchors.left: side.left; width: page.sideW
        y: side.y + side.height - height; height: 32
        visible: side.contentY + side.height < side.contentHeight - 1
        gradient: Gradient {
            GradientStop { position: 0; color: Theme.alpha(Theme.base, 0) }
            GradientStop { position: 1; color: Theme.alpha(Theme.base, 0.92) }
        }
    }
}
