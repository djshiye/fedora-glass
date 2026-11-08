import QtQuick

// A fine-tune value that normally follows the frost slider ("Auto").
// value < 0 means automatic; dragging sets a custom value, "Auto" clears it.
Item {
    id: root
    property string label: ""
    property string caption: ""
    property real value: -1
    property real autoValue: 0
    property real from: 0
    property real to: 1
    property real stepSize: 0.01
    property var format: (v) => Math.round(v * 100) + "%"
    property string tip: ""
    property string autoText: "Auto"    // the chip's label ("Global" for per-part values)
    property string autoTip: "Follows the Liquid to Frosted slider"
    property string resetTip: "Go back to following the Liquid to Frosted slider"
    signal changed(real value)

    readonly property bool isAuto: value < 0
    width: parent ? parent.width : 300
    implicitHeight: head.height + 6 + slider.height

    Item {
        id: head
        width: parent.width
        height: Math.max(labels.height, autoChip.height)
        Column {
            id: labels
            width: parent.width - autoChip.width - valueText.width - 24
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2
            Text { text: root.label; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
            Text {
                visible: root.caption.length > 0
                width: parent.width
                text: root.caption
                color: Theme.textFaint
                font.pixelSize: Theme.fsSmall
                wrapMode: Text.WordWrap
            }
        }
        Text {
            id: valueText
            anchors.right: autoChip.left
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            text: root.format(root.isAuto ? root.autoValue : root.value)
            color: root.isAuto ? Theme.textFaint : Theme.textDim
            font.pixelSize: 13
            font.features: { "tnum": 1 }
        }
        Chip {
            id: autoChip
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            implicitHeight: 28
            text: root.autoText
            selected: root.isAuto
            tip: root.isAuto ? root.autoTip : root.resetTip
            onClicked: root.changed(root.isAuto ? root.autoValue : -1)
        }
    }
    HoverHandler { id: hover }
    LgToolTip { shown: (hover.hovered || slider.visualFocus) && !slider.pressed && !autoChip.hovered; text: root.tip }
    LgSlider {
        id: slider
        y: head.height + 6
        width: parent.width
        from: root.from
        to: root.to
        stepSize: root.stepSize
        value: root.isAuto ? root.autoValue : root.value
        dimmed: root.isAuto
        onMoved: root.changed(value)
        Accessible.name: root.label
    }
}
