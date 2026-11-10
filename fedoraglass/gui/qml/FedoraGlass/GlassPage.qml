import QtQuick
import FedoraGlass.Core

// Glass: how much of it, its effects (folded), where it shows, and speed.
SettingsPage {
    id: page
    objectName: "glassPage"
    pageId: "glass"
    previewSlot: slot

    function frostName(f) {
        if (f < 0.12) return "Liquid"
        if (f < 0.35) return "Clear"
        if (f < 0.62) return "Balanced"
        if (f < 0.9) return "Frosted"
        return "Solid"
    }
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
                    text: "How much glass"
                    resetKeys: ["frost"]
                    resetTip: "Back to Balanced"
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
                ticks: [{ value: 0.0 }, { value: 0.25 }, { value: 0.45 }, { value: 0.8 }, { value: 1.0 }]
                onMoved: (v) => Backend.frost = v
            }
            Fold {
                id: effects
                objectName: "glassEffects"
                card: false
                divider: true
                title: "Glass effects"
                summary: "Bend, rainbow edge, colour bleed and 2 more"
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
                                  ? "The preview shows these as you change them."
                                  : Backend.glassProblemNote !== "" ? Backend.glassProblemNote
                                  : "Drawn by Fedora Glass's own Shell extension. Apply, then restart your PC once to start it."
                        }
                        ResetButton {
                            id: reset
                            objectName: "cardReset"
                            readonly property var keys: ["refraction", "dispersion", "vibrancy", "bleed", "pointer_light"]
                            visible: Backend.changedFromDefault.some((k) => keys.indexOf(k) >= 0)
                            anchors.right: parent.right
                            text: "Reset"
                            tip: "Put the glass effects back to their defaults (Apply to use them)"
                            onClicked: Backend.resetSettings(keys)
                        }
                    }
                    LabeledSlider {
                        objectName: "bend"
                        inline: true
                        label: "Bend"
                        value: Backend.refraction
                        defaultValue: Backend.defaults.refraction
                        onMoved: (v) => { Backend.refraction = v; page.peek() }
                        tip: "How strongly the rounded edge bends what's behind it. Left is flat glass; right is a thick lens."
                    }
                    LabeledSlider {
                        objectName: "rainbowEdge"
                        inline: true
                        label: "Rainbow edge"
                        value: Backend.dispersion
                        defaultValue: Backend.defaults.dispersion
                        onMoved: (v) => { Backend.dispersion = v; page.peek() }
                        tip: "Splits light into colours along the edge, like real glass. Left is no colour fringe; right is a vivid rainbow edge."
                    }
                    LabeledSlider {
                        objectName: "colourThroughGlass"
                        inline: true
                        label: "Colour through glass"
                        value: Backend.vibrancy
                        defaultValue: Backend.defaults.vibrancy
                        onMoved: (v) => Backend.vibrancy = v
                        tip: "How vivid the wallpaper and windows look through the glass. Left keeps their colours as they are; right makes them richer."
                    }
                    LabeledSlider {
                        objectName: "colourBleed"
                        inline: true
                        label: "Colour bleed"
                        value: Backend.bleed
                        defaultValue: Backend.defaults.bleed
                        onMoved: (v) => Backend.bleed = v
                        tip: "How much the colours of icons and text light up the glass around them, like light spreading inside real glass. Left keeps the glass neutral; right gives them a coloured glow."
                    }
                    LabeledSlider {
                        objectName: "lightFollowsPointer"
                        inline: true
                        label: "Light follows pointer"
                        value: Backend.pointerLight
                        defaultValue: Backend.defaults.pointer_light
                        onMoved: (v) => Backend.pointerLight = v
                        tip: "How much the light on the glass edges turns towards your pointer as it moves nearby. Left keeps the light still; right lets it follow closely."
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
                text: "Where the glass shows"
                caption: "Each one costs some graphics power. Turn it off where you don't need it."
                resetKeys: ["glass_panel", "glass_menus", "blur_app_windows", "glass_overview", "glass_see_windows"]
            }
            Flow {
                width: parent.width
                spacing: 8
                ToggleChip {
                    objectName: "glassPanel"
                    text: "Panel"
                    on: Backend.glassPanel
                    tip: "Real glass behind the top bar or Dash to Panel, a dock and the dash in Activities. Off leaves plain tinted bars."
                    onSwitched: (v) => Backend.glassPanel = v
                }
                ToggleChip {
                    objectName: "glassMenus"
                    text: "Menus"
                    on: Backend.glassMenus
                    tip: (Backend.hasStartMenu ? "Quick settings, the calendar, the start menu and app menus. " : "Quick settings, the calendar and app menus. ")
                         + "Off leaves plain tinted panes."
                    onSwitched: (v) => { Backend.glassMenus = v; if (Theme.preview) Theme.preview.showPopup() }
                }
                ToggleChip {
                    objectName: "glassAppWindows"
                    text: "App windows"
                    on: Backend.blurAppWindows
                    tip: "Frosted wallpaper behind see-through app windows. Off shows it sharp, which is lighter on the graphics card."
                    onSwitched: (v) => Backend.blurAppWindows = v
                }
                ToggleChip {
                    objectName: "glassOverview"
                    text: "Overview"
                    on: Backend.glassOverview
                    tip: "Blurred wallpaper behind the Activities overview. Off leaves it sharp."
                    onSwitched: (v) => { Backend.glassOverview = v; if (Theme.preview) Theme.preview.scene = "overview" }
                }
                ToggleChip {
                    objectName: "glassSeeWindows"
                    text: "See windows through"
                    enabled: Backend.glassPanel || Backend.glassMenus
                    on: Backend.glassSeeWindows
                    tip: "On, the panel and menus show the windows behind them as well as the wallpaper. Off shows only the wallpaper, which is lighter on the graphics card."
                    onSwitched: (v) => Backend.glassSeeWindows = v
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
