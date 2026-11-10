import QtQuick
import QtQuick.Controls.Basic as C
import "roving.js" as Roving

// A round colour choice with a check when selected.
// In a row of swatches set `rovingGroup` to the row: the row is then one Tab stop (the
// selected swatch) and the arrow keys move along it; Space or Enter picks.
C.AbstractButton {
    id: control
    property color swatch: "#3584e4"
    property bool selected: false
    property bool rainbow: false     // the "custom colour" swatch
    property bool split: false       // "system": half accent, half neutral
    property string tip: ""
    property real size: 30
    property Item rovingGroup: null
    property bool rovingStop: selected
    property bool rovingSelects: false
    readonly property bool _groupFocused: rovingGroup !== null && Window.activeFocusItem !== null
                                          && Window.activeFocusItem.rovingGroup === rovingGroup
    implicitWidth: size
    implicitHeight: size
    hoverEnabled: true
    focusPolicy: !rovingGroup || activeFocus || (rovingStop && !_groupFocused) ? Qt.StrongFocus : Qt.ClickFocus
    Accessible.name: tip
    Keys.onPressed: (e) => { if (Roving.handleKey(control, e)) e.accepted = true }
    HoverHandler { cursorShape: Qt.PointingHandCursor }
    LgToolTip { shown: control.hovered || control.visualFocus; text: control.tip }

    background: Item {
        Rectangle {     // selection ring
            anchors.fill: parent
            radius: width / 2
            color: "transparent"
            border.width: 2
            border.color: control.selected ? control.swatch : "transparent"
            Behavior on border.color { ColorAnimation { duration: Theme.fast } }
        }
        FocusRing { target: control; gap: 2; radius: width / 2 }
        Rectangle {
            id: dot
            anchors.centerIn: parent
            readonly property real d: control.selected ? parent.width - 8 : (control.hovered ? parent.width - 2 : parent.width - 4)
            width: d
            height: d
            radius: d / 2
            color: control.swatch
            Behavior on width { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }
            Behavior on height { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }
            border.width: 1
            border.color: Qt.rgba(0, 0, 0, 0.12)

            ConicalGradientDot { visible: control.rainbow; anchors.fill: parent }
            Rectangle {
                visible: control.split
                width: parent.width / 2
                height: parent.height
                x: parent.width / 2
                topRightRadius: width
                bottomRightRadius: width
                color: Theme.dark ? "#5e5c64" : "#c0bfbc"
            }
            Icon {
                anchors.centerIn: parent
                visible: control.selected && !control.rainbow
                name: "check"
                size: 14
                strokeWidth: 2.4
                color: control.swatch.hslLightness > 0.72 ? "#1a1b20" : "white"
            }
            Icon {
                anchors.centerIn: parent
                visible: control.rainbow
                name: "plus"
                size: 14
                strokeWidth: 2.4
                color: "white"
            }
        }
    }
}
