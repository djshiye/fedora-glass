import QtQuick
import QtQuick.Controls.Basic as C
import QtQuick.Effects
import QtQuick.Window
import FedoraGlass.Core

// Home: the whole look on one screen. A preset, how much glass, light or dark and the
// accent, and the four big switches. Everything else is one click away in the sidebar.
SettingsPage {
    id: page
    objectName: "homePage"
    pageId: "home"
    previewSlot: slot
    previewInSide: false
    property alias frostHeld: frost.held

    readonly property var presetFrost: ({ Liquid: 0.0, Clear: 0.25, Balanced: 0.45, Frosted: 0.8, Solid: 1.0 })
    readonly property var presetTips: ({
        "Liquid": "Clearest glass, brightest rim",
        "Clear": "Clear glass with a little haze",
        "Balanced": "The default: readable and still glassy",
        "Frosted": "Milky, heavily blurred glass",
        "Solid": "Almost opaque, for maximum readability"
    })
    function frostName(f) {
        if (f < 0.12) return "Liquid"
        if (f < 0.35) return "Clear"
        if (f < 0.62) return "Balanced"
        if (f < 0.9) return "Frosted"
        return "Solid"
    }

    // ---- left: the preview and the presets ------------------------------------------
    Item {
        width: parent.width
        // As big as the room under the title allows, keeping the Look card in view.
        readonly property real maxH: Math.max(220, page.height - lookCard.implicitHeight - 14 - 6)
        height: Math.round(Math.min(width * 0.75, maxH))
        Item {
            id: slot
            objectName: "homePreviewSlot"
            height: parent.height
            width: parent.width
            anchors.horizontalCenter: parent.horizontalCenter
        }
    }

    Card {
        id: lookCard
        width: parent.width
        height: implicitHeight
        padding: 18
        Column {
            width: parent.width
            spacing: 12
            Row {
                spacing: 10
                Text { text: "Look"; color: Theme.text; font.pixelSize: Theme.fsTitle; font.weight: Font.DemiBold }
                Text {
                    anchors.baseline: parent.children[0].baseline
                    text: "Pick one to start. Everything else follows it."
                    color: Theme.textFaint
                    font.pixelSize: Theme.fsSmall + 1
                }
            }
            Row {
                id: presetRow
                objectName: "presetRow"
                width: parent.width
                spacing: 10
                readonly property real tileW: (width - spacing * (Backend.presets.length - 1)) / Math.max(1, Backend.presets.length)
                Repeater {
                    model: Backend.presets
                    delegate: PresetTile {
                        required property string modelData
                        required property int index
                        width: presetRow.tileW
                        name: modelData
                        frost: page.presetFrost[modelData] !== undefined ? page.presetFrost[modelData] : 0.45
                        selected: Backend.activePreset === modelData
                        tip: page.presetTips[modelData] || ""
                        rovingGroup: presetRow
                        rovingStop: selected || (index === 0 && Backend.presets.indexOf(Backend.activePreset) < 0)
                        onClicked: Backend.applyPreset(modelData)
                    }
                }
            }
        }
    }

    // ---- right: glass, colour, the big switches ------------------------------------
    side: [
        Card {
            width: parent.width
            height: implicitHeight
            Column {
                width: parent.width
                spacing: 8
                Item {
                    width: parent.width
                    height: 28
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Glass"; color: Theme.text; font.pixelSize: Theme.fsTitle; font.weight: Font.DemiBold
                    }
                    Rectangle {
                        objectName: "frostValue"
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
                    id: frost
                    objectName: "homeFrost"
                    width: parent.width
                    value: Backend.frost
                    ticks: [{ value: 0.0 }, { value: 0.25 }, { value: 0.45 }, { value: 0.8 }, { value: 1.0 }]
                    onMoved: (v) => Backend.frost = v
                }
            }
        },
        Card {
            width: parent.width
            height: implicitHeight
            Column {
                width: parent.width
                spacing: 14
                Text { text: "Colour"; color: Theme.text; font.pixelSize: Theme.fsTitle; font.weight: Font.DemiBold }
                Segmented {
                    objectName: "homeScheme"
                    width: parent.width
                    model: [{ value: "auto", label: "Auto", tip: "Follow GNOME's light/dark setting" },
                            { value: "dark", label: "Dark", tip: "Always use the dark style" },
                            { value: "light", label: "Light", tip: "Always use the light style" }]
                    value: Backend.scheme
                    onActivated: (v) => Backend.scheme = v
                    Accessible.name: "Style"
                }
                AccentRow { width: parent.width; objectName: "homeAccent" }
            }
        },
        Card {
            width: parent.width
            height: implicitHeight
            padding: 12
            Grid {
                id: tiles
                width: parent.width
                columns: 2
                spacing: 10
                readonly property real tileW: (width - spacing) / 2
                readonly property var pointerName: {
                    if (Backend.cursorTheme === "keep" || Backend.cursorTheme === "")
                        return "Your own"
                    const s = Cursors.styles.find(c => c.id === Backend.cursorTheme)
                    return s ? s.name : Backend.cursorTheme
                }
                readonly property var motionName: {
                    const s = Backend.motionStyles.find(m => m.id === Backend.motionStyle)
                    return s ? s.label : "Your own mix"
                }
                QuickTile {
                    objectName: "tileWindows"
                    width: tiles.tileW
                    iconName: "window"
                    title: "Windows"
                    state_: Backend.blurAppWindows ? "On" : "Off"
                    on: Backend.blurAppWindows
                    tip: "Frosted wallpaper behind see-through app windows. Click to switch it; the arrow opens Glass."
                    onActivated: Backend.blurAppWindows = !Backend.blurAppWindows
                    onMore: Window.window.goTo("glass", "glassAppWindows")
                }
                QuickTile {
                    objectName: "tileMotion"
                    width: tiles.tileW
                    iconName: "wave"
                    title: "Motion"
                    state_: tiles.motionName
                    on: Backend.motionStyle !== "off"
                    tip: "How windows, menus and the panel move"
                    onActivated: Window.window.goTo("motion", "motionStyle")
                    onMore: Window.window.goTo("motion", "motionStyle")
                }
                QuickTile {
                    objectName: "tileLock"
                    width: tiles.tileW
                    iconName: "lock"
                    title: "Glass lock"
                    state_: Backend.lockGlass ? "On" : "Off"
                    on: Backend.lockGlass
                    tip: "A sheet of frosted glass on the lock screen. Click to switch it; the arrow opens Lock and login."
                    onActivated: Backend.lockGlass = !Backend.lockGlass
                    onMore: Window.window.goTo("lock", "lockGlass")
                }
                QuickTile {
                    objectName: "tilePointer"
                    width: tiles.tileW
                    iconName: "pointer"
                    title: "Pointer"
                    state_: tiles.pointerName
                    on: Backend.cursorTheme !== "keep" && Backend.cursorTheme !== ""
                    tip: "Pick a mouse pointer that matches the glass"
                    onActivated: Window.window.goTo("pointer", "cursorCard")
                    onMore: Window.window.goTo("pointer", "cursorCard")
                }
            }
        }
    ]

    // ---- a preset as a little picture of its glass --------------------------------------
    component PresetTile: C.AbstractButton {
        id: tile
        property string name: ""
        property real frost: 0.45
        property bool selected: false
        property string tip: ""
        property Item rovingGroup: null
        property bool rovingStop: selected
        readonly property bool _groupFocused: Window.activeFocusItem !== null && Window.activeFocusItem.rovingGroup === rovingGroup
        focusPolicy: activeFocus || (rovingStop && !_groupFocused) ? Qt.StrongFocus : Qt.ClickFocus
        Keys.onLeftPressed: { const p = tile.nextItemInFocusChain(false); if (p && p.rovingGroup === tile.rovingGroup) p.forceActiveFocus(Qt.TabFocusReason) }
        Keys.onRightPressed: { const n = tile.nextItemInFocusChain(true); if (n && n.rovingGroup === tile.rovingGroup) n.forceActiveFocus(Qt.TabFocusReason) }
        implicitHeight: 104
        hoverEnabled: true
        text: name
        Accessible.name: name + " preset"
        Accessible.role: Accessible.RadioButton
        Accessible.checked: selected
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        LgToolTip { shown: tile.tip.length > 0 && (tile.hovered || tile.visualFocus) && !tile.pressed; text: tile.tip }

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
            spacing: 7
            topPadding: 8
            Item {
                id: thumb
                x: 8
                width: tile.width - 16
                height: 60
                layer.enabled: true
                layer.effect: MultiEffect {
                    maskEnabled: true
                    maskSource: thumbMask
                    maskThresholdMin: 0.5
                    maskSpreadAtMin: 1.0
                }
                Image {
                    id: wall
                    anchors.fill: parent
                    source: Backend.wallpaper
                    sourceSize.width: 200
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                    smooth: true
                }
                Rectangle {     // without a wallpaper picture: a soft night sky
                    anchors.fill: parent
                    visible: wall.status !== Image.Ready
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: "#33296f" }
                        GradientStop { position: 0.55; color: "#161a35" }
                        GradientStop { position: 1; color: "#43215a" }
                    }
                }
                // The pane of glass, as frosted as the preset.
                Item {
                    id: pane
                    x: parent.width * 0.16; y: parent.height * 0.2
                    width: parent.width * 0.68; height: parent.height * 0.6
                    clip: true
                    MultiEffect {
                        x: -pane.x; y: -pane.y
                        width: thumb.width; height: thumb.height
                        source: wall
                        visible: wall.status === Image.Ready
                        blurEnabled: true
                        blurMax: 24
                        blur: 0.1 + 0.9 * tile.frost
                        autoPaddingEnabled: false
                    }
                    Rectangle {
                        anchors.fill: parent
                        radius: 7
                        color: Qt.rgba(1, 1, 1, Theme.dark ? 0.04 + 0.22 * tile.frost : 0.12 + 0.5 * tile.frost)
                        border.width: 1
                        border.color: Qt.rgba(1, 1, 1, 0.55 - 0.25 * tile.frost)
                    }
                }
            }
            Text {
                width: tile.width
                horizontalAlignment: Text.AlignHCenter
                text: tile.name
                color: tile.selected ? Theme.text : Theme.textDim
                font.pixelSize: 13
                font.weight: tile.selected ? Font.DemiBold : Font.Normal
            }
        }
        Rectangle { id: thumbMask; visible: false; layer.enabled: true; width: thumb.width; height: thumb.height; radius: 9 }
    }

    // ---- a big switch or shortcut, like a Quick Settings tile ---------------------------
    component QuickTile: C.AbstractButton {
        id: qt
        property string iconName: ""
        property string title: ""
        property string state_: ""
        property bool on: false
        property string tip: ""
        signal activated()
        signal more()
        implicitHeight: 64
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        onClicked: activated()
        Accessible.name: title + ": " + state_
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        LgToolTip { shown: qt.tip.length > 0 && (qt.hovered || qt.visualFocus) && !qt.pressed; text: qt.tip }
        background: Rectangle {
            radius: Theme.rM - 2
            color: qt.on ? Theme.alpha(Theme.accent, Theme.dark ? (qt.hovered ? 0.24 : 0.17) : (qt.hovered ? 0.18 : 0.12))
                 : qt.down ? Theme.wellHi : qt.hovered ? Theme.surfaceHi : Theme.surface
            border.width: 1
            border.color: qt.on ? Theme.alpha(Theme.accent, 0.42) : Theme.border
            Behavior on color { ColorAnimation { duration: Theme.fast } }
            FocusRing { target: qt; radius: Theme.rM }
        }
        contentItem: Item {
            Icon {
                id: ic
                x: 12; y: 12
                name: qt.iconName
                size: 18
                strokeWidth: 1.8
                color: Theme.text
            }
            Text {
                anchors.left: ic.right; anchors.leftMargin: 8
                anchors.right: parent.right
                anchors.rightMargin: 8
                anchors.verticalCenter: ic.verticalCenter
                text: qt.title
                elide: Text.ElideRight
                color: Theme.text
                font.pixelSize: 14
                font.weight: Font.DemiBold
            }
            Text {
                x: 12
                y: ic.y + ic.height + 7
                width: parent.width - 12 - moreBtn.width - 4
                text: qt.state_
                elide: Text.ElideRight
                color: qt.on ? Theme.accentText : Theme.textFaint
                font.pixelSize: 13
            }
            C.AbstractButton {
                id: moreBtn
                anchors.right: parent.right
                anchors.rightMargin: 4
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 4
                width: 26; height: 26
                hoverEnabled: true
                focusPolicy: Qt.NoFocus
                Accessible.name: "Open " + qt.title + " settings"
                onClicked: qt.more()
                background: Rectangle { radius: 13; color: moreBtn.hovered ? Theme.hover : "transparent" }
                contentItem: Item {
                    Icon { anchors.centerIn: parent; name: "chevronRight"; size: 15; strokeWidth: 2; color: Theme.textDim }
                }
            }
        }
    }
}
