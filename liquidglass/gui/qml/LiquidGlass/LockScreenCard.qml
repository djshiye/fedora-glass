import QtQuick
import LiquidGlass.Core

// The glass lock screen: a frosted sheet over the wallpaper, a glass card behind the
// password, GNOME's clock in a bolder or lighter cut, and the sheet sliding up on unlock.
Card {
    id: root
    readonly property bool on: Backend.lockGlass
    height: implicitHeight

    component Choice: Column {
        property string label: ""
        property alias model: seg.model
        property alias value: seg.value
        property string name: ""
        signal picked(var v)
        width: parent.width
        spacing: 8
        Text { text: parent.label; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
        Segmented {
            id: seg
            width: parent.width
            onActivated: (v) => parent.picked(v)
            Accessible.name: parent.label
        }
    }

    Column {
        width: parent.width
        spacing: 16
        SectionTitle { text: "Lock screen" }
        Text {
            width: parent.width
            wrapMode: Text.WordWrap
            color: Theme.textFaint
            font.pixelSize: Theme.fsSmall
            text: "Only your wallpaper shows through the glass. Your open windows and notifications never do. Changes show the next time you lock."
        }
        SwitchRow {
            objectName: "lockGlass"
            label: "Glass lock screen"
            caption: "A sheet of frosted glass that slides up into your desktop"
            tip: "Turns the lock screen into one sheet of frosted glass over your wallpaper. When you unlock, the sheet slides up and your desktop appears underneath. Off gives you GNOME's own lock screen."
            checked: root.on
            onToggled: (v) => Backend.lockGlass = v
        }
        LabeledSlider {
            objectName: "lockBlur"
            enabled: root.on
            label: "Frost"
            from: 10; to: 100; stepSize: 1
            value: Backend.lockBlur
            format: (v) => Math.round(v) + " px"
            onMoved: (v) => Backend.lockBlur = Math.round(v)
            tip: "How frosted the glass is. Left shows more of your wallpaper's shapes; right turns it into soft colour, which keeps the clock calm on a busy picture."
        }
        LabeledSlider {
            objectName: "lockDim"
            enabled: root.on
            label: "Darken"
            from: 0; to: 0.65
            value: Backend.lockDim
            onMoved: (v) => Backend.lockDim = v
            tip: "How much darker the glass is than your wallpaper. More keeps the white clock and text easy to read on a bright picture."
        }
        LabeledSlider {
            objectName: "lockTint"
            enabled: root.on
            label: "Tint"
            value: Backend.lockTint
            onMoved: (v) => Backend.lockTint = v
            tip: "How much of your glass tint colour washes over the lock screen. Left keeps your wallpaper's own colours."
        }
        SwitchRow {
            objectName: "lockCard"
            enabled: root.on
            label: "Glass card behind the password"
            caption: "Your picture, name and password field sit on their own pane"
            tip: "Puts a pane of glass, a little lighter than the rest, behind your picture, name and password field when you start typing."
            checked: Backend.lockCard
            onToggled: (v) => Backend.lockCard = v
        }
        Choice {
            objectName: "lockClock"
            enabled: root.on
            label: "Clock"
            value: Backend.lockClock
            model: [{ value: "gnome", label: "GNOME", tip: "GNOME's own clock" },
                    { value: "bold", label: "Bold", tip: "Large, heavy numbers that stand out on the glass" },
                    { value: "thin", label: "Thin", tip: "Large, light numbers for a quieter look" }]
            onPicked: (v) => Backend.lockClock = v
        }
        Choice {
            objectName: "lockClockPosition"
            enabled: root.on
            label: "Clock position"
            value: Backend.lockClockPosition
            model: [{ value: "gnome", label: "GNOME", tip: "Where GNOME puts it, about a third of the way down" },
                    { value: "top", label: "Top", tip: "Near the top of the screen, with more wallpaper below. The password appears there too." },
                    { value: "middle", label: "Middle", tip: "In the middle of the screen. The password appears there too." }]
            onPicked: (v) => Backend.lockClockPosition = v
        }
        Choice {
            objectName: "lockSlide"
            enabled: root.on
            label: "Unlock animation"
            value: Backend.lockSlide
            model: [{ value: "gnome", label: "GNOME", tip: "GNOME's own quick slide" },
                    { value: "smooth", label: "Smooth", tip: "The glass glides up and slows as it leaves" },
                    { value: "spring", label: "Spring", tip: "The glass gathers itself, then lifts away quickly" }]
            onPicked: (v) => Backend.lockSlide = v
        }
        LabeledSlider {
            objectName: "lockSlideMs"
            enabled: root.on && Backend.lockSlide !== "gnome"
            label: "Slide time"
            from: 250; to: 1200; stepSize: 10
            value: Backend.lockSlideMs
            format: (v) => (v / 1000).toFixed(2) + " s"
            onMoved: (v) => Backend.lockSlideMs = Math.round(v)
            tip: "How long the glass takes to slide away when you unlock. Reduce animation in GNOME's settings makes it instant."
        }
        LabeledSlider {
            objectName: "lockBounce"
            enabled: root.on && Backend.lockSlide === "spring"
            label: "Bounce"
            value: Backend.lockBounce
            onMoved: (v) => Backend.lockBounce = v
            tip: "How much the glass gathers itself before it lifts away, like a spring letting go. Left lifts straight off; right gives a small dip first."
        }
    }
}
