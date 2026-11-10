import QtQuick
import QtQuick.Controls.Basic as C
import FedoraGlass.Core

// The mouse pointer: a style to pick from pictures of each one, and a size.
// Picking changes only the app (the tiles, and the app's own pointer while it is over a
// tile); Apply sets it for the desktop, and Restore original brings the user's own back.
Card {
    id: root
    height: implicitHeight
    // Every choice: the user's own pointer first, then the styles that come with the app.
    readonly property var choices: [{ id: "keep", name: "Keep mine", blurb: Cursors.ownName, credit: "", installed: true }]
                                   .concat(Cursors.styles)
    readonly property real innerW: width - 2 * padding
    readonly property int columns: innerW > 520 ? 3 : 2
    readonly property real tileW: Math.floor((innerW - (columns - 1) * grid.spacing) / columns)

    Column {
        width: parent.width
        spacing: 16
        SectionTitle {
            text: "Mouse pointer"
            caption: "Point at a style to try it here. Apply sets it for the whole desktop; Restore original brings yours back."
        }

        Grid {
            id: grid
            objectName: "cursorGrid"
            width: parent.width
            columns: root.columns
            spacing: 10
            Repeater {
                model: root.choices
                delegate: C.AbstractButton {
                    id: tile
                    required property var modelData
                    readonly property bool selected: Backend.cursorTheme === modelData.id
                    readonly property bool usable: modelData.installed || modelData.id === "keep"
                    objectName: "cursor_" + modelData.id
                    width: root.tileW
                    height: 112
                    hoverEnabled: true
                    focusPolicy: Qt.StrongFocus
                    Accessible.name: "Pointer style " + modelData.name
                    Accessible.role: Accessible.RadioButton
                    Accessible.checked: selected
                    onClicked: Backend.cursorTheme = modelData.id
                    onHoveredChanged: Cursors.tryOn(hovered && usable ? modelData.id : "")
                    Component.onDestruction: if (hovered) Cursors.tryOn("")
                    LgToolTip {
                        shown: tile.hovered && tile.modelData.credit !== ""
                        text: tile.usable ? tile.modelData.credit
                                          : tile.modelData.credit + ". Not installed with this copy of Fedora Glass."
                    }

                    background: Rectangle {
                        radius: Theme.rS
                        color: tile.selected ? Theme.alpha(Theme.accent, Theme.dark ? 0.16 : 0.10)
                               : tile.down ? Theme.wellHi : tile.hovered ? Theme.surfaceHi : Theme.well
                        border.width: tile.selected ? 2 : 1
                        border.color: tile.selected ? Theme.alpha(Theme.accent, 0.8) : Theme.border
                        Behavior on color { ColorAnimation { duration: Theme.fast } }
                        FocusRing { target: tile; radius: Theme.rS }
                    }

                    contentItem: Item {
                        // The pointers over a slice of the user's own wallpaper, as on the desktop.
                        Rectangle {
                            id: stage
                            x: 6; y: 6
                            width: parent.width - 12
                            height: 58
                            radius: Theme.rS - 4
                            clip: true
                            color: "#2a2347"
                            gradient: Backend.wallpaper === "" ? night : null
                            Gradient {
                                id: night
                                orientation: Gradient.Horizontal
                                GradientStop { position: 0; color: "#2b1d5c" }
                                GradientStop { position: 0.55; color: "#7a4fc9" }
                                GradientStop { position: 1; color: "#e8e6f2" }
                            }
                            Image {
                                anchors.fill: parent
                                visible: Backend.wallpaper !== ""
                                source: Backend.wallpaper !== "" ? "file://" + Backend.wallpaper : ""
                                sourceSize.width: 480
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                cache: true
                                opacity: 0.95
                            }
                            // Half light, half dark: a pointer has to read on both.
                            Rectangle {
                                anchors.right: parent.right
                                width: parent.width * 0.36
                                height: parent.height
                                color: Qt.rgba(1, 1, 1, 0.82)
                            }
                            Row {
                                anchors.centerIn: parent
                                spacing: Math.max(2, (stage.width - 4 * 32) / 6)
                                Repeater {
                                    model: ["left_ptr", "hand2", "xterm", "left_ptr_watch"]
                                    delegate: Image {
                                        required property string modelData
                                        width: 32; height: 32
                                        sourceSize: Qt.size(64, 64)
                                        smooth: true
                                        mipmap: true
                                        // The tile reloads when the user's own pointer changes.
                                        source: "image://lgcursor/" + tile.modelData.id + "/" + modelData
                                                + (tile.modelData.id === "keep" ? "?" + Cursors.ownName : "")
                                        opacity: tile.usable ? 1 : 0.35
                                    }
                                }
                            }
                        }
                        Column {
                            x: 10
                            anchors.top: stage.bottom
                            anchors.topMargin: 7
                            width: parent.width - 20 - (tile.selected ? 22 : 0)
                            spacing: 1
                            Text {
                                width: parent.width
                                text: tile.modelData.name
                                elide: Text.ElideRight
                                color: tile.selected ? Theme.accentText : Theme.text
                                font.pixelSize: 13
                                font.weight: tile.selected ? Font.DemiBold : Font.Medium
                            }
                            Text {
                                width: parent.width
                                text: tile.usable ? tile.modelData.blurb : "Not installed"
                                elide: Text.ElideRight
                                color: Theme.textFaint
                                font.pixelSize: 11
                            }
                        }
                        Icon {
                            visible: tile.selected
                            anchors.right: parent.right
                            anchors.rightMargin: 10
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 12
                            name: "check"
                            size: 16
                            color: Theme.accentText
                        }
                    }
                }
            }
        }

        Column {
            width: parent.width
            spacing: 8
            Text { text: "Size"; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
            Segmented {
                objectName: "cursorSize"
                width: parent.width
                model: [{ value: 0, label: "Keep mine", tip: "Leave the pointer size as it is now" },
                        { value: 24, label: "Normal", tip: "GNOME's normal pointer size" },
                        { value: 32, label: "Large", tip: "A third bigger than normal" },
                        { value: 48, label: "Larger", tip: "Twice the normal size" }]
                value: Backend.cursorSize
                onActivated: (v) => Backend.cursorSize = v
                Accessible.name: "Pointer size"
            }
        }
    }
}
