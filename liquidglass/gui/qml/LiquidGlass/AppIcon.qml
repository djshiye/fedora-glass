import QtQuick

// An app icon from the icon theme, or a tidy lettered tile when the theme has none.
Item {
    id: root
    property url source: ""
    property string label: ""
    property real size: 32
    property color tileColor: "#3584e4"

    implicitWidth: size
    implicitHeight: size
    width: size
    height: size

    Image {
        id: img
        anchors.fill: parent
        source: root.source
        sourceSize: Qt.size(Math.max(16, root.size * 2), Math.max(16, root.size * 2))
        smooth: true
        mipmap: true
        asynchronous: false
        visible: status === Image.Ready
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: root.size * 0.06
        visible: img.status !== Image.Ready
        radius: width * 0.26
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.lighter(root.tileColor, 1.35) }
            GradientStop { position: 1; color: root.tileColor }
        }
        Text {
            anchors.centerIn: parent
            text: root.label.length ? root.label.charAt(0).toUpperCase() : "?"
            color: "white"
            font.pixelSize: parent.height * 0.5
            font.weight: Font.DemiBold
        }
    }
}
