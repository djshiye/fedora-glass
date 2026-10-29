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
            RimLight {
                radius: 18
                rim: Qt.rgba(1, 1, 1, 0.22)
                edge: Qt.rgba(1, 1, 1, Theme.dark ? 0.10 : 0.0)
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
                RimLight { radius: height / 2; rim: Qt.rgba(1, 1, 1, 0.25); edge: Qt.rgba(1, 1, 1, 0.10) }
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
                                    { value: "dark", label: "Dark", icon: "moon" },
                                    { value: "light", label: "Light", icon: "sun" }]
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
                            width: 92
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
                    }
                    LabeledSlider {
                        label: "Corner roundness"
                        from: 0; to: 32; stepSize: 1
                        value: Backend.radius
                        format: (v) => Math.round(v) + " px"
                        onMoved: (v) => Backend.radius = v
                    }
                    LabeledSlider {
                        label: "Rim light"
                        value: Backend.highlight
                        onMoved: (v) => Backend.highlight = v
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
                    }
                    SwitchRow {
                        label: "Blur behind app windows"
                        caption: "Blur my Shell blurs the desktop behind translucent windows"
                        checked: Backend.blurAppWindows
                        onToggled: (on) => Backend.blurAppWindows = on
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
                            format: (v) => Math.round(v * 100) + "% solid"
                        }
                        OverrideSlider {
                            label: "Blur"
                            value: Backend.blur
                            autoValue: Backend.autoValues.blur
                            from: 0; to: 100; stepSize: 1
                            format: (v) => Math.round(v) + " px"
                            onChanged: (v) => Backend.blur = v
                        }
                        OverrideSlider {
                            label: "Terminal opacity"
                            value: Backend.terminalOpacity
                            autoValue: Backend.autoValues.terminal_opacity
                            from: 0.3; to: 1
                            onChanged: (v) => Backend.terminalOpacity = v
                        }
                        SwitchRow {
                            label: "Reduce transparency"
                            caption: "Nearly opaque surfaces and no blur, for readability"
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
