import QtQuick
import QtQuick.Controls.Basic as C
import LiquidGlass.Core

// One target: name, summary, availability, notes and its on/off switch.
Item {
    id: row
    property var item: ({})
    property bool first: false
    readonly property bool available: item.available === true
    readonly property bool on: item.enabled === true
    readonly property var notes: item.notes || []
    property bool notesOpen: false

    implicitHeight: body.height + 32

    Rectangle {
        visible: !row.first
        x: 20; width: parent.width - 40; height: 1
        color: Theme.divider
    }

    Item {
        id: body
        x: 20; y: 16
        width: parent.width - 40
        height: Math.max(info.height, 32)

        Rectangle {     // status dot
            id: dot
            y: 6
            width: 10; height: 10; radius: 5
            color: !row.available ? Theme.textFaint : row.on ? Theme.good : Theme.warn
            opacity: row.available ? 1 : 0.6
        }

        Column {
            id: info
            x: 24
            width: parent.width - 24 - sw.width - 16
            spacing: 4
            Row {
                spacing: 8
                Text {
                    text: row.item.name || row.item.id
                    color: Theme.text
                    font.pixelSize: Theme.fsBody
                    font.weight: Font.DemiBold
                }
                Rectangle {
                    visible: !row.available
                    anchors.verticalCenter: parent.verticalCenter
                    height: 20
                    width: naLabel.implicitWidth + 16
                    radius: 10
                    color: Theme.well
                    Text { id: naLabel; anchors.centerIn: parent; text: "Not available"; color: Theme.textDim; font.pixelSize: 11; font.weight: Font.DemiBold }
                }
                Rectangle {
                    visible: row.available && !row.on
                    anchors.verticalCenter: parent.verticalCenter
                    height: 20
                    width: offLabel.implicitWidth + 16
                    radius: 10
                    color: Theme.alpha(Theme.warn, 0.16)
                    Text { id: offLabel; anchors.centerIn: parent; text: "Off"; color: Theme.warn; font.pixelSize: 11; font.weight: Font.DemiBold }
                }
            }
            Text {
                width: parent.width
                text: row.item.summary || ""
                color: Theme.textDim
                font.pixelSize: 13
                wrapMode: Text.WordWrap
                lineHeight: 1.1
            }
            TextEdit {      // often an install command: selectable
                visible: !row.available && (row.item.detail || "").length > 0
                width: parent.width
                text: row.item.detail || ""
                readOnly: true
                selectByMouse: true
                color: Theme.warn
                selectionColor: Theme.alpha(Theme.accent, 0.4)
                font.pixelSize: 13
                wrapMode: TextEdit.Wrap
            }
            C.AbstractButton {
                id: notesToggle
                visible: row.notes.length > 0
                height: 26
                width: notesLabel.implicitWidth + 26
                hoverEnabled: true
                focusPolicy: Qt.StrongFocus
                onClicked: row.notesOpen = !row.notesOpen
                Accessible.name: row.notesOpen ? "Hide notes" : "Show notes"
                HoverHandler { cursorShape: Qt.PointingHandCursor }
                contentItem: Row {
                    spacing: 4
                    Icon {
                        name: "chevronRight"; size: 16; color: Theme.accentText
                        anchors.verticalCenter: parent.verticalCenter
                        rotation: row.notesOpen ? 90 : 0
                        Behavior on rotation { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                    }
                    Text {
                        id: notesLabel
                        anchors.verticalCenter: parent.verticalCenter
                        text: (row.notesOpen ? "Hide " : "") + (row.notes.length === 1 ? "1 note" : row.notes.length + " notes")
                        color: Theme.accentText
                        font.pixelSize: 13
                        font.weight: Font.Medium
                    }
                }
                background: Rectangle {
                    radius: 8
                    color: notesToggle.hovered ? Theme.hover : "transparent"
                    FocusRing { target: notesToggle; radius: 10; gap: 1 }
                }
            }
            Column {
                visible: row.notesOpen
                width: parent.width
                spacing: 6
                Repeater {
                    model: row.notes
                    delegate: Rectangle {
                        required property string modelData
                        width: parent.width
                        height: noteText.height + 16
                        radius: 10
                        color: Theme.well
                        Icon { x: 10; y: 9; name: "info"; size: 15; color: Theme.textDim }
                        TextEdit {      // selectable, so commands and theme strings can be copied
                            id: noteText
                            x: 32; y: 8
                            width: parent.width - 42
                            text: modelData
                            readOnly: true
                            selectByMouse: true
                            wrapMode: TextEdit.Wrap
                            color: Theme.text
                            selectionColor: Theme.alpha(Theme.accent, 0.4)
                            selectedTextColor: Theme.text
                            font.pixelSize: 13
                        }
                    }
                }
            }
        }

        LgSwitch {
            id: sw
            anchors.right: parent.right
            y: 0
            checked: row.on && row.available
            enabled: row.available
            onToggled: Backend.setTargetEnabled(row.item.id, checked)
            Accessible.name: (row.item.name || "") + (row.available ? "" : " (not available)")
            LgToolTip {
                shown: sw.hovered
                text: !row.available ? "Not installed here, so it is skipped" : row.on ? "Themed on Apply" : "Left alone (turning it off later restores it)"
            }
        }
    }
}
