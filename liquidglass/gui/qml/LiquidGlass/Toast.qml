import QtQuick

// A short message that floats above the footer and fades away.
Rectangle {
    id: toast
    property string text: ""
    property string iconName: "info"
    property color iconColor: Theme.accent
    function show(msg, icon, color) {
        text = msg; iconName = icon || "info"; iconColor = color || Theme.accent
        shown = true; timer.restart()
    }
    property bool shown: false
    width: Math.min(row.implicitWidth + 32, 640)
    height: 44
    radius: 22
    color: Theme.sheet
    opacity: shown ? 1 : 0
    visible: opacity > 0
    scale: shown ? 1 : 0.96
    Behavior on opacity { NumberAnimation { duration: Theme.normal } }
    Behavior on scale { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
    RimLight { radius: 22; edge: Theme.borderHi }
    Row {
        id: row
        anchors.centerIn: parent
        spacing: 10
        Icon { name: toast.iconName; size: 18; color: toast.iconColor; anchors.verticalCenter: parent.verticalCenter }
        Text { text: toast.text; color: Theme.text; font.pixelSize: Theme.fsBody; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight; width: Math.min(implicitWidth, 560) }
    }
    Timer { id: timer; interval: 4200; onTriggered: toast.shown = false }
}
