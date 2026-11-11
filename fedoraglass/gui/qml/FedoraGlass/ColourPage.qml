import QtQuick
import QtQuick.Controls.Basic as C
import FedoraGlass.Core

// Colour: light or dark, the accent, the tint the glass leans towards, and corners.
SettingsPage {
    id: page
    objectName: "colourPage"
    pageId: "colour"
    previewSlot: slot

    Card {
        width: parent.width
        height: implicitHeight
        Column {
            width: parent.width
            spacing: 16
            SectionTitle { text: qsTr("Style and accent"); resetKeys: ["scheme", "accent", "accent_from_wallpaper", "accent_own"] }
            Column {
                width: parent.width
                spacing: 8
                Text { text: qsTr("Style"); color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
                Segmented {
                    objectName: "schemeChoice"
                    width: parent.width
                    model: [{ value: "auto", label: qsTr("Auto"), icon: "auto", tip: qsTr("Follow GNOME's light/dark setting") },
                            { value: "dark", label: qsTr("Dark"), icon: "moon", tip: qsTr("Always use the dark style, whatever GNOME is set to") },
                            { value: "light", label: qsTr("Light"), icon: "sun", tip: qsTr("Always use the light style, whatever GNOME is set to") }]
                    value: Backend.scheme
                    onActivated: (v) => Backend.scheme = v
                    Accessible.name: qsTr("Style")
                }
            }
            Column {
                width: parent.width
                spacing: 10
                Text { text: qsTr("Accent colour"); color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
                AccentRow { width: parent.width }
            }
            SwitchRow {
                objectName: "wallpaperAccent"
                label: qsTr("Accent matches my wallpaper")
                caption: qsTr("Buttons and highlights take a clear colour from your wallpaper when you press Apply")
                tip: qsTr("Fedora Glass picks the main colour of your wallpaper and makes it clear enough for buttons and switches. It looks again each time you press Apply. Picking an accent above turns this off.")
                checked: Backend.accentFromWallpaper
                onToggled: (on) => Backend.accentFromWallpaper = on
            }
        }
    }

    Card {
        width: parent.width
        height: implicitHeight
        Column {
            width: parent.width
            spacing: 16
            SectionTitle { text: qsTr("Tint and corners"); resetKeys: ["tint", "tint_strength", "radius", "tint_from_wallpaper", "tint_own", "wallpaper_match"] }
            Item {
                width: parent.width
                height: 36
                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2
                    Text { text: qsTr("Tint"); color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
                    Text {
                        objectName: "tintCaption"
                        text: Backend.tintFromWallpaper ? qsTr("Taken from your wallpaper") : qsTr("The colour the glass leans towards")
                        color: Theme.textFaint; font.pixelSize: Theme.fsSmall
                    }
                }
                C.AbstractButton {
                    id: tintButton
                objectName: "tintButton"
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    width: 108
                    height: 34
                    hoverEnabled: true
                    focusPolicy: Qt.StrongFocus
                    onClicked: tintPicker.open()
                    Accessible.name: qsTr("Tint colour")
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    LgToolTip { shown: tintButton.hovered; text: Backend.tintFromWallpaper ? qsTr("Choose your own tint colour instead") : qsTr("Choose the tint colour") }
                    background: Rectangle {
                        radius: height / 2
                        color: tintButton.hovered ? Theme.surfaceHi : Theme.well
                        border.width: 1
                        border.color: Theme.border
                        FocusRing { target: tintButton; radius: height / 2 }
                    }
                    contentItem: Row {
                        spacing: 8
                        leftPadding: 6
                        Rectangle {
                            width: 22; height: 22; radius: 11
                            anchors.verticalCenter: parent.verticalCenter
                            color: Backend.tint
                            border.width: 1
                            border.color: Qt.rgba(0, 0, 0, 0.15)
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: Backend.tint.toUpperCase()
                            color: Theme.textDim
                            font.family: Theme.mono
                            font.pixelSize: 12
                        }
                    }
                    ColorPicker {
                        id: tintPicker
                        y: parent.height + 8
                        x: parent.width - width
                        title: qsTr("Tint colour")
                        color: Backend.tint
                        onPicked: (hex) => Backend.tint = hex
                    }
                }
            }
            SwitchRow {
                objectName: "wallpaperTint"
                label: qsTr("Match my wallpaper")
                caption: qsTr("The glass takes a soft colour from your wallpaper when you press Apply")
                tip: qsTr("Fedora Glass picks the main colour of your wallpaper, leaving out black, white and grey, and softens it into a tint. It looks again each time you press Apply, not by itself. Picking a tint colour turns this off.")
                checked: Backend.tintFromWallpaper
                onToggled: (on) => Backend.tintFromWallpaper = on
            }
            // A word on the wallpaper match: looking, can't, or a new wallpaper since Apply.
            Row {
                objectName: "wallpaperNote"
                readonly property string note: Backend.wallpaperMatchBusy ? qsTr("Looking at your wallpaper…")
                    : Backend.wallpaperMatchNote !== "" ? Backend.wallpaperMatchNote
                    : Backend.wallpaperChangedSince ? qsTr("Your wallpaper changed since the last Apply. Press Apply to take its colour again.")
                    : ""
                visible: (Backend.tintFromWallpaper || Backend.accentFromWallpaper) && note !== ""
                width: parent.width
                spacing: 8
                Icon {
                    id: noteIcon
                    name: "info"; size: 16
                    color: Backend.wallpaperChangedSince && !Backend.wallpaperMatchBusy ? Theme.accentText : Theme.textDim
                }
                Text {
                    objectName: "wallpaperNoteText"
                    width: parent.width - noteIcon.width - 8
                    text: parent.note
                    wrapMode: Text.WordWrap
                    color: Theme.textDim
                    font.pixelSize: Theme.fsSmall + 1
                }
            }
            LabeledSlider {
                objectName: "tintStrength"
            label: qsTr("Tint strength")
                value: Backend.tintStrength
                defaultValue: Backend.defaults.tint_strength
                onMoved: (v) => Backend.tintStrength = v
                tip: qsTr("How much of the tint colour is mixed into the glass. Left is clear, colourless glass; right is a strongly coloured pane.")
            }
            LabeledSlider {
                objectName: "cornerRoundness"
            label: qsTr("Corner roundness")
                from: 0; to: 32; stepSize: 1
                value: Backend.radius
                defaultValue: Backend.defaults.radius
                format: (v) => qsTr("%1 px").arg(Math.round(v))
                onMoved: (v) => Backend.radius = v
                tip: qsTr("How round the corners of the panel, menus and windows are. Left is sharp, square corners; right is soft, pill-like corners.")
            }
        }
    }

    side: [
        Item { id: slot; objectName: "colourPreviewSlot"; width: parent.width; height: page.previewH },
        PreviewNote {}
    ]
}
