import QtQuick
import FedoraGlass.Core

// Day and night: a saved look for GNOME's light style and one for its dark style. When
// GNOME switches, the watcher (fedora-glass watch) puts the matching look on the desktop.
// This is the one thing that changes the desktop without Apply, so the caption says so.
// The picks are saved at once (they say what happens at the next switch, not how it looks
// now). Without saved looks the card is one line on how to start; with Style set to Dark
// or Light (not following GNOME) the picks show, but can't be changed, and say why.
Card {
    id: card
    objectName: "dayNight"
    padding: 16
    height: implicitHeight

    readonly property var looks: Backend.savedLooks
    readonly property bool hasLooks: looks.length > 0
    readonly property bool follows: Backend.scheme === "auto"
    readonly property var choices: {
        const out = [{ value: "", label: qsTr("Same look") }]
        for (let i = 0; i < looks.length; i++)
            out.push({ value: looks[i].id, label: looks[i].name })
        return out
    }
    // A look picked here and then deleted outside the app reads as no look.
    function shown(id) { return looks.some(l => l.id === id) ? id : "" }

    Column {
        width: parent.width
        spacing: 10

        Column {
            width: parent.width
            spacing: 4
            Text {
                text: qsTr("Day and night")
                color: Theme.text
                font.pixelSize: Theme.fsTitle
                font.weight: Font.DemiBold
            }
            Text {
                objectName: "dayNightCaption"
                width: parent.width
                wrapMode: Text.WordWrap
                text: !card.hasLooks
                      ? qsTr("Save two looks to switch between them with GNOME's light and dark style.")
                      : card.follows
                      ? qsTr("When GNOME turns light or dark, the matching look goes on your desktop without Apply.")
                      : qsTr("Works only when Style is Auto, so it follows GNOME.")
                color: Theme.textDim
                font.pixelSize: Theme.fsSmall + 1
                lineHeight: 1.1
            }
        }

        Row {
            id: picks
            visible: card.hasLooks
            width: parent.width
            spacing: 10
            readonly property real colW: (width - spacing) / 2
            Pick {
                width: picks.colW
                iconName: "sun"
                label: qsTr("Light style")
                name: "dayNightLight"
                accessibleName: qsTr("Look for the light style")
                value: card.shown(Backend.lookForLight)
                onPicked: (v) => Backend.lookForLight = v
            }
            Pick {
                width: picks.colW
                iconName: "moon"
                label: qsTr("Dark style")
                name: "dayNightDark"
                accessibleName: qsTr("Look for the dark style")
                value: card.shown(Backend.lookForDark)
                onPicked: (v) => Backend.lookForDark = v
            }
        }
    }

    component Pick: Column {
        id: pick
        property string iconName: ""
        property string label: ""
        property string name: ""
        property string accessibleName: ""
        property string value: ""
        signal picked(string v)
        spacing: 6
        Row {
            spacing: 6
            opacity: card.follows ? 1 : 0.6
            Icon {
                anchors.verticalCenter: parent.verticalCenter
                name: pick.iconName
                size: 14
                strokeWidth: 1.8
                color: Theme.textDim
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: pick.label
                color: Theme.textDim
                font.pixelSize: Theme.fsSmall + 1
                font.weight: Font.Medium
            }
        }
        LgDropdown {
            objectName: pick.name
            width: parent.width
            glyphs: false
            enabled: card.follows
            model: card.choices
            value: pick.value
            Accessible.name: pick.accessibleName
            onActivated: (v) => pick.picked(String(v))
        }
    }
}
