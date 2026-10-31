import QtQuick
import QtQuick.Controls.Basic as C
import QtQuick.Effects
import QtQuick.Window
import LiquidGlass
import LiquidGlass.Core

// Frameless window with its own glass header, rounded corners and a soft
// client-side shadow (the same approach as Wheelguard), so the header, page
// switcher and window buttons live on one calm surface.
Window {
    id: win
    property int pageIndex: 0
    property alias fineTuneOpen: look.fineTuneOpen
    property alias frostHeld: look.frostHeld
    property string startSheet: ""
    onStartSheetChanged: if (startSheet === "restore") confirmSheet.open()

    readonly property bool maximized: visibility === Window.Maximized || visibility === Window.FullScreen
    readonly property int margin: maximized ? 0 : 18
    readonly property int cornerRadius: maximized ? 0 : Theme.rL

    width: 1280 + 2 * margin
    height: 820 + 2 * margin
    minimumWidth: 1000 + 2 * margin
    minimumHeight: 680 + 2 * margin
    color: "transparent"
    flags: Qt.Window | Qt.FramelessWindowHint
    title: "Liquid Glass"

    Shortcut { sequences: [StandardKey.Quit]; onActivated: Qt.quit() }
    Shortcut { sequence: "Ctrl+W"; onActivated: win.close() }
    Shortcut { sequence: "Ctrl+Return"; enabled: !Backend.busy; onActivated: Backend.apply() }
    Shortcut { sequence: "Ctrl+1"; onActivated: win.pageIndex = 0 }
    Shortcut { sequence: "Ctrl+2"; onActivated: win.pageIndex = 1 }

    // Popups (tooltips, dropdowns, colour pickers) capture this for their glass.
    Binding { target: Theme; property: "backdrop"; value: frame }

    // ------------------------------------------------------------ shadow
    RectangularShadow {
        anchors.fill: frame
        visible: !win.maximized
        radius: win.cornerRadius
        blur: 18
        offset.y: 4
        spread: -2
        color: Qt.rgba(0, 0, 0, Theme.dark ? 0.55 : 0.22)
    }

    // ------------------------------------------------------------ frame
    Item {
        id: frame
        anchors.fill: parent
        anchors.margins: win.margin

        // Backdrop: the wallpaper, heavily blurred under a scrim, so the app
        // carries the desktop's colours the way glass does.
        Item {
            id: backdrop
            objectName: "backdrop"
            anchors.fill: parent
            layer.enabled: true
            layer.effect: MultiEffect {
                maskEnabled: true
                maskSource: frameMask
                maskThresholdMin: 0.5
                maskSpreadAtMin: 1.0
            }
            Rectangle { anchors.fill: parent; color: Theme.base }
            Image {
                id: wallImg
                anchors.fill: parent
                source: Backend.wallpaper
                sourceSize.width: 640
                fillMode: Image.PreserveAspectCrop
                visible: false
                asynchronous: true
            }
            MultiEffect {
                anchors.fill: parent
                source: wallImg
                visible: wallImg.status === Image.Ready
                blurEnabled: true
                blur: 1
                blurMax: 64
                saturation: 0.2
                autoPaddingEnabled: false
            }
            Rectangle { anchors.fill: parent; color: Theme.scrim }
        }
        Rectangle {
            id: frameMask
            anchors.fill: parent
            radius: win.cornerRadius
            visible: false
            layer.enabled: true
        }
        Rectangle {     // glass edge (a plain border: cheaper than a shader over the whole window)
            anchors.fill: parent
            radius: win.cornerRadius
            color: "transparent"
            border.width: 1
            border.color: Theme.dark ? Qt.rgba(1, 1, 1, 0.09) : Qt.rgba(0, 0, 0, 0.12)
            visible: !win.maximized
            z: 10
        }
        Rectangle {     // rim light along the top edge
            x: win.cornerRadius; width: parent.width - 2 * win.cornerRadius
            y: 1; height: 1
            visible: !win.maximized
            z: 10
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: "transparent" }
                GradientStop { position: 0.3; color: Theme.dark ? Qt.rgba(1, 1, 1, 0.16) : Qt.rgba(1, 1, 1, 0.9) }
                GradientStop { position: 0.7; color: Theme.dark ? Qt.rgba(1, 1, 1, 0.16) : Qt.rgba(1, 1, 1, 0.9) }
                GradientStop { position: 1; color: "transparent" }
            }
        }

        // ---------------------------------------------------------- header
        Item {
            id: header
            width: parent.width
            height: 64

            DragHandler {
                target: null
                grabPermissions: PointerHandler.CanTakeOverFromAnything
                onActiveChanged: if (active) win.startSystemMove()
            }
            TapHandler {
                acceptedButtons: Qt.LeftButton
                onDoubleTapped: win.visibility = win.maximized ? Window.Windowed : Window.Maximized
            }

            Row {
                x: 24
                anchors.verticalCenter: parent.verticalCenter
                spacing: 12
                Image {
                    width: 30; height: 30
                    source: appIconUrl
                    sourceSize: Qt.size(60, 60)
                    smooth: true
                    mipmap: true
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: "Liquid Glass"
                    color: Theme.text
                    font.pixelSize: Theme.fsTitle + 1
                    font.weight: Font.Bold
                    anchors.verticalCenter: parent.verticalCenter
                }
            }

            Segmented {
                id: nav
                anchors.centerIn: parent
                width: 232
                model: [{ value: 0, label: "Look", icon: "brush", tip: "Glass, colours and panel (Ctrl+1)" },
                        { value: 1, label: "Apps", icon: "apps", tip: "Choose what gets themed (Ctrl+2)" }]
                value: win.pageIndex
                onActivated: (v) => win.pageIndex = v
                Accessible.name: "Page"
            }

            Row {
                anchors.right: parent.right
                anchors.rightMargin: 18
                anchors.verticalCenter: parent.verticalCenter
                spacing: 10
                Repeater {
                    model: [{ icon: "minimize", act: "min", tip: "Minimize" },
                            { icon: win.maximized ? "restore" : "maximize", act: "max", tip: win.maximized ? "Restore" : "Maximize" },
                            { icon: "close", act: "close", tip: "Close" }]
                    delegate: C.AbstractButton {
                        id: wb
                        required property var modelData
                        width: 26; height: 26
                        hoverEnabled: true
                        focusPolicy: Qt.TabFocus
                        Accessible.name: modelData.tip
                        onClicked: modelData.act === "min" ? win.showMinimized()
                                 : modelData.act === "max" ? (win.visibility = win.maximized ? Window.Windowed : Window.Maximized)
                                 : win.close()
                        background: Rectangle {
                            radius: Theme.rS
                            color: wb.down ? Theme.wellHi : wb.hovered ? Theme.alpha(Theme.text, Theme.dark ? 0.16 : 0.12) : Theme.well
                            Behavior on color { ColorAnimation { duration: Theme.fast } }
                            FocusRing { target: wb; radius: Theme.rS + 3 }
                        }
                        contentItem: Item {
                            Icon { anchors.centerIn: parent; name: wb.modelData.icon; size: 16; strokeWidth: 1.8; color: Theme.text }
                        }
                        LgToolTip { shown: wb.hovered; text: wb.modelData.tip; y: parent.height + 8 }
                    }
                }
            }
        }

        // ---------------------------------------------------------- pages
        Item {
            id: pages
            anchors.top: header.bottom
            anchors.bottom: lostBanner.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 24
            anchors.rightMargin: 24
            anchors.topMargin: 4
            anchors.bottomMargin: 16

            LookPage {
                id: look
                anchors.fill: parent
                opacity: win.pageIndex === 0 ? 1 : 0
                visible: opacity > 0
                enabled: win.pageIndex === 0
                transform: Translate { x: win.pageIndex === 0 ? 0 : -16; Behavior on x { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } } }
                Behavior on opacity { NumberAnimation { duration: Theme.normal } }
            }
            AppsPage {
                anchors.fill: parent
                anchors.leftMargin: Math.max(0, (parent.width - 880) / 2)
                anchors.rightMargin: Math.max(0, (parent.width - 880) / 2)
                opacity: win.pageIndex === 1 ? 1 : 0
                visible: opacity > 0
                enabled: win.pageIndex === 1
                transform: Translate { x: win.pageIndex === 1 ? 0 : 16; Behavior on x { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } } }
                Behavior on opacity { NumberAnimation { duration: Theme.normal } }
            }
        }

        // ------------------------------------- another app replaced what Apply wrote
        // (a theme update relinking gtk.css, say). Said once, quietly, with a way back.
        Rectangle {
            id: lostBanner
            objectName: "lostBanner"
            readonly property bool shown: Backend.lostNote !== "" && !Backend.busy
            anchors.bottom: footer.top
            anchors.bottomMargin: shown ? 12 : 0
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.min(parent.width - 48, 760)
            height: shown ? 48 : 0
            visible: height > 0
            clip: true
            radius: Theme.rM
            color: Theme.well
            Behavior on height { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
            Icon {
                x: 14
                anchors.verticalCenter: parent.verticalCenter
                name: "info"
                color: Theme.warn
                size: 18
            }
            Text {
                x: 42
                width: parent.width - x - reapply.width - 28
                anchors.verticalCenter: parent.verticalCenter
                text: Backend.lostNote
                color: Theme.textDim
                font.pixelSize: Theme.fsSmall
                elide: Text.ElideRight
            }
            LgButton {
                id: reapply
                objectName: "reapply"
                anchors.right: parent.right
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                kind: "primary"
                implicitHeight: 32
                leftPadding: 14; rightPadding: 14
                text: "Re-apply"
                iconName: "refresh"
                enabled: !Backend.busy
                tip: "Write the Liquid Glass look again. Nothing else changes."
                onClicked: Backend.apply()
            }
        }

        // ---------------------------------------------------------- footer
        Item {
            id: footer
            anchors.bottom: parent.bottom
            width: parent.width
            height: 72

            Rectangle { x: 0; width: parent.width; height: 1; color: Theme.divider }

            LgButton {
                id: restoreButton
                x: 16
                anchors.verticalCenter: parent.verticalCenter
                kind: "danger"
                text: "Restore original…"
                iconName: "undo"
                leftPadding: 14
                enabled: !Backend.busy && Backend.hasBackup
                tip: Backend.hasBackup ? "Put back every file and setting as it was before Liquid Glass"
                                       : "Nothing to restore: Liquid Glass hasn't changed anything yet"
                onClicked: confirmSheet.open()
            }

            // status
            Row {
                anchors.left: restoreButton.right
                anchors.leftMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                spacing: 10
                Rectangle {
                    visible: !Backend.busy
                    width: 8; height: 8; radius: 4
                    anchors.verticalCenter: parent.verticalCenter
                    color: Backend.dirty ? Theme.accent : Backend.lostNote !== "" ? Theme.warn : Theme.good
                }
                Text {
                    visible: !Backend.busy
                    anchors.verticalCenter: parent.verticalCenter
                    text: Backend.dirty ? "Unapplied changes" : Backend.lostNote !== "" ? "Needs re-apply" : "Up to date"
                    color: Theme.textDim
                    font.pixelSize: 13
                }
                Item {
                    visible: Backend.busy
                    width: 240; height: 32
                    anchors.verticalCenter: parent.verticalCenter
                    Text {
                        text: Backend.busyKind === "apply" ? "Applying " + Backend.progressText + "…"
                            : Backend.busyKind === "revert" ? "Restoring your original look…"
                            : "Working out the changes…"
                        color: Theme.textDim
                        font.pixelSize: 13
                        elide: Text.ElideRight
                        width: parent.width
                    }
                    Rectangle {
                        y: 22; width: parent.width; height: 4; radius: 2
                        color: Theme.wellHi
                        Rectangle {
                            height: parent.height; radius: 2
                            width: Math.max(8, parent.width * Backend.progress)
                            color: Theme.accent
                            Behavior on width { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                        }
                    }
                }
            }

            Row {
                anchors.right: parent.right
                anchors.rightMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8
                LgButton {
                    kind: "secondary"
                    text: "Show changes"
                    iconName: "list"
                    leftPadding: 16
                    enabled: !Backend.busy
                    busy: Backend.busyKind === "plan"
                    tip: "List every file and setting Apply would change"
                    onClicked: Backend.requestPlan()
                }
                LgButton {
                    id: applyButton
                    objectName: "applyButton"
                    // While the Re-apply banner shows, it is the one call to action.
                    kind: lostBanner.shown ? "secondary" : "primary"
                    text: "Apply"
                    iconName: "check"
                    leftPadding: 18
                    rightPadding: 22
                    enabled: !Backend.busy
                    busy: Backend.busyKind === "apply"
                    tip: "Save and apply the theme everywhere (Ctrl+Enter)"
                    onClicked: Backend.apply()
                }
            }
        }

        Toast { id: toast; anchors.horizontalCenter: parent.horizontalCenter; y: footer.y - height - 12 }
    }

    // ------------------------------------------------------------ sheets
    Connections {
        target: Backend
        function onPlanReady(plan) { changesSheet.plan = plan; changesSheet.open() }
        function onApplyFinished(results) { changesSheet.close(); resultsSheet.results = results; resultsSheet.open() }
        function onRevertFinished(problems) {
            if (problems.length === 0) toast.show("Your original look is back", "okCircle", Theme.good)
            else { problemsSheet.problems = problems; problemsSheet.open() }
        }
        function onFailed(message) { toast.show(message, "alert", Theme.bad) }
    }

    ChangesSheet { id: changesSheet }
    ResultsSheet { id: resultsSheet }

    Sheet {
        id: confirmSheet
        title: "Restore your original look?"
        subtitle: "Every file and setting Liquid Glass changed goes back to how it was before your first Apply. Your Liquid Glass settings are kept, so you can apply them again later."
        iconName: "undo"
        iconColor: Theme.bad
        width: Math.min(520, win.width - 64)
        buttons: [
            LgButton { text: "Cancel"; kind: "secondary"; onClicked: confirmSheet.close() },
            LgButton {
                text: "Restore"
                kind: "destructive"
                iconName: "undo"
                onClicked: { confirmSheet.close(); Backend.revert() }
            }
        ]
        Item { width: 1; height: 1 }
    }

    Sheet {
        id: problemsSheet
        property var problems: []
        title: "Some things could not be restored"
        subtitle: "Everything else is back. These need a look:"
        iconName: "alert"
        iconColor: Theme.warn
        buttons: [ LgButton { text: "Close"; kind: "primary"; onClicked: problemsSheet.close() } ]
        Column {
            width: parent.width
            spacing: 6
            Repeater {
                model: problemsSheet.problems
                delegate: Text {
                    required property string modelData
                    width: parent.width
                    text: modelData
                    color: Theme.textDim
                    font.family: Theme.mono
                    font.pixelSize: 12
                    wrapMode: Text.WrapAnywhere
                }
            }
        }
    }

    // ------------------------------------------------------------ resize handles
    component EdgeHandle: MouseArea {
        required property int edges
        visible: !win.maximized
        hoverEnabled: true
        onPressed: win.startSystemResize(edges)
    }
    readonly property int grip: win.margin + 4
    EdgeHandle { edges: Qt.TopEdge; x: win.grip; y: 0; width: win.width - 2 * win.grip; height: win.margin; cursorShape: Qt.SizeVerCursor }
    EdgeHandle { edges: Qt.BottomEdge; x: win.grip; y: win.height - height; width: win.width - 2 * win.grip; height: win.margin; cursorShape: Qt.SizeVerCursor }
    EdgeHandle { edges: Qt.LeftEdge; x: 0; y: win.grip; width: win.margin; height: win.height - 2 * win.grip; cursorShape: Qt.SizeHorCursor }
    EdgeHandle { edges: Qt.RightEdge; x: win.width - width; y: win.grip; width: win.margin; height: win.height - 2 * win.grip; cursorShape: Qt.SizeHorCursor }
    EdgeHandle { edges: Qt.TopEdge | Qt.LeftEdge; x: 0; y: 0; width: win.grip; height: win.grip; cursorShape: Qt.SizeFDiagCursor }
    EdgeHandle { edges: Qt.TopEdge | Qt.RightEdge; x: win.width - width; y: 0; width: win.grip; height: win.grip; cursorShape: Qt.SizeBDiagCursor }
    EdgeHandle { edges: Qt.BottomEdge | Qt.LeftEdge; x: 0; y: win.height - height; width: win.grip; height: win.grip; cursorShape: Qt.SizeBDiagCursor }
    EdgeHandle { edges: Qt.BottomEdge | Qt.RightEdge; x: win.width - width; y: win.height - height; width: win.grip; height: win.grip; cursorShape: Qt.SizeFDiagCursor }
}
