import QtQuick
import QtQuick.Controls.Basic as C

// Progressive disclosure: a header row that reveals its content smoothly.
Item {
    id: root
    property string title: ""
    property string caption: ""
    property bool expanded: false
    default property alias content: inner.data
    width: parent ? parent.width : 300
    implicitHeight: header.height + body.height
    clip: true

    C.AbstractButton {
        id: header
        width: parent.width
        height: 52
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        onClicked: root.expanded = !root.expanded
        Accessible.name: root.title
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        background: Rectangle {
            radius: Theme.rS
            color: header.hovered ? Theme.hover : "transparent"
            Behavior on color { ColorAnimation { duration: Theme.fast } }
            FocusRing { target: header; radius: Theme.rS + 2; gap: 0 }
        }
        contentItem: Item {
            Icon {
                id: chev
                x: 4
                anchors.verticalCenter: parent.verticalCenter
                name: "chevronRight"
                size: 18
                color: Theme.textDim
                rotation: root.expanded ? 90 : 0
                Behavior on rotation { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
            }
            Column {
                anchors.left: chev.right
                anchors.leftMargin: 10
                anchors.verticalCenter: parent.verticalCenter
                spacing: 1
                Text { text: root.title; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.DemiBold }
                Text { text: root.caption; visible: text.length > 0; color: Theme.textFaint; font.pixelSize: Theme.fsSmall }
            }
        }
    }
    Item {
        id: body
        y: header.height
        width: parent.width
        height: root.expanded ? inner.childrenRect.height + 8 : 0
        opacity: root.expanded ? 1 : 0
        Behavior on height { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
        visible: height > 0.5
        Item {
            id: inner
            y: 8
            width: parent.width
            height: childrenRect.height
        }
    }
}
