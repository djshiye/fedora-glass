import QtQuick
import QtQuick.Controls.Basic as C

// A short message that floats above the footer and fades away.
// show(): a one-line note that goes by itself after a few seconds.
// showError(): something went wrong. The reason can run to a few lines and stays until it is
// closed (the close button or Esc), so it can be read to the end.
// showAction(): a note with one button ("Put back"); it waits a little longer than a note.
Rectangle {
    id: toast
    property string text: ""
    property string iconName: "info"
    property color iconColor: Theme.accent
    property bool sticky: false           // an error: stays until dismissed, wraps
    property string actionText: ""
    signal actionTriggered()
    property bool shown: false
    // Something else wants Esc first (the search field, an open sheet): set by the window.
    property bool escapeTaken: false

    function show(msg, icon, color) { _open(msg, icon, color, false, "", 4200) }
    function showError(msg) { _open(msg, "alert", Theme.bad, true, "", 0) }
    function showAction(msg, icon, color, label) { _open(msg, icon, color, false, label, 9000) }
    function hide() { shown = false; timer.stop() }
    function _open(msg, icon, color, isSticky, label, ms) {
        text = msg; iconName = icon || "info"; iconColor = color || Theme.accent
        sticky = isSticky; actionText = label
        shown = true
        if (ms > 0) { timer.interval = ms; timer.restart() } else timer.stop()
    }

    width: Math.min(row.implicitWidth + 32, 640)
    height: Math.max(44, row.implicitHeight + (sticky ? 24 : 0))
    radius: Theme.rM
    color: Theme.sheet
    opacity: shown ? 1 : 0
    visible: opacity > 0
    scale: shown ? 1 : 0.96
    Behavior on opacity { NumberAnimation { duration: Theme.normal } }
    Behavior on scale { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
    Accessible.role: sticky ? Accessible.AlertMessage : Accessible.StaticText
    Accessible.name: toast.text
    Accessible.description: toast.sticky ? qsTr("Press Esc to close") : ""

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 10
        Icon { name: toast.iconName; size: 18; color: toast.iconColor; anchors.verticalCenter: parent.verticalCenter }
        Text {
            id: label
            text: toast.text
            color: Theme.text
            font.pixelSize: Theme.fsBody
            anchors.verticalCenter: parent.verticalCenter
            width: Math.min(implicitWidth, 560 - (actionBtn.visible ? actionBtn.width + 10 : 0) - (closeBtn.visible ? closeBtn.width + 10 : 0))
            wrapMode: toast.sticky ? Text.Wrap : Text.NoWrap
            maximumLineCount: toast.sticky ? 4 : 1
            elide: Text.ElideRight
        }
        LgButton {
            id: actionBtn
            objectName: "toastAction"
            visible: toast.actionText.length > 0
            anchors.verticalCenter: parent.verticalCenter
            kind: "flat"
            implicitHeight: 30
            leftPadding: 10; rightPadding: 10
            font.pixelSize: Theme.fsBody
            text: toast.actionText
            onClicked: { toast.hide(); toast.actionTriggered() }
        }
        C.AbstractButton {
            id: closeBtn
            objectName: "toastClose"
            visible: toast.sticky
            anchors.verticalCenter: parent.verticalCenter
            width: 28; height: 28
            hoverEnabled: true
            focusPolicy: Qt.StrongFocus
            Accessible.name: qsTr("Close")
            onClicked: toast.hide()
            HoverHandler { cursorShape: Qt.PointingHandCursor }
            background: Rectangle {
                radius: width / 2
                color: closeBtn.down ? Theme.pressed : closeBtn.hovered ? Theme.hover : "transparent"
                FocusRing { target: closeBtn; radius: width / 2 }
            }
            contentItem: Item { Icon { anchors.centerIn: parent; name: "close"; size: 14; strokeWidth: 2; color: Theme.textDim } }
        }
    }
    Shortcut { sequence: "Escape"; enabled: toast.shown && toast.sticky && !toast.escapeTaken; onActivated: toast.hide() }
    Timer { id: timer; interval: 4200; onTriggered: toast.shown = false }
}
