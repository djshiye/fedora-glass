import QtQuick
import QtQuick.Controls.Basic as C
import QtQuick.Window
import FedoraGlass.Core

// Advanced: one part of the desktop with its own look (pick it here or click it in the
// preview), the fine-tune overrides, and starting over.
SettingsPage {
    id: page
    objectName: "advancedPage"
    pageId: "advanced"
    previewSlot: slot

    // --fine-tune opens the Fine-tune fold.
    Component.onCompleted: { if (Window.window && Window.window.fineTuneOpen) fine.expanded = true; outline() }

    // While this page shows, the preview outlines the part and picks one on a click.
    readonly property bool current: visible && Window.window && Window.window.page === "advanced"
    onCurrentChanged: outline()
    function outline() { if (Theme.preview) previewPaneOf().outlinedPart = current ? partsCard.part : "" }
    function previewPaneOf() {      // the pane around the preview (it sits in a viewport)
        let p = Theme.preview.parent
        while (p && p.outlinedPart === undefined)
            p = p.parent
        return p
    }
    Connections {
        target: Theme.preview ? page.previewPaneOf() : null
        function onPartPicked(name) { if (page.current && partsCard.partList.some((p) => p.id === name)) partsCard.part = name }
    }
    Component.onDestruction: if (Theme.preview && previewPaneOf().outlinedPart) previewPaneOf().outlinedPart = ""

    Card {
        id: partsCard
        objectName: "partsCard"
        width: parent.width
        height: implicitHeight
        readonly property var partList: [
            { id: "panel", label: qsTr("Panel"), tip: qsTr("Look of the top bar or Dash to Panel, a dock and the dash in Activities only") },
            { id: "arcmenu", label: qsTr("Start menu"), tip: qsTr("Look of the ArcMenu or Spawn application menu only") },
            { id: "quicksettings", label: qsTr("Quick settings"), tip: qsTr("Look of quick settings, menus, volume pop-ups and dialogs") },
            { id: "calendar", label: qsTr("Calendar"), tip: qsTr("Look of the calendar and notification pop-ups") },
            { id: "overview", label: qsTr("Overview"), tip: qsTr("Look of the dash and the app grid in Activities") },
            { id: "windows", label: qsTr("Windows"), tip: qsTr("Look of app windows, their sidebars and header bars") },
            { id: "terminal", label: qsTr("Terminal"), tip: qsTr("Look of terminal windows") }
        ].filter(p => p.id !== "arcmenu" || Backend.hasStartMenu)   // no start menu, no chip for it
        property string part: "panel"
        // Bring the part being edited into view in the preview, and outline it.
        onPartChanged: {
            if (Theme.preview) {
                const sc = ({ quicksettings: "quicksettings", calendar: "calendar", overview: "overview" })[part] || "desktop"
                Theme.preview.scene = sc
                if (part === "arcmenu") Theme.preview.showMenu = true
            }
            page.outline()
        }
        readonly property var info: partList.find(p => p.id === part) ?? partList[0]
        readonly property var own: Backend.parts[part] || ({})
        readonly property bool any: Object.keys(own).length > 0
        function hasOwn(id) { return !!Backend.parts[id] && Object.keys(Backend.parts[id]).length > 0 }
        // Which settings make sense for the chosen part.
        readonly property bool hasRadius: part !== "terminal"
        readonly property bool hasLens: part !== "overview"
        // App windows keep their content as the app draws it: no colour bleed there.
        readonly property bool hasBleed: hasLens && part !== "windows" && part !== "terminal"
        readonly property int moreCount: 1 + (hasLens ? 2 : 0) + (hasBleed ? 1 : 0)
        function val(key) { return own[key] !== undefined ? own[key] : -1 }
        function setOrClear(key, v) { v < 0 ? Backend.clearPart(part, key) : Backend.setPart(part, key, v) }
        function peek() { if (Theme.preview) Theme.preview.peekEdge(part) }

        Column {
            width: parent.width
            spacing: 12
            SectionTitle {
                text: qsTr("Part by part")
                resetKeys: ["parts"]
                resetTip: qsTr("Every part looks like the rest of the desktop again")
                caption: qsTr("Give one part its own look. Click a part in the preview or pick it here.")
            }
            Flow {
                id: partRow
                objectName: "partRow"
                width: parent.width
                spacing: 8
                Repeater {
                    model: partsCard.partList
                    delegate: Chip {
                        required property var modelData
                        objectName: "part_" + modelData.id
                        readonly property bool own: partsCard.hasOwn(modelData.id)
                        text: own && selected ? qsTr("%1 \u00b7 own look").arg(modelData.label) : modelData.label
                        // Tabs: one Tab stop, and the arrow keys pick the part.
                        rovingGroup: partRow
                        rovingSelects: true
                        selected: partsCard.part === modelData.id
                        tip: own ? qsTr("%1. Has its own look.").arg(modelData.tip) : modelData.tip
                        Rectangle {      // a dot marks the other parts that have their own look
                            visible: parent.own && !parent.selected
                            width: 6; height: 6; radius: 3
                            color: Theme.accent
                            anchors.top: parent.top; anchors.right: parent.right
                            anchors.topMargin: 3; anchors.rightMargin: 5
                        }
                        onClicked: partsCard.part = modelData.id
                    }
                }
            }
            Column {
                width: parent.width
                spacing: 0
                OverrideSlider {
                    objectName: "partTintStrength"
                    inline: true
                    label: qsTr("Tint strength")
                    autoText: qsTr("Same as everywhere")
                    autoTip: qsTr("Follows the tint strength on the Colour page")
                    resetTip: qsTr("Go back to the tint strength used everywhere")
                    tip: qsTr("How much of the tint colour is mixed into this part. Left is clear, colourless glass; right is strongly coloured.")
                    value: partsCard.val("tint_strength")
                    autoValue: Backend.tintStrength
                    onChanged: (v) => partsCard.setOrClear("tint_strength", v)
                }
                Rectangle { width: parent.width; height: 1; color: Theme.divider }
                OverrideSlider {
                    objectName: "partFrost"
                    inline: true
                    label: qsTr("Frost")
                    autoText: qsTr("Same as everywhere")
                    autoTip: qsTr("Follows How much glass on the Glass page")
                    resetTip: qsTr("Go back to the glass used everywhere")
                    tip: qsTr("How frosted this part is. Left is clear glass with a light blur; right is milky, heavily blurred and easier to read.")
                    value: partsCard.val("frost")
                    autoValue: Backend.frost
                    onChanged: (v) => partsCard.setOrClear("frost", v)
                }
                Rectangle { visible: partsCard.hasRadius; width: parent.width; height: 1; color: Theme.divider }
                OverrideSlider {
                    objectName: "partCorners"
                    visible: partsCard.hasRadius
                    inline: true
                    label: qsTr("Corners")
                    autoText: qsTr("Same as everywhere")
                    autoTip: qsTr("Follows Corner roundness on the Colour page")
                    resetTip: qsTr("Go back to the corners used everywhere")
                    tip: qsTr("How round this part's corners are. Left is sharp, square corners; right is soft, pill-like corners.")
                    from: 0; to: 32; stepSize: 1
                    value: partsCard.val("radius")
                    autoValue: Backend.radius
                    format: (v) => qsTr("%1 px").arg(Math.round(v))
                    onChanged: (v) => partsCard.setOrClear("radius", v < 0 ? v : Math.round(v))
                }
            }
            Fold {
                id: more
                objectName: "partMore"
                card: false
                divider: true
                title: qsTr("%1 more for this part").arg(partsCard.moreCount)
                summary: partsCard.hasLens ? qsTr("Tint colour, bend, reflections") : qsTr("Tint colour")
                Column {
                    width: parent.width
                    spacing: 0
                    Item {
                        width: parent.width
                        height: 44
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2
                            Text { text: qsTr("Tint"); color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
                            Text {
                                text: partsCard.own.tint !== undefined ? qsTr("Its own colour") : qsTr("Same as everywhere")
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
                                text: qsTr("Same as everywhere")
                                selected: partsCard.own.tint === undefined
                                tip: selected ? qsTr("Follows the tint colour on the Colour page") : qsTr("Go back to the tint colour used everywhere")
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
                                Accessible.name: qsTr("Tint colour for this part")
                                HoverHandler { cursorShape: Qt.PointingHandCursor }
                                LgToolTip { shown: partTint.hovered; text: qsTr("Choose a tint colour for this part only") }
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
                                    title: qsTr("Tint colour")
                                    color: partTint.shown
                                    onPicked: (hex) => Backend.setPart(partsCard.part, "tint", hex)
                                }
                            }
                        }
                    }
                    OverrideSlider {
                        objectName: "partBend"
                        visible: partsCard.hasLens
                        inline: true
                        label: qsTr("Bend")
                        autoText: qsTr("Same as everywhere")
                        autoTip: qsTr("Follows Bend under Glass effects on the Glass page")
                        resetTip: qsTr("Go back to the bend used everywhere")
                        tip: qsTr("How strongly this part's rounded edge bends what's behind it. Left is flat glass; right is a thick lens.")
                        value: partsCard.val("refraction")
                        autoValue: Backend.refraction
                        onChanged: (v) => { partsCard.setOrClear("refraction", v); partsCard.peek() }
                    }
                    OverrideSlider {
                        objectName: "partBleed"
                        visible: partsCard.hasBleed
                        inline: true
                        label: qsTr("Colour bleed")
                        autoText: qsTr("Same as everywhere")
                        autoTip: qsTr("Follows Colour bleed under Glass effects on the Glass page")
                        resetTip: qsTr("Go back to the colour bleed used everywhere")
                        tip: qsTr("How much the colours of icons and text light up the glass of this part. Left keeps it neutral; right gives them a coloured glow.")
                        value: partsCard.val("bleed")
                        autoValue: Backend.bleed
                        onChanged: (v) => partsCard.setOrClear("bleed", v)
                    }
                    OverrideSlider {
                        objectName: "partReflections"
                        visible: partsCard.hasLens
                        inline: true
                        label: qsTr("Edge reflections")
                        autoText: qsTr("Same as everywhere")
                        autoTip: qsTr("Follows the default edge reflections")
                        resetTip: qsTr("Go back to the default edge reflections")
                        tip: qsTr("How strongly the edge of this part catches reflections of its surroundings. Left shows none; right gives bright, mirror-like edges.")
                        value: partsCard.val("reflections")
                        autoValue: Backend.highlight
                        onChanged: (v) => { partsCard.setOrClear("reflections", v); partsCard.peek() }
                    }
                    Item {
                        width: parent.width
                        height: 44
                        LgButton {
                            objectName: "resetPart"
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            kind: "flat"
                            implicitHeight: 32
                            leftPadding: 12; rightPadding: 12
                            text: qsTr("Reset %1").arg(Qt.uiLanguage === "de" ? partsCard.info.label : partsCard.info.label.toLocaleLowerCase())  // German nouns keep their capital
                            iconName: "undo"
                            enabled: partsCard.any
                            tip: qsTr("Make this part look like the rest of the desktop again")
                            onClicked: Backend.resetPart(partsCard.part)
                        }
                    }
                }
            }
        }
    }

    Fold {
        id: fine
        objectName: "fineTune"
        title: qsTr("Fine-tune")
        summary: qsTr("Transparency, blur, terminal opacity, reduce transparency")
        Column {
            width: parent.width
            spacing: 18
            OverrideSlider {
                objectName: "fineOpacity"
                label: qsTr("Transparency")
                caption: qsTr("How solid panels and header bars look")
                value: Backend.opacity
                autoValue: Backend.autoValues.opacity
                onChanged: (v) => Backend.opacity = v
                autoTip: qsTr("Follows How much glass on the Glass page")
                resetTip: qsTr("Go back to following How much glass")
                tip: qsTr("How solid panels and header bars look. Left is see-through; right is nearly solid.")
                format: (v) => qsTr("%1% solid").arg(Math.round(v * 100))
            }
            OverrideSlider {
                objectName: "fineBlur"
                label: qsTr("Blur")
                value: Backend.blur
                autoValue: Backend.autoValues.blur
                from: 0; to: 100; stepSize: 1
                format: (v) => qsTr("%1 px").arg(Math.round(v))
                autoTip: qsTr("Follows How much glass on the Glass page")
                resetTip: qsTr("Go back to following How much glass")
                tip: qsTr("How much the background behind glass is blurred. Left shows it sharp; right melts it into soft colour.")
                onChanged: (v) => Backend.blur = v
            }
            OverrideSlider {
                objectName: "fineTerminalOpacity"
                label: qsTr("Terminal opacity")
                value: Backend.terminalOpacity
                autoValue: Backend.autoValues.terminal_opacity
                from: 0.3; to: 1
                autoTip: qsTr("Follows How much glass on the Glass page")
                resetTip: qsTr("Go back to following How much glass")
                tip: qsTr("How see-through terminal windows are. Left lets the desktop show through; right is a solid background.")
                onChanged: (v) => Backend.terminalOpacity = v
            }
            SwitchRow {
                objectName: "reduceTransparency"
                label: qsTr("Reduce transparency")
                caption: qsTr("Nearly opaque surfaces and no blur, for readability")
                tip: qsTr("Makes every surface nearly solid and turns the blur off. Easier to read, but no longer see-through.")
                checked: Backend.reduceTransparency
                onToggled: (on) => Backend.reduceTransparency = on
            }
            LgButton {
                objectName: "fineReset"
                readonly property var keys: ["opacity", "blur", "terminal_opacity", "reduce_transparency"]
                visible: Backend.changedFromDefault.some((k) => keys.indexOf(k) >= 0)
                kind: "flat"
                implicitHeight: 32
                text: qsTr("Reset fine-tune")
                iconName: "undo"
                leftPadding: 12
                tip: qsTr("Let How much glass decide these again (Apply to use it)")
                onClicked: Backend.resetSettings(keys)
            }
        }
    }

    Card {
        objectName: "startOverCard"
        width: parent.width
        height: implicitHeight
        Item {
            width: parent.width
            height: Math.max(startText.height, resetAll.height)
            Column {
                id: startText
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - resetAll.width - 16
                spacing: 3
                Text { text: qsTr("Start over"); color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.DemiBold }
                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: Backend.canResetAll
                          ? qsTr("Every look setting back to its default. The apps you picked stay. Applied after Apply, and Undo takes it back until then.")
                          : qsTr("Every look setting is at its default.")
                    color: Theme.textFaint
                    font.pixelSize: Theme.fsSmall
                }
            }
            LgButton {
                id: resetAll
                objectName: "resetAll"
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                kind: "secondary"
                implicitHeight: 36
                leftPadding: 16; rightPadding: 16
                text: qsTr("Reset all")
                enabled: Backend.canResetAll
                tip: qsTr("Back to the default look on every page (Apply to use it)")
                onClicked: Backend.resetDefaults()
            }
        }
    }

    side: [
        Item { id: slot; objectName: "advancedPreviewSlot"; width: parent.width; height: page.previewH },
        PreviewNote { text: qsTr("Click a part of the preview to give it its own look.") }
    ]
}
