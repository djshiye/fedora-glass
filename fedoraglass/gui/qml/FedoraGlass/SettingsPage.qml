import QtQuick
import QtQuick.Controls.Basic as C

// One page of the app: its cards in a scrolling column on the left and, when the page
// has one, a fixed column on the right (the shared live preview sits in `previewSlot`).
// Search lands here through reveal(name): it opens any fold around the control,
// scrolls it into view and lights it up for a moment.
Item {
    id: page
    property string pageId: ""
    property bool hasSide: true
    // Pages without a side column (Apps) keep a comfortable reading width.
    property real maxColumn: 880
    readonly property real sideW: !hasSide ? 0 : width >= 1060 ? 420 : width >= 900 ? 360 : 300
    readonly property real gap: 24
    default property alias content: col.data
    property alias side: sideCol.data
    property Item previewSlot: null
    readonly property alias scroller: flick
    readonly property alias column: col

    Flickable {
        id: flick
        objectName: page.pageId + "Scroller"
        x: page.hasSide ? 0 : Math.max(0, (page.width - width) / 2)
        width: page.hasSide ? page.width - page.sideW - page.gap + 12 : Math.min(page.width, page.maxColumn + 12)
        height: page.height
        contentHeight: col.height + 20
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        C.ScrollBar.vertical: LgScrollBar {}
        Behavior on contentY {
            enabled: flick.gliding
            NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic }
        }
        property bool gliding: false

        Column {
            id: col
            width: flick.width - 12
            spacing: 14
        }
    }
    // Soft fades where the column scrolls under the edges.
    Rectangle {
        x: flick.x; width: flick.width - 12; height: 14
        visible: flick.contentY > 2
        gradient: Gradient {
            GradientStop { position: 0; color: Theme.alpha(Theme.base, 0.55) }
            GradientStop { position: 1; color: "transparent" }
        }
    }

    Column {
        id: sideCol
        visible: page.hasSide
        x: page.width - page.sideW
        width: page.sideW
        spacing: 12
    }

    // ---- search: reveal one control --------------------------------------------------
    function findNamed(root, name) {
        if (!root)
            return null
        if (root.objectName === name)
            return root
        const kids = root.children || []
        for (let i = 0; i < kids.length; ++i) {
            const hit = findNamed(kids[i], name)
            if (hit)
                return hit
        }
        return null
    }
    function reveal(name) {
        const it = findNamed(page, name)
        if (!it)
            return false
        let opened = false
        for (let p = it.parent; p && p !== page; p = p.parent)
            if (p.expanded !== undefined && p.summary !== undefined && !p.expanded) {
                p.expanded = true
                opened = true
            }
        revealTimer.target = it
        revealTimer.interval = opened ? Theme.slow + 40 : 10
        revealTimer.restart()
        return true
    }
    Timer {
        id: revealTimer
        property Item target: null
        onTriggered: {
            const it = target
            if (!it)
                return
            if (page.isInside(it, flick.contentItem)) {
                const top = it.mapToItem(flick.contentItem, 0, 0).y
                const want = Math.max(0, Math.min(top - 60, flick.contentHeight - flick.height))
                if (top < flick.contentY + 20 || top + it.height > flick.contentY + flick.height - 20) {
                    flick.gliding = true
                    flick.contentY = want
                    flick.gliding = false
                }
            }
            flashTimer.target = it
            flashTimer.restart()
        }
    }
    Timer {
        id: flashTimer
        property Item target: null
        interval: Theme.slow + 20
        onTriggered: {
            const it = target
            if (!it)
                return
            const r = it.mapToItem(page, 0, 0)
            flash.x = r.x - 8; flash.y = r.y - 6
            flash.width = it.width + 16; flash.height = it.height + 12
            flashAnim.restart()
            // Hand the keyboard to the control, so Space or the arrows work right away.
            const f = it.activeFocusOnTab || it.focusPolicy !== undefined ? it : it.nextItemInFocusChain(true)
            if (f && page.isInside(f, it))
                f.forceActiveFocus(Qt.OtherFocusReason)
        }
    }
    function isInside(it, root) {
        for (let p = it; p; p = p.parent)
            if (p === root)
                return true
        return false
    }
    Rectangle {
        id: flash
        objectName: "searchFlash"
        opacity: 0
        radius: Theme.rS
        color: Theme.alpha(Theme.accent, 0.14)
        border.width: 2
        border.color: Theme.alpha(Theme.accent, 0.8)
        z: 50
        SequentialAnimation {
            id: flashAnim
            NumberAnimation { target: flash; property: "opacity"; to: 1; duration: 120 }
            PauseAnimation { duration: 900 }
            NumberAnimation { target: flash; property: "opacity"; to: 0; duration: 500; easing.type: Easing.InOutQuad }
        }
    }
}
