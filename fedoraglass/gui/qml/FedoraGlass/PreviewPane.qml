import QtQuick
import QtQuick.Effects
import FedoraGlass.Core

// The one live preview of the desktop, shared by every page that shows it: Main lays it
// over the page's preview slot, so moving between pages never builds a second copy.
// Floating on it: what it shows (desktop, Quick Settings, calendar, overview) and the
// dark/light switch, like Shell pop-ups.
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
        function onSceneChanged() { outline.later() }
        function onShowMenuChanged() { outline.later() }
    }

    RectangularShadow {
        anchors.fill: parent
        radius: Theme.rM
        blur: 28
        offset.y: 8
        color: Qt.rgba(0, 0, 0, Theme.dark ? 0.5 : 0.22)
    }

    PreviewDesktop {
        id: preview
        // Make sure a menu is open, for the switches that change menus.
        function showPopup() { if (scene === "overview") scene = "desktop"; if (scene === "desktop") showMenu = true }
        objectName: "preview"
        anchors.fill: parent
        t: Backend.tokens
        wallpaper: Backend.wallpaper
        dock: Backend.dock
        reduceTransparency: Backend.reduceTransparency
        motion: Theme.motionDriver ? Theme.motionDriver.fr : null
        motionEvent: Theme.motionDriver ? Theme.motionDriver.pvEvent : ""
        motionPlaying: Theme.motionDriver ? Theme.motionDriver.playing : false
        layer.enabled: true
        layer.smooth: true
        layer.effect: MultiEffect {
            maskEnabled: true
            maskSource: previewMask
            maskThresholdMin: 0.5
            maskSpreadAtMin: 1.0
        }
    }
    Rectangle {
        id: previewMask
        anchors.fill: parent
        radius: Theme.rM
        visible: false
        layer.enabled: true
        layer.smooth: true
    }
    Rectangle {     // a faint edge, so the preview reads as a pane on light pages too
        anchors.fill: parent
        radius: Theme.rM
        color: "transparent"
        border.width: 1
        border.color: Theme.border
    }

    Rectangle {
        anchors.top: preview.topBar ? undefined : parent.top
        anchors.bottom: preview.topBar ? parent.bottom : undefined
        anchors.left: parent.left
        anchors.margins: 12
        visible: pane.showControls
        width: sceneSeg.width + 8
        height: sceneSeg.height + 8
        radius: height / 2
        color: Qt.rgba(0.08, 0.085, 0.11, 0.55)
        Segmented {
            id: sceneSeg
            objectName: "previewScene"
            anchors.centerIn: parent
            width: 160
            compact: true
            iconOnly: true
            onWallpaper: true
            model: [{ value: "desktop", icon: "screen", tip: preview.hasMenu ? "Show the desktop with the start menu" : "Show the desktop" },
                    { value: "quicksettings", icon: "sliders", tip: "Show Quick Settings" },
                    { value: "calendar", icon: "clock", tip: "Show the calendar and notifications" },
                    { value: "overview", icon: "grid", tip: "Show Activities (the overview)" }]
            value: preview.scene
            onActivated: (v) => { preview.scene = v; if (v === "desktop") preview.showMenu = true }
            Accessible.name: "Preview shows"
        }
    }

    Rectangle {
        anchors.top: preview.topBar ? undefined : parent.top
        anchors.bottom: preview.topBar ? parent.bottom : undefined
        anchors.right: parent.right
        anchors.margins: 12
        visible: pane.showControls
        width: schemeSeg.width + 8
        height: schemeSeg.height + 8
        radius: height / 2
        color: Qt.rgba(0.08, 0.085, 0.11, 0.55)
        Segmented {
            id: schemeSeg
            anchors.centerIn: parent
            width: 80
            compact: true
            iconOnly: true
            onWallpaper: true
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
        anchors.fill: parent
        enabled: pane.outlinedPart !== ""
        visible: enabled
        cursorShape: Qt.PointingHandCursor
        onClicked: (m) => {
            const name = preview.partAt(m.x, m.y)
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
            width = Math.min(pane.width - 2, r.x + r.width + 3) - x0
            height = Math.min(pane.height - 2, r.y + r.height + 3) - y0
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
