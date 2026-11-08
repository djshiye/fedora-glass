import QtQuick
import QtQuick.Controls.Basic as C

// iOS/libadwaita-style switch.
C.Switch {
    id: control
    implicitWidth: 52
    implicitHeight: 30
    padding: 0
    spacing: 0
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : 0.4
    Behavior on opacity { NumberAnimation { duration: Theme.fast } }
    HoverHandler { cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }

    indicator: Rectangle {
        width: 50
        height: 30
        x: control.width - width
        anchors.verticalCenter: parent.verticalCenter
        radius: 15
        color: control.checked ? Theme.accent : Theme.wellHi
        border.width: control.checked ? 0 : 1
        border.color: Theme.border
        Behavior on color { ColorAnimation { duration: Theme.normal } }

        Rectangle {
            id: knob
            readonly property real grow: control.pressed ? 6 : 0
            width: 24 + grow
            height: 24
            radius: 12
            y: 3
            x: control.checked ? parent.width - width - 3 : 3
            color: Theme.knob
            Behavior on x { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutBack; easing.overshoot: 1.2 } }
            Behavior on width { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }
            border.width: Theme.dark ? 0 : 1
            border.color: Qt.rgba(0, 0, 0, 0.06)
        }
        FocusRing { target: control; radius: 18 }
    }
    contentItem: Item {}
}
