import QtQuick
import QtQuick.Controls.Basic as C

// A compact colour popover: saturation/value square, hue strip, hex entry.
C.Popup {
    id: pop
    property color color: "#3584e4"
    property string title: "Custom colour"
    signal picked(string hex)

    property real hue: 0
    property real sat: 0
    property real val: 0
    function load(c) {
        hue = Math.max(0, c.hsvHue); sat = c.hsvSaturation; val = c.hsvValue
        hex.text = current.toString().substring(0, 7)
    }
    readonly property color current: Qt.hsva(hue, sat, val, 1)
    function emitPick() { pop.picked(current.toString().substring(0, 7)) }

    onAboutToShow: load(color)
    width: 280
    padding: 16
    modal: false
    focus: true
    closePolicy: C.Popup.CloseOnEscape | C.Popup.CloseOnPressOutside

    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.fast }
        NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
    }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.fast } }

    background: Rectangle {
        radius: 18
        color: Theme.sheet
        border.width: 1
        border.color: Theme.borderHi
    }

    contentItem: Column {
        spacing: 12
        Text { text: pop.title; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.DemiBold }

        Rectangle {
            id: square
            width: parent.width
            height: 150
            radius: 10
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: "white" }
                GradientStop { position: 1; color: Qt.hsva(pop.hue, 1, 1, 1) }
            }
            Rectangle {
                anchors.fill: parent
                radius: 10
                gradient: Gradient {
                    GradientStop { position: 0; color: "transparent" }
                    GradientStop { position: 1; color: "black" }
                }
                border.width: 1
                border.color: Theme.border
            }
            Rectangle {
                x: pop.sat * parent.width - width / 2
                y: (1 - pop.val) * parent.height - height / 2
                width: 18; height: 18; radius: 9
                color: pop.current
                border.width: 3
                border.color: "white"
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.CrossCursor
                function set(m) {
                    pop.sat = Math.max(0, Math.min(1, m.x / width))
                    pop.val = 1 - Math.max(0, Math.min(1, m.y / height))
                    hex.text = pop.current.toString().substring(0, 7)
                    pop.emitPick()
                }
                onPressed: (m) => set(m)
                onPositionChanged: (m) => { if (pressed) set(m) }
            }
        }

        Rectangle {
            width: parent.width
            height: 16
            radius: 8
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.000; color: "#ff0000" }
                GradientStop { position: 0.166; color: "#ffff00" }
                GradientStop { position: 0.333; color: "#00ff00" }
                GradientStop { position: 0.500; color: "#00ffff" }
                GradientStop { position: 0.666; color: "#0000ff" }
                GradientStop { position: 0.833; color: "#ff00ff" }
                GradientStop { position: 1.000; color: "#ff0000" }
            }
            Rectangle {
                x: pop.hue * parent.width - width / 2
                anchors.verticalCenter: parent.verticalCenter
                width: 20; height: 20; radius: 10
                color: Qt.hsva(pop.hue, 1, 1, 1)
                border.width: 3
                border.color: "white"
            }
            MouseArea {
                anchors.fill: parent
                anchors.margins: -6
                cursorShape: Qt.PointingHandCursor
                function set(m) {
                    pop.hue = Math.max(0, Math.min(0.999, (m.x - 6) / (width - 12)))
                    hex.text = pop.current.toString().substring(0, 7)
                    pop.emitPick()
                }
                onPressed: (m) => set(m)
                onPositionChanged: (m) => { if (pressed) set(m) }
            }
        }

        Row {
            spacing: 10
            width: parent.width
            Rectangle {
                width: 36; height: 36; radius: 18
                color: pop.current
                border.width: 1
                border.color: Theme.border
            }
            C.TextField {
                id: hex
                width: parent.width - 46
                height: 36
                leftPadding: 14
                color: Theme.text
                selectionColor: Theme.alpha(Theme.accent, 0.4)
                selectedTextColor: Theme.text
                font.family: Theme.mono
                font.pixelSize: 14
                maximumLength: 7
                validator: RegularExpressionValidator { regularExpression: /#?[0-9a-fA-F]{0,6}/ }
                Accessible.name: "Hex colour"
                background: Rectangle {
                    radius: 18
                    color: Theme.well
                    border.width: hex.activeFocus ? 2 : 1
                    border.color: hex.activeFocus ? Theme.alpha(Theme.accent, 0.85) : Theme.border
                }
                onTextEdited: {
                    let t = text.startsWith("#") ? text : "#" + text
                    if (t.length === 7) {
                        let c = Qt.color(t)
                        pop.hue = Math.max(0, c.hsvHue); pop.sat = c.hsvSaturation; pop.val = c.hsvValue
                        pop.picked(t.toLowerCase())
                    }
                }
            }
        }
    }
}
