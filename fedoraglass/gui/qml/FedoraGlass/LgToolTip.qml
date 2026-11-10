import QtQuick

// Tooltip on frosted glass, for any control: LgToolTip { shown: hovered; text: "…" }
// Appears after a short pause, stays while `shown` is true (no timeout), wraps at
// 300 px and is kept inside the window.
// The glass popup (TipPopup) is built the first time the tooltip is wanted, not with
// the page: a page has dozens of tooltips and most are never seen.
Loader {
    id: lazy
    property bool shown: false
    property bool below: false
    property string text: ""
    // Out of the way of Rows and Columns: the popup positions itself on the control.
    visible: false
    width: 0
    height: 0
    active: false
    onShownChanged: if (shown && text.length > 0) active = true
    sourceComponent: TipPopup {
        parent: lazy.parent
        shown: lazy.shown
        below: lazy.below
        text: lazy.text
    }
}
