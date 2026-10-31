import QtQuick
import LiquidGlass.Core

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
        SectionTitle { text: "Window header bars" }
        Text {
            width: parent.width
            wrapMode: Text.WordWrap
            color: Theme.textFaint
            font.pixelSize: Theme.fsSmall
            text: "The bar along the top of Files, Terminal, Settings and other GNOME apps. Apps opened after Apply show the change."
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
                        text: noteCol.done ? "Files shows the new bars the next time you open it. Terminal does once all its windows are closed."
                                           : "Open apps keep the old bars until reopened. Terminal updates once all its windows are closed. Files keeps running in the background, so restart it here."
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
                    text: "Restart Files"
                    iconName: "refresh"
                    tip: "Closes all open Files windows so Files starts fresh with the new bars. Terminal is left alone."
                    onClicked: Backend.restartFiles()
                }
            }
        }
        LabeledSlider {
            objectName: "headerHeight"
            label: "Height"
            from: 36; to: 64; stepSize: 1
            value: Backend.headerHeight
            format: (v) => Math.round(v) === root.gnomeHeight ? Math.round(v) + " px · GNOME default" : Math.round(v) + " px"
            onMoved: (v) => Backend.headerHeight = v
            tip: "Sets how tall the bar at the top of app windows is. 47 px is GNOME's normal size."
        }
        OverrideSlider {
            objectName: "headerOpacity"
            label: "See-through"
            caption: "Glass of the header bar only"
            value: Backend.headerOpacity
            autoValue: root.windowAlpha
            from: 0.1; to: 1
            format: (v) => Math.round(v * 100) + "% solid"
            onChanged: (v) => Backend.headerOpacity = v
            autoText: "Window"
            autoTip: "The header bar uses the same glass as the rest of the window"
            resetTip: "Go back to the same glass as the rest of the window"
            tip: "Sets how much of the desktop shows through the bar at the top of app windows. Left is clearer, right is more solid."
        }
        // Terminal draws its top bar from its colour palette, so the glass only reaches it
        // with the Liquid Glass palette. Never switched without the user asking.
        Rectangle {
            objectName: "terminalColors"
            readonly property string pal: Backend.terminalPalette
            readonly property bool own: pal !== "" && pal !== Backend.liquidGlassPalette
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
                              ? "Terminal switches to Liquid Glass colours when you Apply, and its top bar turns to glass."
                              : "Terminal uses its own colours (" + termCol.palName + "), so its top bar stays solid."
                    }
                }
                LgButton {
                    objectName: "useTerminalColors"
                    x: 28
                    kind: termCol.chosen ? "flat" : "secondary"
                    implicitHeight: 32
                    leftPadding: 14; rightPadding: 14
                    tipBelow: true
                    text: termCol.chosen ? "Keep my colours" : "Use Liquid Glass terminal colours"
                    tip: termCol.chosen
                         ? "Leaves Terminal on " + termCol.palName + ". Its top bar stays solid."
                         : "Changes Terminal's text and background colours to the Liquid Glass palette, which also turns its top bar to glass. Restore original brings your own colours back."
                    onClicked: Backend.terminalColors = !termCol.chosen
                }
            }
        }
        SwitchRow {
            objectName: "terminalFollowsStyle"
            width: parent.width
            label: "Terminal follows light and dark"
            caption: "Terminal is dark on its own, even in light mode"
            tip: "Terminal has its own light/dark setting, which starts out dark. Turn this on and Terminal follows GNOME's light or dark style like your other apps. Turn it off, or Restore original, and Terminal goes back to your own setting."
            checked: Backend.terminalFollowsStyle
            onToggled: (on) => Backend.terminalFollowsStyle = on
        }
        SwitchRow {
            objectName: "qtGnomeTitlebars"
            width: parent.width
            label: "Qt apps get the same title bar"
            caption: "For apps like qBittorrent. Applies after you log out and back in"
            tip: "Qt apps draw their own title bar in fixed colours that no theme can change. Turn this on and they open through GNOME's X11 support instead, so GNOME draws their title bar exactly like your other apps. Two trade-offs: through X11 an app is less sealed off than on Wayland, so other X11 apps can see what you type into it, and with fractional scaling (such as 125%) it can look a little soft. Flatpak apps keep their own bar. Turn it off, or Restore original, to go back."
            checked: Backend.qtGnomeTitlebars
            onToggled: (on) => Backend.qtGnomeTitlebars = on
        }
    }
}
