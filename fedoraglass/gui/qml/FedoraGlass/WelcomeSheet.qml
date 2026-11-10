import QtQuick
import QtQuick.Controls.Basic as C
import QtQuick.Effects
import FedoraGlass.Core

// First launch only: what the app does, a starting look to pick, and the
// promise that nothing changes until Apply. Closing it in any way marks it seen.
Sheet {
    id: sheet
    objectName: "welcomeSheet"
    title: "Welcome to Fedora Glass"
    subtitle: "Glass for your panel, menus, lock screen and apps. Try anything here: your desktop only changes when you press Apply."
    iconName: "sparkle"
    width: Math.min(680, (parent ? parent.width : 800) - 64)
    onClosed: Backend.dismissWelcome()

    readonly property var looks: [
        { name: "Liquid", caption: "Clear and bright", blur: 0.25, haze: 0.04 },
        { name: "Balanced", caption: "Readable, still glassy", blur: 0.6, haze: 0.14 },
        { name: "Frosted", caption: "Calm, milky frost", blur: 1.0, haze: 0.32 }
    ]

    // Nothing changes on the desktop until a button that says Apply: "Customise first"
    // only closes the welcome, "Apply this look" applies the look picked above.
    buttons: [
        LgButton {
            objectName: "welcomeStart"
            text: "Customise first"
            kind: "secondary"
            onClicked: sheet.close()
        },
        LgButton {
            objectName: "welcomeApply"
            text: "Apply this look"
            kind: "primary"
            iconName: "check"
            leftPadding: 18; rightPadding: 22
            enabled: !Backend.busy
            tip: "Applies the look you picked to your desktop and apps. Restore original undoes it."
            onClicked: { sheet.close(); Backend.dismissWelcome(); Backend.apply() }
        }
    ]

    Column {
        width: parent.width
        spacing: 20

        Column {
            width: parent.width
            spacing: 10
            Text { text: "Pick a starting look"; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.DemiBold }
            Row {
                id: tiles
                width: parent.width
                spacing: 12
                readonly property real tileW: (width - 2 * spacing) / 3
                Repeater {
                    model: sheet.looks
                    delegate: C.AbstractButton {
                        id: tile
                        required property var modelData
                        objectName: "welcomeLook" + modelData.name
                        readonly property bool selected: Backend.activePreset === modelData.name
                        width: tiles.tileW
                        height: pic.height + 54
                        hoverEnabled: true
                        focusPolicy: Qt.StrongFocus
                        Accessible.name: modelData.name + ": " + modelData.caption
                        onClicked: Backend.applyPreset(modelData.name)
                        HoverHandler { cursorShape: Qt.PointingHandCursor }

                        background: Rectangle {
                            radius: Theme.rM
                            color: tile.selected ? Theme.alpha(Theme.accent, Theme.dark ? 0.16 : 0.10)
                                 : tile.hovered ? Theme.surfaceHi : Theme.well
                            border.width: tile.selected ? 2 : 1
                            border.color: tile.selected ? Theme.accent : Theme.border
                            Behavior on color { ColorAnimation { duration: Theme.fast } }
                            FocusRing { target: tile; radius: Theme.rM + 3 }
                        }
                        contentItem: Item {
                            // A little scene: the wallpaper with a pane of this glass on it.
                            Item {
                                id: pic
                                x: 6; y: 6
                                width: parent.width - 12
                                height: Math.round(width * 0.56)
                                layer.enabled: true
                                layer.effect: MultiEffect {
                                    maskEnabled: true
                                    maskSource: picMask
                                    maskThresholdMin: 0.5
                                    maskSpreadAtMin: 1.0
                                }
                                Rectangle {
                                    anchors.fill: parent
                                    gradient: Gradient {
                                        GradientStop { position: 0; color: "#3a2a6e" }
                                        GradientStop { position: 1; color: "#0d1030" }
                                    }
                                }
                                Image {
                                    id: wall
                                    anchors.fill: parent
                                    source: Backend.wallpaper
                                    sourceSize.width: 480
                                    fillMode: Image.PreserveAspectCrop
                                    asynchronous: true
                                }
                                // The pane: the same wallpaper, blurred and hazed, in a rounded glass shape.
                                Item {
                                    id: pane
                                    x: parent.width * 0.16; y: parent.height * 0.22
                                    width: parent.width * 0.68; height: parent.height * 0.56
                                    layer.enabled: true
                                    layer.effect: MultiEffect {
                                        maskEnabled: true
                                        maskSource: paneMask
                                        maskThresholdMin: 0.5
                                        maskSpreadAtMin: 1.0
                                    }
                                    MultiEffect {
                                        x: -pane.x; y: -pane.y
                                        width: pic.width; height: pic.height
                                        source: wall
                                        visible: wall.status === Image.Ready
                                        blurEnabled: true
                                        blur: tile.modelData.blur
                                        blurMax: 48
                                        saturation: 0.15
                                        autoPaddingEnabled: false
                                    }
                                    Rectangle {
                                        anchors.fill: parent
                                        color: Qt.rgba(1, 1, 1, tile.modelData.haze)
                                    }
                                    // Rim light along the top edge
                                    Rectangle {
                                        anchors.fill: parent
                                        radius: 10
                                        color: "transparent"
                                        border.width: 1
                                        border.color: Qt.rgba(1, 1, 1, 0.35)
                                    }
                                }
                                Rectangle {
                                    id: paneMask
                                    width: pane.width; height: pane.height
                                    radius: 10
                                    visible: false
                                    layer.enabled: true
                                }
                            }
                            Rectangle {
                                id: picMask
                                width: pic.width; height: pic.height
                                radius: Theme.rM - 6
                                visible: false
                                layer.enabled: true
                            }
                            Column {
                                x: 12
                                y: pic.y + pic.height + 9
                                width: parent.width - 24
                                spacing: 1
                                Text {
                                    text: tile.modelData.name
                                    color: tile.selected ? Theme.accentText : Theme.text
                                    font.pixelSize: Theme.fsBody
                                    font.weight: Font.DemiBold
                                }
                                Text {
                                    width: parent.width
                                    elide: Text.ElideRight
                                    text: tile.modelData.caption
                                    color: Theme.textDim
                                    font.pixelSize: Theme.fsSmall
                                }
                            }
                            Rectangle {     // check badge on the chosen look
                                visible: tile.selected
                                anchors.right: parent.right
                                anchors.rightMargin: 14
                                y: pic.y + pic.height + 14
                                width: 22; height: 22; radius: 11
                                color: Theme.accent
                                Icon { anchors.centerIn: parent; name: "check"; size: 14; strokeWidth: 2.2; color: Theme.accentFg }
                            }
                        }
                    }
                }
            }
            // What this desktop is made of, so the look above clearly fits it.
            Text {
                objectName: "welcomeFound"
                visible: text.length > 0
                width: parent.width
                text: Backend.foundSummary
                color: Theme.textDim
                font.pixelSize: Theme.fsSmall
                wrapMode: Text.WordWrap
            }
        }

        // How the app works, in three steps.
        Rectangle {
            width: parent.width
            height: steps.height + 32
            radius: Theme.rM
            color: Theme.well
            Row {
                id: steps
                x: 16; y: 16
                width: parent.width - 32
                spacing: 16
                readonly property real stepW: (width - 2 * spacing) / 3
                Repeater {
                    model: [
                        { icon: "eye", title: "Try it here", text: "The preview shows every change straight away." },
                        { icon: "check", title: "Press Apply", text: "Your apps change at once. Restart once for the glass." },
                        { icon: "undo", title: "Undo any time", text: "Restore original puts everything back." }
                    ]
                    delegate: Row {
                        required property var modelData
                        width: steps.stepW
                        spacing: 10
                        Rectangle {
                            width: 30; height: 30; radius: 15
                            color: Theme.alpha(Theme.accent, Theme.dark ? 0.2 : 0.14)
                            Icon { anchors.centerIn: parent; name: modelData.icon; size: 16; color: Theme.accentText }
                        }
                        Column {
                            width: parent.width - 40
                            spacing: 2
                            Text { text: modelData.title; color: Theme.text; font.pixelSize: 13; font.weight: Font.DemiBold }
                            Text {
                                width: parent.width
                                text: modelData.text
                                wrapMode: Text.WordWrap
                                color: Theme.textDim
                                font.pixelSize: Theme.fsSmall
                            }
                        }
                    }
                }
            }
        }
        Item { width: 1; height: 1 }
    }
}
