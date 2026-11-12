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

    readonly property var presetFrost: Backend.presetFrost
    readonly property var presetTips: ({
        "Liquid": qsTr("Clearest glass, brightest rim"),
        "Clear": qsTr("Clear glass with a little haze"),
        "Balanced": qsTr("The default: readable and still glassy"),
        "Frosted": qsTr("Milky, heavily blurred glass"),
        "Solid": qsTr("Almost opaque, for maximum readability")
    })
    // Named after the preset the slider sits nearest to (settings.PRESETS, through Backend).
    function frostName(f) { return Theme.presetLabel(Backend.frostName(f)) }

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
            Item {
                width: parent.width
                height: 30
                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 10
                    Text { id: lookTitle; text: qsTr("Look"); color: Theme.text; font.pixelSize: Theme.fsTitle; font.weight: Font.DemiBold }
                    Text {
                        anchors.baseline: lookTitle.baseline
                        // Gives way to the buttons in a narrow window.
                        width: Math.max(0, Math.min(implicitWidth, lookButtons.x - lookTitle.width - 10 - 16))
                        visible: width >= 80
                        elide: Text.ElideRight
                        text: qsTr("Pick one to start. Everything else follows it.")
                        color: Theme.textFaint
                        font.pixelSize: Theme.fsSmall + 1
                    }
                }
                // Measure the buttons with their words, whatever they show now.
                LgButton { id: saveLookFull; visible: false; kind: "flat"; implicitHeight: 30; leftPadding: 8; rightPadding: 10; iconName: "plus"; text: qsTr("Save look…") }
                LgButton { id: importLookFull; visible: false; kind: "flat"; implicitHeight: 30; leftPadding: 8; rightPadding: 10; iconName: "document"; text: qsTr("Add from file…") }
                Row {
                    id: lookButtons
                    // Too little room for the words (a narrow window, a longer language):
                    // the buttons show only their icons, and say what they do in the tooltip.
                    readonly property bool iconsOnly: saveLookFull.implicitWidth + importLookFull.implicitWidth + 4
                                                      > parent.width - lookTitle.width - 24
                    anchors.right: parent.right
                    anchors.rightMargin: -8
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 4
                    LgButton {
                        objectName: "saveLook"
                        kind: "flat"
                        implicitHeight: 30
                        leftPadding: 8; rightPadding: 10
                        text: lookButtons.iconsOnly ? "" : saveLookFull.text
                        Accessible.name: saveLookFull.text
                        iconName: "plus"
                        tip: qsTr("Keep this look under a name, to pick again or share")
                        tipBelow: true
                        onClicked: savedLooks.saveNew()
                    }
                    LgButton {
                        objectName: "importLook"
                        kind: "flat"
                        implicitHeight: 30
                        leftPadding: 8; rightPadding: 10
                        text: lookButtons.iconsOnly ? "" : importLookFull.text
                        Accessible.name: importLookFull.text
                        iconName: "document"
                        tip: qsTr("Add a look someone shared with you (a .json file)")
                        tipBelow: true
                        onClicked: savedLooks.importFile()
                    }
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
                    delegate: LookTile {
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
            SavedLooks {
                id: savedLooks
                width: parent.width
                tileW: presetRow.tileW
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
                        text: qsTr("Glass"); color: Theme.text; font.pixelSize: Theme.fsTitle; font.weight: Font.DemiBold
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
                    ticks: Backend.frostTicks
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
                Text { text: qsTr("Colour"); color: Theme.text; font.pixelSize: Theme.fsTitle; font.weight: Font.DemiBold }
                Segmented {
                    objectName: "homeScheme"
                    width: parent.width
                    model: [{ value: "auto", label: qsTr("Auto"), tip: qsTr("Follow GNOME's light/dark setting") },
                            { value: "dark", label: qsTr("Dark"), tip: qsTr("Always use the dark style") },
                            { value: "light", label: qsTr("Light"), tip: qsTr("Always use the light style") }]
                    value: Backend.scheme
                    onActivated: (v) => Backend.scheme = v
                    Accessible.name: qsTr("Style")
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
                        return qsTr("Your own")
                    const s = Cursors.styles.find(c => c.id === Backend.cursorTheme)
                    return s ? s.name : Backend.cursorTheme
                }
                readonly property var motionName: {
                    const s = Backend.motionStyles.find(m => m.id === Backend.motionStyle)
                    return s ? s.label : qsTr("Your own mix")
                }
                QuickTile {
                    objectName: "tileWindows"
                    width: tiles.tileW
                    iconName: "window"
                    title: qsTr("Windows")
                    state_: Backend.blurAppWindows ? qsTr("On") : qsTr("Off")
                    on: Backend.blurAppWindows
                    tip: qsTr("Frosted wallpaper behind see-through app windows. Click to switch it; the arrow opens Glass.")
                    onActivated: Backend.blurAppWindows = !Backend.blurAppWindows
                    onMore: Window.window.goTo("glass", "glassAppWindows")
                }
                QuickTile {
                    objectName: "tileMotion"
                    width: tiles.tileW
                    iconName: "wave"
                    title: qsTr("Motion")
                    state_: tiles.motionName
                    on: Backend.motionStyle !== "off"
                    tip: qsTr("How windows, menus and the panel move")
                    onActivated: Window.window.goTo("motion", "motionStyle")
                    onMore: Window.window.goTo("motion", "motionStyle")
                }
                QuickTile {
                    objectName: "tileLock"
                    width: tiles.tileW
                    iconName: "lock"
                    title: qsTr("Glass lock")
                    state_: Backend.lockGlass ? qsTr("On") : qsTr("Off")
                    on: Backend.lockGlass
                    tip: qsTr("A sheet of frosted glass on the lock screen. Click to switch it; the arrow opens Lock and login.")
                    onActivated: Backend.lockGlass = !Backend.lockGlass
                    onMore: Window.window.goTo("lock", "lockGlass")
                }
                QuickTile {
                    objectName: "tilePointer"
                    width: tiles.tileW
                    iconName: "pointer"
                    title: qsTr("Pointer")
                    state_: tiles.pointerName
                    on: Backend.cursorTheme !== "keep" && Backend.cursorTheme !== ""
                    tip: qsTr("Pick a mouse pointer that matches the glass")
                    onActivated: Window.window.goTo("pointer", "cursorCard")
                    onMore: Window.window.goTo("pointer", "cursorCard")
                }
            }
        },
        DayNightCard { width: parent.width }
    ]

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
        Accessible.name: qsTr("%1: %2").arg(title).arg(state_)
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
                fontSizeMode: Text.HorizontalFit
                minimumPixelSize: 11
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
                Accessible.name: qsTr("Open %1 settings").arg(qt.title)
                onClicked: qt.more()
                background: Rectangle { radius: 13; color: moreBtn.hovered ? Theme.hover : "transparent" }
                contentItem: Item {
                    Icon { anchors.centerIn: parent; name: "chevronRight"; size: 15; strokeWidth: 2; color: Theme.textDim }
                }
            }
        }
    }
}
