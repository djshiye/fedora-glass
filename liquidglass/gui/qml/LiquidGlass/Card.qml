import QtQuick

// A glass card: translucent fill, faint edge, specular top rim.
Rectangle {
    id: root
    property real padding: 20
    default property alias content: body.data
    radius: Theme.rM
    color: Theme.surface
    implicitHeight: body.childrenRect.height + 2 * padding

    Item {
        id: body
        x: root.padding
        y: root.padding
        width: root.width - 2 * root.padding
        height: root.height - 2 * root.padding
    }
}
