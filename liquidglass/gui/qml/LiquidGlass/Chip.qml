import QtQuick
import QtQuick.Controls.Basic as C

// A glass chip (presets). `selected` draws it as the active choice.
C.AbstractButton {
    id: control
    property bool selected: false
    property string tip: ""
    implicitHeight: 34
    implicitWidth: label.implicitWidth + 32
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus

    LgToolTip { shown: control.tip.length > 0 && control.hovered; text: control.tip }
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
        RimLight { radius: height / 2; edge: "transparent" }
        FocusRing { target: control; radius: height / 2 }
    }
}
