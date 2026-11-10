import QtQuick

// Label + value on one line, slider underneath.
// With `defaultValue` set, a small mark on the track shows where the default is, and a
// "Default" pill next to the value puts it back whenever the slider is somewhere else.
Item {
    id: root
    property string label: ""
    property real value: 0
    property real from: 0
    property real to: 1
    property real stepSize: 0.01
    property var format: (v) => Math.round(v * 100) + "%"
    property string tip: ""
    property real defaultValue: NaN
    readonly property bool hasDefault: !isNaN(defaultValue)
    // Within half a step counts as the default: a dragged slider lands on 0.449 for 0.45.
    readonly property bool atDefault: !hasDefault || Math.abs(value - defaultValue) <= Math.max(stepSize, 1e-6) / 2
    // On one line: the label on the left, the slider in the middle, the value on the right
    // (the compact rows inside folds).
    property bool inline: false
    property real labelWidth: 170
    signal moved(real value)
    width: parent ? parent.width : 300
    implicitHeight: inline ? 40 : 20 + 6 + slider.height

    Text {
        id: labelText
        anchors.verticalCenter: root.inline ? parent.verticalCenter : undefined
        width: root.inline ? root.labelWidth - 12 : implicitWidth
        elide: Text.ElideRight
        text: root.label
        color: root.enabled ? Theme.text : Theme.textFaint
        font.pixelSize: Theme.fsBody
        font.weight: Font.Medium
    }
    ResetButton {
        id: reset
        objectName: "sliderDefault"
        visible: !root.atDefault && root.enabled
        anchors.right: valueText.left
        anchors.rightMargin: root.inline ? 8 : 10
        anchors.verticalCenter: valueText.verticalCenter
        tip: "Back to the default, " + root.format(root.defaultValue)
        onClicked: root.moved(root.defaultValue)
    }
    Text {
        id: valueText
        anchors.right: parent.right
        anchors.verticalCenter: root.inline ? parent.verticalCenter : undefined
        width: root.inline ? Math.max(44, implicitWidth) : implicitWidth
        horizontalAlignment: Text.AlignRight
        text: root.format(slider.value)
        color: Theme.textDim
        font.pixelSize: 13
        font.features: { "tnum": 1 }
    }
    HoverHandler { id: hover }
    LgToolTip { shown: (hover.hovered || slider.visualFocus) && !slider.pressed && !reset.hovered; text: root.tip }
    LgSlider {
        id: slider
        y: root.inline ? (root.height - height) / 2 : 26
        x: root.inline ? root.labelWidth : 0
        width: root.inline ? parent.width - root.labelWidth - valueText.width - 12
                             - (reset.visible ? reset.width + 8 : 0) : parent.width
        from: root.from
        to: root.to
        stepSize: root.stepSize
        value: root.value
        markValue: root.defaultValue
        enabled: root.enabled
        onMoved: root.moved(value)
        Accessible.name: root.label
    }
}
