import QtQuick
import FedoraGlass.Core

// A card's title, with an optional one- or two-line caption right under it.
// `group` is the small, quieter label above a group of rows (the Apps page uses
// it for "Desktop", "Apps" and so on).
// `resetKeys` (Settings names) gives the card a "Reset" pill next to its title, shown only
// while one of them differs from its default: the way back from any change in the card.
Column {
    id: root
    property alias text: title.text
    property string caption: ""
    property string captionName: ""     // objectName for the caption, for tests
    property bool group: false
    property var resetKeys: []
    property string resetTip: qsTr("Put this card back to its defaults")
    readonly property bool changed: resetKeys.length > 0
                                    && Backend.changedFromDefault.some((k) => resetKeys.indexOf(k) >= 0)
    width: parent ? parent.width : implicitWidth
    spacing: 4

    Item {
        width: parent.width - root.leftPadding - root.rightPadding
        height: Math.max(title.implicitHeight, reset.visible ? reset.implicitHeight : 0)
        Text {
            id: title
            width: parent.width - (reset.visible ? reset.width + 12 : 0)
            anchors.verticalCenter: parent.verticalCenter
            elide: Text.ElideRight
            color: root.group ? Theme.textDim : Theme.text
            font.pixelSize: root.group ? 13 : Theme.fsTitle
            font.weight: Font.DemiBold
            font.letterSpacing: root.group ? 0.2 : 0
        }
        ResetButton {
            id: reset
            objectName: "cardReset"
            visible: root.changed
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: qsTr("Reset")
            tip: qsTr("%1 (Apply to use them)").arg(root.resetTip)
            onClicked: Backend.resetSettings(root.resetKeys)
        }
    }
    Text {
        objectName: root.captionName
        visible: root.caption.length > 0
        width: parent.width - root.leftPadding - root.rightPadding
        text: root.caption
        wrapMode: Text.WordWrap
        color: Theme.textDim
        font.pixelSize: Theme.fsSmall + 1
        lineHeight: 1.1
    }
}
