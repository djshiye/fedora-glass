import QtQuick

// A label, a caption and a switch; the whole row toggles.
Item {
    id: root
    property string label: ""
    property string caption: ""
    property bool checked: false
    signal toggled(bool on)
    width: parent ? parent.width : 300
    implicitHeight: Math.max(44, labels.implicitHeight + 8)

    Column {
        id: labels
        width: parent.width - sw.width - 16
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2
        Text { width: parent.width; text: root.label; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium; wrapMode: Text.WordWrap }
        Text {
            visible: root.caption.length > 0
            width: parent.width
            text: root.caption
            color: Theme.textFaint
            font.pixelSize: Theme.fsSmall
            wrapMode: Text.WordWrap
        }
    }
    TapHandler { enabled: root.enabled; onTapped: root.toggled(!root.checked) }
    LgSwitch {
        id: sw
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        checked: root.checked
        enabled: root.enabled
        onToggled: root.toggled(checked)
        Accessible.name: root.label
    }
}
