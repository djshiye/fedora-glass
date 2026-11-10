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
}
