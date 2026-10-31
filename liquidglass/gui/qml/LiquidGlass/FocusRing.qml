import QtQuick

// Keyboard focus indicator, shown only for keyboard (visual) focus.
Rectangle {
    property Item target
    property real gap: 3
    anchors.fill: parent
    anchors.margins: -gap
    radius: Theme.rS
    color: "transparent"
    border.width: 2
    border.color: Theme.alpha(Theme.accent, 0.85)
    visible: opacity > 0
    opacity: target && target.visualFocus ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: Theme.fast } }
}
