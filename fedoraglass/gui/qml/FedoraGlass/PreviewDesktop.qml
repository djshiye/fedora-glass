import QtQuick
import QtQuick.Effects
import FedoraGlass.Core

// A faithful miniature of the desktop: the real wallpaper, Nautilus and Ptyxis
// windows, Dash to Panel and an open ArcMenu, drawn with the very Tokens the
// theme writes. Everything is laid out on a virtual 1920x1080 screen and
// scaled by `s`, so the effects render at the preview's own resolution.
// Every setting shows here as it changes: `scene` brings up the part being edited
// (Quick Settings, the calendar or the overview), switches that only act in motion
// play a short demo, and the Apps page's switches give a part GNOME's own look back.
Item {
    id: root

    property var t: ({})
    property string wallpaper: ""
    property var dock: []
    property bool reduceTransparency: false
    // What the preview shows: "desktop" (with ArcMenu), "quicksettings", "calendar" or "overview".
    property string scene: "desktop"
    property bool showMenu: true
    // The Motion card's preview, played along on the Files window and the panel.
    property var motion: null
    property string motionEvent: ""
    property bool motionPlaying: false

    readonly property bool menuOpen: scene === "desktop" && showMenu && hasMenu
    // A start menu to show: ArcMenu or Spawn, or Dash to Panel's own bar (Dino's desktop).
    readonly property bool hasMenu: Backend.hasStartMenu || !topBar
    property real menuProgress: menuOpen ? 1 : 0
    Behavior on menuProgress { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }

    readonly property real s: width / 1920
    function u(n) { return n * root.s }

    // ---- glass recipe, from the tokens ---------------------------------------------
    readonly property real frost: t.frost !== undefined ? t.frost : 0.45
    readonly property bool dark: t.dark !== undefined ? t.dark : true
    readonly property real blurPx: (t.blur_radius || 0) * s
    // The same lens the Shell extension draws (see render/glass.py), scaled to the preview.
    readonly property real refraction: reduceTransparency ? 0 : (t.lens_bend !== undefined ? t.lens_bend : 16 - 11 * frost) * s
    readonly property real bezel: Math.max(4, (t.lens_width !== undefined ? t.lens_width : 20 - 8 * frost) * s)
    // The rainbow split is a px or two on the desktop; at the preview's scale that falls
    // under a pixel, so it is drawn as wide as it looks at full size.
    readonly property real fringe: reduceTransparency ? 0 : (t.dispersion !== undefined ? t.dispersion : 0.35 - 0.28 * frost) * Math.min(4.5, 1.8 / Math.max(0.33, s))
    readonly property real vivid: t.vibrancy !== undefined ? (t.vibrancy - 1) * 0.5 : 0
    readonly property real sheen: t.highlight ? Math.min(1, t.highlight.a * 1.6) : 0
    readonly property real brightness: ((t.blur_brightness || 1) - 1) * 0.35
    readonly property real saturation: reduceTransparency ? 0 : Math.min(1, root.vivid)
    // ---- what the desktop draws (the switches under Glass effects and on the Apps page)
    readonly property var targetStates: Backend.targetStates || ({})
    function themed(id) { return targetStates[id] !== false }
    readonly property bool glassOn: themed("glass") && !reduceTransparency
    readonly property bool gtkThemed: themed("gtk4")
    readonly property bool ptyxisThemed: themed("ptyxis")
    readonly property bool dtpThemed: themed("dash-to-panel")
    readonly property bool shellThemed: themed("shell")
    // Glass quality: "lightest" shows only the wallpaper behind the glass; auto follows
    // what the desktop draws at now. "lighter" looks the same in a still picture.
    readonly property string quality: Backend.glassQuality === "auto" ? (Backend.speedLevel || "full") : Backend.glassQuality
    readonly property bool seeWindows: Backend.glassSeeWindows && quality !== "lightest"
    readonly property bool panelGlass: glassOn && Backend.glassPanel
    readonly property bool menuGlass: glassOn && Backend.glassMenus
    readonly property bool windowsBlur: glassOn && (t.blur_app_windows !== undefined ? t.blur_app_windows : true)
    readonly property bool overviewGlass: glassOn && Backend.glassOverview
    // The same corner ladder as fedoraglass/radius.py (8/12/16/24 at base 18, scaled with the base).
    function lad(base, name) { return Math.round({xs: 8, s: 12, m: 16, l: 24}[name] * base / 18) }
    readonly property real r: t.radius !== undefined ? t.radius : 18
    readonly property real rPanel: part("panel", "radius", r)
    readonly property real rMenu: part("arcmenu", "radius", r)
    readonly property real rWin: gtkThemed ? lad(part("windows", "radius", r), "l") : 12
    readonly property real rXs: lad(r, "xs")
    readonly property real rS: lad(r, "s")
    readonly property color fg: t.fg || "white"
    readonly property color fgDim: t.fg_dim || "white"
    readonly property color fgFaint: t.fg_faint || "white"
    readonly property color folderBlue: dark ? "#62a0ea" : "#438de6"
    readonly property string clock: Qt.formatDate(new Date(), "MMM d") + "  " + Qt.formatTime(new Date(), "h:mm AP")

    function withAlpha(c, a) { return Qt.rgba(c.r, c.g, c.b, a) }

    // The look of one part (panel, arcmenu, windows, ...): its own tint, roundness, frost and
    // lens when the user set them, the global ones otherwise. See Tokens.parts.
    function part(name, key, fallback) {
        const p = t.parts ? t.parts[name] : undefined
        return p && p[key] !== undefined ? p[key] : fallback
    }
    readonly property real bleedGlobal: t.bleed !== undefined ? t.bleed : 0.6
    // Window header bars: their height (47 px is GNOME's) and, when set, their own see-through glass.
    readonly property real headH: u((gtkThemed ? (Backend.headerHeight || 47) : 47) + 3)
    readonly property bool headCustom: Backend.headerOpacity >= 0 && !reduceTransparency && gtkThemed
    function headerColor(c) { return headCustom ? withAlpha(c, Backend.headerOpacity) : c }

    // GNOME's own look, for a part whose switch is off on the Apps page.
    readonly property var adw: dark
        ? { side: "#2e2e32", view: "#1d1d20", popup: "#2e2e32", fg: "#ffffff" }
        : { side: "#ebebed", view: "#ffffff", popup: "#fafafb", fg: "#1f1f21" }
    function filesColor(token) { return gtkThemed ? part("windows", token, "transparent") : (token === "chrome" ? adw.side : adw.view) }

    // Edge reflections per part (the Reflections slider under Parts): the rim's strength
    // scaled by that part's own share of the global reflections.
    function rimFor(name) {
        const h = t.highlight
        if (!h) return "transparent"
        const p = name && t.parts ? t.parts[name] : undefined
        if (!p || p.glare === undefined) return h
        const g = t.glare || 0
        const a = g > 0.001 ? h.a * p.glare / g : p.glare * (dark ? 0.55 : 1.3)
        return withAlpha(h, Math.min(1, a))
    }

    // ---- the pointer light: the light on the glass turns towards the pointer near it
    property bool pointerPinned: false      // screenshots: a pointer held at demoX, demoY
    readonly property bool pointerOn: hover.hovered || demoPointer.running || pointerPinned
    readonly property point pointerAt: hover.hovered ? hover.point.position : Qt.point(demoX, demoY)
    readonly property real pointerLight: glassOn ? Backend.pointerLight : 0
    function pointerK(x, y, w, h) {
        if (!pointerOn || pointerLight <= 0) return 0
        const dx = Math.max(x - pointerAt.x, 0, pointerAt.x - x - w)
        const dy = Math.max(y - pointerAt.y, 0, pointerAt.y - y - h)
        return Math.min(1, pointerLight * 1.6) * Math.max(0, 1 - Math.hypot(dx, dy) / u(220))
    }
    HoverHandler { id: hover }
    // When the setting changes, a pointer glides over the panel and the menu once.
    property real demoX: 0
    property real demoY: 0
    readonly property real pointerSetting: Backend.pointerLight
    onPointerSettingChanged: if (pointerLight > 0 && !hover.hovered) demoPointer.restart()
    SequentialAnimation {
        id: demoPointer
        ScriptAction { script: { root.demoX = root.u(1500); root.demoY = root.height - root.u(30) } }
        ParallelAnimation {
            NumberAnimation { target: root; property: "demoX"; to: root.u(260); duration: 1100; easing.type: Easing.InOutSine }
        }
        ParallelAnimation {
            NumberAnimation { target: root; property: "demoX"; to: root.u(560); duration: 900; easing.type: Easing.InOutSine }
            NumberAnimation { target: root; property: "demoY"; to: root.u(560); duration: 900; easing.type: Easing.InOutSine }
        }
        PauseAnimation { duration: 500 }
    }

    // ---- menus opening: grow out of their button (Menus grow) with a spring (Liquid motion)
    property real pop: 1
    readonly property bool grow: Backend.menuGrow
    readonly property bool springy: Backend.liquidMotion && glassOn
    function replayPop() { Qt.callLater(replayNow) }    // once the new timing is bound
    function replayNow() { popAnim.stop(); pop = 0; popAnim.start() }
    NumberAnimation {
        id: popAnim
        target: root; property: "pop"; from: 0; to: 1
        duration: root.springy ? 520 : 260
        easing.type: root.springy ? Easing.OutBack : Easing.OutCubic
        easing.overshoot: 2.4
    }
    onGrowChanged: replayPop()
    onSpringyChanged: replayPop()
    onSceneChanged: replayPop()
    onShowMenuChanged: if (showMenu) replayPop()
    readonly property real popScale: grow ? 0.25 + 0.75 * pop : 1 - 0.06 * (1 - pop)
    readonly property real popOpacity: Math.max(0, Math.min(1, grow ? pop * 2.5 : pop * 1.4))
    component Pop: Scale {
        property real ox: 0
        property real oy: 0
        origin.x: ox; origin.y: oy
        xScale: root.popScale; yScale: xScale
    }

    // ---- the taskbar: one hover highlight gliding from icon to icon (Hover glide)
    property int hoverIdx: -1
    readonly property bool glideSetting: Backend.hoverGlide
    onGlideSettingChanged: { demoHover.step = 0; demoHover.restart() }
    Timer {
        id: demoHover
        property int step: 0
        interval: 300; repeat: true
        onTriggered: {
            const n = Math.min(root.dock.length, 5)
            root.hoverIdx = step < n ? step : -1
            if (++step > n) stop()
        }
    }
    readonly property var hoverMotion: Backend.motion ? Backend.motion.hover : undefined
    readonly property real hoverLift: hoverMotion && hoverMotion.preset !== "off" ? hoverMotion.intensity : 0
    // The Files window plays the Motion card's open, minimize, close and launch.
    readonly property bool winMotion: motionPlaying && !!motion && ["open", "minimize", "close", "launch"].indexOf(motionEvent) >= 0
    readonly property int filesIcon: Math.max(0, dock.findIndex(d => String(d.id).indexOf("Nautilus") >= 0))

    // ---- the terminal: Ptyxis's own style switch and colours
    // Ptyxis stays dark by itself; "Follow the style" lets it go light with GNOME.
    readonly property bool termDark: ptyxisThemed && Backend.terminalFollowsStyle ? dark : true
    readonly property var tt: termDark === dark ? t : (termDark ? Backend.darkTokens : Backend.lightTokens)
    function tpart(key, fallback) {
        const p = tt.parts ? tt.parts.terminal : undefined
        return p && p[key] !== undefined ? p[key] : fallback
    }
    // GNOME's stock terminal colours, which Ptyxis keeps unless Fedora Glass colours are on.
    readonly property var gnomeTerm: termDark
        ? { bg: "#1e1e1e", fg: "#ffffff", green: "#2ec27e", blue: "#51a1ff", yellow: "#f5c211" }
        : { bg: "#ffffff", fg: "#1f1f21", green: "#26a269", blue: "#1c71d8", yellow: "#c88800" }
    readonly property bool glassTermColors: ptyxisThemed && Backend.terminalColors
    readonly property var termPal: glassTermColors && Backend.terminalPalettes
        ? Backend.terminalPalettes[termDark ? "dark" : "light"] : gnomeTerm

    // Reusable recipes so every glass surface reads its numbers from one place.
    component ShellGlass: GlassSurface {
        id: sg
        property string part: ""
        // Off (the Glass effects switches, the glass app switch, Reduce transparency): the
        // theme's own surface with a plain edge, and nothing blurred or bent behind it.
        property bool glass: true
        blurRadius: !glass ? 0 : part ? root.part(part, "blur", t.blur_radius || 0) * root.s : root.blurPx
        brightness: glass ? root.brightness : 0
        saturation: glass ? root.saturation : 0
        refraction: !glass || root.reduceTransparency ? 0 : (part ? root.part(part, "lens_bend", 0) * root.s : root.refraction)
        bezel: part ? Math.max(4, root.part(part, "lens_width", 0) * root.s) : root.bezel
        fringe: glass ? root.fringe : 0
        bleed: !glass ? 0 : part ? root.part(part, "bleed", root.bleedGlobal) : root.bleedGlobal
        sheen: part && t.glare > 0 ? Math.min(1, root.sheen * root.part(part, "glare", t.glare) / t.glare) : root.sheen
        rim: glass ? root.rimFor(part) : "transparent"
        edge: root.t.edge || "transparent"
        rimWidth: Math.max(0.8, root.u(1.6))
        shadowColor: root.t.shadow || "transparent"
        shadowBlur: root.u(40)
        shadowY: root.u(10)
        // What shows through: the windows too, or only the wallpaper (See windows through
        // glass off, or the lightest glass quality).
        backdrop: root.seeWindows ? desk : wall
        // Only followed while it lights this pane, so a pointer moving about elsewhere costs nothing.
        pointer: pointerK > 0 ? Qt.point(root.pointerAt.x - x, root.pointerAt.y - y) : Qt.point(0, 0)
        pointerK: glass ? root.pointerK(x, y, width, height) : 0
        pointerReach: root.u(180)
        Behavior on pointerK { NumberAnimation { duration: 120 } }
        Rectangle {     // the theme's 1 px edge, drawn when the glass doesn't draw its own
            anchors.fill: parent
            z: 10
            visible: !sg.glass
            radius: sg.radius
            color: "transparent"
            border.width: 1
            border.color: root.t.edge || "transparent"
        }
    }
    // Behind app windows the extension draws plain frost; the window paints its own rim.
    component WindowGlass: ShellGlass {
        part: "windows"
        glass: root.windowsBlur
        blurRadius: root.windowsBlur ? Math.max(root.part("windows", "blur", t.blur_radius || 0) * root.s, root.u(24)) : 0
        refraction: 0
        fringe: 0
        saturation: root.windowsBlur ? root.saturation : 0
        brightness: root.windowsBlur ? root.brightness : 0
        radius: root.rWin
        rimOnTop: true
        shadowBlur: root.u(64)
        shadowY: root.u(18)
    }
    component Label: Text {
        color: root.fg
        font.pixelSize: root.u(15)
        elide: Text.ElideRight
        renderType: Text.QtRendering
    }
    component Sym: Icon {
        size: root.u(17)
        strokeWidth: Math.max(0.9, root.u(1.7))
        color: root.fg
    }
    component Circle: Rectangle {
        property real d: root.u(28)
        width: d
        height: d
        radius: d / 2
    }

    // =====================================================================================
    Item {
        id: desk
        anchors.fill: parent

        Item {
            id: belowTerminal
            anchors.fill: parent

            Item {
                id: wall
                anchors.fill: parent
                Rectangle {     // bundled night-sky gradient when no wallpaper is readable
                    anchors.fill: parent
                    gradient: Gradient {
                        orientation: Gradient.Vertical
                        GradientStop { position: 0.0; color: "#070912" }
                        GradientStop { position: 0.45; color: "#1b1838" }
                        GradientStop { position: 0.62; color: "#3a2f55" }
                        GradientStop { position: 1.0; color: "#05060c" }
                    }
                    Rectangle {
                        width: parent.width * 0.7; height: width * 0.35
                        x: parent.width * 0.15; y: parent.height * 0.38
                        radius: height / 2
                        color: "#6f7fb8"
                        opacity: 0.35
                        layer.enabled: true
                        layer.effect: MultiEffect { blurEnabled: true; blur: 1; blurMax: 64 }
                    }
                }
                Image {
                    anchors.fill: parent
                    source: root.wallpaper
                    fillMode: Image.PreserveAspectCrop
                    sourceSize.width: 2560
                    asynchronous: true
                    smooth: true
                    visible: status === Image.Ready
                }
            }

            // ---------------------------------------------------------------- Nautilus
            WindowGlass {
                id: files
                backdrop: wall
                glass: root.windowsBlur && root.gtkThemed      // GNOME's own Files is solid
                x: root.u(120); y: root.u(64)
                width: root.u(1060); height: root.u(660)
                tint: "transparent"
                rim: root.gtkThemed && glass ? root.rimFor("windows") : "transparent"
                // The Motion card's preview: open, minimize (into its taskbar icon), close.
                readonly property var mf: root.winMotion ? root.motion : null
                opacity: mf ? mf.op : 1
                transform: [
                    Scale {
                        origin.x: files.width / 2; origin.y: files.height / 2
                        xScale: files.mf ? files.mf.sx : 1; yScale: files.mf ? files.mf.sy : 1
                    },
                    Translate {
                        readonly property real m: files.mf && root.motionEvent === "minimize" ? Math.max(0, Math.min(1, files.mf.m)) : 0
                        x: m * ((root.topBar ? panel.x + activities.x + activities.width / 2 : panel.x + root.u(56 + 52 * root.filesIcon + 24)) - files.x - files.width / 2)
                        y: m * (panel.y + panel.height / 2 - files.y - files.height / 2)
                    }
                ]

                readonly property real side: root.u(250)
                readonly property real head: root.headH

                Rectangle {     // sidebar pane
                    width: files.side
                    height: parent.height
                    color: root.filesColor("chrome")
                    topLeftRadius: root.rWin
                    bottomLeftRadius: root.rWin
                }
                Rectangle {     // content header bar
                    x: files.side
                    width: parent.width - files.side
                    height: files.head
                    color: root.headerColor(root.filesColor("view"))
                    topRightRadius: root.rWin
                }
                Rectangle {     // content pane
                    x: files.side; y: files.head
                    width: parent.width - files.side
                    height: parent.height - files.head
                    color: root.filesColor("view")
                    bottomRightRadius: root.rWin
                }
                Rectangle {
                    x: files.side; width: 1; height: parent.height
                    color: root.t.divider || "transparent"
                }

                // sidebar header
                Row {
                    x: root.u(16); height: files.head
                    spacing: root.u(8)
                    Sym { name: "search"; anchors.verticalCenter: parent.verticalCenter }
                }
                Label {
                    x: 0; width: files.side; height: files.head
                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                    text: "Files"; font.weight: Font.Bold
                }
                Sym { name: "menu"; x: files.side - root.u(34); y: (files.head - height) / 2 }

                Column {
                    x: root.u(8); y: files.head + root.u(4)
                    width: files.side - root.u(16)
                    spacing: root.u(2)
                    Repeater {
                        model: [["clock", "Recent"], ["star", "Starred"], ["home", "Home"], ["document", "Documents"],
                                ["download", "Downloads"], ["music", "Music"], ["picture", "Pictures"],
                                ["video", "Videos"], ["trash", "Trash"]]
                        delegate: Rectangle {
                            required property var modelData
                            required property int index
                            width: parent.width; height: root.u(38)
                            radius: root.rXs
                            color: index === 2 ? (root.t.selection || "transparent") : "transparent"
                            Row {
                                x: root.u(12); anchors.verticalCenter: parent.verticalCenter
                                spacing: root.u(12)
                                Sym { name: modelData[0]; anchors.verticalCenter: parent.verticalCenter; color: index === 2 ? root.fg : root.fgDim }
                                Label { text: modelData[1]; anchors.verticalCenter: parent.verticalCenter; font.weight: index === 2 ? Font.DemiBold : Font.Normal }
                            }
                        }
                    }
                }

                // content header bar
                Item {
                    x: files.side; width: parent.width - files.side; height: files.head
                    Row {
                        x: root.u(10); anchors.verticalCenter: parent.verticalCenter
                        spacing: root.u(4)
                        Repeater {
                            model: ["back", "forward"]
                            delegate: Item {
                                required property string modelData
                                width: root.u(34); height: root.u(34)
                                Sym { anchors.centerIn: parent; name: modelData; color: modelData === "back" ? root.fg : root.fgFaint }
                            }
                        }
                    }
                    Rectangle {     // path bar
                        x: root.u(96); anchors.verticalCenter: parent.verticalCenter
                        width: parent.width - root.u(96) - root.u(170); height: root.u(34)
                        radius: Math.min(height / 2, root.rS)
                        color: root.t.card || "transparent"
                        Row {
                            x: root.u(12); anchors.verticalCenter: parent.verticalCenter
                            spacing: root.u(8)
                            Sym { name: "home"; size: root.u(15); anchors.verticalCenter: parent.verticalCenter }
                            Label { text: "Home"; anchors.verticalCenter: parent.verticalCenter; font.weight: Font.DemiBold }
                        }
                    }
                    Row {
                        anchors.right: parent.right; anchors.rightMargin: root.u(12)
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: root.u(14)
                        Sym { name: "grid"; anchors.verticalCenter: parent.verticalCenter }
                        Sym { name: "menu"; anchors.verticalCenter: parent.verticalCenter }
                        Circle {
                            d: root.u(26); anchors.verticalCenter: parent.verticalCenter
                            color: root.t.hover || "transparent"
                            Sym { anchors.centerIn: parent; name: "close"; size: root.u(15) }
                        }
                    }
                }

                // folder grid
                Grid {
                    x: files.side + root.u(28); y: files.head + root.u(24)
                    columns: 6
                    columnSpacing: root.u(16); rowSpacing: root.u(18)
                    Repeater {
                        model: ["Desktop", "Documents", "Downloads", "Music", "Pictures", "Projects",
                                "Videos", "Public", "Templates", "linux-extensions", "Games", "notes.md"]
                        delegate: Column {
                            required property string modelData
                            required property int index
                            width: root.u(118)
                            spacing: root.u(8)
                            Item {
                                width: parent.width; height: root.u(76)
                                // Adwaita-style folder: back flap and front body
                                Rectangle {
                                    visible: index !== 11
                                    x: root.u(22); y: root.u(8); width: root.u(30); height: root.u(14); radius: root.u(4)
                                    color: Qt.darker(root.folderBlue, 1.25)
                                }
                                Rectangle {
                                    visible: index !== 11
                                    x: root.u(22); y: root.u(13); width: root.u(74); height: root.u(56); radius: root.u(6)
                                    color: Qt.darker(root.folderBlue, 1.12)
                                }
                                Rectangle {
                                    visible: index !== 11
                                    x: root.u(22); y: root.u(20); width: root.u(74); height: root.u(49); radius: root.u(6)
                                    gradient: Gradient {
                                        GradientStop { position: 0; color: Qt.lighter(root.folderBlue, 1.12) }
                                        GradientStop { position: 1; color: root.folderBlue }
                                    }
                                }
                                Rectangle {
                                    visible: index === 11
                                    x: root.u(36); y: root.u(6); width: root.u(46); height: root.u(62); radius: root.u(5)
                                    color: root.dark ? "#e8e9ee" : "#ffffff"
                                    border.width: root.dark ? 0 : 1
                                    border.color: "#d0d2da"
                                    Column {
                                        x: root.u(8); y: root.u(12); spacing: root.u(6)
                                        Repeater { model: 5; delegate: Rectangle { width: root.u(30 - (index % 2) * 8); height: root.u(2.5); color: "#9a9dab" } }
                                    }
                                }
                            }
                            Label {
                                width: parent.width
                                horizontalAlignment: Text.AlignHCenter
                                text: modelData
                                font.pixelSize: root.u(14)
                            }
                        }
                    }
                }
            }
        }

        // ---------------------------------------------------------------- Ptyxis
        // Drawn in Ptyxis's own style (dark unless it follows GNOME's), with Fedora Glass's
        // colours when they are on and GNOME's stock colours otherwise.
        WindowGlass {
            id: term
            part: "terminal"
            glass: root.windowsBlur && root.ptyxisThemed
            radius: root.rWin
            backdrop: root.seeWindows ? belowTerminal : wall
            x: root.u(900); y: root.u(330)
            width: root.u(880); height: root.u(540)
            tint: "transparent"
            rim: glass ? root.withAlpha(root.tt.highlight || "transparent", root.rimFor("terminal").a) : "transparent"
            edge: root.tt.edge || "transparent"
            readonly property real head: root.headH
            readonly property color fg: root.tt.fg || "white"
            readonly property color ink: root.termPal.fg || fg

            Rectangle {
                width: parent.width; height: term.head
                color: root.tpart("chrome", "transparent")
                topLeftRadius: root.rWin; topRightRadius: root.rWin
            }
            Rectangle {
                y: term.head; width: parent.width; height: parent.height - term.head
                color: !root.ptyxisThemed ? root.gnomeTerm.bg
                     : root.withAlpha(root.glassTermColors ? root.tpart("view", "transparent") : root.gnomeTerm.bg, root.tt.terminal_opacity || 1)
                bottomLeftRadius: root.rWin; bottomRightRadius: root.rWin
            }
            Rectangle { y: term.head; width: parent.width; height: 1; color: root.tt.divider || "transparent" }

            Item {
                width: parent.width; height: term.head
                Circle {
                    d: root.u(32); x: root.u(10); anchors.verticalCenter: parent.verticalCenter
                    color: "transparent"
                    Sym { anchors.centerIn: parent; name: "plus"; color: term.fg }
                }
                Label {
                    anchors.centerIn: parent
                    text: Backend.userName + "@" + Backend.hostName + ":~"
                    font.weight: Font.Bold
                    color: term.fg
                }
                Row {
                    anchors.right: parent.right; anchors.rightMargin: root.u(12)
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: root.u(14)
                    Sym { name: "search"; anchors.verticalCenter: parent.verticalCenter; color: term.fg }
                    Sym { name: "menu"; anchors.verticalCenter: parent.verticalCenter; color: term.fg }
                    Circle {
                        d: root.u(26); anchors.verticalCenter: parent.verticalCenter
                        color: root.tt.hover || "transparent"
                        Sym { anchors.centerIn: parent; name: "close"; size: root.u(15); color: term.fg }
                    }
                }
            }

            Column {
                id: lines
                x: root.u(20); y: term.head + root.u(18)
                spacing: root.u(5)
                component Line: Text {
                    font.family: Theme.mono
                    font.pixelSize: root.u(16)
                    color: term.ink
                    textFormat: Text.StyledText
                    renderType: Text.QtRendering
                }
                readonly property string green: String(root.termPal.green)
                readonly property string blue: String(root.termPal.blue)
                readonly property string dim: Qt.rgba(term.ink.r, term.ink.g, term.ink.b, 0.55).toString()
                readonly property string yellow: String(root.termPal.yellow)
                readonly property string prompt: "<font color='" + green + "'><b>" + Backend.userName + "@" + Backend.hostName + "</b></font>:<font color='" + blue + "'><b>~</b></font>$ "
                Line { text: lines.prompt + "fedora-glass apply" }
                Line { text: "<font color='" + lines.green + "'>✓</font> GNOME Shell           <font color='" + lines.dim + "'>applied</font>" }
                Line { text: "<font color='" + lines.green + "'>✓</font> GTK 4 and libadwaita  <font color='" + lines.dim + "'>applied</font>" }
                Line { text: "<font color='" + lines.green + "'>✓</font> " + (root.topBar ? "Glass effects  " : "Dash to Panel  ") + "       <font color='" + lines.dim + "'>applied</font>" }
                Line { text: "<font color='" + lines.green + "'>✓</font> Ptyxis                <font color='" + lines.dim + "'>applied</font>" }
                Line { text: "<font color='" + lines.yellow + "'>–</font> Steam                 <font color='" + lines.dim + "'>skipped</font>" }
                Line { text: " " }
                Line { text: lines.prompt }
            }
            Rectangle {     // cursor
                x: root.u(20) + root.u(16) * 0.6 * 14; y: term.head + root.u(18) + 7 * root.u(16 * 1.18 + 5)
                width: root.u(9.5); height: root.u(19)
                color: root.glassTermColors && root.termPal.cursor ? root.termPal.cursor : term.ink
                opacity: 0.85
            }
        }
    }

    // =====================================================================================
    // The Shell layer blurs the desktop and the windows below it.
    // Dash to Panel's own look (its switch off on the Apps page) is a dark bar along the edge.
    // Without Dash to Panel the desktop has GNOME's own top bar: a thin bar along the top
    // edge with Activities, the clock in the middle and the system icons, and its menus
    // open downwards.
    readonly property bool topBar: !Backend.hasDashToPanel
    readonly property bool floating: !topBar && dtpThemed && (t.panel_floating !== undefined ? t.panel_floating : true)
    readonly property real margin: floating ? (t.panel_margin || 0) : 0
    readonly property real panelH: topBar ? 34 : 48
    // Where a menu opened from the bar sits: above a bottom bar, below the top bar.
    function popY(h) { return topBar ? panel.y + panel.height + u(8) : panel.y - h - u(10) }
    function popOY(h) { return topBar ? -u(8) : h + u(10) }

    ShellGlass {
        id: panel
        part: "panel"
        glass: root.panelGlass && (root.dtpThemed || root.topBar)
        z: 5
        x: root.u(root.margin)
        width: root.width - 2 * root.u(root.margin)
        height: root.u(root.panelH)
        y: root.topBar ? 0 : root.height - height - root.u(root.margin)
        radius: root.floating ? Math.min(height / 2, root.u(root.lad(root.rPanel, "l"))) : 0
        tint: root.topBar ? (root.shellThemed ? root.part("panel", "chrome", "transparent") : Qt.rgba(0, 0, 0, 1))
            : root.dtpThemed ? root.part("panel", "chrome", "transparent") : Qt.rgba(0, 0, 0, 0.86)
        shadowColor: root.floating ? (root.t.shadow || "transparent") : "transparent"
        shadowBlur: root.u(30)
        shadowY: root.u(6)
        Behavior on x { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
        Behavior on y { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
        Behavior on width { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }

        Rectangle {     // menu button, pressed while the menu is open
            id: menuButton
            visible: root.hasMenu
            x: root.u(6); anchors.verticalCenter: parent.verticalCenter
            width: root.u(44); height: root.u(root.topBar ? 28 : 40)
            radius: Math.min(height / 2, root.rS)
            color: root.menuOpen ? (root.t.active || "transparent") : "transparent"
            Icon {
                anchors.centerIn: parent
                name: "fedora"
                size: root.u(root.topBar ? 20 : 28)
                strokeWidth: Math.max(0.9, root.u(2))
                color: root.panelFg
            }
            TapHandler {
                onTapped: {
                    if (root.scene !== "desktop") { root.scene = "desktop"; root.showMenu = true }
                    else root.showMenu = !root.showMenu
                }
            }
        }
        Rectangle {     // GNOME's Activities button: the workspace dots, opening the overview
            id: activities
            visible: root.topBar
            x: menuButton.visible ? menuButton.x + menuButton.width + root.u(4) : root.u(8)
            anchors.verticalCenter: parent.verticalCenter
            width: root.u(56); height: root.u(24)
            radius: height / 2
            color: root.scene === "overview" ? (root.t.active || "transparent") : "transparent"
            Row {
                anchors.centerIn: parent
                spacing: root.u(5)
                Rectangle { width: root.u(22); height: root.u(8); radius: height / 2; color: root.panelFg; anchors.verticalCenter: parent.verticalCenter }
                Rectangle { width: root.u(8); height: width; radius: width / 2; color: root.panelFg; opacity: 0.6; anchors.verticalCenter: parent.verticalCenter }
            }
            TapHandler { onTapped: root.scene = root.scene === "overview" ? "desktop" : "overview" }
        }
        // Hover glide: one highlight that glides from icon to icon. Off, Dash to Panel
        // lights each icon by itself.
        Rectangle {
            id: glide
            readonly property bool on: Backend.hoverGlide && root.hoverIdx >= 0
            x: menuButton.x + menuButton.width + root.u(6) + Math.max(0, root.hoverIdx) * root.u(52) + root.u(2)
            anchors.verticalCenter: parent.verticalCenter
            width: root.u(44); height: root.u(40)
            radius: Math.min(height / 2, root.rXs)
            color: root.t.hover || "transparent"
            visible: Backend.hoverGlide && !root.topBar
            opacity: on ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 160 } }
            Behavior on x {
                enabled: glide.opacity > 0.05
                NumberAnimation { duration: root.springy ? 380 : 220; easing.type: root.springy ? Easing.OutBack : Easing.OutCubic; easing.overshoot: 1.4 }
            }
        }
        Row {
            visible: !root.topBar      // GNOME's top bar has no app icons
            x: menuButton.x + menuButton.width + root.u(6)
            height: parent.height
            spacing: root.u(4)
            Repeater {
                model: root.dock
                delegate: Item {
                    id: dockItem
                    required property var modelData
                    required property int index
                    readonly property bool focused: index === root.dock.findIndex(d => d.running)
                    readonly property bool hovered: root.hoverIdx === index
                    // The Motion card: an app starting (its icon hops) and the panel hover.
                    readonly property var mf: root.motionPlaying && root.motion
                        && ((root.motionEvent === "launch" && index === root.filesIcon) || (root.motionEvent === "hover" && index === 0)) ? root.motion : null
                    width: root.u(48); height: parent.height
                    HoverHandler {
                        onHoveredChanged: {
                            if (hovered) root.hoverIdx = dockItem.index
                            else if (root.hoverIdx === dockItem.index) root.hoverIdx = -1
                        }
                    }
                    // Like Dash to Panel: a faint wash behind the focused app only.
                    Rectangle {
                        anchors.centerIn: parent
                        width: root.u(44); height: root.u(40)
                        radius: Math.min(height / 2, root.rXs)
                        color: root.dark ? "#ffffff" : "#000000"
                        opacity: focused ? 0.08 : 0
                    }
                    Rectangle {     // Dash to Panel's own hover highlight, when Hover glide is off
                        anchors.centerIn: parent
                        width: root.u(44); height: root.u(40)
                        radius: Math.min(height / 2, root.rXs)
                        color: root.t.hover || "transparent"
                        visible: !Backend.hoverGlide && dockItem.hovered
                    }
                    AppIcon {
                        anchors.centerIn: parent
                        anchors.verticalCenterOffset: -(dockItem.mf ? root.u(2 * dockItem.mf.iconLift) : (dockItem.hovered ? root.u(5 * root.hoverLift) : 0))
                        size: root.u(30)
                        scale: dockItem.mf ? dockItem.mf.iconS : (dockItem.hovered ? 1 + 0.16 * root.hoverLift : 1)
                        Behavior on scale { enabled: !dockItem.mf; NumberAnimation { duration: 260; easing.type: Easing.OutBack } }
                        Behavior on anchors.verticalCenterOffset { enabled: !dockItem.mf; NumberAnimation { duration: 260; easing.type: Easing.OutBack } }
                        source: modelData.icon
                        label: modelData.name
                        tileColor: root.t.accent || "#3584e4"
                    }
                    // A small dot under each running app, as on the desktop.
                    Rectangle {
                        visible: modelData.running
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: parent.height - root.u(5)
                        width: root.u(3); height: width; radius: width / 2
                        color: root.panelFg
                        opacity: focused ? 0.9 : 0.55
                    }
                }
            }
        }
        Row {
            id: trayRow
            anchors.right: parent.right; anchors.rightMargin: root.u(root.floating ? 18 : 14)
            anchors.verticalCenter: parent.verticalCenter
            spacing: root.u(18)
            Rectangle {     // the clock opens the calendar
                id: clockButton
                width: clockLabel.width + root.u(20); height: root.u(root.topBar ? 26 : 36)
                anchors.verticalCenter: parent.verticalCenter
                radius: Math.min(height / 2, root.rS)
                color: root.scene === "calendar" ? (root.t.active || "transparent") : "transparent"
                Label { id: clockLabel; anchors.centerIn: parent; text: root.clock; font.weight: Font.DemiBold; color: root.panelFg }
                TapHandler { onTapped: root.scene = root.scene === "calendar" ? "desktop" : "calendar" }
            }
            Item {          // GNOME's top bar: the room that puts the clock in the middle
                visible: root.topBar
                height: 1
                width: Math.max(0, panel.width / 2 - trayRow.anchors.rightMargin + clockButton.width / 2
                                   - clockButton.width - qsButton.width - 2 * trayRow.spacing)
            }
            Rectangle {     // the system icons open Quick Settings
                id: qsButton
                width: qsIcons.width + root.u(20); height: root.u(root.topBar ? 26 : 36)
                anchors.verticalCenter: parent.verticalCenter
                radius: Math.min(height / 2, root.rS)
                color: root.scene === "quicksettings" ? (root.t.active || "transparent") : "transparent"
                Row {
                    id: qsIcons
                    anchors.centerIn: parent
                    spacing: root.u(10)
                    Sym { name: "wifi"; color: root.panelFg }
                    Sym { name: "volume"; color: root.panelFg }
                    Sym { name: "power"; color: root.panelFg }
                }
                TapHandler { onTapped: root.scene = root.scene === "quicksettings" ? "desktop" : "quicksettings" }
            }
        }
    }
    readonly property color panelFg: dtpThemed || (topBar && shellThemed) ? fg : "white"

    // ---------------------------------------------------------------- Dash to Dock
    // Dash to Dock or Ubuntu Dock on GNOME's own desktop: a dock along the bottom edge,
    // with glass behind it as on the desktop. It stays on screen in the overview, where
    // it takes the place of GNOME's dash.
    readonly property bool showDock: topBar && Backend.hasDock
    ShellGlass {
        id: deskDock
        part: "panel"
        visible: root.showDock
        glass: root.panelGlass
        z: 5
        anchors.horizontalCenter: parent.horizontalCenter
        y: root.height - height - root.u(10)
        width: deskDockRow.width + root.u(20); height: root.u(64)
        radius: Math.min(height / 2, root.u(root.lad(root.rPanel, "l")))
        tint: root.shellThemed ? root.part("panel", "chrome", "transparent") : Qt.rgba(0, 0, 0, 0.7)
        shadowColor: root.t.shadow || "transparent"
        shadowBlur: root.u(30)
        shadowY: root.u(6)
        Row {
            id: deskDockRow
            anchors.centerIn: parent
            spacing: root.u(6)
            Repeater {
                model: root.dock
                delegate: Item {
                    required property var modelData
                    width: root.u(52); height: root.u(64)
                    AppIcon {
                        anchors.centerIn: parent
                        anchors.verticalCenterOffset: -root.u(2)
                        size: root.u(42)
                        source: modelData.icon
                        label: modelData.name
                        tileColor: root.t.accent || "#3584e4"
                    }
                    Rectangle {     // a dot under each running app
                        visible: modelData.running
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: parent.height - root.u(7)
                        width: root.u(4); height: width; radius: width / 2
                        color: root.panelFg
                        opacity: 0.8
                    }
                }
            }
        }
    }


    // ---------------------------------------------------------------- ArcMenu
    ShellGlass {
        id: menu
        part: "arcmenu"
        glass: root.menuGlass
        z: 4
        visible: root.menuProgress > 0.01
        opacity: root.menuProgress * root.popOpacity
        width: root.u(640); height: root.u(600)
        x: root.u(Math.max(8, root.margin))
        y: root.popY(height) + (root.topBar ? -1 : 1) * (root.u(16) * (1 - root.menuProgress) + (root.grow ? 0 : root.u(14) * (1 - Math.min(1, root.pop))))
        radius: root.lad(root.rMenu, "m")
        tint: root.shellThemed ? root.part("arcmenu", "popover", "transparent") : root.adw.popup
        transform: Pop { ox: panel.x + menuButton.x + menuButton.width / 2 - menu.x; oy: root.popOY(menu.height) }
        shadowBlur: root.u(50)
        shadowY: root.u(14)

        readonly property real pad: root.u(18)
        readonly property real split: root.u(400)

        Rectangle {     // search entry
            x: menu.pad; y: menu.pad
            width: menu.width - 2 * menu.pad; height: root.u(40)
            radius: height / 2
            // Mostly opaque, as in the Shell, so the window behind never shows through.
            readonly property color pop: root.shellThemed ? root.part("arcmenu", "popover", "transparent") : root.adw.popup
            color: Qt.rgba(pop.r, pop.g, pop.b, 0.62)
            border.width: Math.max(1, root.u(1))
            border.color: root.t.edge || "transparent"
            Row {
                x: root.u(14); anchors.verticalCenter: parent.verticalCenter
                spacing: root.u(10)
                Sym { name: "search"; color: root.fgDim; anchors.verticalCenter: parent.verticalCenter }
                Label { text: "Search…"; color: root.fgFaint; anchors.verticalCenter: parent.verticalCenter }
            }
        }

        Label {
            x: menu.pad + root.u(8); y: root.u(76)
            text: "Pinned"; color: root.fgDim; font.weight: Font.DemiBold; font.pixelSize: root.u(14)
        }
        Column {
            x: menu.pad; y: root.u(104)
            width: menu.split - menu.pad - root.u(8)
            spacing: root.u(2)
            Repeater {
                model: [
                    { n: "Files", i: "org.gnome.Nautilus" }, { n: "Ptyxis", i: "org.gnome.Ptyxis" },
                    { n: "Helium", i: "helium" }, { n: "Text Editor", i: "org.gnome.TextEditor" },
                    { n: "Calculator", i: "org.gnome.Calculator" }, { n: "Lutris", i: "net.lutris.Lutris" },
                    { n: "Settings", i: "org.gnome.Settings" }, { n: "Extensions", i: "org.gnome.Extensions" }
                ]
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    width: parent.width; height: root.u(50)
                    radius: root.rXs
                    color: index === 1 ? (root.t.hover || "transparent") : "transparent"
                    Row {
                        x: root.u(10); anchors.verticalCenter: parent.verticalCenter
                        spacing: root.u(14)
                        AppIcon {
                            anchors.verticalCenter: parent.verticalCenter
                            size: root.u(32)
                            source: Backend.iconUrl(modelData.i)
                            label: modelData.n
                            tileColor: root.t.accent || "#3584e4"
                        }
                        Label { text: modelData.n; anchors.verticalCenter: parent.verticalCenter }
                    }
                }
            }
        }

        Rectangle {
            x: menu.split; y: root.u(76); width: 1; height: menu.height - root.u(76) - menu.pad
            color: root.t.divider || "transparent"
        }

        Column {
            x: menu.split + root.u(14); y: root.u(76)
            width: menu.width - menu.split - root.u(14) - menu.pad
            spacing: root.u(2)
            Row {
                height: root.u(56); spacing: root.u(12)
                Circle {
                    d: root.u(36); anchors.verticalCenter: parent.verticalCenter
                    color: root.t.accent || "#3584e4"
                    Sym { anchors.centerIn: parent; name: "user"; color: root.t.accent_fg || "white"; size: root.u(20) }
                }
                Label { text: Backend.userName; anchors.verticalCenter: parent.verticalCenter; font.weight: Font.DemiBold }
            }
            Repeater {
                model: [["home", "Home"], ["document", "Documents"], ["download", "Downloads"],
                        ["picture", "Pictures"], ["gear", "Settings"], ["apps", "Software"]]
                delegate: Item {
                    required property var modelData
                    width: parent.width; height: root.u(42)
                    Row {
                        x: root.u(8); anchors.verticalCenter: parent.verticalCenter
                        spacing: root.u(12)
                        Sym { name: modelData[0]; color: root.fgDim; anchors.verticalCenter: parent.verticalCenter }
                        Label { text: modelData[1]; anchors.verticalCenter: parent.verticalCenter }
                    }
                }
            }
        }
        Row {
            anchors.right: parent.right; anchors.rightMargin: menu.pad
            anchors.bottom: parent.bottom; anchors.bottomMargin: menu.pad
            spacing: root.u(10)
            Repeater {
                model: ["lock", "refresh", "power"]
                delegate: Circle {
                    required property string modelData
                    d: root.u(40)
                    color: root.t.card || "transparent"
                    Sym { anchors.centerIn: parent; name: modelData }
                }
            }
        }
    }

    // ---------------------------------------------------------------- Quick Settings
    // The Quick settings part: the system menu, opened from the icons at the panel's end.
    ShellGlass {
        id: qs
        part: "quicksettings"
        glass: root.menuGlass
        z: 4
        readonly property bool shown: root.scene === "quicksettings"
        visible: shown
        opacity: root.popOpacity
        width: root.u(440); height: root.u(470)
        x: Math.min(root.width - width - root.u(Math.max(8, root.margin)), panel.x + qsButton.parent.x + qsButton.x + qsButton.width - width)
        y: root.popY(height) + (root.topBar ? -1 : 1) * (root.grow ? 0 : root.u(14) * (1 - Math.min(1, root.pop)))
        radius: root.lad(root.part("quicksettings", "radius", root.r), "l")
        tint: root.shellThemed ? root.part("quicksettings", "popover", "transparent") : root.adw.popup
        shadowBlur: root.u(50)
        shadowY: root.u(14)
        transform: Pop { ox: panel.x + qsButton.parent.x + qsButton.x + qsButton.width / 2 - qs.x; oy: root.popOY(qs.height) }

        readonly property real pad: root.u(22)
        readonly property color fgQ: root.shellThemed ? root.fg : root.adw.fg
        readonly property color pill: root.shellThemed ? (root.t.card || "transparent") : root.withAlpha(root.adw.fg, 0.1)

        Row {       // battery, screenshot, settings, lock, power
            x: qs.pad; y: qs.pad
            width: qs.width - 2 * qs.pad
            spacing: root.u(10)
            Rectangle {
                width: root.u(92); height: root.u(40); radius: height / 2
                color: qs.pill
                Row {
                    anchors.centerIn: parent; spacing: root.u(6)
                    Sym { name: "battery"; color: qs.fgQ; anchors.verticalCenter: parent.verticalCenter }
                    Label { text: "84 %"; color: qs.fgQ; font.pixelSize: root.u(14); anchors.verticalCenter: parent.verticalCenter }
                }
            }
            Item { width: parent.width - root.u(92) - 4 * root.u(40) - 4 * root.u(10); height: 1 }
            Repeater {
                model: ["picture", "gear", "lock", "power"]
                delegate: Circle {
                    required property string modelData
                    d: root.u(40)
                    color: qs.pill
                    Sym { anchors.centerIn: parent; name: modelData; color: qs.fgQ }
                }
            }
        }
        Column {    // volume and brightness sliders
            x: qs.pad; y: qs.pad + root.u(64)
            width: qs.width - 2 * qs.pad
            spacing: root.u(18)
            Repeater {
                model: [["volume", 0.62], ["sun", 0.8]]
                delegate: Row {
                    required property var modelData
                    spacing: root.u(14)
                    Sym { name: modelData[0]; color: qs.fgQ; anchors.verticalCenter: parent.verticalCenter }
                    Rectangle {
                        width: qs.width - 2 * qs.pad - root.u(32); height: root.u(6); radius: height / 2
                        anchors.verticalCenter: parent.verticalCenter
                        color: root.withAlpha(qs.fgQ, 0.18)
                        Rectangle { width: parent.width * modelData[1]; height: parent.height; radius: parent.radius; color: root.t.accent || "#3584e4" }
                        Circle {
                            d: root.u(20); x: parent.width * modelData[1] - d / 2; anchors.verticalCenter: parent.verticalCenter
                            color: "white"
                        }
                    }
                }
            }
        }
        Grid {      // the toggle pills
            x: qs.pad; y: qs.pad + root.u(150)
            columns: 2
            columnSpacing: root.u(12); rowSpacing: root.u(12)
            Repeater {
                model: [["wifi", "Wi-Fi", "Home", true], ["bluetooth", "Bluetooth", "Off", false],
                        ["sparkle", "Power Mode", "Balanced", false], ["moon", "Night Light", "", true],
                        ["auto", "Dark Style", "", root.dark], ["bell", "Do Not Disturb", "", false]]
                delegate: Rectangle {
                    required property var modelData
                    width: (qs.width - 2 * qs.pad - root.u(12)) / 2; height: root.u(58)
                    radius: height / 2
                    color: modelData[3] ? (root.t.accent || "#3584e4") : qs.pill
                    readonly property color ink: modelData[3] ? (root.t.accent_fg || "white") : qs.fgQ
                    Row {
                        x: root.u(18); anchors.verticalCenter: parent.verticalCenter
                        spacing: root.u(12)
                        Sym { name: modelData[0]; color: parent.parent.ink; anchors.verticalCenter: parent.verticalCenter }
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            Label { text: modelData[1]; color: parent.parent.parent.ink; font.weight: Font.DemiBold; font.pixelSize: root.u(15) }
                            Label { text: modelData[2]; visible: text !== ""; color: parent.parent.parent.ink; opacity: 0.8; font.pixelSize: root.u(13) }
                        }
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------------- Calendar
    // The Calendar part (notifications share it), opened from the clock.
    ShellGlass {
        id: cal
        part: "calendar"
        glass: root.menuGlass
        z: 4
        readonly property bool shown: root.scene === "calendar"
        visible: shown
        opacity: root.popOpacity
        width: root.u(760); height: root.u(470)
        x: Math.min(root.width - width - root.u(Math.max(8, root.margin)), panel.x + clockButton.parent.x + clockButton.x + clockButton.width / 2 - width / 2)
        y: root.popY(height) + (root.topBar ? -1 : 1) * (root.grow ? 0 : root.u(14) * (1 - Math.min(1, root.pop)))
        radius: root.lad(root.part("calendar", "radius", root.r), "l")
        tint: root.shellThemed ? root.part("calendar", "popover", "transparent") : root.adw.popup
        shadowBlur: root.u(50)
        shadowY: root.u(14)
        transform: Pop { ox: panel.x + clockButton.parent.x + clockButton.x + clockButton.width / 2 - cal.x; oy: root.popOY(cal.height) }

        readonly property real pad: root.u(22)
        readonly property real split: root.u(400)
        readonly property color fgC: root.shellThemed ? root.fg : root.adw.fg
        readonly property color card: root.shellThemed ? (root.t.card || "transparent") : root.withAlpha(root.adw.fg, 0.08)
        readonly property var today: new Date()

        Column {    // notifications
            x: cal.pad; y: cal.pad
            width: cal.split - cal.pad - root.u(12)
            spacing: root.u(10)
            Repeater {
                model: [["Files", "org.gnome.Nautilus", "Copied 12 photos to Pictures", "2 min"],
                        ["Software", "org.gnome.Software", "3 updates are ready to install", "1 h"]]
                delegate: Rectangle {
                    required property var modelData
                    width: parent.width; height: root.u(86)
                    radius: root.rS
                    color: cal.card
                    Row {
                        x: root.u(14); y: root.u(14)
                        spacing: root.u(12)
                        AppIcon {
                            size: root.u(32)
                            source: Backend.iconUrl(modelData[1])
                            label: modelData[0]
                            tileColor: root.t.accent || "#3584e4"
                        }
                        Column {
                            spacing: root.u(4)
                            Label { text: modelData[0] + "  ·  " + modelData[3]; color: cal.fgC; opacity: 0.7; font.pixelSize: root.u(13) }
                            Label { text: modelData[2]; color: cal.fgC; font.weight: Font.DemiBold; width: cal.split - root.u(120) }
                        }
                    }
                }
            }
        }
        Row {
            x: cal.pad; anchors.bottom: parent.bottom; anchors.bottomMargin: cal.pad
            spacing: root.u(10)
            Rectangle {
                width: root.u(150); height: root.u(36); radius: height / 2
                color: cal.card
                Label { anchors.centerIn: parent; text: "Do Not Disturb"; color: cal.fgC; font.pixelSize: root.u(13) }
            }
        }
        Rectangle {
            x: cal.split; y: cal.pad; width: 1; height: cal.height - 2 * cal.pad
            color: root.t.divider || "transparent"
        }
        Column {    // the month
            x: cal.split + root.u(20); y: cal.pad
            width: cal.width - cal.split - root.u(20) - cal.pad
            spacing: root.u(10)
            Label { text: Qt.formatDate(cal.today, "dddd"); color: cal.fgC; opacity: 0.7; font.pixelSize: root.u(14) }
            Label { text: Qt.formatDate(cal.today, "MMMM d yyyy"); color: cal.fgC; font.weight: Font.Bold; font.pixelSize: root.u(20) }
            Grid {
                columns: 7
                columnSpacing: 0; rowSpacing: root.u(4)
                readonly property real cell: (cal.width - cal.split - root.u(20) - cal.pad) / 7
                readonly property int lead: new Date(cal.today.getFullYear(), cal.today.getMonth(), 1).getDay()
                Repeater {
                    model: 42
                    delegate: Item {
                        required property int index
                        readonly property int day: index - parent.lead + 1
                        readonly property bool isToday: day === cal.today.getDate()
                        width: parent.cell; height: root.u(36)
                        Circle {
                            anchors.centerIn: parent; d: root.u(32)
                            visible: parent.isToday
                            color: root.t.accent || "#3584e4"
                        }
                        Label {
                            anchors.centerIn: parent
                            visible: parent.day >= 1 && parent.day <= 31
                            text: parent.day
                            font.pixelSize: root.u(14)
                            color: parent.isToday ? (root.t.accent_fg || "white") : cal.fgC
                            font.weight: parent.isToday ? Font.Bold : Font.Normal
                        }
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------------- Overview
    // Activities: the wallpaper blurred behind it (Glass on the overview), the dash in the
    // Overview part's look, and a note when Activities is switched off altogether.
    Item {
        id: overview
        anchors.fill: parent
        z: 3
        visible: opacity > 0.01
        opacity: root.scene === "overview" ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }

        Rectangle {     // GNOME's own overview background
            anchors.fill: parent
            color: root.dark ? "#1e1e21" : "#d6d7dc"
        }
        ShaderEffectSource {
            id: ovWall
            sourceItem: wall
            visible: false
            live: true
        }
        MultiEffect {   // Fedora Glass: the blurred wallpaper
            anchors.fill: parent
            visible: root.overviewGlass
            source: ovWall
            autoPaddingEnabled: false
            blurEnabled: true
            blurMax: 64
            blur: Math.min(1, Math.max(30, root.part("overview", "blur", 30)) * root.s / 64 * 2.2)
            brightness: root.dark ? -0.16 : -0.06
            saturation: root.saturation
        }
        Rectangle {     // search
            anchors.horizontalCenter: parent.horizontalCenter
            y: root.u(40)
            width: root.u(420); height: root.u(44); radius: height / 2
            color: root.withAlpha(root.t.popover || "#303030", 0.7)
            border.width: 1; border.color: root.t.edge || "transparent"
            Row {
                x: root.u(16); anchors.verticalCenter: parent.verticalCenter
                spacing: root.u(10)
                Sym { name: "search"; color: root.fgDim }
                Label { text: "Type to search"; color: root.fgFaint }
            }
        }
        Item {          // the workspace, with its windows
            id: ws
            x: root.u(260); y: root.u(120)
            width: root.width - 2 * root.u(260); height: width * 9 / 16
            ShaderEffectSource {
                anchors.fill: parent
                sourceItem: wall
                live: true
                layer.enabled: true
                layer.effect: MultiEffect {
                    maskEnabled: true
                    maskSource: wsMask
                    maskThresholdMin: 0.5
                    maskSpreadAtMin: 1.0
                }
            }
            Rectangle { id: wsMask; anchors.fill: parent; radius: root.u(18); visible: false; layer.enabled: true }
            Rectangle {
                anchors.fill: parent; radius: root.u(18); color: "transparent"
                border.width: 1; border.color: root.withAlpha(root.fg, 0.15)
            }
            Repeater {      // Files and Ptyxis, small: live copies of the windows above
                model: [[files, "Files"], [term, "Terminal"]]
                delegate: Item {
                    required property var modelData
                    readonly property real k: ws.width / root.width
                    x: modelData[0].x * k; y: modelData[0].y * k
                    width: modelData[0].width * k; height: modelData[0].height * k
                    ShaderEffectSource {
                        anchors.fill: parent
                        sourceItem: overview.visible ? parent.modelData[0] : null
                        live: true
                        smooth: true
                    }
                    Label {
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: parent.height + root.u(8)
                        text: parent.modelData[1]
                        font.pixelSize: root.u(14)
                        color: "white"
                    }
                }
            }
        }
        ShellGlass {    // the dash
            id: dash
            part: "overview"
            visible: !root.showDock      // Dash to Dock takes the dash's place
            glass: root.panelGlass && root.overviewGlass   // real glass behind GNOME's dash, as on the desktop
            anchors.horizontalCenter: parent.horizontalCenter
            y: root.topBar ? root.height - height - root.u(16) : panel.y - height - root.u(28)
            width: dashRow.width + root.u(24); height: root.u(72)
            radius: root.lad(root.part("overview", "radius", root.r), "l")
            tint: root.shellThemed ? root.part("overview", "chrome", "transparent") : root.withAlpha(root.adw.popup, 0.9)
            Row {
                id: dashRow
                anchors.centerIn: parent
                spacing: root.u(8)
                Repeater {
                    model: root.dock.slice(0, 7)
                    delegate: AppIcon {
                        required property var modelData
                        size: root.u(48)
                        source: modelData.icon
                        label: modelData.name
                        tileColor: root.t.accent || "#3584e4"
                    }
                }
            }
        }
        Rectangle {     // Activities switched off
            visible: Backend.overviewOff
            anchors.centerIn: ws
            width: offRow.width + root.u(40); height: root.u(64)
            radius: height / 2
            color: root.withAlpha(root.dark ? "#16171c" : "#ffffff", 0.88)
            border.width: 1; border.color: root.t.edge || "transparent"
            Row {
                id: offRow
                anchors.centerIn: parent
                spacing: root.u(12)
                Sym { name: "info"; size: root.u(24); color: root.t.accent_text || root.fg; anchors.verticalCenter: parent.verticalCenter }
                Label {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Activities is off: no hot corner, Super key or swipe opens this"
                    font.pixelSize: root.u(20); font.weight: Font.DemiBold
                    elide: Text.ElideNone
                }
            }
        }
    }

    // The pointer of the pointer-light demo: the style picked on the Look page, if any.
    readonly property string cursorStyle: Backend.cursorTheme
    onCursorStyleChanged: if (!hover.hovered) demoPointer.restart()
    // Over the preview, the app's own pointer takes the picked style before Apply.
    HoverHandler {
        onHoveredChanged: Cursors.tryOn(hovered && root.cursorStyle !== "keep" ? root.cursorStyle : "")
    }
    Image {
        objectName: "previewCursor"
        z: 20
        visible: demoPointer.running && root.cursorStyle !== "keep"
        x: root.demoX - width * 0.2; y: root.demoY - height * 0.07
        width: root.u(36); height: width
        sourceSize: Qt.size(64, 64)
        source: root.cursorStyle !== "keep" ? "image://lgcursor/" + root.cursorStyle + "/left_ptr" : ""
        smooth: true
        mipmap: true
    }
    Icon {
        z: 20
        visible: demoPointer.running && root.cursorStyle === "keep"
        x: root.demoX - root.u(6); y: root.demoY - root.u(3)
        name: "pointer"
        filled: true
        size: root.u(30)
        color: "white"
        layer.effect: MultiEffect { shadowEnabled: true; shadowBlur: 0.4; shadowColor: "#80000000" }
    }

    // ---------------------------------------------------------------- Edge close-up
    // The lens is a few px wide on the desktop, so at the preview's scale the Bend and
    // Rainbow edge sliders barely show. While one moves, a corner of the glass appears
    // here at its real size, drawn with the same numbers the desktop uses.
    property bool closeUp: false
    property string closeUpPart: "panel"
    function peekEdge(name) {
        closeUpPart = name && name !== "windows" && name !== "terminal" ? name : "panel"
        closeUp = true
        closeUpTimer.restart()
    }
    Timer { id: closeUpTimer; interval: 3500; onTriggered: if (!closeUpHover.hovered) root.closeUp = false }
    Rectangle {
        id: closeUpBox
        objectName: "edgeCloseUp"
        z: 15
        readonly property real m: 1 / root.s                 // inset px = desktop px
        // Where on the wallpaper the close-up looks (preview px): a stretch below the windows.
        readonly property real cx: root.width * 0.40
        readonly property real cy: root.height * 0.84
        width: Math.round(root.width * 0.34); height: Math.round(width * 0.58)
        x: root.width - width - root.u(40)
        y: root.u(150)
        radius: root.u(26)
        color: "black"
        clip: true
        visible: opacity > 0.01
        opacity: root.closeUp ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
        HoverHandler { id: closeUpHover; onHoveredChanged: if (!hovered) closeUpTimer.restart() }
        layer.enabled: true
        layer.effect: MultiEffect {
            maskEnabled: true
            maskSource: closeUpMask
            maskThresholdMin: 0.5
            maskSpreadAtMin: 1.0
        }
        Item {
            id: closeUpScene
            anchors.fill: parent
            Item {
                id: closeUpBack
                anchors.fill: parent
                // The wallpaper at full resolution, so the lens has real detail to bend.
                ShaderEffectSource {
                    anchors.fill: parent
                    visible: wallFull.status !== Image.Ready
                    sourceItem: closeUpBox.visible && !visible ? null : wall
                    sourceRect: Qt.rect(closeUpBox.cx - closeUpBox.width / 2 / closeUpBox.m, closeUpBox.cy - closeUpBox.height / 2 / closeUpBox.m,
                                        closeUpBox.width / closeUpBox.m, closeUpBox.height / closeUpBox.m)
                    live: true
                    smooth: true
                }
                Image {
                    id: wallFull
                    x: closeUpBox.width / 2 - closeUpBox.cx * closeUpBox.m
                    y: closeUpBox.height / 2 - closeUpBox.cy * closeUpBox.m
                    width: root.width * closeUpBox.m; height: root.height * closeUpBox.m
                    source: closeUpBox.visible || status === Image.Ready ? root.wallpaper : ""
                    fillMode: Image.PreserveAspectCrop
                    sourceSize.width: 2560
                    asynchronous: true
                    smooth: true
                    visible: status === Image.Ready
                }
                // A window behind the glass, so the lens has crisp edges and text to bend.
                Rectangle {
                    x: closeUpBox.width * 0.42; y: closeUpBox.height * 0.18
                    width: closeUpBox.width; height: closeUpBox.height
                    radius: 12
                    color: root.gtkThemed ? root.part("windows", "view", "#242424") : root.adw.view
                    border.width: 1; border.color: root.t.edge || "transparent"
                    Column {
                        x: 22; y: 18; spacing: 14
                        Repeater {
                            model: ["Documents", "Downloads", "Pictures", "Projects"]
                            delegate: Row {
                                required property string modelData
                                spacing: 12
                                Rectangle { width: 26; height: 20; radius: 4; color: root.folderBlue; anchors.verticalCenter: parent.verticalCenter }
                                Text { text: modelData; color: root.fg; font.pixelSize: 17; font.weight: Font.DemiBold; anchors.verticalCenter: parent.verticalCenter }
                            }
                        }
                    }
                }
            }
            GlassSurface {
                readonly property string pn: root.closeUpPart
                backdrop: closeUpBack
                // The panel's rounded end, or the corner of a menu, near the middle of the box.
                readonly property bool bar: pn === "panel"
                x: bar ? -closeUpBox.width * 0.3 : -closeUpBox.width * 0.4
                y: bar ? closeUpBox.height * 0.5 - root.panelH / 2 : closeUpBox.height * 0.36
                width: closeUpBox.width; height: bar ? root.panelH : closeUpBox.height
                radius: bar ? (root.floating ? Math.min(height / 2, root.lad(root.rPanel, "l")) : 0) : root.lad(root.part(pn, "radius", root.r), "m")
                blurRadius: root.glassOn ? root.part(pn, "blur", t.blur_radius || 0) : 0
                brightness: root.glassOn ? root.brightness : 0
                saturation: root.glassOn ? root.saturation : 0
                refraction: root.glassOn ? root.part(pn, "lens_bend", 0) : 0
                bezel: Math.max(4, root.part(pn, "lens_width", 0))
                fringe: root.glassOn ? (t.dispersion || 0) : 0
                rim: root.glassOn ? root.rimFor(pn) : "transparent"
                edge: root.t.edge || "transparent"
                tint: root.shellThemed ? root.part(pn, pn === "panel" ? "chrome" : "popover", "transparent") : root.adw.popup
                shadowColor: root.t.shadow || "transparent"
                shadowBlur: 40
                shadowY: 10
            }
        }
        Rectangle { id: closeUpMask; anchors.fill: parent; radius: closeUpBox.radius; visible: false; layer.enabled: true }
        Rectangle {     // the label
            x: root.u(18); y: root.u(16)
            width: closeUpLabel.width + root.u(24); height: root.u(34)
            radius: height / 2
            color: Qt.rgba(0, 0, 0, 0.55)
            Text {
                id: closeUpLabel
                anchors.centerIn: parent
                text: "Glass edge at full size"
                color: "white"
                font.pixelSize: root.u(15)
                font.weight: Font.DemiBold
            }
        }
    }
    Rectangle {     // a thin frame around the close-up
        z: 16
        visible: closeUpBox.visible
        opacity: closeUpBox.opacity
        x: closeUpBox.x; y: closeUpBox.y; width: closeUpBox.width; height: closeUpBox.height
        radius: closeUpBox.radius
        color: "transparent"
        border.width: Math.max(1, root.u(2))
        border.color: Qt.rgba(1, 1, 1, 0.35)
    }
}
