import QtQuick
import QtQuick.Shapes

// A hue wheel disc, for the "custom colour" swatch.
Shape {
    id: root
    layer.enabled: true
    layer.samples: 4
    ShapePath {
        strokeColor: "transparent"
        fillGradient: ConicalGradient {
            centerX: root.width / 2; centerY: root.height / 2; angle: 90
            GradientStop { position: 0.000; color: "#ff4d4d" }
            GradientStop { position: 0.166; color: "#ffcc33" }
            GradientStop { position: 0.333; color: "#4cd964" }
            GradientStop { position: 0.500; color: "#33c3ff" }
            GradientStop { position: 0.666; color: "#5b5bff" }
            GradientStop { position: 0.833; color: "#ff4dd2" }
            GradientStop { position: 1.000; color: "#ff4d4d" }
        }
        PathAngleArc {
            centerX: root.width / 2; centerY: root.height / 2
            radiusX: root.width / 2; radiusY: root.height / 2
            startAngle: 0; sweepAngle: 360
        }
    }
}
