import QtQuick
import QtQuick.Controls.Basic as C

// A modal sheet over a dimmed window: title, subtitle, body, buttons.
C.Popup {
    id: sheet
    property string title: ""
    property string subtitle: ""
    property string iconName: ""
    property color iconColor: Theme.accent
    default property alias body: bodyHolder.data
    property alias buttons: buttonRow.data
    property real maxBodyHeight: (parent ? parent.height : 600) * 0.62 - 160

    parent: C.Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(600, (parent ? parent.width : 800) - 64)
    modal: true
    focus: true
    padding: 0
    closePolicy: C.Popup.CloseOnEscape

    C.Overlay.modal: Rectangle {
        color: Theme.dark ? Qt.rgba(0, 0, 0, 0.45) : Qt.rgba(0.1, 0.12, 0.18, 0.22)
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
    }
    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.95; to: 1; duration: Theme.slow; easing.type: Easing.OutBack; easing.overshoot: 0.8 }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.fast }
        NumberAnimation { property: "scale"; from: 1; to: 0.97; duration: Theme.fast }
    }

    background: Item {
        Rectangle {
            anchors.fill: parent
            anchors.margins: -1
            anchors.topMargin: 6
            radius: Theme.rL + 2
            color: Qt.rgba(0, 0, 0, Theme.dark ? 0.35 : 0.10)
            opacity: 0.6
        }
        Rectangle {
            anchors.fill: parent
            radius: Theme.rL
            color: Theme.sheet
        }
    }

    contentItem: Column {
        spacing: 0
        Item {
            width: parent.width
            height: head.height + 48
            Row {
                id: head
                x: 24; y: 24
                width: parent.width - 48
                spacing: 14
                Rectangle {
                    visible: sheet.iconName.length > 0
                    width: 40; height: 40; radius: 20
                    color: Theme.alpha(sheet.iconColor, 0.16)
                    Icon { anchors.centerIn: parent; name: sheet.iconName; size: 20; color: sheet.iconColor }
                }
                Column {
                    width: parent.width - (sheet.iconName.length > 0 ? 54 : 0)
                    spacing: 4
                    anchors.verticalCenter: parent.verticalCenter
                    Text {
                        width: parent.width
                        text: sheet.title
                        color: Theme.text
                        font.pixelSize: 18
                        font.weight: Font.Bold
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        visible: text.length > 0
                        width: parent.width
                        text: sheet.subtitle
                        color: Theme.textDim
                        font.pixelSize: Theme.fsBody
                        wrapMode: Text.WordWrap
                        lineHeight: 1.15
                    }
                }
            }
        }
        Item {
            id: bodyHolder
            x: 24
            width: parent.width - 48
            height: childrenRect.height
        }
        Item {
            width: parent.width
            height: 80
            Row {
                id: buttonRow
                anchors.right: parent.right
                anchors.rightMargin: 24
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8
            }
        }
    }
}
