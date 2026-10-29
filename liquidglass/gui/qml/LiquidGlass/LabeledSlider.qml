import QtQuick

// Label + value on one line, slider underneath.
Item {
    id: root
    property string label: ""
    property real value: 0
    property real from: 0
    property real to: 1
    property real stepSize: 0.01
    property var format: (v) => Math.round(v * 100) + "%"
    signal moved(real value)
    width: parent ? parent.width : 300
    implicitHeight: 20 + 6 + slider.height

    Text {
        text: root.label
        color: root.enabled ? Theme.text : Theme.textFaint
        font.pixelSize: Theme.fsBody
        font.weight: Font.Medium
    }
    Text {
        anchors.right: parent.right
        text: root.format(slider.value)
        color: Theme.textDim
        font.pixelSize: 13
        font.features: { "tnum": 1 }
    }
    LgSlider {
        id: slider
        y: 26
        width: parent.width
        from: root.from
        to: root.to
        stepSize: root.stepSize
        value: root.value
        enabled: root.enabled
        onMoved: root.moved(value)
        Accessible.name: root.label
    }
}
