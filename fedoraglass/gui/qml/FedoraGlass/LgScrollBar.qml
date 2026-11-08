import QtQuick
import QtQuick.Controls.Basic as C

// A slim overlay scrollbar that widens on hover.
C.ScrollBar {
    id: bar
    padding: 2
    minimumSize: 0.08
    policy: C.ScrollBar.AsNeeded
    contentItem: Rectangle {
        implicitWidth: bar.hovered || bar.pressed ? 8 : 5
        radius: width / 2
        color: bar.pressed ? Theme.textDim : Theme.textFaint
        opacity: bar.active || bar.hovered ? 0.9 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
        Behavior on implicitWidth { NumberAnimation { duration: Theme.fast } }
    }
    background: Item {}
}
