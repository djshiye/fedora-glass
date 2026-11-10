import QtQuick
import QtQuick.Effects
import FedoraGlass.Core

// The one live preview of the desktop, shared by every page that shows it: Main lays it
// over the page's preview slot, so moving between pages never builds a second copy.
// In a bar under it, so nothing covers the glass: what it shows (desktop, Quick Settings,
// calendar, overview), close up or the whole screen, and the dark/light switch.
//
// Close up (the default) draws the desktop at about half its real size and looks at the
// part being shown: the start menu, Quick Settings or the calendar, with the panel and
// the windows around it. Blur, corners, the rim and the tint then read as they will on
// the screen. Drag the preview to look around; the overview always shows it all.
Item {
    id: pane
    property alias preview: preview
    property bool showControls: true
    // A part outlined on the preview (the Advanced page's Part by part).
    property string outlinedPart: ""
    // While a part is outlined, clicking the preview picks the part under the pointer.
    signal partPicked(string name)
    onOutlinedPartChanged: outline.later()
    onWidthChanged: outline.later()
    onHeightChanged: outline.later()
    Connections {
        target: preview
        function onSceneChanged() { outline.later(); pane.recentre() }
        function onShowMenuChanged() { outline.later() }
    }

    // The desktop picture fills the pane above the bar of controls.
    readonly property real barH: showControls ? 44 : 0
    readonly property real viewW: width
    readonly property real viewH: Math.max(1, height - barH)

    // ---- the camera ------------------------------------------------------------------
    // Close up or the whole screen; the user's pick holds while the app is open.
    property bool closeUp: true
    // How big the desktop is drawn: at least filling the pane ("whole screen" shows as
    // much as the pane's shape allows), and about half real size close up.
    // A short strip (a small window) zooms in less, so it still shows a whole menu.
    readonly property real closeScale: Math.min(0.55, Math.max(0.36, viewH / 720))
    readonly property real fitScale: Math.max(viewW / 1920, viewH / 1080, 0.01)
    readonly property bool canZoom: fitScale < closeScale * 0.9
    readonly property bool zoomed: closeUp && canZoom && preview.scene !== "overview"
    readonly property real scale_: zoomed ? closeScale : fitScale
    readonly property real deskW: Math.round(1920 * scale_)
    readonly property real deskH: Math.round(1080 * scale_)
    // What to look at, on the 1920x1080 desktop: the open pop-up, else the start menu
    // with the windows beside it, always along the panel's edge.
    readonly property point lookAt: {
        const sc = preview.scene
        const pop = sc === "quicksettings" || sc === "calendar" ? preview.partItem(sc) : null
        // The start menu sits at the left edge: show it whole, the windows beside it.
        const fx = pop ? (pop.x + pop.width / 2) / Math.max(0.01, preview.s)
                 : preview.menuOpen ? 0 : 1000
        return Qt.point(fx, preview.topBar ? 0 : 1080)
    }
    // Dragging moves the view by this much (preview px), until the next scene or zoom.
    property real panX: 0
    property real panY: 0
    function recentre() { glide.restart(); panX = 0; panY = 0 }
    onZoomedChanged: recentre()
    function clampTo(v, hi) { return Math.max(0, Math.min(v, Math.max(0, hi))) }
    readonly property real camX: clampTo(lookAt.x * scale_ - viewW / 2 + panX, deskW - viewW)
    readonly property real camY: clampTo(lookAt.y * scale_ - viewH / 2 + panY, deskH - viewH)
    readonly property bool canPan: deskW > viewW + 1 || deskH > viewH + 1
    onCamXChanged: outline.later()
    onCamYChanged: outline.later()
    // A short glide when the view moves to a new scene, not while resizing or dragging.
    Timer { id: glide; interval: 700 }

    RectangularShadow {
        width: pane.viewW; height: pane.viewH
        radius: Theme.rM
        blur: 28
        offset.y: 8
        color: Qt.rgba(0, 0, 0, Theme.dark ? 0.5 : 0.22)
    }

    Item {
        id: viewport
        objectName: "previewViewport"
        width: pane.viewW; height: pane.viewH
        // The rounded mask works on what is in view only, so a close-up costs no bigger
        // texture than the pane itself.
        layer.enabled: true
        layer.smooth: true
        layer.effect: MultiEffect {
            maskEnabled: true
            maskSource: previewMask
            maskThresholdMin: 0.5
            maskSpreadAtMin: 1.0
        }

        PreviewDesktop {
            id: preview
            // Make sure a menu is open, for the switches that change menus.
            function showPopup() { if (scene === "overview") scene = "desktop"; if (scene === "desktop") showMenu = true }
            objectName: "preview"
            width: pane.deskW
            height: pane.deskH
            x: -pane.camX
            y: -pane.camY
            view: Qt.rect(pane.camX, pane.camY, pane.viewW, pane.viewH)
            Behavior on x { enabled: glide.running && !drag.active; NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
            Behavior on y { enabled: glide.running && !drag.active; NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
            t: Backend.tokens
            wallpaper: Backend.wallpaper
            dock: Backend.dock
            reduceTransparency: Backend.reduceTransparency
            motion: Theme.motionDriver ? Theme.motionDriver.fr : null
            motionEvent: Theme.motionDriver ? Theme.motionDriver.pvEvent : ""
            motionPlaying: Theme.motionDriver ? Theme.motionDriver.playing : false
        }
    }

    // Drag to look around the close-up (on the picture only, not on the bar of controls).
    Item {
        objectName: "previewDragArea"
        width: pane.viewW; height: pane.viewH
        DragHandler {
            id: drag
            objectName: "previewDrag"
            target: null
            enabled: pane.canPan
            cursorShape: active ? Qt.ClosedHandCursor : Qt.OpenHandCursor
            property real startX: 0
            property real startY: 0
            onActiveChanged: if (active) {
                // Start from where the view is, even when it sits against an edge.
                startX = pane.camX - (pane.lookAt.x * pane.scale_ - pane.viewW / 2)
                startY = pane.camY - (pane.lookAt.y * pane.scale_ - pane.viewH / 2)
            }
            onTranslationChanged: if (active) {
                pane.panX = startX - translation.x
                pane.panY = startY - translation.y
            }
        }
        HoverHandler {
            enabled: pane.canPan && pane.outlinedPart === ""
            cursorShape: Qt.OpenHandCursor
        }
    }
    Rectangle {
        id: previewMask
        width: pane.viewW; height: pane.viewH
        radius: Theme.rM
        visible: false
        layer.enabled: true
        layer.smooth: true
    }
    Rectangle {     // a faint edge, so the preview reads as a pane on light pages too
        width: pane.viewW; height: pane.viewH
        radius: Theme.rM
        color: "transparent"
        border.width: 1
        border.color: Theme.border
    }

    Item {
        y: pane.viewH + pane.barH - height
        x: 0
        visible: pane.showControls
        width: sceneSeg.width
        height: sceneSeg.height
        Segmented {
            id: sceneSeg
            objectName: "previewScene"
            anchors.centerIn: parent
            width: 160
            compact: true
            iconOnly: true
            model: [{ value: "desktop", icon: "screen", tip: preview.hasMenu ? "Show the desktop with the start menu" : "Show the desktop" },
                    { value: "quicksettings", icon: "sliders", tip: "Show Quick Settings" },
                    { value: "calendar", icon: "clock", tip: "Show the calendar and notifications" },
                    { value: "overview", icon: "grid", tip: "Show Activities (the overview)" }]
            value: preview.scene
            onActivated: (v) => { preview.scene = v; if (v === "desktop") preview.showMenu = true }
            Accessible.name: "Preview shows"
        }
    }

    Item {
        id: zoomPill
        y: pane.viewH + pane.barH - height
        anchors.right: schemePill.left
        anchors.rightMargin: 8
        // Hidden where it would change nothing (the overview, a very big pane) or crowd
        // the other two.
        visible: pane.showControls && pane.canZoom && preview.scene !== "overview" && pane.width >= 360
        width: zoomSeg.width
        height: zoomSeg.height
        Segmented {
            id: zoomSeg
            objectName: "previewZoom"
            anchors.centerIn: parent
            width: 80
            compact: true
            iconOnly: true
            model: [{ value: true, icon: "zoom-in", tip: "Close up: glass at about half its real size. Drag to look around." },
                    { value: false, icon: "zoom-out", tip: "Show the whole screen" }]
            value: pane.closeUp
            onActivated: (v) => pane.closeUp = v
            Accessible.name: "Preview size"
        }
    }

    Item {
        id: schemePill
        y: pane.viewH + pane.barH - height
        anchors.right: parent.right
        visible: pane.showControls
        width: schemeSeg.width
        height: schemeSeg.height
        Segmented {
            id: schemeSeg
            anchors.centerIn: parent
            width: 80
            compact: true
            iconOnly: true
            model: [{ value: true, icon: "moon", tip: "Preview the dark style" },
                    { value: false, icon: "sun", tip: "Preview the light style" }]
            value: Backend.previewDark
            onActivated: (v) => Backend.previewDark = v
            Accessible.name: "Preview style"
        }
    }

    // ---- Part by part: the part being edited, outlined; click another to pick it
    MouseArea {
        objectName: "partPicker"
        width: pane.viewW; height: pane.viewH
        enabled: pane.outlinedPart !== ""
        visible: enabled
        cursorShape: Qt.PointingHandCursor
        onClicked: (m) => {
            const p = pane.mapToItem(preview, m.x, m.y)
            const name = preview.partAt(p.x, p.y)
            if (name)
                pane.partPicked(name)
        }
    }
    Rectangle {
        id: outline
        objectName: "partOutline"
        // Measured once things settle (menus pop open), not on every frame.
        function later() { measure.restart() }
        function place() {
            const it = pane.outlinedPart ? preview.partItem(pane.outlinedPart) : null
            shown = !!it && it.visible && it.width > 0
            if (!shown)
                return
            const r = it.mapToItem(pane, 0, 0, it.width, it.height)
            const x0 = Math.max(2, r.x - 3), y0 = Math.max(2, r.y - 3)
            x = x0; y = y0
            width = Math.min(pane.viewW - 2, r.x + r.width + 3) - x0
            height = Math.min(pane.viewH - 2, r.y + r.height + 3) - y0
        }
        property bool shown: false
        Timer { id: measure; interval: 450; onTriggered: outline.place() }
        visible: shown && pane.outlinedPart !== ""
        radius: Math.min(Theme.rS + 2, height / 2)
        color: "transparent"
        border.width: 2
        border.color: Theme.accent
        opacity: visible ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
        Rectangle {     // a soft halo, so the line reads on any wallpaper
            anchors.fill: parent
            anchors.margins: -3
            radius: parent.radius + 3
            color: "transparent"
            border.width: 3
            border.color: Theme.alpha(Theme.accent, 0.3)
        }
    }
}
