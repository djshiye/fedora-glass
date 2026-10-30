import QtQuick
import QtQuick.Controls.Basic as C

// Pill buttons. kind: "primary" (accent), "destructive" (red fill), "secondary" (glass),
// "flat", "danger" (red text).
C.Button {
    id: control
    property string kind: "secondary"
    property string iconName: ""
    property string tip: ""
    property bool tipBelow: false       // show the tooltip under the button, off the text above it
    property bool busy: false

    readonly property bool _primary: kind === "primary" || kind === "destructive"
    readonly property color _fill: kind === "destructive" ? Theme.bad : Theme.accent
    readonly property color _fg: kind === "destructive" ? "white" : _primary ? Theme.accentFg
                                 : kind === "danger" ? Theme.bad : Theme.text

    implicitHeight: 40
    implicitWidth: Math.max(implicitHeight, row.implicitWidth + (text.length ? 40 : 0))
    leftPadding: 20
    rightPadding: 20
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : 0.45
    Behavior on opacity { NumberAnimation { duration: Theme.fast } }

    LgToolTip { shown: control.tip.length > 0 && control.hovered && !control.pressed; text: control.tip; below: control.tipBelow }

    HoverHandler { cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }

    contentItem: Item {
        implicitWidth: row.implicitWidth
        implicitHeight: row.implicitHeight
        Row {
            id: row
            anchors.centerIn: parent
            spacing: 8
            Spinner {
                visible: control.busy
                size: 16
                color: control._fg
                anchors.verticalCenter: parent.verticalCenter
            }
            Icon {
                visible: control.iconName.length > 0 && !control.busy
                name: control.iconName
                size: 18
                color: control._fg
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                visible: control.text.length > 0
                text: control.text
                color: control._fg
                font.pixelSize: Theme.fsBody
                font.weight: control._primary ? Font.DemiBold : Font.Medium
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    background: Rectangle {
        radius: height / 2
        color: control._primary
               ? (control.down ? Qt.darker(control._fill, 1.12) : control.hovered ? Qt.lighter(control._fill, 1.08) : control._fill)
               : control.kind === "flat" || control.kind === "danger"
                 ? (control.down ? Theme.pressed : control.hovered ? Theme.hover : "transparent")
                 : (control.down ? Theme.wellHi : control.hovered ? Theme.surfaceHi : Theme.well)
        border.width: control.kind === "secondary" ? 1 : 0
        border.color: Theme.border
        Behavior on color { ColorAnimation { duration: Theme.fast } }

        FocusRing { target: control; radius: height / 2 }
    }
}
