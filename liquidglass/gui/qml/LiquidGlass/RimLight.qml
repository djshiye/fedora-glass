import QtQuick

// Specular rim plus glass edge, drawn over a flat surface.
ShaderEffect {
    property real radius: 12
    property real rimWidth: 1.4
    property color rim: Theme.rim
    property color edge: Theme.border
    property size size: Qt.size(width, height)
    anchors.fill: parent
    fragmentShader: Qt.resolvedUrl("shaders/rim.frag.qsb")
}
