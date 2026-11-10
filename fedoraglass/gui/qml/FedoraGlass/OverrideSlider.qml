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
    property string autoTip: "Follows How much glass on the Glass page"
    property string resetTip: "Go back to following How much glass"
    // One row: label on the left, slider in the middle, value and chip on the right.
    property bool inline: false
    readonly property bool _row: inline && width >= 520      // stacked when narrow
    property real labelWidth: 150
    property real rightWidth: 176      // fixed, so the slider keeps its length either way
    signal changed(real value)

    readonly property bool isAuto: value < 0
    width: parent ? parent.width : 300
    implicitHeight: _row ? 44 : head.height + 6 + slider.height + (inline ? 14 : 0)

    Item {
        id: head
        width: parent.width
        height: root._row ? root.implicitHeight : Math.max(labels.height, autoChip.height)
        Column {
            id: labels
            width: root._row ? root.labelWidth - 12 : parent.width - autoChip.width - valueText.width - 24
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
            visible: !root._row || !root.isAuto
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
            text: root._row && !root.isAuto ? "Reset" : root.autoText
            selected: root.isAuto
            tip: root.isAuto ? root.autoTip : root.resetTip
            onClicked: root.changed(root.isAuto ? root.autoValue : -1)
        }
    }
    HoverHandler { id: hover }
    LgToolTip { shown: (hover.hovered || slider.visualFocus) && !slider.pressed && !autoChip.hovered; text: root.tip }
    LgSlider {
        id: slider
        x: root._row ? root.labelWidth : 0
        y: root._row ? (root.implicitHeight - height) / 2 : head.height + 6
        width: root._row ? parent.width - root.labelWidth - root.rightWidth : parent.width
        from: root.from
        to: root.to
        stepSize: root.stepSize
        value: root.isAuto ? root.autoValue : root.value
        dimmed: root.isAuto
        onMoved: root.changed(value)
        Accessible.name: root.label
    }
}
