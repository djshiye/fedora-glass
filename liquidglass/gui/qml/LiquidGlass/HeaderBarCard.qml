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
            text: "The bar along the top of Files, Settings, Text Editor and other GNOME apps. Open apps pick changes up when restarted. Terminal takes the height; its glass follows Terminal opacity."
        }
        LabeledSlider {
            objectName: "headerHeight"
            label: "Height"
            from: 36; to: 64; stepSize: 1
            value: Backend.headerHeight
            format: (v) => Math.round(v) === root.gnomeHeight ? Math.round(v) + " px · GNOME default" : Math.round(v) + " px"
            onMoved: (v) => Backend.headerHeight = v
            tip: "How tall the bar at the top of app windows is. Left makes it slimmer, with slightly smaller buttons below 40 px, so apps show more content; right gives it more room. 47 px is GNOME's own size."
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
            tip: "How much of the desktop shows through the header bar. Left makes it clearer than the window below it, so it reads as a pane of glass; right makes it more solid. Titles stay readable because it never goes fully clear."
        }
    }
}
