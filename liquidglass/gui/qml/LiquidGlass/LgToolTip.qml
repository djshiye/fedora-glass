import QtQuick
import QtQuick.Controls.Basic as C

// Tooltip on dark glass, for any control: LgToolTip { shown: hovered; text: "…" }
C.ToolTip {
    id: tip
    property bool shown: false
    visible: shown && text.length > 0
    delay: 600
    timeout: 6000
    padding: 0
    margins: 8
    topPadding: 7
    bottomPadding: 7
    leftPadding: 12
    rightPadding: 12
    y: -implicitHeight - 8
    x: parent ? (parent.width - implicitWidth) / 2 : 0

    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.fast } }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.fast } }

    contentItem: Text {
        text: tip.text
        color: "#f4f5f9"
        font.pixelSize: 13
        wrapMode: Text.WordWrap
        width: Math.min(implicitWidth, 320)
    }
    background: Rectangle {
        radius: 10
        color: Qt.rgba(0.09, 0.095, 0.12, 0.94)
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, 0.10)
    }
}
