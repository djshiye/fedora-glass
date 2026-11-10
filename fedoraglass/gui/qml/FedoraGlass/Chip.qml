import QtQuick
import QtQuick.Controls.Basic as C
import "roving.js" as Roving

// A glass chip (presets). `selected` draws it as the active choice.
// In a row of chips set `rovingGroup` to the row: the row is then one Tab stop (the
// chip with `rovingStop`, normally the selected one) and the arrow keys move along it.
C.AbstractButton {
    id: control
    property bool selected: false
    property string tip: ""
    property Item rovingGroup: null
    property bool rovingStop: selected
    property bool rovingSelects: false      // the arrow keys choose as they move (tabs), not just focus
    readonly property bool _groupFocused: rovingGroup !== null && Window.activeFocusItem !== null
                                          && Window.activeFocusItem.rovingGroup === rovingGroup
    implicitHeight: 34
    implicitWidth: label.implicitWidth + 32
    hoverEnabled: true
    focusPolicy: !rovingGroup || activeFocus || (rovingStop && !_groupFocused) ? Qt.StrongFocus : Qt.ClickFocus
    Keys.onPressed: (e) => { if (Roving.handleKey(control, e)) e.accepted = true }

    LgToolTip { shown: control.tip.length > 0 && (control.hovered || control.visualFocus); text: control.tip }
    HoverHandler { cursorShape: Qt.PointingHandCursor }

    contentItem: Text {
        id: label
        text: control.text
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        color: control.selected ? Theme.accentText : Theme.text
        font.pixelSize: 13
        font.weight: control.selected ? Font.DemiBold : Font.Medium
        Behavior on color { ColorAnimation { duration: Theme.fast } }
    }
    background: Rectangle {
        radius: height / 2
        color: control.selected ? Theme.alpha(Theme.accent, Theme.dark ? 0.22 : 0.14)
               : control.down ? Theme.wellHi : control.hovered ? Theme.surfaceHi : Theme.well
        border.width: 1
        border.color: control.selected ? Theme.alpha(Theme.accent, 0.65) : Theme.border
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        Behavior on border.color { ColorAnimation { duration: Theme.fast } }
        FocusRing { target: control; radius: height / 2 }
    }
}
