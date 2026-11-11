import QtQuick
import QtQuick.Controls.Basic as C

// A small "back to the default" pill: an undo arrow and a word. It shows only while the
// thing next to it differs from its default, so a page at its defaults stays clean.
C.AbstractButton {
    id: control
    property string tip: ""
    text: qsTr("Default")
    implicitHeight: 24
    implicitWidth: row.implicitWidth + 18
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.name: control.tip.length ? control.tip : control.text

    LgToolTip { shown: control.tip.length > 0 && (control.hovered || control.visualFocus) && !control.pressed; text: control.tip }
    HoverHandler { cursorShape: Qt.PointingHandCursor }

    contentItem: Item {
        Row {
            id: row
            anchors.centerIn: parent
            spacing: 4
            Icon {
                name: "undo"
                size: 14
                color: control.hovered ? Theme.text : Theme.textDim
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: control.text
                color: control.hovered ? Theme.text : Theme.textDim
                font.pixelSize: Theme.fsSmall
                font.weight: Font.Medium
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }
    background: Rectangle {
        radius: height / 2
        color: control.down ? Theme.wellHi : control.hovered ? Theme.surfaceHi : Theme.well
        border.width: 1
        border.color: Theme.border
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        FocusRing { target: control; radius: height / 2 }
    }
}
