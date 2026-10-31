import QtQuick
import QtQuick.Controls.Basic as C

// Tooltip on frosted glass, for any control: LgToolTip { shown: hovered; text: "…" }
// Appears after a short pause, stays while `shown` is true (no timeout), wraps at
// 300 px and is kept inside the window.
C.ToolTip {
    id: tip
    property bool shown: false
    property bool below: false          // under the control instead of above it
    visible: shown && text.length > 0
    delay: 400
    timeout: 0
    padding: 0
    margins: 10                         // the popup never gets closer than this to the window edge
    topPadding: 8
    bottomPadding: 8
    leftPadding: 12
    rightPadding: 12
    y: below ? (parent ? parent.height + 8 : 0) : -implicitHeight - 8
    x: parent ? (parent.width - implicitWidth) / 2 : 0
    closePolicy: C.Popup.NoAutoClose

    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.fast } }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.fast } }

    contentItem: Item {
        implicitWidth: Math.min(measure.advanceWidth, 300)
        implicitHeight: label.implicitHeight
        Text {
            id: label
            width: parent.width
            text: tip.text
            color: Theme.text
            font.pixelSize: 13
            lineHeight: 1.12
            wrapMode: Text.Wrap
        }
        TextMetrics { id: measure; text: tip.text; font.pixelSize: 13 }
    }
    // Heavy frost over a dark (or light) tint, so the text reads over anything.
    background: PopupGlass {
        owner: tip
        radius: Theme.rS
        blurRadius: 32
        tintAlphaDark: 0.72
        tintAlphaLight: 0.76
        shadowBlur: 18
        shadowY: 4
    }
}
