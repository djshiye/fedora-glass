import QtQuick
import FedoraGlass.Core

// Window header bars: how tall they are and how see-through, for GTK 3, GTK 4 and libadwaita apps.
Card {
    id: root
    readonly property int gnomeHeight: 47
    // How solid the window glass is right now; the header follows it until the user drags.
    readonly property real windowAlpha: Backend.tokens.window ? Backend.tokens.window.a : 0.7
    height: implicitHeight

    Column {
        width: parent.width
        spacing: 16
        SectionTitle {
            text: qsTr("Window header bars")
            resetKeys: ["header_height", "header_opacity", "terminal_colors", "terminal_follows_style", "qt_gnome_titlebars"]
            caption: qsTr("The bar along the top of Files, Terminal, Settings and other GNOME apps")
        }
        // After Apply: open apps keep the old bars, and Files keeps running in the background.
        Rectangle {
            objectName: "headerNote"
            visible: Backend.headerNote !== ""
            width: parent.width
            height: noteCol.implicitHeight + 24
            radius: Theme.rS
            color: Theme.well
            Column {
                id: noteCol
                readonly property bool done: Backend.headerNote === "restarted"
                x: 14; y: 12
                width: parent.width - 28
                spacing: 10
                Row {
                    width: parent.width
                    spacing: 10
                    Icon {
                        name: noteCol.done ? "okCircle" : "info"
                        color: noteCol.done ? Theme.good : Theme.accentText
                        size: 18
                    }
                    Text {
                        width: parent.width - 28
                        wrapMode: Text.WordWrap
                        color: Theme.textDim
                        font.pixelSize: Theme.fsSmall
                        lineHeight: 1.15
                        text: noteCol.done ? qsTr("Files shows the new bars the next time you open it. Terminal does once all its windows are closed.")
                                           : qsTr("Open apps keep the old bars until reopened. Terminal updates once all its windows are closed. Files keeps running in the background, so restart it here.")
                    }
                }
                LgButton {
                    objectName: "restartFiles"
                    visible: !noteCol.done && Backend.canRestartFiles
                    x: 28
                    kind: "secondary"
                    implicitHeight: 32
                    leftPadding: 14; rightPadding: 14
                    tipBelow: true
                    text: qsTr("Restart Files")
                    iconName: "refresh"
                    tip: qsTr("Closes all open Files windows so Files starts fresh with the new bars. Terminal is left alone.")
                    onClicked: Backend.restartFiles()
                }
            }
        }
        LabeledSlider {
            objectName: "headerHeight"
            label: qsTr("Height")
            from: 36; to: 64; stepSize: 1
            value: Backend.headerHeight
            defaultValue: Backend.defaults.header_height
            format: (v) => Math.round(v) === root.gnomeHeight ? qsTr("%1 px · GNOME default").arg(Math.round(v)) : qsTr("%1 px").arg(Math.round(v))
            onMoved: (v) => Backend.headerHeight = v
            tip: qsTr("Sets how tall the bar at the top of app windows is. 47 px is GNOME's normal size.")
        }
        OverrideSlider {
            objectName: "headerOpacity"
            label: qsTr("Opacity")
            caption: qsTr("How solid the header bar's glass is")
            value: Backend.headerOpacity
            autoValue: root.windowAlpha
            from: 0.1; to: 1
            format: (v) => qsTr("%1% solid").arg(Math.round(v * 100))
            onChanged: (v) => Backend.headerOpacity = v
            autoText: qsTr("Window")
            autoTip: qsTr("The header bar uses the same glass as the rest of the window")
            resetTip: qsTr("Go back to the same glass as the rest of the window")
            tip: qsTr("Sets how much of the desktop shows through the bar at the top of app windows. Left is clearer, right is more solid.")
        }
        Fold {
            objectName: "terminalQtFold"
            card: false
            divider: true
            title: qsTr("Terminal and Qt apps")
            summary: qsTr("Light and dark, colours, Qt title bars")
            Column {
                width: parent.width
                spacing: 12
                // Terminal draws its top bar from its colour palette, so the glass only reaches it
                // with the Fedora Glass palette. Never switched without the user asking.
                Rectangle {
                    objectName: "terminalColors"
                    readonly property string pal: Backend.terminalPalette
                    readonly property bool own: pal !== "" && pal !== Backend.fedoraGlassPalette
                    visible: own
                    width: parent.width
                    height: termCol.implicitHeight + 24
                    radius: Theme.rS
                    color: Theme.well
                    Column {
                        id: termCol
                        readonly property bool chosen: Backend.terminalColors
                        readonly property string palName: parent.pal === "gnome" ? "GNOME" : parent.pal.charAt(0).toUpperCase() + parent.pal.slice(1)
                        x: 14; y: 12
                        width: parent.width - 28
                        spacing: 10
                        Row {
                            width: parent.width
                            spacing: 10
                            Icon { name: termCol.chosen ? "check" : "info"; color: termCol.chosen ? Theme.good : Theme.textDim; size: 18 }
                            Text {
                                width: parent.width - 28
                                wrapMode: Text.WordWrap
                                color: Theme.textDim
                                font.pixelSize: Theme.fsSmall
                                lineHeight: 1.15
                                text: termCol.chosen
                                      ? qsTr("Terminal switches to Fedora Glass colours when you Apply, and its top bar turns to glass.")
                                      : qsTr("Terminal uses its own colours (%1), so its top bar stays solid.").arg(termCol.palName)
                            }
                        }
                        LgButton {
                            objectName: "useTerminalColors"
                            x: 28
                            kind: termCol.chosen ? "flat" : "secondary"
                            implicitHeight: 32
                            leftPadding: 14; rightPadding: 14
                            tipBelow: true
                            text: termCol.chosen ? qsTr("Keep my colours") : qsTr("Use Fedora Glass terminal colours")
                            tip: termCol.chosen
                                 ? qsTr("Leaves Terminal on %1. Its top bar stays solid.").arg(termCol.palName)
                                 : qsTr("Changes Terminal's text and background colours to the Fedora Glass palette, which also turns its top bar to glass. Restore original brings your own colours back.")
                            onClicked: Backend.terminalColors = !termCol.chosen
                        }
                    }
                }
                SwitchRow {
                    objectName: "terminalFollowsStyle"
                    width: parent.width
                    label: qsTr("Terminal follows light and dark")
                    caption: qsTr("Terminal is dark on its own, even in light mode")
                    tip: qsTr("Terminal has its own light/dark setting, which starts out dark. Turn this on and Terminal follows GNOME's light or dark style like your other apps. Turn it off, or Restore original, and Terminal goes back to your own setting.")
                    checked: Backend.terminalFollowsStyle
                    onToggled: (on) => Backend.terminalFollowsStyle = on
                }
                SwitchRow {
                    objectName: "qtGnomeTitlebars"
                    width: parent.width
                    label: qsTr("Qt apps get the same title bar")
                    caption: qsTr("For apps like qBittorrent. Applies after you restart your PC")
                    tip: qsTr("Qt apps draw their own title bar in fixed colours that no theme can change. Turn this on and they open through GNOME's X11 support instead, so GNOME draws their title bar exactly like your other apps. Two trade-offs: through X11 an app is less sealed off than on Wayland, so other X11 apps can see what you type into it, and with fractional scaling (such as 125%) it can look slightly soft. Flatpak apps keep their own bar. Turn it off, or Restore original, to go back.")
                    checked: Backend.qtGnomeTitlebars
                    onToggled: (on) => Backend.qtGnomeTitlebars = on
                }
                // While it is on, the trade-off stays in view, not only in the tooltip.
                Rectangle {
                    objectName: "qtGnomeTitlebarsNote"
                    visible: Backend.qtGnomeTitlebars
                    width: parent.width
                    height: visible ? qtNote.implicitHeight + 20 : 0
                    radius: Theme.rS
                    color: Theme.alpha(Theme.warn, Theme.dark ? 0.10 : 0.12)
                    Row {
                        id: qtNote
                        x: 12; y: 10
                        width: parent.width - 24
                        spacing: 10
                        Icon { name: "alert"; color: Theme.warn; size: 18 }
                        Text {
                            width: parent.width - 28
                            wrapMode: Text.WordWrap
                            color: Theme.text
                            font.pixelSize: Theme.fsSmall
                            lineHeight: 1.15
                            text: qsTr("X11 keeps apps less separated: other X11 apps can see what you type in them. Leave this off if you use a Qt password manager such as KeePassXC.")
                        }
                    }
                }
            }
        }
    }
}
