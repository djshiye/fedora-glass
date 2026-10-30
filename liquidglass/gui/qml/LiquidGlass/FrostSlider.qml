import QtQuick
import QtQuick.Controls.Basic as C

// The headline control, Liquid ↔ Frosted. At rest the knob is a white pill;
// while held it swells into a clear glass lens that magnifies and bends the
// track behind it, like the sliders in iOS 26.
FocusScope {
    id: root
    property real value: 0.45
    property var ticks: []          // [{ value, label }] preset positions
    property string tip: "The main control. Left is clear, bright liquid glass that bends what is behind it. Right is thick, milky frost that blurs it and keeps text easy to read."
    signal moved(real value)

    implicitHeight: 72
    implicitWidth: 480
    activeFocusOnTab: true
    onActiveFocusChanged: if (activeFocus) slider.forceActiveFocus()

    Icon {
        id: dropIcon
        name: "droplet"
        size: 22
        color: Theme.textDim
        anchors.left: parent.left
        y: slider.y + slider.height / 2 - height / 2
    }
    Icon {
        id: frostIcon
        name: "snowflake"
        size: 22
        color: Theme.textDim
        anchors.right: parent.right
        y: slider.y + slider.height / 2 - height / 2
    }

    C.Slider {
        id: slider
        anchors.left: dropIcon.right
        anchors.right: frostIcon.left
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        y: 4
        height: 52
        from: 0
        to: 1
        stepSize: 0.01
        value: root.value
        live: true
        padding: 0
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        onMoved: root.moved(value)
        Accessible.name: "Glass: liquid to frosted"

        readonly property real restW: 46
        readonly property real restH: 30
        readonly property real grow: pressed ? 1 : 0
        property real g: grow
        Behavior on g { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutBack; easing.overshoot: 1.6 } }
        readonly property real knobCx: leftPadding + restW / 2 + visualPosition * (availableWidth - restW)

        HoverHandler { cursorShape: Qt.PointingHandCursor }

        background: Item {
            width: slider.width
            height: slider.height

            // Everything the lens may see: the track and its marks, not the knob.
            Item {
                id: trackLayer
                anchors.fill: parent

                Rectangle {
                    id: groove
                    x: 0
                    width: parent.width
                    height: 14
                    radius: 7
                    anchors.verticalCenter: parent.verticalCenter
                    color: Theme.wellHi
                    border.width: 1
                    border.color: Theme.border

                    Rectangle {     // fill: clear accent glass turning milky towards "frosted"
                        width: Math.max(height, slider.knobCx)
                        height: parent.height
                        radius: height / 2
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0; color: Theme.accent }
                            GradientStop { position: 1; color: Qt.tint(Theme.accent, Qt.rgba(1, 1, 1, 0.25 + 0.45 * slider.visualPosition)) }
                        }
                    }
                    Repeater {
                        model: root.ticks
                        delegate: Rectangle {
                            required property var modelData
                            readonly property real cx: slider.restW / 2 + modelData.value * (groove.width - slider.restW)
                            x: cx - width / 2
                            anchors.verticalCenter: parent.verticalCenter
                            width: 4
                            height: 4
                            radius: 2
                            color: cx < slider.knobCx ? Qt.rgba(1, 1, 1, 0.75) : Theme.textFaint
                        }
                    }
                }
            }
        }

        handle: Item {
            // Hit-testing and value mapping use the resting size; the visuals grow freely.
            x: slider.knobCx - width / 2
            y: (slider.height - height) / 2
            width: slider.restW
            height: slider.restH
        }

        // The knob: shadow, glass lens and the white pill that melts away while held.
        Item {
            id: knob
            readonly property real w: slider.restW + slider.g * 30
            readonly property real h: slider.restH + slider.g * 18
            x: slider.knobCx - w / 2
            y: slider.height / 2 - h / 2
            width: w
            height: h
            z: 2

            GlassSurface {
                anchors.fill: parent
                backdrop: trackLayer
                sourceRect: Qt.rect(knob.x, knob.y, knob.width, knob.height)
                radius: height / 2
                blurRadius: 0
                refraction: 9
                bezel: Math.min(16, height * 0.42)
                magnify: 1.0 + 0.45 * slider.g
                fringe: 0.22
                sheen: 0.9
                tint: Qt.rgba(1, 1, 1, Theme.dark ? 0.06 : 0.12)
                rim: Qt.rgba(1, 1, 1, 0.95)
                edge: Theme.dark ? Qt.rgba(1, 1, 1, 0.35) : Qt.rgba(0, 0, 0, 0.14)
                rimWidth: 1.6
                shadowColor: Qt.rgba(0, 0, 0, Theme.dark ? 0.45 : 0.22)
                shadowBlur: 10 + slider.g * 14
                shadowY: 2 + slider.g * 4
            }
            Rectangle {
                anchors.fill: parent
                radius: height / 2
                color: Theme.knob
                opacity: 1 - Math.min(1, slider.g * 1.15)
                border.width: Theme.dark ? 0 : 1
                border.color: Qt.rgba(0, 0, 0, 0.07)
            }
            Rectangle {
                anchors.fill: parent
                anchors.margins: -4
                radius: height / 2
                color: "transparent"
                border.width: 2
                border.color: Theme.alpha(Theme.accent, 0.85)
                opacity: slider.visualFocus ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: Theme.fast } }
            }
        }
    }

    Item {
        anchors.left: slider.left
        anchors.right: slider.right
        y: slider.y + slider.height - 2
        height: 18
        Text {
            text: "Liquid"
            color: Theme.textDim
            font.pixelSize: Theme.fsSmall
            font.weight: Font.Medium
            anchors.left: parent.left
        }
        Text {
            text: "Frosted"
            color: Theme.textDim
            font.pixelSize: Theme.fsSmall
            font.weight: Font.Medium
            anchors.right: parent.right
        }
    }

    HoverHandler { id: rowHover }
    LgToolTip { shown: (rowHover.hovered || slider.visualFocus) && !slider.pressed; text: root.tip }

    // Programmatic preview of the held state (screenshots).
    property alias held: slider.g
}
