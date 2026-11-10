import QtQuick
import QtQuick.Controls.Basic as C
import QtQuick.Window
import FedoraGlass.Core

// Motion: one style for every animation, one speed, the glass's own motion switches,
// and (folded) each animation on its own.
SettingsPage {
    id: page
    objectName: "motionPage"
    pageId: "motion"
    previewSlot: slot

    // The big preview plays along with the animation player inside the fold.
    Component.onCompleted: Theme.motionDriver = motionCard
    Component.onDestruction: if (Theme.motionDriver === motionCard) Theme.motionDriver = null
    function play() { motionCard.playEvent("open") }

    readonly property var glyphFor: ({ off: "off", calm: "scalefade", gnome: "gnome", lively: "spring", playful: "bounce" })

    Card {
        width: parent.width
        height: implicitHeight
        Column {
            width: parent.width
            spacing: 14
            SectionTitle {
                text: "Motion style"
                caption: Backend.motionStyle === "custom" ? "Your own mix. Pick a style to set every animation at once."
                                                          : "One choice sets every animation"
                resetKeys: ["motion"]
                resetTip: "Back to Lively, at normal speed"
            }
            Row {
                id: styleRow
                objectName: "motionStyle"
                width: parent.width
                spacing: 10
                readonly property real tileW: (width - spacing * (Backend.motionStyles.length - 1)) / Math.max(1, Backend.motionStyles.length)
                Repeater {
                    model: Backend.motionStyles
                    delegate: C.AbstractButton {
                        id: tile
                        required property var modelData
                        required property int index
                        readonly property bool selected: Backend.motionStyle === modelData.id
                        objectName: "motionStyle_" + modelData.id
                        width: styleRow.tileW
                        implicitHeight: 96
                        hoverEnabled: true
                        focusPolicy: Qt.StrongFocus
                        Accessible.name: modelData.label + " motion"
                        Accessible.role: Accessible.RadioButton
                        Accessible.checked: selected
                        onClicked: { Backend.setMotionStyle(modelData.id); page.play() }
                        Keys.onLeftPressed: { const p = styleRow.children[index - 1]; if (p && p.objectName.startsWith("motionStyle_")) { p.forceActiveFocus(Qt.TabFocusReason); p.clicked() } }
                        Keys.onRightPressed: { const n = styleRow.children[index + 1]; if (n && n.objectName.startsWith("motionStyle_")) { n.forceActiveFocus(Qt.TabFocusReason); n.clicked() } }
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                        LgToolTip { shown: (tile.hovered || tile.visualFocus) && !tile.pressed; text: tile.modelData.tip }
                        background: Rectangle {
                            radius: Theme.rM - 2
                            color: tile.selected ? Theme.alpha(Theme.accent, Theme.dark ? 0.16 : 0.1)
                                   : tile.down ? Theme.wellHi : tile.hovered ? Theme.surfaceHi : Theme.surface
                            border.width: tile.selected ? 1.5 : 1
                            border.color: tile.selected ? Theme.alpha(Theme.accent, 0.85) : Theme.border
                            Behavior on color { ColorAnimation { duration: Theme.fast } }
                            FocusRing { target: tile; radius: Theme.rM }
                        }
                        contentItem: Column {
                            spacing: 8
                            topPadding: 8
                            Rectangle {
                                x: 8
                                width: tile.width - 16
                                height: 50
                                radius: 9
                                color: tile.selected ? Theme.alpha(Theme.accent, Theme.dark ? 0.2 : 0.14) : Theme.well
                                CurveGlyph {
                                    anchors.centerIn: parent
                                    width: Math.min(parent.width - 20, 64)
                                    height: 30
                                    preset: page.glyphFor[tile.modelData.id] || "spring"
                                    color: tile.selected ? Theme.accentText : Theme.textDim
                                }
                            }
                            Text {
                                width: tile.width
                                horizontalAlignment: Text.AlignHCenter
                                text: tile.modelData.label
                                color: tile.selected ? Theme.text : Theme.textDim
                                font.pixelSize: 13
                                font.weight: tile.selected ? Font.DemiBold : Font.Normal
                            }
                        }
                    }
                }
            }
            Rectangle { width: parent.width; height: 1; color: Theme.divider }
            Item {
                objectName: "motionSpeed"
                width: parent.width
                height: 32
                enabled: Backend.motionStyle !== "off"
                opacity: enabled ? 1 : 0.5
                Text { id: speedLabel; anchors.verticalCenter: parent.verticalCenter; text: "Speed"; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
                Text { id: slower; x: 90; anchors.verticalCenter: parent.verticalCenter; text: "Slower"; color: Theme.textFaint; font.pixelSize: Theme.fsSmall }
                Text { id: faster; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: "Faster"; color: Theme.textFaint; font.pixelSize: Theme.fsSmall }
                LgSlider {
                    anchors.left: slower.right; anchors.leftMargin: 12
                    anchors.right: faster.left; anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    from: 0.5; to: 2; stepSize: 0.05
                    value: Backend.motionSpeed
                    markValue: 1
                    onMoved: Backend.motionSpeed = value
                    onPressedChanged: if (!pressed) page.play()
                    Accessible.name: "Animation speed"
                }
            }
        }
    }

    Card {
        width: parent.width
        height: implicitHeight
        padding: 12
        Column {
            x: 8
            width: parent.width - 16
            spacing: 0
            SwitchRow {
                objectName: "liquidMotion"
                label: "Liquid motion"
                caption: "Glass gives a little when pressed and settles as menus open"
                tip: "Makes the glass respond to your touch with a soft spring. It stays off when Reduce animation is on in Settings."
                checked: Backend.liquidMotion
                onToggled: (on) => { Backend.liquidMotion = on; if (Theme.preview) Theme.preview.showPopup() }
            }
            Rectangle { width: parent.width; height: 1; color: Theme.divider }
            SwitchRow {
                objectName: "menuGrow"
                label: "Menus grow from their button"
                caption: ""
                tip: (Backend.hasStartMenu ? "The start menu, quick settings and the calendar" : "Quick settings and the calendar")
                     + " pour out of the button you clicked, and flow back into it when they close. Off, menus open in place. It stays off when Reduce animation is on in Settings."
                enabled: Backend.liquidMotion
                checked: Backend.menuGrow
                onToggled: (on) => { Backend.menuGrow = on; if (Theme.preview) Theme.preview.showPopup() }
            }
            Rectangle { visible: glide.visible; width: parent.width; height: 1; color: Theme.divider }
            SwitchRow {
                id: glide
                objectName: "motionGlide"
                visible: Backend.hasDashToPanel     // it glides along Dash to Panel's taskbar only
                label: "Gliding highlight"
                caption: ""
                tip: "Instead of a separate highlight blinking on each taskbar icon, one soft highlight follows your pointer along the taskbar. It jumps straight there when Reduce animation is on."
                checked: Backend.hoverGlide
                onToggled: (on) => Backend.hoverGlide = on
            }
        }
    }

    Fold {
        objectName: "eachAnimation"
        title: "Each animation on its own"
        summary: "Open, minimize, close, app starting, panel hover"
        MotionCard { id: motionCard; embedded: true; width: parent.width }
    }

    side: [
        Item { id: slot; objectName: "motionPreviewSlot"; width: parent.width; height: Math.round(width * 9 / 16) },
        Row {
            spacing: 10
            LgButton {
                objectName: "playMotion"
                kind: "secondary"
                implicitHeight: 32
                leftPadding: 12; rightPadding: 14
                text: "Play again"
                iconName: "run"
                enabled: Backend.motionStyle !== "off"
                onClicked: page.play()
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: "Pick a style to watch it play here."
                color: Theme.textFaint
                font.pixelSize: Theme.fsSmall + 1
            }
        }
    ]
}
