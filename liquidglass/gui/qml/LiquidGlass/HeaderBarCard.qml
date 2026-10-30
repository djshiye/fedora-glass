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
            text: "The bar along the top of Files, Terminal, Settings and other GNOME apps. Apps opened after Apply show the change. Files and Terminal keep running after you close them, so they update after you log out and back in."
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
    }
}
