import QtQuick

// A card's title, with an optional one- or two-line caption right under it.
// `group` is the small, quieter label above a group of rows (the Apps page uses
// it for "Desktop", "Apps" and so on).
Column {
    id: root
    property alias text: title.text
    property string caption: ""
    property string captionName: ""     // objectName for the caption, for tests
    property bool group: false
    width: parent ? parent.width : implicitWidth
    spacing: 4

    Text {
        id: title
        width: parent.width - root.leftPadding - root.rightPadding
        elide: Text.ElideRight
        color: root.group ? Theme.textDim : Theme.text
        font.pixelSize: root.group ? 13 : Theme.fsTitle
        font.weight: Font.DemiBold
        font.letterSpacing: root.group ? 0.2 : 0
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
