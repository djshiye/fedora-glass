import QtQuick
import QtQuick.Controls.Basic as C

// The labelled fold: expert controls tucked away, with the header saying what is
// inside ("Bend, rainbow edge, colour bleed and 2 more"). Search opens it when it
// reveals a control inside. `card: true` draws it as its own glass card.
Item {
    id: root
    property string title: ""
    property string summary: ""
    property bool expanded: false
    property bool card: true
    property bool divider: false        // a line above, when it sits inside another card
    default property alias content: inner.data
    width: parent ? parent.width : 300
    implicitHeight: (card ? 0 : 0) + header.height + body.height + (divider ? 6 : 0)

    Rectangle {
        visible: root.card
        anchors.fill: parent
        radius: Theme.rM
        color: Theme.surface
    }
    Rectangle {
        visible: root.divider
        width: parent.width; height: 1
        color: Theme.divider
    }

    C.AbstractButton {
        id: header
        objectName: root.objectName.length ? root.objectName + "Header" : ""
        y: root.divider ? 6 : 0
        x: root.card ? 6 : -6
        width: parent.width - (root.card ? 12 : -12)
        // The summary's full width against the room beside the title.
        readonly property bool stacked: root.summary.length > 0
            && summaryText.implicitWidth > width - (14 + 16 + 10 + titleText.implicitWidth + 16 + 14)
        height: (root.card ? 54 : 46) + (stacked ? 14 : 0)
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        onClicked: root.expanded = !root.expanded
        Accessible.name: root.summary ? qsTr("%1: %2").arg(root.title).arg(root.summary) : root.title
        Accessible.role: Accessible.Button
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        background: Rectangle {
            radius: Theme.rS
            anchors.fill: parent
            anchors.topMargin: root.card ? 5 : 2
            anchors.bottomMargin: root.card ? 5 : 2
            color: header.down ? Theme.pressed : header.hovered ? Theme.hover : "transparent"
            Behavior on color { ColorAnimation { duration: Theme.fast } }
            FocusRing { target: header; radius: Theme.rS + 2; gap: 0 }
        }
        contentItem: Item {
            Icon {
                id: chev
                x: 14
                anchors.verticalCenter: parent.verticalCenter
                name: "chevronRight"
                size: 16
                strokeWidth: 2
                color: Theme.textDim
                rotation: root.expanded ? 90 : 0
                Behavior on rotation { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
            }
            Text {
                id: titleText
                anchors.left: chev.right
                anchors.leftMargin: 10
                y: header.stacked ? (parent.height - height - summaryText.height - 1) / 2
                                  : (parent.height - height) / 2
                textFormat: Text.PlainText
                text: root.title
                color: Theme.text
                font.pixelSize: Theme.fsBody
                font.weight: Font.DemiBold
            }
            // What is inside. Beside the title while it fits there in full; a longer one
            // (a narrow window, another language) goes under the title, never cut mid-word.
            Text {
                id: summaryText
                x: header.stacked ? titleText.x : titleText.x + titleText.width + 16
                y: header.stacked ? titleText.y + titleText.height + 1 : (parent.height - height) / 2
                width: parent.width - x - 14
                horizontalAlignment: header.stacked ? Text.AlignLeft : Text.AlignRight
                textFormat: Text.PlainText
                text: root.summary
                elide: Text.ElideRight
                color: Theme.textFaint
                font.pixelSize: Theme.fsSmall + 1
            }
        }
    }
    Item {
        id: body
        y: header.y + header.height
        width: parent.width
        height: root.expanded ? inner.childrenRect.height + (root.card ? 18 : 8) : 0
        opacity: root.expanded ? 1 : 0
        clip: true
        Behavior on height { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
        visible: height > 0.5
        Item {
            id: inner
            x: root.card ? 20 : 0
            y: 2
            width: parent.width - (root.card ? 40 : 0)
            height: childrenRect.height
        }
    }
}
