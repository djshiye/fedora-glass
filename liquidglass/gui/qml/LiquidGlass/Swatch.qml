import QtQuick
import QtQuick.Controls.Basic as C

// A round colour choice with a check when selected.
C.AbstractButton {
    id: control
    property color swatch: "#3584e4"
    property bool selected: false
    property bool rainbow: false     // the "custom colour" swatch
    property bool split: false       // "system": half accent, half neutral
    property string tip: ""
    property real size: 30
    implicitWidth: size
    implicitHeight: size
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.name: tip
    HoverHandler { cursorShape: Qt.PointingHandCursor }
    LgToolTip { shown: control.hovered; text: control.tip }

    background: Item {
        Rectangle {     // selection ring
            anchors.fill: parent
            radius: width / 2
            color: "transparent"
            border.width: 2
            border.color: control.selected ? control.swatch : (control.visualFocus ? Theme.accent : "transparent")
            Behavior on border.color { ColorAnimation { duration: Theme.fast } }
        }
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
