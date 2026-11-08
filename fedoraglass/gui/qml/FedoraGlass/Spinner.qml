import QtQuick
import QtQuick.Shapes

// A small activity arc.
Item {
    id: root
    property real size: 18
    property color color: Theme.text
    implicitWidth: size
    implicitHeight: size
    width: size
    height: size
    layer.enabled: true
    layer.samples: 4

    Shape {
        anchors.fill: parent
        RotationAnimator on rotation { from: 0; to: 360; duration: 900; loops: Animation.Infinite; running: root.visible }
        ShapePath {
            strokeColor: root.color
            strokeWidth: Math.max(1.5, root.size / 9)
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            PathAngleArc {
                centerX: root.size / 2; centerY: root.size / 2
                radiusX: root.size / 2 - 2; radiusY: root.size / 2 - 2
                startAngle: 0; sweepAngle: 270
            }
        }
    }
}
