import QtQuick
import QtQuick.Controls.Basic as C

// A segmented control with a sliding glass thumb.
// model: [{ value, label, icon, tip }]
FocusScope {
    id: root
    property var model: []
    property var value
    property bool compact: false
    property bool iconOnly: false
    property bool onWallpaper: false     // floats over the preview: always light-on-dark
    readonly property color _text: onWallpaper ? "#f4f5f9" : Theme.text
    readonly property color _textDim: onWallpaper ? Qt.rgba(0.96, 0.96, 0.98, 0.7) : Theme.textDim
    readonly property bool _dark: onWallpaper || Theme.dark
    signal activated(var value)

    readonly property int count: model.length
    readonly property int currentIndex: {
        for (let i = 0; i < model.length; i++)
            if (model[i].value === value)
                return i
        return -1
    }

    implicitHeight: compact ? 32 : 36
    implicitWidth: 240
    activeFocusOnTab: true

    Keys.onLeftPressed: if (currentIndex > 0) activated(model[currentIndex - 1].value)
    Keys.onRightPressed: if (currentIndex < count - 1) activated(model[currentIndex + 1].value)

    Rectangle {
        id: track
        anchors.fill: parent
        radius: height / 2
        color: root.onWallpaper ? "transparent" : Theme.well
        border.width: root.onWallpaper ? 0 : 1
        border.color: Theme.border
    }

    Rectangle {
        id: thumb
        visible: root.currentIndex >= 0
        readonly property real segW: (root.width - 6) / Math.max(1, root.count)
        x: 3 + Math.max(0, root.currentIndex) * segW
        y: 3
        width: segW
        height: root.height - 6
        radius: height / 2
        color: root._dark ? Qt.rgba(1, 1, 1, 0.18) : "white"
        border.width: 1
        border.color: root._dark ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(0, 0, 0, 0.06)
        Behavior on x { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
        Rectangle {
            anchors.fill: parent
            anchors.margins: 1
            radius: height / 2
            color: "transparent"
            border.width: 1
            border.color: root._dark ? Qt.rgba(1, 1, 1, 0.07) : Qt.rgba(1, 1, 1, 1)
        }
    }

    Row {
        anchors.fill: parent
        anchors.margins: 3
        Repeater {
            model: root.model
            delegate: Item {
                id: seg
                required property var modelData
                required property int index
                readonly property bool selected: index === root.currentIndex
                width: (root.width - 6) / Math.max(1, root.count)
                height: parent.height

                LgToolTip { shown: hover.hovered; text: seg.modelData.tip || "" }

                Row {
                    anchors.centerIn: parent
                    spacing: 6
                    Icon {
                        visible: (seg.modelData.icon || "") !== ""
                        name: seg.modelData.icon || ""
                        size: root.compact ? 15 : 16
                        color: seg.selected ? root._text : root._textDim
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        visible: !root.iconOnly
                        text: seg.modelData.label || ""
                        color: seg.selected ? root._text : root._textDim
                        font.pixelSize: root.compact ? 13 : Theme.fsBody
                        font.weight: seg.selected ? Font.DemiBold : Font.Medium
                        anchors.verticalCenter: parent.verticalCenter
                        Behavior on color { ColorAnimation { duration: Theme.fast } }
                    }
                }
                HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: { root.forceActiveFocus(); root.activated(seg.modelData.value) } }
            }
        }
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: -3
        radius: height / 2
        color: "transparent"
        border.width: 2
        border.color: Theme.alpha(Theme.accent, 0.85)
        opacity: root.activeFocus ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
    }
}
