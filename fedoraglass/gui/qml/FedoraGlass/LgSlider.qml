import QtQuick
import QtQuick.Controls.Basic as C

// A compact slider: thin track, white knob that swells while held.
C.Slider {
    id: control
    property string valueText: ""
    property bool dimmed: false     // shows an "automatic" value, not a chosen one
    property real markValue: NaN    // a small mark on the track: where the default is

    implicitHeight: 28
    implicitWidth: 200
    padding: 0
    leftPadding: 0
    rightPadding: 0
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : 0.45
    Behavior on opacity { NumberAnimation { duration: Theme.fast } }
    // Qt's slider moves only on Left and Right. Up and Down step too, Page Up and Page Down move ten
    // steps, Home and End go to the ends. Stepped with increase() and decrease(), so the value keeps
    // its binding to the setting.
    Keys.onPressed: (e) => {
        const steps = { [Qt.Key_Up]: 1, [Qt.Key_Down]: -1, [Qt.Key_PageUp]: 10, [Qt.Key_PageDown]: -10,
                        [Qt.Key_Home]: -100000, [Qt.Key_End]: 100000 }[e.key]
        // Ctrl, Alt, Meta or Shift with a key keeps its other meanings.
        if (steps === undefined || (e.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier | Qt.ShiftModifier)))
            return
        e.accepted = true
        const was = value
        for (let i = 0; i < Math.abs(steps); i++) {
            const before = value
            steps > 0 ? increase() : decrease()
            if (value === before)
                break
        }
        if (value !== was)
            moved()
    }
    HoverHandler { cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }

    background: Item {
        x: control.leftPadding
        width: control.availableWidth
        height: control.height
        Rectangle {
            id: groove
            x: 0
            width: parent.width
            height: 6
            radius: 3
            anchors.verticalCenter: parent.verticalCenter
            color: Theme.wellHi
            Rectangle {
                width: control.handle.x + control.handle.width / 2
                height: parent.height
                radius: 3
                color: control.dimmed ? Theme.textFaint : Theme.accent
                Behavior on color { ColorAnimation { duration: Theme.fast } }
            }
        }
        // The default's mark: a short tick under the track, out of the knob's way.
        Rectangle {
            objectName: "defaultMark"
            visible: !isNaN(control.markValue) && control.to > control.from
            readonly property real pos: Math.max(0, Math.min(1, (control.markValue - control.from) / (control.to - control.from)))
            width: 2
            height: 5
            radius: 1
            x: 11 + pos * (parent.width - 22) - width / 2
            y: groove.y + groove.height + 3
            color: Theme.textFaint
        }
    }

    handle: Item {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: (control.height - height) / 2
        width: 22
        height: 22
        Rectangle {
            anchors.centerIn: parent
            readonly property real d: control.pressed ? 28 : (control.hovered ? 23 : 22)
            width: d
            height: d
            radius: d / 2
            color: Theme.knob
            border.width: 1
            border.color: Qt.rgba(0, 0, 0, Theme.dark ? 0.25 : 0.12)
            Behavior on width { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }
            Behavior on height { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }
        }
        Rectangle {
            anchors.fill: parent
            anchors.margins: -4
            radius: width / 2
            color: "transparent"
            border.width: 2
            border.color: Theme.alpha(Theme.accent, 0.85)
            opacity: control.visualFocus ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.fast } }
        }
    }
}
