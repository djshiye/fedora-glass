import QtQuick
import FedoraGlass.Core

// Glass: how much of it, its effects (folded), where it shows, and speed.
SettingsPage {
    id: page
    objectName: "glassPage"
    pageId: "glass"
    previewSlot: slot

    // Named after the preset the slider sits nearest to (settings.PRESETS, through Backend).
    function frostName(f) { return Theme.presetLabel(Backend.frostName(f)) }
    function peek() { if (Theme.preview) Theme.preview.peekEdge("") }

    Card {
        width: parent.width
        height: implicitHeight
        Column {
            width: parent.width
            spacing: 6
            Item {
                width: parent.width
                height: 28
                SectionTitle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - pill.width - 12
                    text: qsTr("How much glass")
                    resetKeys: ["frost"]
                    resetTip: qsTr("Back to Balanced")
                }
                Rectangle {
                    id: pill
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    height: 28
                    width: valueRow.width + 22
                    radius: height / 2
                    color: Theme.alpha(Theme.accent, Theme.dark ? 0.18 : 0.12)
                    Row {
                        id: valueRow
                        anchors.centerIn: parent
                        spacing: 6
                        Text { text: page.frostName(Backend.frost); color: Theme.accentText; font.pixelSize: 13; font.weight: Font.DemiBold }
                        Text { text: Math.round(Backend.frost * 100) + "%"; color: Theme.accentText; opacity: 0.75; font.pixelSize: 13; font.features: { "tnum": 1 } }
                    }
                }
            }
            FrostSlider {
                objectName: "glassFrost"
                width: parent.width
                value: Backend.frost
                ticks: Backend.frostTicks
                onMoved: (v) => Backend.frost = v
            }
            Fold {
                id: effects
                objectName: "glassEffects"
                card: false
                divider: true
                title: qsTr("Glass effects")
                summary: qsTr("Bend, rainbow edge, colour bleed and 2 more")
                Column {
                    width: parent.width
                    spacing: 2
                    Item {
                        width: parent.width
                        height: Math.max(status.implicitHeight + 8, reset.visible ? reset.height : 0)
                        Text {
                            id: status
                            objectName: "glassStatus"
                            width: parent.width - (reset.visible ? reset.width + 12 : 0)
                            wrapMode: Text.WordWrap
                            color: Theme.textFaint
                            font.pixelSize: Theme.fsSmall
                            text: Backend.glassLive
                                  ? qsTr("The preview shows these as you change them.")
                                  : Backend.glassProblemNote !== "" ? Backend.glassProblemNote
                                  : qsTr("Drawn by Fedora Glass's own Shell extension. Apply, then restart your PC once to start it.")
                        }
                        ResetButton {
                            id: reset
                            objectName: "cardReset"
                            readonly property var keys: ["refraction", "dispersion", "vibrancy", "bleed", "pointer_light"]
                            visible: Backend.changedFromDefault.some((k) => keys.indexOf(k) >= 0)
                            anchors.right: parent.right
                            text: qsTr("Reset")
                            tip: qsTr("Put the glass effects back to their defaults (Apply to use them)")
                            onClicked: Backend.resetSettings(keys)
                        }
                    }
                    LabeledSlider {
                        objectName: "bend"
                        inline: true
                        label: qsTr("Bend")
                        value: Backend.refraction
                        defaultValue: Backend.defaults.refraction
                        onMoved: (v) => { Backend.refraction = v; page.peek() }
                        tip: qsTr("How strongly the rounded edge bends what's behind it. Left is flat glass; right is a thick lens.")
                    }
                    LabeledSlider {
                        objectName: "rainbowEdge"
                        inline: true
                        label: qsTr("Rainbow edge")
                        value: Backend.dispersion
                        defaultValue: Backend.defaults.dispersion
                        onMoved: (v) => { Backend.dispersion = v; page.peek() }
                        tip: qsTr("Splits light into colours along the edge, like real glass. Left is no colour fringe; right is a vivid rainbow edge.")
                    }
                    LabeledSlider {
                        objectName: "colourThroughGlass"
                        inline: true
                        label: qsTr("Colour through glass")
                        value: Backend.vibrancy
                        defaultValue: Backend.defaults.vibrancy
                        onMoved: (v) => Backend.vibrancy = v
                        tip: qsTr("How vivid the wallpaper and windows look through the glass. Left keeps their colours as they are; right makes them richer.")
                    }
                    LabeledSlider {
                        objectName: "colourBleed"
                        inline: true
                        label: qsTr("Colour bleed")
                        value: Backend.bleed
                        defaultValue: Backend.defaults.bleed
                        onMoved: (v) => Backend.bleed = v
                        tip: qsTr("How much the colours of icons and text light up the glass around them, like light spreading inside real glass. Left keeps the glass neutral; right gives them a coloured glow.")
                    }
                    LabeledSlider {
                        objectName: "lightFollowsPointer"
                        inline: true
                        label: qsTr("Light follows pointer")
                        value: Backend.pointerLight
                        defaultValue: Backend.defaults.pointer_light
                        onMoved: (v) => Backend.pointerLight = v
                        tip: qsTr("How much the light on the glass edges turns towards your pointer as it moves nearby. Left keeps the light still; right lets it follow closely.")
                    }
                }
            }
        }
    }

    Card {
        width: parent.width
        height: implicitHeight
        Column {
            width: parent.width
            spacing: 14
            SectionTitle {
                text: qsTr("Where the glass shows")
                caption: qsTr("Each one costs some graphics power. Turn it off where you don't need it.")
                resetKeys: ["glass_panel", "glass_menus", "blur_app_windows", "glass_overview", "glass_see_windows", "quick_toggle"]
            }
            Flow {
                width: parent.width
                spacing: 8
                ToggleChip {
                    objectName: "glassPanel"
                    text: qsTr("Panel")
                    on: Backend.glassPanel
                    tip: qsTr("Real glass behind the top bar or Dash to Panel, a dock and the dash in Activities. Off leaves plain tinted bars.")
                    onSwitched: (v) => Backend.glassPanel = v
                }
                ToggleChip {
                    objectName: "glassMenus"
                    text: qsTr("Menus")
                    on: Backend.glassMenus
                    tip: Backend.hasStartMenu ? qsTr("Quick settings, the calendar, the start menu and app menus. Off leaves plain tinted panes.")
                                  : qsTr("Quick settings, the calendar and app menus. Off leaves plain tinted panes.")
                    onSwitched: (v) => { Backend.glassMenus = v; if (Theme.preview) Theme.preview.showPopup() }
                }
                ToggleChip {
                    objectName: "glassAppWindows"
                    text: qsTr("App windows")
                    on: Backend.blurAppWindows
                    tip: qsTr("Frosted wallpaper behind see-through app windows. Off shows it sharp, which is lighter on the graphics card.")
                    onSwitched: (v) => Backend.blurAppWindows = v
                }
                ToggleChip {
                    objectName: "glassOverview"
                    text: qsTr("Overview")
                    on: Backend.glassOverview
                    tip: qsTr("Blurred wallpaper behind the Activities overview. Off leaves it sharp.")
                    onSwitched: (v) => { Backend.glassOverview = v; if (Theme.preview) Theme.preview.scene = "overview" }
                }
                ToggleChip {
                    objectName: "glassSeeWindows"
                    text: qsTr("See windows through")
                    enabled: Backend.glassPanel || Backend.glassMenus
                    on: Backend.glassSeeWindows
                    tip: qsTr("On, the panel and menus show the windows behind them as well as the wallpaper. Off shows only the wallpaper, which is lighter on the graphics card.")
                    onSwitched: (v) => Backend.glassSeeWindows = v
                }
            }
            Rectangle { width: parent.width; height: 1; color: Theme.divider }
            // The Glass tile in GNOME's Quick Settings, drawn as GNOME draws it (an accent pill
            // when on), next to the switch that puts it there.
            Item {
                width: parent.width
                height: Math.max(tile.height, qsRow.implicitHeight)
                Rectangle {
                    id: tile
                    objectName: "quickTogglePreview"
                    anchors.verticalCenter: parent.verticalCenter
                    width: 132; height: 44
                    radius: height / 2
                    color: Theme.accent
                    opacity: Backend.quickToggle ? 1 : 0.35
                    Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                    Accessible.ignored: true
                    Row {
                        x: 16
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 10
                        Icon { name: "glassPane"; size: 18; strokeWidth: 2; color: Theme.accentFg; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: qsTr("Glass"); color: Theme.accentFg; font.pixelSize: Theme.fsBody; font.weight: Font.DemiBold; anchors.verticalCenter: parent.verticalCenter }
                    }
                }
                SwitchRow {
                    id: qsRow
                    objectName: "quickToggle"
                    x: tile.width + 16
                    width: parent.width - x
                    anchors.verticalCenter: parent.verticalCenter
                    label: qsTr("Glass switch in Quick Settings")
                    caption: qsTr("Pause all the glass from Quick Settings, and turn it on again there. It is back on at your next login.")
                    checked: Backend.quickToggle
                    tip: qsTr("Handy for a game or a screen share. The tile says Paused while the glass is off.")
                    onToggled: (on) => Backend.quickToggle = on
                }
            }
        }
    }

    SpeedCard { width: parent.width }

    side: [
        Item { id: slot; objectName: "glassPreviewSlot"; width: parent.width; height: page.previewH },
        PreviewNote {}
    ]
}
