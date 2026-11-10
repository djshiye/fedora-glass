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
            SectionTitle { text: "Style and accent"; resetKeys: ["scheme", "accent"] }
            Column {
                width: parent.width
                spacing: 8
                Text { text: "Style"; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
                Segmented {
                    objectName: "schemeChoice"
                    width: parent.width
                    model: [{ value: "auto", label: "Auto", icon: "auto", tip: "Follow GNOME's light/dark setting" },
                            { value: "dark", label: "Dark", icon: "moon", tip: "Always use the dark style, whatever GNOME is set to" },
                            { value: "light", label: "Light", icon: "sun", tip: "Always use the light style, whatever GNOME is set to" }]
                    value: Backend.scheme
                    onActivated: (v) => Backend.scheme = v
                    Accessible.name: "Style"
                }
            }
            Column {
                width: parent.width
                spacing: 10
                Text { text: "Accent colour"; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
                AccentRow { width: parent.width }
            }
        }
    }

    Card {
        width: parent.width
        height: implicitHeight
        Column {
            width: parent.width
            spacing: 16
            SectionTitle { text: "Tint and corners"; resetKeys: ["tint", "tint_strength", "radius"] }
            Item {
                width: parent.width
                height: 36
                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2
                    Text { text: "Tint"; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
                    Text { text: "The colour the glass leans towards"; color: Theme.textFaint; font.pixelSize: Theme.fsSmall }
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
                    Accessible.name: "Tint colour"
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    LgToolTip { shown: tintButton.hovered; text: "Choose the tint colour" }
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
                        title: "Tint colour"
                        color: Backend.tint
                        onPicked: (hex) => Backend.tint = hex
                    }
                }
            }
            LabeledSlider {
                objectName: "tintStrength"
            label: "Tint strength"
                value: Backend.tintStrength
                defaultValue: Backend.defaults.tint_strength
                onMoved: (v) => Backend.tintStrength = v
                tip: "How much of the tint colour is mixed into the glass. Left is clear, colourless glass; right is a strongly coloured pane."
            }
            LabeledSlider {
                objectName: "cornerRoundness"
            label: "Corner roundness"
                from: 0; to: 32; stepSize: 1
                value: Backend.radius
                defaultValue: Backend.defaults.radius
                format: (v) => Math.round(v) + " px"
                onMoved: (v) => Backend.radius = v
                tip: "How round the corners of the panel, menus and windows are. Left is sharp, square corners; right is soft, pill-like corners."
            }
        }
    }

    side: [
        Item { id: slot; objectName: "colourPreviewSlot"; width: parent.width; height: Math.round(width * 9 / 16) },
        PreviewNote {}
    ]
}
