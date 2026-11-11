import QtQuick
import QtQuick.Controls.Basic as C
import QtQuick.Effects
import QtQuick.Window
import FedoraGlass.Core

// A look as a little picture of its glass on the wallpaper: the five built-in presets and
// the user's own saved looks. A saved look shows its tint and accent too, and has a menu.
C.AbstractButton {
    id: tile
    property string name: ""
    property real frost: 0.45
    property bool selected: false
    property string tip: ""
    property Item rovingGroup: null
    property bool rovingStop: selected
    property string tintHex: ""          // a saved look: the glass leans towards this colour
    property string accentHex: ""        // and this is its accent
    property bool hasMenu: false
    property int thumbHeight: 60
    signal menuRequested(Item from)
    readonly property bool _groupFocused: Window.activeFocusItem !== null && Window.activeFocusItem.rovingGroup === rovingGroup
    focusPolicy: activeFocus || (rovingStop && !_groupFocused) ? Qt.StrongFocus : Qt.ClickFocus
    Keys.onLeftPressed: { const p = tile.nextItemInFocusChain(false); if (p && p.rovingGroup === tile.rovingGroup) p.forceActiveFocus(Qt.TabFocusReason) }
    Keys.onRightPressed: { const n = tile.nextItemInFocusChain(true); if (n && n.rovingGroup === tile.rovingGroup) n.forceActiveFocus(Qt.TabFocusReason) }
    // The menu key or Shift+F10 opens a saved look's menu, as a right click does.
    Keys.onMenuPressed: if (hasMenu) tile.menuRequested(menuBtn)
    Keys.onPressed: (e) => { if (hasMenu && e.key === Qt.Key_F10 && (e.modifiers & Qt.ShiftModifier)) { tile.menuRequested(menuBtn); e.accepted = true } }
    implicitHeight: thumbHeight + 44
    hoverEnabled: true
    readonly property string shownName: hasMenu ? name : Theme.presetLabel(name)   // presets are keyed by their English name
    text: shownName
    Accessible.name: hasMenu ? qsTr("%1, your look").arg(name) : qsTr("%1 preset").arg(shownName)
    Accessible.role: Accessible.RadioButton
    Accessible.checked: selected
    HoverHandler { cursorShape: Qt.PointingHandCursor }
    TapHandler { acceptedButtons: Qt.RightButton; enabled: tile.hasMenu; onTapped: tile.menuRequested(menuBtn) }
    LgToolTip { shown: tile.tip.length > 0 && (tile.hovered || tile.visualFocus) && !tile.pressed && !menuBtn.hovered; text: tile.tip }

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
            height: tile.thumbHeight
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
            // The pane of glass, as frosted as the look, leaning towards its tint.
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
                    readonly property color base: tile.tintHex.length ? tile.tintHex : "white"
                    anchors.fill: parent
                    radius: 7
                    color: Qt.rgba(base.r, base.g, base.b,
                                   (Theme.dark ? 0.04 + 0.22 * tile.frost : 0.12 + 0.5 * tile.frost) + (tile.tintHex.length ? 0.14 : 0))
                    border.width: 1
                    border.color: Qt.rgba(1, 1, 1, 0.55 - 0.25 * tile.frost)
                }
                Rectangle {     // the accent, as a small button on the glass
                    visible: tile.accentHex.length > 0
                    anchors.right: parent.right; anchors.bottom: parent.bottom
                    anchors.margins: 5
                    width: 14; height: 6; radius: 3
                    color: tile.accentHex.length ? tile.accentHex : "transparent"
                }
            }
        }
        Text {
            x: tile.hasMenu ? 8 : 0
            width: tile.width - (tile.hasMenu ? 16 : 0)
            horizontalAlignment: Text.AlignHCenter
            text: tile.shownName
            elide: Text.ElideRight
            // Longer names (other languages) shrink a little before they are cut.
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: 10
            color: tile.selected ? Theme.text : Theme.textDim
            font.pixelSize: 13
            font.weight: tile.selected ? Font.DemiBold : Font.Normal
        }
    }
    Rectangle { id: thumbMask; visible: false; layer.enabled: true; width: thumb.width; height: thumb.height; radius: 9 }

    // A saved look's menu: rename, save as a file, delete.
    C.AbstractButton {
        id: menuBtn
        objectName: "lookMenuButton"
        visible: tile.hasMenu
        x: tile.width - width - 12
        y: 12
        width: 24; height: 24
        hoverEnabled: true
        focusPolicy: Qt.NoFocus
        opacity: tile.hovered || tile.visualFocus || hovered ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
        Accessible.name: qsTr("More for %1").arg(tile.name)
        onClicked: tile.menuRequested(menuBtn)
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        background: Rectangle {
            radius: 12
            color: menuBtn.down ? Qt.rgba(0, 0, 0, 0.55) : Qt.rgba(0, 0, 0, menuBtn.hovered ? 0.5 : 0.38)
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, 0.18)
        }
        contentItem: Item {
            Row {
                anchors.centerIn: parent
                spacing: 3
                Repeater { model: 3; delegate: Rectangle { width: 3; height: 3; radius: 1.5; color: "white" } }
            }
        }
    }
}
