import QtQuick

// The glass for popups (tooltips, dropdown lists, popovers): use it as a
// Popup's `background`: background: PopupGlass { owner: pop; radius: Theme.rM }
//
// Popups live in the window's overlay, which is not a sibling of the page, so
// the backdrop is the shared Theme.backdrop (the window's content, set from
// Main.qml). Each time the popup opens or moves, the rectangle under it is
// mapped into that item's coordinates and captured. While the popup is closed
// nothing is captured. Without a backdrop it falls back to the old opaque card.
Item {
    id: root

    property var owner                       // the Popup this is the background of
    property real radius: 12
    property real blurRadius: 32
    property real tintAlphaDark: 0.80
    property real tintAlphaLight: 0.82
    property real shadowBlur: 22
    property real shadowY: 6

    readonly property Item backdrop: Theme.backdrop
    readonly property bool glassy: backdrop !== null
    readonly property bool shown: owner ? owner.visible : false

    // dark ink over a dark backdrop, near-white over a light one
    readonly property color tint: Theme.dark
        ? Qt.rgba(0.075, 0.08, 0.10, tintAlphaDark)
        : Qt.rgba(0.985, 0.987, 0.993, tintAlphaLight)

    // Where this item sits in the backdrop's coordinates, with the margin the
    // glass's edge reflects. Refreshed when the popup opens, moves or resizes.
    property rect sourceRect: Qt.rect(0, 0, 1, 1)
    function refresh() {
        const b = root.backdrop
        if (!b || root.width <= 0 || root.height <= 0)
            return
        const p = root.mapToItem(b, 0, 0)
        const pad = glass.pad
        sourceRect = Qt.rect(p.x - pad, p.y - pad, root.width + 2 * pad, root.height + 2 * pad)
    }
    onShownChanged: if (shown) refresh()
    onBackdropChanged: refresh()
    onWidthChanged: refresh()
    onHeightChanged: refresh()
    Component.onCompleted: refresh()

    Connections {
        target: root.owner
        ignoreUnknownSignals: true
        function onXChanged() { root.refresh() }
        function onYChanged() { root.refresh() }
        function onAboutToShow() { root.refresh() }
        function onOpened() { root.refresh() }
    }

    // opaque fallback (no backdrop)
    Rectangle {
        anchors.fill: parent
        visible: !root.glassy
        radius: root.radius
        color: Theme.dark ? Qt.rgba(0.105, 0.11, 0.135, 1) : Qt.rgba(0.985, 0.987, 0.993, 1)
        border.width: 1
        border.color: Theme.borderHi
    }

    GlassSurface {
        id: glass
        anchors.fill: parent
        visible: root.glassy
        backdrop: root.backdrop
        sourceRect: root.sourceRect
        // only captures while the popup is up
        live: root.shown && root.glassy
        radius: root.radius
        blurRadius: root.blurRadius
        tint: root.tint
        rim: Theme.rim
        refraction: 4
        bezel: Math.min(10, root.radius)
        shadowColor: Theme.shadow
        shadowBlur: root.shadowBlur
        shadowY: root.shadowY
    }
}
