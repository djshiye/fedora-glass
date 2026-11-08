import QtQuick
import QtQuick.Controls.Basic as C

// A compact slider: thin track, white knob that swells while held.
C.Slider {
    id: control
    property string valueText: ""
    property bool dimmed: false     // shows an "automatic" value, not a chosen one

    implicitHeight: 28
    implicitWidth: 200
    padding: 0
    leftPadding: 0
    rightPadding: 0
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : 0.45
    Behavior on opacity { NumberAnimation { duration: Theme.fast } }
    HoverHandler { cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }

    background: Item {
        x: control.leftPadding
        width: control.availableWidth
        height: control.height
        Rectangle {
            id: groove
            x: 0
            width: parent.width
            height: 6
            radius: 3
            anchors.verticalCenter: parent.verticalCenter
            color: Theme.wellHi
            Rectangle {
                width: control.handle.x + control.handle.width / 2
                height: parent.height
                radius: 3
                color: control.dimmed ? Theme.textFaint : Theme.accent
                Behavior on color { ColorAnimation { duration: Theme.fast } }
            }
        }
    }

    handle: Item {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: (control.height - height) / 2
        width: 22
        height: 22
        Rectangle {
            anchors.centerIn: parent
            readonly property real d: control.pressed ? 28 : (control.hovered ? 23 : 22)
            width: d
            height: d
            radius: d / 2
            color: Theme.knob
            border.width: 1
            border.color: Qt.rgba(0, 0, 0, Theme.dark ? 0.25 : 0.12)
            Behavior on width { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }
            Behavior on height { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }
        }
        Rectangle {
            anchors.fill: parent
            anchors.margins: -4
            radius: width / 2
            color: "transparent"
            border.width: 2
            border.color: Theme.alpha(Theme.accent, 0.85)
            opacity: control.visualFocus ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.fast } }
        }
    }
}
