import QtQuick
import QtQuick.Effects

// A real glass pane: the part of `backdrop` lying under this item (and a margin
// around it, which the edge reflects) is captured, blurred, bent along a
// refracting bezel and tinted. Its content's colours bleed into the glass.
// `backdrop` must share this item's coordinate space (a sibling filling the
// parent), unless `sourceRect` is given explicitly.
Item {
    id: root

    property Item backdrop
    property rect sourceRect: Qt.rect(x - pad, y - pad, width + 2 * pad, height + 2 * pad)
    // px of backdrop around the pane that its edge can reflect
    property real pad: 24
    property real blurRadius: 0          // px
    property real brightness: 0          // -1..1, added after the blur
    property real saturation: 0          // -1..1
    property real radius: Theme.rM
    property color tint: "transparent"
    property color rim: Qt.rgba(1, 1, 1, 0.5)
    property color edge: Qt.rgba(1, 1, 1, 0.12)
    property real refraction: 0          // px the bezel bends the backdrop
    property real bezel: 12              // px
    property real magnify: 1
    property real fringe: 0
    property real depth: 0.35
    property real rimWidth: 1.2
    property real sheen: 0
    property real bleed: 0               // 0..1, how much the content's colours light up the glass
    // Draw the rim above the content (for panes whose content covers the body).
    property bool rimOnTop: false
    property bool live: true

    property color shadowColor: "transparent"
    property real shadowBlur: 24
    property real shadowY: 6

    default property alias content: contentLayer.data

    readonly property bool _blurred: blurRadius > 0.4

    RectangularShadow {
        anchors.fill: parent
        visible: root.shadowColor.a > 0.001
        radius: Math.min(root.radius, Math.min(width, height) / 2)
        blur: root.shadowBlur
        offset.y: root.shadowY
        spread: -2
        color: root.shadowColor
    }

    ShaderEffectSource {
        id: grab
        sourceItem: root.backdrop
        sourceRect: root.sourceRect
        width: root.width + 2 * root.pad
        height: root.height + 2 * root.pad
        live: root.live
        visible: false
        smooth: true
    }

    MultiEffect {
        id: blurred
        width: grab.width
        height: grab.height
        source: grab
        visible: root._blurred
        autoPaddingEnabled: false
        blurEnabled: root._blurred
        blurMax: 64
        blur: Math.min(1, root.blurRadius / 64)
        blurMultiplier: root.blurRadius > 64 ? (root.blurRadius - 64) / 64 : 0
        brightness: root.brightness
        saturation: root.saturation
    }

    ShaderEffectSource {
        id: blurredTex
        sourceItem: root._blurred ? blurred : null
        hideSource: true
        visible: false
        live: root.live
        smooth: true
    }

    // A blurred copy of the content: the light its icons and text cast.
    readonly property bool _bleeds: bleed > 0.01
    ShaderEffectSource {
        id: contentGrab
        sourceItem: root._bleeds ? contentLayer : null
        width: root.width
        height: root.height
        live: root.live
        visible: false
        smooth: true
    }
    MultiEffect {
        id: contentBlur
        width: root.width
        height: root.height
        source: contentGrab
        visible: false
        autoPaddingEnabled: false
        blurEnabled: true
        blurMax: 32
        blur: 1
    }
    ShaderEffectSource {
        id: contentTex
        sourceItem: root._bleeds ? contentBlur : null
        visible: false
        live: root.live
        smooth: true
    }

    component Pane: ShaderEffect {
        property var source: root._blurred ? blurredTex : grab
        property var content: root._bleeds ? contentTex : grab
        property real bleed: root._bleeds ? root.bleed : 0
        property real pad: root.pad
        property size size: Qt.size(width, height)
        property real radius: root.radius
        property real bezel: root.bezel
        property real refraction: root.refraction
        property real magnify: root.magnify
        property real fringe: root.fringe
        property real depth: root.depth
        property real rimWidth: root.rimWidth
        property real sheen: root.sheen
        property color tint: root.tint
        property color rim: root.rim
        property color edge: root.edge
        property real mode: 0
        fragmentShader: Qt.resolvedUrl("shaders/glass.frag.qsb")
    }

    Pane {
        anchors.fill: parent
        mode: root.rimOnTop ? 1 : 0
    }

    Item {
        id: contentLayer
        anchors.fill: parent
    }

    // Above the content: the edge (for panes whose content covers the body)
    // and the light the content casts into the glass.
    Loader {
        anchors.fill: parent
        active: root.rimOnTop || root._bleeds
        sourceComponent: Pane { mode: root.rimOnTop ? 2 : 3 }
    }
}
