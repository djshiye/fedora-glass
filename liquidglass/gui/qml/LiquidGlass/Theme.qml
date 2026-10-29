pragma Singleton
import QtQuick
import LiquidGlass.Core

// The customizer's own look. It follows GNOME's light/dark style and the
// accent being edited; the preview uses the theme's real Tokens instead.
QtObject {
    readonly property bool dark: Backend.uiDark
    readonly property color accent: Backend.uiAccent
    readonly property color accentFg: Backend.uiAccentFg
    readonly property color accentText: dark ? Qt.tint(accent, Qt.rgba(1, 1, 1, 0.28)) : Qt.tint(accent, Qt.rgba(0, 0, 0, 0.12))

    readonly property color base: dark ? "#101116" : "#eceef3"
    readonly property color scrim: dark ? Qt.rgba(0.06, 0.063, 0.08, 0.80) : Qt.rgba(0.945, 0.95, 0.965, 0.93)
    readonly property color surface: dark ? Qt.rgba(1, 1, 1, 0.045) : Qt.rgba(1, 1, 1, 0.70)
    readonly property color surfaceHi: dark ? Qt.rgba(1, 1, 1, 0.075) : Qt.rgba(1, 1, 1, 0.92)
    readonly property color sheet: dark ? Qt.rgba(0.11, 0.115, 0.14, 0.96) : Qt.rgba(0.975, 0.978, 0.985, 0.97)
    readonly property color well: dark ? Qt.rgba(1, 1, 1, 0.075) : Qt.rgba(0, 0, 0, 0.06)
    readonly property color wellHi: dark ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(0, 0, 0, 0.09)
    readonly property color border: dark ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(0, 0, 0, 0.08)
    readonly property color borderHi: dark ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(0, 0, 0, 0.13)
    readonly property color rim: dark ? Qt.rgba(1, 1, 1, 0.11) : Qt.rgba(1, 1, 1, 1.0)
    readonly property color divider: dark ? Qt.rgba(1, 1, 1, 0.07) : Qt.rgba(0, 0, 0, 0.07)
    readonly property color hover: dark ? Qt.rgba(1, 1, 1, 0.06) : Qt.rgba(0, 0, 0, 0.045)
    readonly property color pressed: dark ? Qt.rgba(1, 1, 1, 0.11) : Qt.rgba(0, 0, 0, 0.085)
    readonly property color knob: "#ffffff"
    readonly property color shadow: dark ? Qt.rgba(0, 0, 0, 0.55) : Qt.rgba(0.08, 0.1, 0.18, 0.20)

    readonly property color text: dark ? "#f2f3f7" : "#17181d"
    readonly property color textDim: dark ? Qt.rgba(0.95, 0.953, 0.97, 0.68) : Qt.rgba(0.09, 0.094, 0.114, 0.66)
    readonly property color textFaint: dark ? Qt.rgba(0.95, 0.953, 0.97, 0.45) : Qt.rgba(0.09, 0.094, 0.114, 0.45)

    readonly property color good: dark ? "#4ad48a" : "#1b8a4b"
    readonly property color warn: dark ? "#f5c04f" : "#9a6500"
    readonly property color bad: dark ? "#ff7272" : "#cc2f3e"

    readonly property string mono: "Adwaita Mono"

    // Type scale (px) and 8 px spacing grid
    readonly property int fsSmall: 12
    readonly property int fsBody: 14
    readonly property int fsTitle: 15
    readonly property int fsHeading: 20
    readonly property int fsHero: 26
    readonly property int gap: 8

    readonly property int rCard: 20
    readonly property int rControl: 12

    readonly property int fast: 150
    readonly property int normal: 200
    readonly property int slow: 250

    function alpha(c, a) { return Qt.rgba(c.r, c.g, c.b, a) }
}
