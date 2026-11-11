import QtQuick
import QtQuick.Controls.Basic as C
import QtQuick.Effects
import QtQuick.Window
import FedoraGlass
import FedoraGlass.Core

// Frameless window with its own glass, rounded corners and a soft client-side shadow.
// One sidebar holds every page; each page is built the first time it is opened, and
// the one live preview moves to whichever page shows it.
Window {
    id: win
    // The pages, in sidebar order. `bottom` ones sit at the foot of the sidebar.
    readonly property var pageList: [
        { id: "home", label: qsTr("Home"), icon: "home", sub: qsTr("Your look in one place"), tip: qsTr("Presets, glass, colour and the big switches (Ctrl+1)") },
        { id: "colour", label: qsTr("Colour"), icon: "palette", sub: "", tip: qsTr("Light or dark, accent, tint and corners (Ctrl+2)") },
        { id: "glass", label: qsTr("Glass"), icon: "droplet", sub: "", tip: qsTr("How much glass, its effects, where it shows and speed (Ctrl+3)") },
        { id: "windows", label: qsTr("Panel and windows"), icon: "window", sub: "", tip: qsTr("The panel, header bars, terminal and Qt apps (Ctrl+4)") },
        { id: "motion", label: qsTr("Motion"), icon: "wave", sub: "", tip: qsTr("How windows, menus and the panel move (Ctrl+5)") },
        { id: "pointer", label: qsTr("Pointer and desktop"), icon: "pointer", sub: "", tip: qsTr("Mouse pointer, start on the desktop, the overview (Ctrl+6)") },
        { id: "lock", label: qsTr("Lock and login"), icon: "lock", sub: "", tip: qsTr("Lock screen glass, clock, widgets and the login screen (Ctrl+7)") },
        { id: "apps", label: qsTr("Apps"), icon: "apps", sub: "", tip: qsTr("Choose what gets themed (Ctrl+8)") },
        { id: "advanced", label: qsTr("Advanced"), icon: "sliders", sub: qsTr("For when you want full control"), tip: qsTr("Part by part, fine-tune and start over (Ctrl+9)"), bottom: true },
        { id: "about", label: qsTr("About and restore"), icon: "info", sub: "", tip: qsTr("Version, shortcuts, restore your original look or remove Fedora Glass"), bottom: true }
    ]
    property string page: "home"
    // Pages are built the first time they are shown, then kept.
    property var visited: ({ home: true })
    onPageChanged: {
        if (!visited[page]) {
            const v = Object.assign({}, visited)
            v[page] = true
            visited = v
        }
    }
    readonly property var pageInfo: pageList.find(p => p.id === page) || pageList[0]
    function pageItem(id) {
        for (let i = 0; i < pageRepeater.count; ++i) {
            const l = pageRepeater.itemAt(i)
            if (l && l.pageId === id)
                return l.item
        }
        return null
    }
    // Go to a page and light up one control there (search, tiles, links).
    function goTo(id, name) {
        page = id
        if (name)
            Qt.callLater(() => { const p = pageItem(id); if (p && p.reveal) p.reveal(name) })
    }
    property bool fineTuneOpen: false
    property string startSheet: ""
    onStartSheetChanged: {
        if (startSheet === "restore") confirmSheet.open()
        else if (startSheet === "welcome") welcomeSheet.open()
    }
    function openRestore() { confirmSheet.open() }
    function openAbout() { aboutSheet.open() }

    readonly property bool maximized: visibility === Window.Maximized || visibility === Window.FullScreen
    readonly property int margin: maximized ? 0 : 18
    readonly property int cornerRadius: maximized ? 0 : Theme.rL

    width: 1280 + 2 * margin
    height: 820 + 2 * margin
    minimumWidth: 1000 + 2 * margin
    // 600 fits a 1280x720 screen (1080p at 150 %) under GNOME's top bar with the
    // shadow margin, footer and Apply in view; the pages scroll.
    minimumHeight: 600 + 2 * margin
    color: "transparent"
    flags: Qt.Window | Qt.FramelessWindowHint
    title: "Fedora Glass"

    // Quit goes through close too, so unapplied changes are never lost without a word.
    Shortcut { sequences: [StandardKey.Quit]; onActivated: { leaveSheet.openedByKeyboard = true; win.close() } }
    Shortcut { sequence: "Ctrl+W"; onActivated: { leaveSheet.openedByKeyboard = true; win.close() } }
    // Enter presses the focused button, chip or switch, as Space does (Qt Quick only knows
    // Space). It wakes only for buttons: dropdowns, sliders and text fields keep Enter.
    // Sheets do the same for their own buttons (a sheet blocks the window's shortcuts).
    function pressable(it) {
        return !!it && typeof it.click === "function" && it.autoRepeat !== undefined
               && it.enabled && it.visible
    }
    // Typing in a text field: "?" and Ctrl+Z belong to it then.
    readonly property bool typing: !!activeFocusItem && activeFocusItem.cursorPosition !== undefined
    Shortcut { sequences: ["Return", "Enter"]; enabled: win.pressable(win.activeFocusItem); onActivated: win.activeFocusItem.click() }
    Shortcut { sequence: "F1"; onActivated: { aboutSheet.openedByKeyboard = true; aboutSheet.open() } }
    Shortcut { sequence: "?"; enabled: !win.typing; onActivated: { aboutSheet.openedByKeyboard = true; aboutSheet.open() } }
    // Ctrl+Z is the footer's Undo: back to the look applied last (after a partly failed
    // Apply, the last one that applied fully).
    Shortcut { sequence: "Ctrl+Z"; enabled: (Backend.dirty || Backend.partlyApplied > 0) && !Backend.busy && !win.typing; onActivated: Backend.discardChanges() }
    Shortcut { sequence: "Ctrl+Return"; enabled: !Backend.busy; onActivated: Backend.apply() }
    // Search: Ctrl+F, Ctrl+K or "/" from anywhere.
    Shortcut { sequences: ["Ctrl+F", "Ctrl+K"]; onActivated: sidebar.focusSearch() }
    Shortcut { sequence: "/"; enabled: !win.typing; onActivated: sidebar.focusSearch() }
    // Pages: Ctrl+1 to Ctrl+9 in sidebar order.
    Repeater {
        model: 9
        delegate: Item {
            required property int index
            Shortcut { sequence: "Ctrl+" + (index + 1); onActivated: win.page = win.pageList[index].id }
        }
    }

    // Closing with unapplied changes asks first: Apply and close, Discard, or Cancel.
    property bool closeAnyway: false
    property bool closeAfterApply: false
    // "Apply and close" waits for the login screen step Apply started (it asks for the password).
    property bool closeAfterLogin: false
    // "Close when done" on the wait sheet: close once Restore or the login screen step ends.
    property bool closeWhenIdle: false
    // What still runs that closing would cut off: removing the app, Apply, Restore or the
    // login screen step (pkexec). "" when nothing does.
    readonly property string running: Backend.removing ? "remove"
        : Backend.busyKind === "apply" || Backend.busyKind === "revert" ? Backend.busyKind
        : Backend.loginGlass === "busy" ? "login" : ""
    onRunningChanged: {
        if (running === "" && closeWhenIdle) {
            closeWhenIdle = false
            Qt.callLater(win.close)
        }
    }
    onClosing: (close) => {
        if (win.running !== "" && !win.closeAnyway) {
            close.accepted = false
            waitSheet.what = win.running
            waitSheet.open()
            return
        }
        if (Backend.dirty && !win.closeAnyway) {
            close.accepted = false
            leaveSheet.open()
            return
        }
        // Closing the window with the welcome still open counts as having seen it.
        if (welcomeSheet.opened)
            Backend.dismissWelcome()
    }
    // GNOME Weather may have been installed or a place chosen while the app was in the background.
    onActiveChanged: if (active) Backend.refreshWeather()

    // Tab and Shift+Tab scroll the focused control into view, so the keyboard never
    // lands on a switch hidden below the fold of a scrolling column.
    onActiveFocusItemChanged: {
        const it = activeFocusItem
        if (!it || (it.focusReason !== undefined && it.focusReason !== Qt.TabFocusReason
                    && it.focusReason !== Qt.BacktabFocusReason))
            return
        let f = it.parent
        let card = null       // the card around the control (a Card has padding and content)
        while (f && !(f.contentItem !== undefined && f.contentY !== undefined && f.flickableDirection !== undefined)) {
            if (!card && f.padding !== undefined && f.content !== undefined && f.radius !== undefined)
                card = f
            f = f.parent
        }
        if (!f || f.contentHeight <= f.height)
            return
        const top = it.mapToItem(f.contentItem, 0, 0).y
        const pad = 28
        // The first control in a card brings the card's title along with it.
        const upTo = card && card.nextItemInFocusChain(true) === it
                     ? Math.min(top - pad, card.mapToItem(f.contentItem, 0, 0).y - 12) : top - pad
        if (upTo < f.contentY)
            f.contentY = Math.max(0, upTo)
        else if (top + it.height + pad > f.contentY + f.height)
            f.contentY = Math.min(f.contentHeight - f.height, top + it.height + pad - f.height)
    }

    // Popups (tooltips, dropdowns, colour pickers) capture this for their glass.
    Binding { target: Theme; property: "backdrop"; value: frame }
    Binding { target: Theme; property: "preview"; value: previewPane.preview }

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
                source: Backend.appWallpaper
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

        // ---------------------------------------------------------- sidebar
        Sidebar {
            id: sidebar
            objectName: "sidebar"
            // Above the pages: search results float out over them (they were drawn under the preview).
            z: 1
            width: 232
            height: parent.height
            pages: win.pageList
            current: win.page
            onPicked: (id) => win.page = id
            onFound: (pg, name) => win.goTo(pg, name)
            onHomeClicked: win.page = "home"
            // The top of the sidebar moves the window, like a title bar.
            Item {
                width: parent.width
                height: 64
                z: -1
                DragHandler {
                    target: null
                    grabPermissions: PointerHandler.CanTakeOverFromAnything
                    onActiveChanged: if (active) win.startSystemMove()
                }
                TapHandler {
                    acceptedButtons: Qt.LeftButton
                    onDoubleTapped: win.visibility = win.maximized ? Window.Windowed : Window.Maximized
                }
            }
        }

        Item {
            id: mainArea
            anchors.left: sidebar.right
            anchors.right: parent.right
            height: parent.height

            // ------------------------------------------------------ title bar
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
                    x: 28
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 12
                    Text {
                        objectName: "pageTitle"
                        text: win.pageInfo.label
                        color: Theme.text
                        font.pixelSize: Theme.fsHeading
                        font.weight: Font.Bold
                        anchors.baseline: parent.children[1].baseline
                    }
                    Text {
                        text: win.pageInfo.sub
                        visible: text.length > 0
                        color: Theme.textFaint
                        font.pixelSize: 13
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.verticalCenterOffset: 2
                    }
                }

                Row {
                    anchors.right: parent.right
                    anchors.rightMargin: 18
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 10
                    Repeater {
                        model: [{ icon: "minimize", act: "min", tip: qsTr("Minimize") },
                                { icon: win.maximized ? "restore" : "maximize", act: "max", tip: win.maximized ? qsTr("Restore") : qsTr("Maximize") },
                                { icon: "close", act: "close", tip: qsTr("Close") }]
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

            // ------------------------------------------------------ pages
            Item {
                id: pages
                objectName: "pages"
                anchors.top: header.bottom
                anchors.bottom: oldCopyBanner.top
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: 28
                anchors.rightMargin: 24
                anchors.topMargin: 4
                anchors.bottomMargin: 16

                readonly property var components: ({
                    home: homeC, colour: colourC, glass: glassC, windows: windowsC, motion: motionC,
                    pointer: pointerC, lock: lockC, apps: appsC, advanced: advancedC, about: aboutC })
                Component { id: homeC; HomePage {} }
                Component { id: colourC; ColourPage {} }
                Component { id: glassC; GlassPage {} }
                Component { id: windowsC; WindowsPage {} }
                Component { id: motionC; MotionPage {} }
                Component { id: pointerC; PointerPage {} }
                Component { id: lockC; LockPage {} }
                Component { id: appsC; AppsPage {} }
                Component { id: advancedC; AdvancedPage {} }
                Component { id: aboutC; AboutPage {} }

                Repeater {
                    id: pageRepeater
                    model: win.pageList
                    delegate: Loader {
                        id: loader
                        required property var modelData
                        readonly property string pageId: modelData.id
                        readonly property bool current: win.page === pageId
                        objectName: pageId + "PageLoader"
                        anchors.fill: parent
                        active: win.visited[pageId] === true
                        sourceComponent: pages.components[pageId]
                        visible: opacity > 0
                        enabled: current
                        opacity: current ? 1 : 0
                        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
                        transform: Translate {
                            y: loader.current ? 0 : 10
                            Behavior on y { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
                        }
                    }
                }

                // The one live preview, sitting in the shown page's slot.
                readonly property Item slot: {
                    const p = win.pageItem(win.page)
                    return p && p.previewSlot ? p.previewSlot : null
                }
                Item { id: previewParking; visible: false; width: 640; height: 360 }
                PreviewPane {
                    id: previewPane
                    objectName: "previewPane"
                    parent: pages.slot || previewParking
                    anchors.fill: parent
                }
            }

            // ------------------------------------- an old copy from a source install (install.sh)
            // still starts at login instead of the package, and brings its older look back.
            Rectangle {
                id: oldCopyBanner
                objectName: "oldCopyBanner"
                readonly property bool shown: Backend.hasOldCopy && !Backend.busy
                anchors.bottom: glassBanner.top
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
                    objectName: "oldCopyNote"
                    x: 42
                    width: parent.width - x - cleanUp.width - 28
                    anchors.verticalCenter: parent.verticalCenter
                    text: qsTr("An old hand-installed copy of Fedora Glass still runs at login with its older look.")
                    color: Theme.textDim
                    font.pixelSize: Theme.fsSmall
                    elide: Text.ElideRight
                }
                LgButton {
                    id: cleanUp
                    objectName: "cleanUpOldCopy"
                    anchors.right: parent.right
                    anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    kind: "primary"
                    implicitHeight: 32
                    leftPadding: 14; rightPadding: 14
                    text: qsTr("Clean up old copy")
                    iconName: "check"
                    enabled: !Backend.busy
                    tip: qsTr("Removes only the old copy's launcher, menu entry and background service. Your look and settings stay.")
                    onClicked: Backend.cleanUpOldCopy()
                }
            }
    
            // ------------------------------------- the glass can't run this version yet, and
            // the reason is more than the first restart: an update that waits for the restart,
            // extensions switched off (one click puts them back), a GNOME this version doesn't
            // support yet, or an error (its text can be copied for a bug report).
            Rectangle {
                id: glassBanner
                objectName: "glassBanner"
                // An update that waits for the restart is already said by the footer ("Restart to
                // finish", with its button) whenever that shows.
                readonly property bool shown: Backend.glassProblem !== "" && !Backend.safeMode
                                              && !(Backend.glassProblem === "old" && Backend.restartNeeded)
                anchors.bottom: safeBanner.top
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
                    color: Backend.glassProblem === "old" ? Theme.accentText : Theme.warn
                    size: 18
                }
                Text {
                    objectName: "glassNote"
                    x: 42
                    width: parent.width - x - glassActions.width - 28
                    anchors.verticalCenter: parent.verticalCenter
                    text: Backend.glassProblemNote
                    color: Theme.textDim
                    font.pixelSize: Theme.fsSmall
                    elide: Text.ElideRight
                }
                Row {
                    id: glassActions
                    anchors.right: parent.right
                    anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 8
                    LgButton {
                        objectName: "extensionsOn"
                        readonly property bool wanted: Backend.glassProblem === "off"
                        visible: wanted
                        kind: "primary"
                        implicitHeight: 32
                        leftPadding: 14; rightPadding: 14
                        text: qsTr("Switch on")
                        iconName: "check"
                        tip: qsTr("Switch GNOME's extensions back on. Then press Apply to finish your look.")
                        onClicked: Backend.switchExtensionsOn()
                    }
                    LgButton {
                        objectName: "copyGlassDetails"
                        readonly property bool wanted: Backend.glassProblem === "error" && Backend.glassProblemDetails !== ""
                        visible: wanted
                        kind: "secondary"
                        implicitHeight: 32
                        leftPadding: 14; rightPadding: 14
                        text: qsTr("Copy details")
                        tip: Backend.glassProblemDetails
                        onClicked: Backend.copyGlassDetails()
                    }
                }
            }
    
            // ------------------------------------- safe mode: the glass kept failing and
            // turned itself off. Plain panels until the user turns it back on.
            Rectangle {
                id: safeBanner
                objectName: "safeBanner"
                readonly property bool shown: Backend.safeMode
                anchors.bottom: pauseBanner.top
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
                    objectName: "safeNote"
                    x: 42
                    width: parent.width - x - resumeGlass.width - 28
                    anchors.verticalCenter: parent.verticalCenter
                    text: Backend.safeModeNote
                    color: Theme.textDim
                    font.pixelSize: Theme.fsSmall
                    elide: Text.ElideRight
                }
                LgButton {
                    id: resumeGlass
                    objectName: "resumeGlass"
                    anchors.right: parent.right
                    anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    kind: "primary"
                    implicitHeight: 32
                    leftPadding: 14; rightPadding: 14
                    text: qsTr("Turn glass back on")
                    iconName: "refresh"
                    tip: qsTr("Start the glass again. If it keeps failing, it turns itself off again.")
                    onClicked: Backend.resumeGlass()
                }
            }

            // ------------------------------------- paused from the Glass tile in Quick
            // Settings, for this session. Not a problem: the look is saved, and one click
            // brings the glass back.
            Rectangle {
                id: pauseBanner
                objectName: "pauseBanner"
                readonly property bool shown: Backend.glassPaused
                anchors.bottom: lostBanner.top
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
                    color: Theme.accentText
                    size: 18
                }
                Text {
                    objectName: "pauseNote"
                    x: 42
                    width: parent.width - x - resumePaused.width - 28
                    anchors.verticalCenter: parent.verticalCenter
                    text: qsTr("Glass is paused from Quick Settings until you resume it or log in again.")
                    color: Theme.textDim
                    font.pixelSize: Theme.fsSmall
                    elide: Text.ElideRight
                }
                LgButton {
                    id: resumePaused
                    objectName: "resumePaused"
                    anchors.right: parent.right
                    anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    kind: "primary"
                    implicitHeight: 32
                    leftPadding: 14; rightPadding: 14
                    text: qsTr("Resume")
                    iconName: "refresh"
                    tip: qsTr("Turn the glass back on now, as the Glass tile in Quick Settings does.")
                    onClicked: Backend.resumePausedGlass()
                }
            }
    
            // ------------------------------------- another app replaced what Apply wrote
            // (a theme update relinking gtk.css, say). Said once, quietly, with a way back.
            Rectangle {
                id: lostBanner
                objectName: "lostBanner"
                readonly property bool shown: Backend.lostNote !== "" && !Backend.busy
                anchors.bottom: damageBanner.top
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
                    text: qsTr("Re-apply")
                    iconName: "refresh"
                    enabled: !Backend.busy
                    tip: qsTr("Write the Fedora Glass look again. Nothing else changes.")
                    onClicked: Backend.apply()
                }
            }

            // ------------------------------------- settings.json was damaged and set aside: the
            // app loaded the last good copy (or the defaults). Said until the next save.
            Rectangle {
                id: damageBanner
                objectName: "damageBanner"
                readonly property bool shown: Backend.damageNote !== ""
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
                    objectName: "damageNote"
                    x: 42
                    width: parent.width - x - 20
                    anchors.verticalCenter: parent.verticalCenter
                    text: Backend.damageNote
                    color: Theme.textDim
                    font.pixelSize: Theme.fsSmall
                    elide: Text.ElideRight
                }
            }

            // ------------------------------------------------------ footer
            Item {
                id: footer
                anchors.bottom: parent.bottom
                width: parent.width
                height: 72

                Rectangle { x: 0; width: parent.width; height: 1; color: Theme.divider }

                // status
                Row {
                    id: footerStatus
                    x: 28
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 10
                    // Applied, but the glass only starts after a restart: not "Up to date" yet.
                    // Some parts failed on the last Apply: said until the next Apply or Undo.
                    readonly property string phase: Backend.dirty ? "dirty" : Backend.partlyApplied > 0 ? "partial"
                        : Backend.lostNote !== "" ? "lost"
                        : Backend.loginGlassStale ? "login" : Backend.restartNeeded ? "restart"
                        : Backend.hasBackup ? "done" : "none"
                    Rectangle {
                        objectName: "statusDot"
                        visible: !Backend.busy
                        width: 8; height: 8; radius: 4
                        anchors.verticalCenter: parent.verticalCenter
                        color: footerStatus.phase === "dirty" ? Theme.accent
                             : footerStatus.phase === "done" ? Theme.good
                             : footerStatus.phase === "none" ? Theme.textFaint : Theme.warn
                    }
                    Text {
                        objectName: "statusText"
                        visible: !Backend.busy
                        anchors.verticalCenter: parent.verticalCenter
                        text: ({ dirty: Backend.changeCount === 1 ? qsTr("1 change not applied yet")
                                        : Backend.changeCount > 1 ? qsTr("%1 changes not applied yet").arg(Backend.changeCount)
                                        : qsTr("Unapplied changes"),
                                 partial: Backend.partlyApplied === 1 ? qsTr("1 part didn't change.")
                                          : qsTr("%1 parts didn't change.").arg(Backend.partlyApplied),
                                 lost: qsTr("Needs re-apply"), login: qsTr("Login screen needs Apply"),
                                 restart: qsTr("Restart to finish"), done: qsTr("Up to date"), none: qsTr("Not applied yet") })[footerStatus.phase]
                        color: Theme.textDim
                        font.pixelSize: 14
                    }
                    LgButton {
                        objectName: "restartButton"
                        visible: footerStatus.phase === "restart" && !Backend.busy
                        anchors.verticalCenter: parent.verticalCenter
                        kind: "secondary"
                        implicitHeight: 30
                        leftPadding: 12; rightPadding: 12
                        font.pixelSize: 13
                        text: qsTr("Restart…")
                        tip: qsTr("The glass on your panel and menus starts when your PC restarts. GNOME asks before it restarts.")
                        onClicked: Backend.restartPC()
                    }
                    LgButton {
                        objectName: "partialButton"
                        visible: footerStatus.phase === "partial" && !Backend.busy
                        anchors.verticalCenter: parent.verticalCenter
                        kind: "flat"
                        implicitHeight: 30
                        leftPadding: 10; rightPadding: 12
                        font.pixelSize: 14
                        text: qsTr("See what happened")
                        tip: qsTr("What applied, and what went wrong with the rest")
                        onClicked: { resultsSheet.results = Backend.partialResults; resultsSheet.open() }
                    }
                    LgButton {
                        objectName: "discardButton"
                        visible: (Backend.dirty || footerStatus.phase === "partial") && !Backend.busy
                        anchors.verticalCenter: parent.verticalCenter
                        kind: "flat"
                        implicitHeight: 30
                        leftPadding: 10; rightPadding: 12
                        font.pixelSize: 14
                        text: qsTr("Undo")
                        iconName: "undo"
                        tip: footerStatus.phase === "partial" ? qsTr("Go back to the last look that applied fully (Ctrl+Z)")
                                                               : qsTr("Go back to the look you applied last (Ctrl+Z)")
                        onClicked: Backend.discardChanges()
                    }
                    Item {
                        visible: Backend.busy
                        width: 260; height: 32
                        anchors.verticalCenter: parent.verticalCenter
                        Text {
                            text: Backend.busyKind === "remove" ? qsTr("Removing Fedora Glass…")
                                : Backend.busyKind === "apply" ? qsTr("Applying %1…").arg(Backend.progressText)
                                : Backend.busyKind === "revert" ? qsTr("Restoring your original look…")
                                : Backend.busyKind === "cleanup" ? qsTr("Cleaning up the old copy…")
                                : qsTr("Working out the changes…")
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
                    anchors.rightMargin: 20
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 10
                    LgButton {
                        objectName: "showChanges"
                        kind: "secondary"
                        text: qsTr("See changes")
                        leftPadding: 18; rightPadding: 18
                        enabled: !Backend.busy
                        busy: Backend.busyKind === "plan"
                        tip: qsTr("What you changed and haven't applied yet, and every file and setting Apply writes")
                        onClicked: Backend.requestPlan()
                    }
                    LgButton {
                        id: applyButton
                        objectName: "applyButton"
                        // While the Re-apply banner shows, it is the one call to action.
                        kind: lostBanner.shown ? "secondary" : "primary"
                        text: qsTr("Apply")
                        iconName: "check"
                        leftPadding: 18
                        rightPadding: 22
                        enabled: !Backend.busy
                        busy: Backend.busyKind === "apply"
                        tip: qsTr("Save and apply the look everywhere (Ctrl+Enter)")
                        onClicked: Backend.apply()
                    }
                }
            }

            Toast { id: toast; anchors.horizontalCenter: parent.horizontalCenter; y: footer.y - height - 12 }
        }
    }

    // ------------------------------------------------------------ sheets
    Connections {
        target: Backend
        function onPlanReady(plan) { changesSheet.plan = plan; changesSheet.open() }
        function onApplyFinished(results) {
            changesSheet.close()
            if (win.closeAfterApply) {
                win.closeAfterApply = false
                // "Apply and close": done quietly, unless something needs a look.
                // A restart to finish, or Files still on the old header bars, is shown, not hidden.
                if (!results.some(r => r.status === "failed") && !Backend.dirty
                        && !resultsSheet.restartNeeded(results) && !Backend.glassBlocked
                        && Backend.headerNote !== "pending") {
                    // The login screen step asks for the password: closing now would cut it off.
                    if (Backend.loginGlass === "busy") {
                        win.closeAfterLogin = true
                        toast.show(qsTr("Closing once the login screen has your new look"), "info", Theme.accentText)
                        return
                    }
                    win.closeAnyway = true
                    win.close()
                    return
                }
            }
            resultsSheet.results = results
            resultsSheet.open()
        }
        function onRevertFinished(problems) {
            if (problems.length === 0) toast.show(qsTr("Your original look is back"), "okCircle", Theme.good)
            else { problemsSheet.problems = problems; problemsSheet.open() }
        }
        function onLoginGlassChanged() {
            if (!win.closeAfterLogin || Backend.loginGlass === "busy")
                return
            win.closeAfterLogin = false
            // A closed password dialog was the user's own choice; an error stays in view.
            if (Backend.loginGlassFailed) {
                toast.show(Backend.loginGlassNote, "alert", Theme.bad)
                return
            }
            win.closeAnyway = true
            win.close()
        }
        function onFailed(message) {
            win.closeAfterApply = false
            win.closeAfterLogin = false
            win.closeWhenIdle = false
            toast.show(message, "alert", Theme.bad)
        }
        function onNoticed(message) { toast.show(message, "okCircle", Theme.good) }
    }

    ChangesSheet {
        id: changesSheet
        pages: win.pageList
        onJump: (pg, name) => win.goTo(pg, name)
    }
    WelcomeSheet { id: welcomeSheet }
    ResultsSheet { id: resultsSheet }
    AboutSheet { id: aboutSheet }

    Sheet {
        id: confirmSheet
        title: qsTr("Restore your original look?")
        subtitle: qsTr("Every file and setting Fedora Glass changed goes back to how it was before your first Apply. Your Fedora Glass settings are kept, so you can apply them again later.")
        iconName: "undo"
        iconColor: Theme.bad
        width: Math.min(520, win.width - 64)
        buttons: [
            LgButton { text: qsTr("Cancel"); kind: "secondary"; onClicked: confirmSheet.close() },
            LgButton {
                text: qsTr("Restore")
                kind: "destructive"
                iconName: "undo"
                onClicked: { confirmSheet.close(); Backend.revert() }
            }
        ]
        Item { width: 1; height: 1 }
    }

    Sheet {
        id: leaveSheet
        objectName: "leaveSheet"
        title: qsTr("Apply your changes before closing?")
        subtitle: qsTr("You changed the look but haven't applied it yet. If you close now, those changes are lost and your desktop keeps the look you applied last.")
        iconName: "info"
        width: Math.min(560, win.width - 64)
        buttons: [
            LgButton {
                text: qsTr("Close without applying")
                kind: "danger"
                onClicked: { leaveSheet.close(); win.closeAnyway = true; win.close() }
            },
            LgButton { text: qsTr("Cancel"); kind: "secondary"; onClicked: leaveSheet.close() },
            LgButton {
                text: qsTr("Apply and close")
                kind: "primary"
                iconName: "check"
                enabled: !Backend.busy
                onClicked: { leaveSheet.close(); win.closeAfterApply = true; Backend.apply() }
            }
        ]
        Item { width: 1; height: 1 }
    }

    // Closing while something runs that must not be cut off half way.
    Sheet {
        id: waitSheet
        objectName: "waitSheet"
        property string what: ""
        readonly property bool removal: what === "remove"
        title: ({ remove: qsTr("Fedora Glass is being removed"), apply: qsTr("Your look is being applied"),
                  revert: qsTr("Your original look is coming back"), login: qsTr("The login screen is being updated") })[what] || ""
        subtitle: removal ? qsTr("Closing now could stop it half way. Fedora Glass tells you when it's done.")
                : what === "login" ? qsTr("It waits for your password. Closing now would stop it half way.")
                : qsTr("Closing now would stop it half way. It only takes a moment.")
        iconName: "info"
        width: Math.min(520, win.width - 64)
        buttons: [
            LgButton {
                text: waitSheet.removal ? qsTr("OK") : qsTr("Keep open")
                kind: waitSheet.removal ? "primary" : "secondary"
                onClicked: waitSheet.close()
            },
            LgButton {
                objectName: "closeWhenDone"
                visible: !waitSheet.removal
                text: qsTr("Close when done")
                kind: "primary"
                onClicked: {
                    waitSheet.close()
                    // After Apply, the same rules as "Apply and close": a problem is shown, not hidden.
                    if (waitSheet.what === "apply") win.closeAfterApply = true
                    else win.closeWhenIdle = true
                }
            }
        ]
        Item { width: 1; height: 1 }
    }

    Sheet {
        id: problemsSheet
        property var problems: []
        title: qsTr("Some things could not be restored")
        subtitle: qsTr("Everything else is back. These need a look:")
        iconName: "alert"
        iconColor: Theme.warn
        buttons: [ LgButton { text: qsTr("Close"); kind: "primary"; onClicked: problemsSheet.close() } ]
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
