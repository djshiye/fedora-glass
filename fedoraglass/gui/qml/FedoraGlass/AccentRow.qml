import QtQuick
import FedoraGlass.Core

// The accent colours: the system one, GNOME's nine, and a custom colour.
// One Tab stop; the arrow keys move along the row.
Row {
    objectName: "accentRow"
    id: swatches
    width: parent.width
    spacing: 4
    property real maxSize: 30
    readonly property real d: Math.min(maxSize, Math.floor((width - 10 * spacing) / 11))
    // One Tab stop: the chosen colour (the system one when none matches).
    readonly property bool known: Backend.accent === "system" || Backend.accent.startsWith("#")
                                  || Backend.accents.some(a => a.id === Backend.accent)
    Swatch {
        objectName: "accentSystem"
        size: swatches.d
        swatch: Backend.accents.find(a => a.id === Backend.systemAccent)?.color ?? "#3584e4"
        split: true
        rovingGroup: swatches
        rovingStop: selected || !swatches.known
        selected: Backend.accent === "system"
        tip: qsTr("System accent (follows GNOME Settings)")
        onClicked: Backend.accent = "system"
    }
    Repeater {
        model: Backend.accents
        delegate: Swatch {
            required property var modelData
            objectName: "accent_" + modelData.id
            size: swatches.d
            rovingGroup: swatches
            swatch: modelData.color
            selected: Backend.accent === modelData.id
            tip: modelData.label
            onClicked: Backend.accent = modelData.id
        }
    }
    Swatch {
        id: customAccent
        objectName: "accentCustom"
        size: swatches.d
        rovingGroup: swatches
        readonly property bool isCustom: Backend.accent.startsWith("#")
        swatch: isCustom ? Backend.accent : "#888888"
        rainbow: !isCustom
        selected: isCustom
        tip: qsTr("Custom colour…")
        onClicked: accentPicker.open()
        ColorPicker {
            id: accentPicker
            y: parent.height + 8
            x: parent.width - width
            title: qsTr("Custom accent")
            color: customAccent.isCustom ? Backend.accent : Theme.accent
            onPicked: (hex) => Backend.accent = hex
        }
    }
}