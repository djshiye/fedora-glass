import QtQuick
import QtQuick.Controls.Basic as C

// An on/off chip with a tick: a row of these replaces a stack of switches
// ("Where the glass shows", the lock screen's widgets). Space and Enter toggle it.
C.AbstractButton {
    id: control
    property bool on: false
    property string tip: ""
    signal switched(bool on)
    implicitHeight: 34
    implicitWidth: row.implicitWidth + 28
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    checkable: false
    onClicked: switched(!on)
    Accessible.role: Accessible.CheckBox
    Accessible.checkable: true
    Accessible.checked: on
    Accessible.name: text

    LgToolTip { shown: control.tip.length > 0 && (control.hovered || control.visualFocus) && !control.pressed; text: control.tip }
    HoverHandler { cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }

    contentItem: Item {
        Row {
            id: row
            anchors.centerIn: parent
            spacing: 7
            Item {
                width: 15; height: 15
                anchors.verticalCenter: parent.verticalCenter
                Rectangle {     // off: an empty ring where the tick goes, so the gap reads as a box to tick
                    anchors.centerIn: parent
                    width: 13; height: 13; radius: 6.5
                    color: "transparent"
                    border.width: 1.5
                    border.color: control.hovered ? Theme.textDim : Theme.textFaint
                    opacity: control.on ? 0 : 0.8
                    Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                }
                Icon {
                    anchors.centerIn: parent
                    name: "check"
                    size: 15
                    strokeWidth: 2.2
                    color: Theme.accentText
                    opacity: control.on ? 1 : 0
                    scale: control.on ? 1 : 0.6
                    Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                    Behavior on scale { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutBack } }
                }
            }
            Text {
                text: control.text
                anchors.verticalCenter: parent.verticalCenter
                color: !control.enabled ? Theme.textFaint : control.on ? Theme.accentText : Theme.textDim
                font.pixelSize: 14
                font.weight: control.on ? Font.DemiBold : Font.Medium
                Behavior on color { ColorAnimation { duration: Theme.fast } }
            }
        }
    }
    background: Rectangle {
        radius: height / 2
        opacity: control.enabled ? 1 : 0.55
        color: control.on ? Theme.alpha(Theme.accent, Theme.dark ? (control.hovered ? 0.28 : 0.2) : (control.hovered ? 0.2 : 0.14))
               : control.down ? Theme.wellHi : control.hovered ? Theme.surfaceHi : Theme.well
        border.width: 1
        border.color: control.on ? Theme.alpha(Theme.accent, 0.45) : Theme.border
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        FocusRing { target: control; radius: height / 2 }
    }
}
