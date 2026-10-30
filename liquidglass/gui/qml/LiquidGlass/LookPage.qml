import QtQuick
import QtQuick.Controls.Basic as C
import QtQuick.Effects
import LiquidGlass.Core

// The main page: live preview and the frost slider on the left, every other
// option on the right (basics first, the rest under "Fine-tune").
Item {
    id: page
    property alias fineTuneOpen: fine.expanded
    property alias frostHeld: frost.held

    readonly property real sideW: width >= 1180 ? 400 : 360
    readonly property var presetTips: ({
        "Liquid": "Clearest glass, brightest rim",
        "Clear": "Clear glass with a little haze",
        "Balanced": "The default: readable and still glassy",
        "Frosted": "Milky, heavily blurred glass",
        "Solid": "Almost opaque, for maximum readability"
    })
    function pct(v) { return Math.round(v * 100) + "%" }
    function frostName(f) {
        if (f < 0.12) return "Liquid"
        if (f < 0.35) return "Clear"
        if (f < 0.62) return "Balanced"
        return "Frosted"
    }

    // ================================================================ left: preview + glass
    Item {
        id: left
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.right: side.left
        anchors.rightMargin: 24

        Item {
            id: previewBox
            readonly property real maxH: left.height - hero.height - 16
            width: Math.min(left.width, maxH * 16 / 9)
            height: width * 9 / 16
            anchors.horizontalCenter: parent.horizontalCenter

            RectangularShadow {
                anchors.fill: parent
                radius: 18
                blur: 28
                offset.y: 8
                color: Qt.rgba(0, 0, 0, Theme.dark ? 0.5 : 0.22)
            }

            PreviewDesktop {
                id: preview
                objectName: "preview"
                anchors.fill: parent
                t: Backend.tokens
                wallpaper: Backend.wallpaper
                dock: Backend.dock
                reduceTransparency: Backend.reduceTransparency
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
                radius: 18
                visible: false
                layer.enabled: true
                layer.smooth: true
            }

            // Dark/light preview switch, floating on the preview like a Shell OSD.
            Rectangle {
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.margins: 12
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

        Card {
            id: hero
            anchors.top: previewBox.bottom
            anchors.topMargin: 16
            width: parent.width
            height: implicitHeight
            padding: 20

            Column {
                width: parent.width
                spacing: 12

                Item {
                    width: parent.width
                    height: 40
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2
                        Text { text: "Glass"; color: Theme.text; font.pixelSize: 17; font.weight: Font.Bold }
                        Text {
                            text: "From clear, bright liquid glass to calm, milky frost"
                            color: Theme.textDim
                            font.pixelSize: 13
                        }
                    }
                    Rectangle {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        height: 28
                        width: valueRow.width + 24
                        radius: 14
                        color: Theme.alpha(Theme.accent, Theme.dark ? 0.18 : 0.12)
                        Row {
                            id: valueRow
                            anchors.centerIn: parent
                            spacing: 6
                            Text {
                                text: page.frostName(Backend.frost)
                                color: Theme.accentText
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                            }
                            Text {
                                text: page.pct(Backend.frost)
                                color: Theme.accentText
                                opacity: 0.75
                                font.pixelSize: 13
                                font.features: { "tnum": 1 }
                            }
                        }
                    }
                }

                FrostSlider {
                    id: frost
                    width: parent.width
                    value: Backend.frost
                    ticks: [{ value: 0.0 }, { value: 0.25 }, { value: 0.45 }, { value: 0.8 }, { value: 1.0 }]
                    onMoved: (v) => Backend.frost = v
                }

                Flow {
                    width: parent.width
                    spacing: 8
                    Repeater {
                        model: Backend.presets
                        delegate: Chip {
                            required property string modelData
                            text: modelData
                            selected: Backend.activePreset === modelData
                            tip: page.presetTips[modelData] || ""
                            onClicked: Backend.applyPreset(modelData)
                        }
                    }
                }
            }
        }
    }

    // ================================================================ right: options
    Flickable {
        id: side
        objectName: "options"
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.rightMargin: -12
        width: page.sideW + 12
        contentHeight: opts.height + 8
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        C.ScrollBar.vertical: LgScrollBar {}
        Behavior on contentY { enabled: revealTimer.running || side.revealing; NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
        property bool revealing: false

        // Opening Fine-tune scrolls it into view once it has grown.
        Timer {
            id: revealTimer
            interval: Theme.slow + 20
            onTriggered: {
                side.revealing = true
                side.contentY = Math.max(0, side.contentHeight - side.height)
                side.revealing = false
            }
        }
        Connections {
            target: fine
            function onExpandedChanged() { if (fine.expanded) revealTimer.restart() }
        }

        Column {
            id: opts
            width: page.sideW
            spacing: 16

            Card {
                width: parent.width
                height: implicitHeight
                Column {
                    width: parent.width
                    spacing: 16
                    SectionTitle { text: "Appearance" }
                    Column {
                        width: parent.width
                        spacing: 8
                        Text { text: "Style"; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
                        Segmented {
                            width: parent.width
                            model: [{ value: "auto", label: "Auto", icon: "auto", tip: "Follow GNOME's light/dark setting" },
                                    { value: "dark", label: "Dark", icon: "moon", tip: "Always use the dark style, whatever GNOME is set to" },
                                    { value: "light", label: "Light", icon: "sun", tip: "Always use the light style, whatever GNOME is set to" }]
                            value: Backend.scheme
                            onActivated: (v) => Backend.scheme = v
                            Accessible.name: "Style"
                        }
                    }
                    Column {
                        width: parent.width
                        spacing: 10
                        Text { text: "Accent colour"; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
                        Row {
                            id: swatches
                            width: parent.width
                            spacing: 4
                            readonly property real d: Math.min(30, Math.floor((width - 10 * spacing) / 11))
                            Swatch {
                                size: swatches.d
                                swatch: Backend.accents.find(a => a.id === Backend.systemAccent)?.color ?? "#3584e4"
                                split: true
                                selected: Backend.accent === "system"
                                tip: "System accent (follows GNOME Settings)"
                                onClicked: Backend.accent = "system"
                            }
                            Repeater {
                                model: Backend.accents
                                delegate: Swatch {
                                    required property var modelData
                                    size: swatches.d
                                    swatch: modelData.color
                                    selected: Backend.accent === modelData.id
                                    tip: modelData.label
                                    onClicked: Backend.accent = modelData.id
                                }
                            }
                            Swatch {
                                id: customAccent
                                size: swatches.d
                                readonly property bool isCustom: Backend.accent.startsWith("#")
                                swatch: isCustom ? Backend.accent : "#888888"
                                rainbow: !isCustom
                                selected: isCustom
                                tip: "Custom colour…"
                                onClicked: accentPicker.open()
                                ColorPicker {
                                    id: accentPicker
                                    y: parent.height + 8
                                    x: parent.width - width
                                    title: "Custom accent"
                                    color: customAccent.isCustom ? Backend.accent : Theme.accent
                                    onPicked: (hex) => Backend.accent = hex
                                }
                            }
                        }
                    }
                }
            }

            Card {
                width: parent.width
                height: implicitHeight
                Column {
                    width: parent.width
                    spacing: 16
                    SectionTitle { text: "Glass" }
                    Item {
                        width: parent.width
                        height: 36
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2
                            Text { text: "Tint"; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
                            Text { text: "The colour the glass leans towards"; color: Theme.textFaint; font.pixelSize: Theme.fsSmall }
                        }
                        C.AbstractButton {
                            id: tintButton
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            width: 108
                            height: 34
                            hoverEnabled: true
                            focusPolicy: Qt.StrongFocus
                            onClicked: tintPicker.open()
                            Accessible.name: "Tint colour"
                            HoverHandler { cursorShape: Qt.PointingHandCursor }
                            LgToolTip { shown: tintButton.hovered; text: "Choose the tint colour" }
                            background: Rectangle {
                                radius: height / 2
                                color: tintButton.hovered ? Theme.surfaceHi : Theme.well
                                border.width: 1
                                border.color: Theme.border
                                FocusRing { target: tintButton; radius: height / 2 }
                            }
                            contentItem: Row {
                                spacing: 8
                                leftPadding: 6
                                Rectangle {
                                    width: 22; height: 22; radius: 11
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: Backend.tint
                                    border.width: 1
                                    border.color: Qt.rgba(0, 0, 0, 0.15)
                                }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: Backend.tint.toUpperCase()
                                    color: Theme.textDim
                                    font.family: Theme.mono
                                    font.pixelSize: 12
                                }
                            }
                            ColorPicker {
                                id: tintPicker
                                y: parent.height + 8
                                x: parent.width - width
                                title: "Tint colour"
                                color: Backend.tint
                                onPicked: (hex) => Backend.tint = hex
                            }
                        }
                    }
                    LabeledSlider {
                        label: "Tint strength"
                        value: Backend.tintStrength
                        onMoved: (v) => Backend.tintStrength = v
                        tip: "How much of the tint colour is mixed into the glass. Left is clear, colourless glass; right is a strongly coloured pane."
                    }
                    LabeledSlider {
                        label: "Corner roundness"
                        from: 0; to: 32; stepSize: 1
                        value: Backend.radius
                        format: (v) => Math.round(v) + " px"
                        onMoved: (v) => Backend.radius = v
                        tip: "How round the corners of the panel, menus and windows are. Left is sharp, square corners; right is soft, pill-like corners."
                    }
                }
            }

            // ---- per-part overrides: one part at a time, everything follows the global look until changed
            Card {
                id: partsCard
                width: parent.width
                height: implicitHeight
                readonly property var partList: [
                    { id: "panel", label: "Panel", caption: "Dash to Panel or the top bar",
                      tip: "Look of the Dash to Panel bar or the top bar only" },
                    { id: "arcmenu", label: "ArcMenu", caption: "The ArcMenu application menu",
                      tip: "Look of the ArcMenu application menu only" },
                    { id: "quicksettings", label: "Quick settings", caption: "Quick settings, app menus, on-screen pop-ups and dialogs",
                      tip: "Look of quick settings, menus, volume pop-ups and dialogs" },
                    { id: "calendar", label: "Calendar", caption: "The calendar and notification pop-ups",
                      tip: "Look of the calendar and notification pop-ups" },
                    { id: "overview", label: "Overview", caption: "The dash and app grid in Activities",
                      tip: "Look of the dash and the app grid in Activities" },
                    { id: "windows", label: "Windows", caption: "App windows, their sidebars and header bars",
                      tip: "Look of app windows" },
                    { id: "terminal", label: "Terminal", caption: "Terminal windows",
                      tip: "Look of terminal windows" }
                ]
                property string part: "panel"
                readonly property var info: partList.find(p => p.id === part)
                readonly property var own: Backend.parts[part] || ({})
                readonly property bool any: Object.keys(own).length > 0
                // Which settings make sense for the chosen part.
                readonly property bool hasRadius: part !== "terminal"
                readonly property bool hasLens: part === "panel" || part === "arcmenu" || part === "quicksettings" || part === "calendar"
                function val(key) { return own[key] !== undefined ? own[key] : -1 }
                function setOrClear(key, v) { v < 0 ? Backend.clearPart(part, key) : Backend.setPart(part, key, v) }

                Column {
                    width: parent.width
                    spacing: 16
                    SectionTitle { text: "Parts" }
                    Column {
                        width: parent.width
                        spacing: 10
                        Text {
                            width: parent.width
                            wrapMode: Text.WordWrap
                            color: Theme.textFaint
                            font.pixelSize: Theme.fsSmall
                            text: "Give one part of the desktop its own look. Anything you leave on Global follows the settings above."
                        }
                        Flow {
                            width: parent.width
                            spacing: 8
                            Repeater {
                                model: partsCard.partList
                                delegate: Chip {
                                    required property var modelData
                                    text: modelData.label
                                    selected: partsCard.part === modelData.id
                                    tip: modelData.tip
                                    Rectangle {      // a dot marks parts that have their own look
                                        visible: !!Backend.parts[modelData.id] && Object.keys(Backend.parts[modelData.id]).length > 0
                                        width: 6; height: 6; radius: 3
                                        color: Theme.accent
                                        anchors.top: parent.top; anchors.right: parent.right
                                        anchors.topMargin: 3; anchors.rightMargin: 5
                                    }
                                    onClicked: partsCard.part = modelData.id
                                }
                            }
                        }
                    }
                    Item {
                        width: parent.width
                        height: 36
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - 120
                            spacing: 2
                            Text { text: partsCard.info.label; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
                            Text {
                                width: parent.width
                                text: partsCard.any ? "Has its own look" : "Same as global"
                                color: Theme.textFaint
                                font.pixelSize: Theme.fsSmall
                            }
                        }
                        LgButton {
                            objectName: "resetPart"
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            kind: "flat"
                            implicitHeight: 32
                            leftPadding: 12; rightPadding: 12
                            text: "Reset this part"
                            iconName: "refresh"
                            enabled: partsCard.any
                            tip: "Put every setting of this part back to following the global look"
                            onClicked: Backend.resetPart(partsCard.part)
                        }
                    }
                    Item {
                        width: parent.width
                        height: 36
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2
                            Text { text: "Tint"; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
                            Text {
                                text: partsCard.own.tint !== undefined ? "Its own colour" : "Same as global"
                                color: Theme.textFaint; font.pixelSize: Theme.fsSmall
                            }
                        }
                        Row {
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 8
                            Chip {
                                anchors.verticalCenter: parent.verticalCenter
                                implicitHeight: 28
                                text: "Global"
                                selected: partsCard.own.tint === undefined
                                tip: selected ? "Follows the tint colour in the Glass card" : "Go back to the global tint colour"
                                onClicked: partsCard.own.tint === undefined ? Backend.setPart(partsCard.part, "tint", Backend.tint)
                                                                            : Backend.clearPart(partsCard.part, "tint")
                            }
                            C.AbstractButton {
                                id: partTint
                                anchors.verticalCenter: parent.verticalCenter
                                width: 108
                                height: 34
                                hoverEnabled: true
                                focusPolicy: Qt.StrongFocus
                                readonly property string shown: partsCard.own.tint !== undefined ? partsCard.own.tint : Backend.tint
                                onClicked: partTintPicker.open()
                                Accessible.name: "Tint colour for this part"
                                HoverHandler { cursorShape: Qt.PointingHandCursor }
                                LgToolTip { shown: partTint.hovered; text: "Choose a tint colour for this part only" }
                                background: Rectangle {
                                    radius: height / 2
                                    color: partTint.hovered ? Theme.surfaceHi : Theme.well
                                    border.width: 1
                                    border.color: Theme.border
                                    FocusRing { target: partTint; radius: height / 2 }
                                }
                                contentItem: Row {
                                    spacing: 8
                                    leftPadding: 6
                                    Rectangle {
                                        width: 22; height: 22; radius: 11
                                        anchors.verticalCenter: parent.verticalCenter
                                        color: partTint.shown
                                        border.width: 1
                                        border.color: Qt.rgba(0, 0, 0, 0.15)
                                    }
                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: partTint.shown.toUpperCase()
                                        color: partsCard.own.tint !== undefined ? Theme.textDim : Theme.textFaint
                                        font.family: Theme.mono
                                        font.pixelSize: 12
                                    }
                                }
                                ColorPicker {
                                    id: partTintPicker
                                    y: parent.height + 8
                                    x: parent.width - width
                                    title: "Tint colour"
                                    color: partTint.shown
                                    onPicked: (hex) => Backend.setPart(partsCard.part, "tint", hex)
                                }
                            }
                        }
                    }
                    OverrideSlider {
                        label: "Tint strength"
                        autoText: "Global"
                        autoTip: "Follows the tint strength in the Glass card"
                        resetTip: "Go back to the global tint strength"
                        tip: "How much of the tint colour is mixed into this part. Left is clear, colourless glass; right is strongly coloured."
                        value: partsCard.val("tint_strength")
                        autoValue: Backend.tintStrength
                        onChanged: (v) => partsCard.setOrClear("tint_strength", v)
                    }
                    OverrideSlider {
                        visible: partsCard.hasRadius
                        label: "Corner roundness"
                        autoText: "Global"
                        autoTip: "Follows the corner roundness in the Glass card"
                        resetTip: "Go back to the global corner roundness"
                        tip: "How round this part's corners are. Left is sharp, square corners; right is soft, pill-like corners."
                        from: 0; to: 32; stepSize: 1
                        value: partsCard.val("radius")
                        autoValue: Backend.radius
                        format: (v) => Math.round(v) + " px"
                        onChanged: (v) => partsCard.setOrClear("radius", v < 0 ? v : Math.round(v))
                    }
                    OverrideSlider {
                        label: "Frost"
                        autoText: "Global"
                        autoTip: "Follows the Liquid to Frosted slider"
                        resetTip: "Go back to following the Liquid to Frosted slider"
                        tip: "How frosted this part is. Left is clear glass with a light blur; right is milky, heavily blurred and easier to read."
                        value: partsCard.val("frost")
                        autoValue: Backend.frost
                        onChanged: (v) => partsCard.setOrClear("frost", v)
                    }
                    OverrideSlider {
                        visible: partsCard.hasLens
                        label: "Glass strength"
                        autoText: "Global"
                        autoTip: "Follows Bend in the Glass effects card"
                        resetTip: "Go back to the global Bend"
                        tip: "How strongly this part's rounded edge bends what's behind it. Left is flat glass; right is a thick lens."
                        value: partsCard.val("refraction")
                        autoValue: Backend.refraction
                        onChanged: (v) => partsCard.setOrClear("refraction", v)
                    }
                    OverrideSlider {
                        visible: partsCard.hasLens
                        label: "Colour bleed"
                        autoText: "Global"
                        autoTip: "Follows Colour bleed in the Glass effects card"
                        resetTip: "Go back to the global Colour bleed"
                        tip: "How much the colours of icons and text light up the glass of this part. Left keeps it neutral; right gives them a coloured glow."
                        value: partsCard.val("bleed")
                        autoValue: Backend.bleed
                        onChanged: (v) => partsCard.setOrClear("bleed", v)
                    }
                    OverrideSlider {
                        visible: partsCard.hasLens
                        label: "Edge reflections"
                        autoText: "Global"
                        autoTip: "Follows the default edge reflections"
                        resetTip: "Go back to the default edge reflections"
                        tip: "How strongly the edge of this part catches reflections of its surroundings. Left shows none; right gives bright, mirror-like edges."
                        value: partsCard.val("reflections")
                        autoValue: Backend.highlight
                        onChanged: (v) => partsCard.setOrClear("reflections", v)
                    }
                }
            }

            Card {
                width: parent.width
                height: implicitHeight
                Column {
                    width: parent.width
                    spacing: 16
                    SectionTitle { text: "Panel and windows" }
                    Column {
                        width: parent.width
                        spacing: 8
                        Text { text: "Dash to Panel"; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
                        Segmented {
                            width: parent.width
                            model: [{ value: "floating", label: "Floating", icon: "panelFloat", tip: "A glass pill that floats above the screen edge" },
                                    { value: "docked", label: "Docked", icon: "panelDock", tip: "A full-width bar along the screen edge" }]
                            value: Backend.panelStyle
                            onActivated: (v) => Backend.panelStyle = v
                            Accessible.name: "Panel style"
                        }
                    }
                    LabeledSlider {
                        label: "Panel margin"
                        enabled: Backend.panelStyle === "floating"
                        from: 0; to: 32; stepSize: 1
                        value: Backend.panelMargin
                        format: (v) => Math.round(v) + " px"
                        onMoved: (v) => Backend.panelMargin = v
                        tip: "The gap between the floating panel and the screen edge. Left sits it against the edge; right floats it further away."
                    }
                }
            }

            HeaderBarCard { width: parent.width }

            Card {
                width: parent.width
                height: implicitHeight
                Column {
                    width: parent.width
                    spacing: 16
                    SectionTitle { text: "Glass effects" }
                    Text {
                        objectName: "glassStatus"
                        width: parent.width
                        wrapMode: Text.WordWrap
                        color: Theme.textFaint
                        font.pixelSize: Theme.fsSmall
                        text: Backend.glassLive
                              ? "Live: your desktop follows these as you change them."
                              : "Drawn by Liquid Glass's own Shell extension. Apply, then log out once to start it."
                    }
                    LabeledSlider {
                        label: "Bend"
                        value: Backend.refraction
                        onMoved: (v) => Backend.refraction = v
                        tip: "How strongly the rounded edge bends what's behind it. Left is flat glass; right is a thick lens."
                    }
                    LabeledSlider {
                        label: "Rainbow edge"
                        value: Backend.dispersion
                        onMoved: (v) => Backend.dispersion = v
                        tip: "Splits light into colours along the edge, like real glass. Left is no colour fringe; right is a vivid rainbow edge."
                    }
                    LabeledSlider {
                        label: "Colour through glass"
                        value: Backend.vibrancy
                        onMoved: (v) => Backend.vibrancy = v
                        tip: "How vivid the wallpaper and windows look through the glass. Left keeps their colours as they are; right makes them richer."
                    }
                    LabeledSlider {
                        label: "Colour bleed"
                        value: Backend.bleed
                        onMoved: (v) => Backend.bleed = v
                        tip: "How much the colours of icons and text light up the glass around them, like light spreading inside real glass. Left keeps the glass neutral; right gives them a coloured glow."
                    }
                    Column {
                        width: parent.width
                        spacing: 4
                        SwitchRow {
                            label: "Panel"
                            caption: "Dash to Panel or the top bar"
                            tip: "Draws real glass behind the panel. Off leaves a plain tinted bar."
                            checked: Backend.glassPanel
                            onToggled: (on) => Backend.glassPanel = on
                        }
                        SwitchRow {
                            label: "Menus"
                            caption: "Quick settings, calendar, ArcMenu and app menus"
                            tip: "Draws real glass behind menus and pop-ups. Off leaves plain tinted panes."
                            checked: Backend.glassMenus
                            onToggled: (on) => Backend.glassMenus = on
                        }
                        SwitchRow {
                            label: "App windows"
                            caption: "Frosted wallpaper behind translucent windows"
                            tip: "Blurs the wallpaper behind see-through app windows. Off shows it sharp, which is lighter on the GPU."
                            checked: Backend.blurAppWindows
                            onToggled: (on) => Backend.blurAppWindows = on
                        }
                        SwitchRow {
                            label: "Overview"
                            caption: "Blurred wallpaper behind the Activities overview"
                            tip: "Blurs the wallpaper when you open Activities. Off leaves it sharp."
                            checked: Backend.glassOverview
                            onToggled: (on) => Backend.glassOverview = on
                        }
                        SwitchRow {
                            label: "See windows through the glass"
                            caption: "Off shows only the wallpaper behind the panel and menus, which is lighter on the GPU"
                            tip: "On, the panel and menus show the windows behind them as well as the wallpaper. Off shows only the wallpaper."
                            enabled: Backend.glassPanel || Backend.glassMenus
                            checked: Backend.glassSeeWindows
                            onToggled: (on) => Backend.glassSeeWindows = on
                        }
                    }
                }
            }

            Card {
                width: parent.width
                height: implicitHeight
                padding: 8
                Expander {
                    id: fine
                    width: parent.width
                    title: "Fine-tune"
                    caption: "Override what the slider decides"
                    Column {
                        x: 12
                        width: parent.width - 24
                        spacing: 18
                        OverrideSlider {
                            label: "Transparency"
                            caption: "How solid panels and header bars look"
                            value: Backend.opacity
                            autoValue: Backend.autoValues.opacity
                            onChanged: (v) => Backend.opacity = v
                            tip: "How solid panels and header bars look. Left is see-through; right is nearly solid."
                            format: (v) => Math.round(v * 100) + "% solid"
                        }
                        OverrideSlider {
                            label: "Blur"
                            value: Backend.blur
                            autoValue: Backend.autoValues.blur
                            from: 0; to: 100; stepSize: 1
                            format: (v) => Math.round(v) + " px"
                            tip: "How much the background behind glass is blurred. Left shows it sharp; right melts it into soft colour."
                            onChanged: (v) => Backend.blur = v
                        }
                        OverrideSlider {
                            label: "Terminal opacity"
                            value: Backend.terminalOpacity
                            autoValue: Backend.autoValues.terminal_opacity
                            from: 0.3; to: 1
                            tip: "How see-through terminal windows are. Left lets the desktop show through; right is a solid background."
                            onChanged: (v) => Backend.terminalOpacity = v
                        }
                        SwitchRow {
                            label: "Reduce transparency"
                            caption: "Nearly opaque surfaces and no blur, for readability"
                            tip: "Makes every surface nearly solid and turns the blur off. Easier to read, but no longer see-through."
                            checked: Backend.reduceTransparency
                            onToggled: (on) => Backend.reduceTransparency = on
                        }
                        LgButton {
                            kind: "flat"
                            text: "Reset all to defaults"
                            iconName: "refresh"
                            leftPadding: 12
                            tip: "Back to the default look (Apply to use it)"
                            onClicked: Backend.resetDefaults()
                        }
                        Item { width: 1; height: 4 }
                    }
                }
            }
            Item { width: 1; height: 8 }
        }
    }
    // Soft edges where the options scroll under, so it's clear there is more.
    Rectangle {
        anchors.left: side.left; width: page.sideW
        y: side.y; height: 24
        visible: side.contentY > 1
        gradient: Gradient {
            GradientStop { position: 0; color: Theme.alpha(Theme.base, 0.9) }
            GradientStop { position: 1; color: Theme.alpha(Theme.base, 0) }
        }
    }
    Rectangle {
        anchors.left: side.left; width: page.sideW
        y: side.y + side.height - height; height: 32
        visible: side.contentY + side.height < side.contentHeight - 1
        gradient: Gradient {
            GradientStop { position: 0; color: Theme.alpha(Theme.base, 0) }
            GradientStop { position: 1; color: Theme.alpha(Theme.base, 0.92) }
        }
    }
}
