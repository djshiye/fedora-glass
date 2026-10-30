import QtQuick
import QtQuick.Effects
import LiquidGlass.Core

// A faithful miniature of the desktop: the real wallpaper, Nautilus and Ptyxis
// windows, Dash to Panel and an open ArcMenu, drawn with the very Tokens the
// theme writes. Everything is laid out on a virtual 1920x1080 screen and
// scaled by `s`, so the effects render at the preview's own resolution.
Item {
    id: root

    property var t: ({})
    property string wallpaper: ""
    property var dock: []
    property bool reduceTransparency: false
    property bool showMenu: true
    property real menuProgress: showMenu ? 1 : 0
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
    readonly property real fringe: reduceTransparency ? 0 : (t.dispersion !== undefined ? t.dispersion : 0.35 - 0.28 * frost)
    readonly property real vivid: t.vibrancy !== undefined ? (t.vibrancy - 1) * 0.5 : 0
    readonly property real sheen: t.highlight ? Math.min(1, t.highlight.a * 1.6) : 0
    readonly property real brightness: ((t.blur_brightness || 1) - 1) * 0.35
    readonly property real saturation: reduceTransparency ? 0 : Math.min(1, root.vivid)
    readonly property bool windowsBlur: t.blur_app_windows !== undefined ? t.blur_app_windows : true
    readonly property real r: t.radius !== undefined ? t.radius : 18
    readonly property real rPanel: part("panel", "radius", r)
    readonly property real rMenu: part("arcmenu", "radius", r)
    readonly property real rWin: part("windows", "radius", r)
    readonly property real rs: t.radius_small !== undefined ? t.radius_small : 10
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
    readonly property real headH: u((Backend.headerHeight || 47) + 3)
    readonly property bool headCustom: Backend.headerOpacity >= 0 && !reduceTransparency
    function headerColor(c) { return headCustom ? withAlpha(c, Backend.headerOpacity) : c }

    // Reusable recipes so every glass surface reads its numbers from one place.
    component ShellGlass: GlassSurface {
        property string part: ""
        blurRadius: part ? root.part(part, "blur", t.blur_radius || 0) * root.s : root.blurPx
        brightness: root.brightness
        saturation: root.saturation
        refraction: root.reduceTransparency ? 0 : (part ? root.part(part, "lens_bend", 0) * root.s : root.refraction)
        bezel: part ? Math.max(4, root.part(part, "lens_width", 0) * root.s) : root.bezel
        fringe: root.fringe
        bleed: part ? root.part(part, "bleed", root.bleedGlobal) : root.bleedGlobal
        sheen: part && t.glare > 0 ? Math.min(1, root.sheen * root.part(part, "glare", t.glare) / t.glare) : root.sheen
        rim: root.t.highlight || "transparent"
        edge: root.t.edge || "transparent"
        rimWidth: Math.max(0.8, root.u(1.6))
        shadowColor: root.t.shadow || "transparent"
        shadowBlur: root.u(40)
        shadowY: root.u(10)
    }
    // Behind app windows the extension draws plain frost; the window paints its own rim.
    component WindowGlass: ShellGlass {
        part: "windows"
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
                x: root.u(120); y: root.u(64)
                width: root.u(1060); height: root.u(660)
                tint: "transparent"

                readonly property real side: root.u(250)
                readonly property real head: root.headH

                Rectangle {     // sidebar pane
                    width: files.side
                    height: parent.height
                    color: root.part("windows", "chrome", "transparent")
                    topLeftRadius: root.rWin
                    bottomLeftRadius: root.rWin
                }
                Rectangle {     // content header bar
                    x: files.side
                    width: parent.width - files.side
                    height: files.head
                    color: root.headerColor(root.part("windows", "view", "transparent"))
                    topRightRadius: root.rWin
                }
                Rectangle {     // content pane
                    x: files.side; y: files.head
                    width: parent.width - files.side
                    height: parent.height - files.head
                    color: root.part("windows", "view", "transparent")
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
                            radius: root.rs
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
                        radius: Math.min(height / 2, root.rs)
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
        WindowGlass {
            id: term
            part: "terminal"
            radius: root.rWin
            backdrop: belowTerminal
            x: root.u(900); y: root.u(330)
            width: root.u(880); height: root.u(540)
            tint: "transparent"
            readonly property real head: root.headH

            Rectangle {
                width: parent.width; height: term.head
                color: root.part("terminal", "chrome", "transparent")
                topLeftRadius: root.rWin; topRightRadius: root.rWin
            }
            Rectangle {
                y: term.head; width: parent.width; height: parent.height - term.head
                color: root.t.parts ? root.withAlpha(root.part("terminal", "view", "transparent"), root.t.terminal_opacity) : "transparent"
                bottomLeftRadius: root.rWin; bottomRightRadius: root.rWin
            }
            Rectangle { y: term.head; width: parent.width; height: 1; color: root.t.divider || "transparent" }

            Item {
                width: parent.width; height: term.head
                Circle {
                    d: root.u(32); x: root.u(10); anchors.verticalCenter: parent.verticalCenter
                    color: "transparent"
                    Sym { anchors.centerIn: parent; name: "plus" }
                }
                Label {
                    anchors.centerIn: parent
                    text: Backend.userName + "@" + Backend.hostName + ":~"
                    font.weight: Font.Bold
                }
                Row {
                    anchors.right: parent.right; anchors.rightMargin: root.u(12)
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: root.u(14)
                    Sym { name: "search"; anchors.verticalCenter: parent.verticalCenter }
                    Sym { name: "menu"; anchors.verticalCenter: parent.verticalCenter }
                    Circle {
                        d: root.u(26); anchors.verticalCenter: parent.verticalCenter
                        color: root.t.hover || "transparent"
                        Sym { anchors.centerIn: parent; name: "close"; size: root.u(15) }
                    }
                }
            }

            Column {
                x: root.u(20); y: term.head + root.u(18)
                spacing: root.u(5)
                component Line: Text {
                    font.family: Theme.mono
                    font.pixelSize: root.u(16)
                    color: root.fg
                    textFormat: Text.StyledText
                    renderType: Text.QtRendering
                }
                readonly property string green: root.t.success ? root.t.success.toString() : "#4ad48a"
                readonly property string blue: root.t.accent_text ? root.t.accent_text.toString() : "#78aeed"
                readonly property string dim: root.t.fg_faint ? Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.55).toString() : "#888"
                readonly property string yellow: root.t.warning ? root.t.warning.toString() : "#f5c04f"
                Line { text: "<font color='" + parent.green + "'><b>" + Backend.userName + "@" + Backend.hostName + "</b></font>:<font color='" + parent.blue + "'><b>~</b></font>$ liquid-glass apply" }
                Line { text: "<font color='" + parent.green + "'>✓</font> GNOME Shell           <font color='" + parent.dim + "'>applied</font>" }
                Line { text: "<font color='" + parent.green + "'>✓</font> GTK 4 and libadwaita  <font color='" + parent.dim + "'>applied</font>" }
                Line { text: "<font color='" + parent.green + "'>✓</font> Dash to Panel         <font color='" + parent.dim + "'>applied</font>" }
                Line { text: "<font color='" + parent.green + "'>✓</font> Ptyxis                <font color='" + parent.dim + "'>applied</font>" }
                Line { text: "<font color='" + parent.yellow + "'>–</font> Steam                 <font color='" + parent.dim + "'>skipped</font>" }
                Line { text: " " }
                Line { text: "<font color='" + parent.green + "'><b>" + Backend.userName + "@" + Backend.hostName + "</b></font>:<font color='" + parent.blue + "'><b>~</b></font>$ " }
            }
            Rectangle {     // cursor
                x: root.u(20) + root.u(16) * 0.6 * 14; y: term.head + root.u(18) + 7 * root.u(16 * 1.18 + 5)
                width: root.u(9.5); height: root.u(19)
                color: root.fg
                opacity: 0.85
            }
        }
    }

    // =====================================================================================
    // The Shell layer blurs the desktop and the windows below it.
    readonly property bool floating: t.panel_floating !== undefined ? t.panel_floating : true
    readonly property real margin: floating ? (t.panel_margin || 0) : 0
    readonly property real panelH: 48

    ShellGlass {
        id: panel
        part: "panel"
        backdrop: desk
        x: root.u(root.margin)
        width: root.width - 2 * root.u(root.margin)
        height: root.u(root.panelH)
        y: root.height - height - root.u(root.margin)
        radius: root.floating ? Math.min(height / 2, root.u(root.rPanel + 6)) : 0
        tint: root.part("panel", "chrome", "transparent")
        shadowColor: root.floating ? (root.t.shadow || "transparent") : "transparent"
        shadowBlur: root.u(30)
        shadowY: root.u(6)
        Behavior on x { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
        Behavior on y { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
        Behavior on width { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }

        Rectangle {     // menu button, pressed while the menu is open
            id: menuButton
            x: root.u(6); anchors.verticalCenter: parent.verticalCenter
            width: root.u(44); height: root.u(40)
            radius: Math.min(height / 2, root.rs)
            color: root.showMenu ? (root.t.active || "transparent") : "transparent"
            Icon {
                anchors.centerIn: parent
                name: "fedora"
                size: root.u(28)
                strokeWidth: Math.max(0.9, root.u(2))
                color: root.fg
            }
        }
        Row {
            x: menuButton.x + menuButton.width + root.u(6)
            height: parent.height
            spacing: root.u(4)
            Repeater {
                model: root.dock
                delegate: Item {
                    required property var modelData
                    width: root.u(48); height: parent.height
                    Rectangle {
                        anchors.centerIn: parent
                        width: root.u(44); height: root.u(40)
                        radius: Math.min(height / 2, root.rs)
                        color: modelData.running ? (root.t.hover || "transparent") : "transparent"
                    }
                    AppIcon {
                        anchors.centerIn: parent
                        size: root.u(30)
                        source: modelData.icon
                        label: modelData.name
                        tileColor: root.t.accent || "#3584e4"
                    }
                    Rectangle {
                        visible: modelData.running
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: parent.height - root.u(6)
                        width: root.u(12); height: root.u(3); radius: height / 2
                        color: root.t.accent || "white"
                    }
                }
            }
        }
        Row {
            anchors.right: parent.right; anchors.rightMargin: root.u(root.floating ? 18 : 14)
            anchors.verticalCenter: parent.verticalCenter
            spacing: root.u(18)
            Label { text: root.clock; anchors.verticalCenter: parent.verticalCenter; font.weight: Font.DemiBold }
            Row {
                spacing: root.u(10); anchors.verticalCenter: parent.verticalCenter
                Sym { name: "wifi" }
                Sym { name: "volume" }
                Sym { name: "power" }
            }
        }
    }

    // ---------------------------------------------------------------- ArcMenu
    ShellGlass {
        id: menu
        part: "arcmenu"
        backdrop: desk
        visible: root.menuProgress > 0.01
        opacity: root.menuProgress
        width: root.u(640); height: root.u(600)
        x: root.u(Math.max(8, root.margin))
        y: panel.y - height - root.u(10) + root.u(16) * (1 - root.menuProgress)
        radius: root.rMenu + root.u(4)
        tint: root.part("arcmenu", "popover", "transparent")
        shadowBlur: root.u(50)
        shadowY: root.u(14)

        readonly property real pad: root.u(18)
        readonly property real split: root.u(400)

        Rectangle {     // search entry
            x: menu.pad; y: menu.pad
            width: menu.width - 2 * menu.pad; height: root.u(40)
            radius: height / 2
            // Mostly opaque, as in the Shell, so the window behind never shows through.
            color: root.t.popover ? Qt.rgba(root.t.popover.r, root.t.popover.g, root.t.popover.b, 0.62)
                                  : "transparent"
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
                    radius: root.rs
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
}
