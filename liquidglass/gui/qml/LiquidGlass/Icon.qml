import QtQuick
import QtQuick.Shapes

// Inline vector icons, stroked on a 24x24 grid so they recolour and scale crisply.
Item {
    id: root
    property string name: ""
    property color color: Theme.text
    property real size: 18
    property real strokeWidth: 1.8
    property bool filled: false
    // The layer gives MSAA edges and respects clipping; inside the preview the
    // curve renderer antialiases by itself and avoids one offscreen pass per icon.
    property bool layered: true

    implicitWidth: size
    implicitHeight: size
    layer.enabled: layered
    layer.samples: 4
    layer.smooth: true

    readonly property var paths: ({
        "droplet": "M12 3.2 C12 3.2 18.5 10 18.5 14.4 A6.5 6.5 0 0 1 5.5 14.4 C5.5 10 12 3.2 12 3.2 Z",
        "snowflake": "M12 3 V21 M4.2 7.5 L19.8 16.5 M4.2 16.5 L19.8 7.5 M9.5 4.5 L12 7 L14.5 4.5 M9.5 19.5 L12 17 L14.5 19.5 M4 10.5 L7.4 9.6 L6.5 6.2 M20 13.5 L16.6 14.4 L17.5 17.8 M4 13.5 L7.4 14.4 L6.5 17.8 M20 10.5 L16.6 9.6 L17.5 6.2",
        "sun": "M8.5 12 A3.5 3.5 0 1 1 15.5 12 A3.5 3.5 0 1 1 8.5 12 Z M12 2.8 V5 M12 19 V21.2 M2.8 12 H5 M19 12 H21.2 M5.5 5.5 L7 7 M17 17 L18.5 18.5 M5.5 18.5 L7 17 M17 7 L18.5 5.5",
        "moon": "M19.5 14.6 A8 8 0 1 1 9.4 4.5 A6.4 6.4 0 0 0 19.5 14.6 Z",
        "auto": "M3.8 12 A8.2 8.2 0 1 1 20.2 12 A8.2 8.2 0 1 1 3.8 12 Z M12 3.8 V20.2",
        "close": "M7.5 7.5 L16.5 16.5 M16.5 7.5 L7.5 16.5",
        "minimize": "M7.5 16 H16.5",
        "maximize": "M7 7 H17 V17 H7 Z",
        "restore": "M7 9.5 H14.5 V17 H7 Z M9.5 7 H17 V14.5",
        "check": "M5.5 12.5 L10 17 L18.5 7.5",
        "chevronDown": "M7 9.5 L12 14.5 L17 9.5",
        "chevronRight": "M9.5 7 L14.5 12 L9.5 17",
        "chevronLeft": "M14.5 7 L9.5 12 L14.5 17",
        "plus": "M12 6 V18 M6 12 H18",
        "info": "M3.5 12 A8.5 8.5 0 1 1 20.5 12 A8.5 8.5 0 1 1 3.5 12 Z M12 11 V16.5 M12 7.6 V7.7",
        "alert": "M12 4 L21 19.5 H3 Z M12 10 V14 M12 16.6 V16.7",
        "okCircle": "M3.5 12 A8.5 8.5 0 1 1 20.5 12 A8.5 8.5 0 1 1 3.5 12 Z M8 12.3 L10.8 15 L16 9.3",
        "xCircle": "M3.5 12 A8.5 8.5 0 1 1 20.5 12 A8.5 8.5 0 1 1 3.5 12 Z M9 9 L15 15 M15 9 L9 15",
        "skipCircle": "M3.5 12 A8.5 8.5 0 1 1 20.5 12 A8.5 8.5 0 1 1 3.5 12 Z M8.5 12 H15.5",
        "undo": "M8.5 5.5 L4.5 9.5 L8.5 13.5 M4.5 9.5 H14 A5.5 5.5 0 0 1 14 20.5 H9",
        "list": "M9 7 H19.5 M9 12 H19.5 M9 17 H19.5 M4.6 7 H4.7 M4.6 12 H4.7 M4.6 17 H4.7",
        "sparkle": "M12 3.5 C12.6 8.6 15.4 11.4 20.5 12 C15.4 12.6 12.6 15.4 12 20.5 C11.4 15.4 8.6 12.6 3.5 12 C8.6 11.4 11.4 8.6 12 3.5 Z",
        "palette": "M12 3.5 A8.5 8.5 0 0 0 12 20.5 C13.4 20.5 13.8 19.4 13.2 18.4 C12.5 17.2 13.3 15.8 14.7 15.8 H16.5 A4 4 0 0 0 20.5 11.8 C20.5 7.2 16.7 3.5 12 3.5 Z M7.6 11.4 H7.7 M9.6 7.8 H9.7 M14 7.4 H14.1 M17 10 H17.1",
        "apps": "M5 5 H10 V10 H5 Z M14 5 H19 V10 H14 Z M5 14 H10 V19 H5 Z M14 14 H19 V19 H14 Z",
        "brush": "M14.5 4.5 L19.5 9.5 L11 18 L6 13 Z M6 13 C3.5 14 4.5 17 3.5 19.5 C6.5 19.5 9.5 19.5 11 18",
        "search": "M4.5 10.5 A6 6 0 1 1 16.5 10.5 A6 6 0 1 1 4.5 10.5 Z M15 15 L20 20",
        "back": "M15 6 L9 12 L15 18",
        "forward": "M9 6 L15 12 L9 18",
        "menu": "M5 7.5 H19 M5 12 H19 M5 16.5 H19",
        "grid": "M5 5 H10.5 V10.5 H5 Z M13.5 5 H19 V10.5 H13.5 Z M5 13.5 H10.5 V19 H5 Z M13.5 13.5 H19 V19 H13.5 Z",
        "home": "M4.5 11 L12 4.5 L19.5 11 V19.5 H14.5 V14.5 H9.5 V19.5 H4.5 Z",
        "clock": "M3.5 12 A8.5 8.5 0 1 1 20.5 12 A8.5 8.5 0 1 1 3.5 12 Z M12 7.5 V12 L15 14",
        "star": "M12 4 L14.4 9 L19.8 9.6 L15.8 13.3 L16.9 18.7 L12 16 L7.1 18.7 L8.2 13.3 L4.2 9.6 L9.6 9 Z",
        "document": "M6.5 3.5 H13.5 L18 8 V20.5 H6.5 Z M13.5 3.5 V8 H18 M9.5 12.5 H15 M9.5 16 H15",
        "download": "M12 4 V15 M7.5 10.5 L12 15 L16.5 10.5 M5 19.5 H19",
        "music": "M9.5 17.5 V6 L18.5 4 V15.5 M6.5 17.5 A3 2.5 0 1 0 12.5 17.5 A3 2.5 0 1 0 6.5 17.5 Z M15.5 15.5 A3 2.5 0 1 0 21.5 15.5 A3 2.5 0 1 0 15.5 15.5 Z",
        "picture": "M4 5.5 H20 V18.5 H4 Z M4 15.5 L9 11 L13 14.5 L15.5 12.5 L20 16.5 M14.5 9 H14.6",
        "video": "M4 6.5 H15.5 V17.5 H4 Z M15.5 10.5 L20 7.5 V16.5 L15.5 13.5",
        "trash": "M5 7 H19 M9.5 7 V4.5 H14.5 V7 M7 7 L8 20 H16 L17 7",
        "terminal": "M4 5 H20 V19 H4 Z M7.5 9.5 L10.5 12 L7.5 14.5 M12.5 14.5 H16.5",
        "folder": "M3.5 6.5 A1.5 1.5 0 0 1 5 5 H9.5 L11.5 7 H19 A1.5 1.5 0 0 1 20.5 8.5 V17.5 A1.5 1.5 0 0 1 19 19 H5 A1.5 1.5 0 0 1 3.5 17.5 Z",
        "power": "M12 3.5 V11.5 M7 6.5 A7.5 7.5 0 1 0 17 6.5",
        "gear": "M9 12 A3 3 0 1 1 15 12 A3 3 0 1 1 9 12 Z M12 3 V5.5 M12 18.5 V21 M3 12 H5.5 M18.5 12 H21 M5.6 5.6 L7.4 7.4 M16.6 16.6 L18.4 18.4 M5.6 18.4 L7.4 16.6 M16.6 7.4 L18.4 5.6",
        "wifi": "M3.5 9.5 A12 12 0 0 1 20.5 9.5 M6.5 12.8 A7.8 7.8 0 0 1 17.5 12.8 M9.4 16 A3.6 3.6 0 0 1 14.6 16 M12 19.2 V19.3",
        "volume": "M4.5 9.5 H8 L12.5 5.5 V18.5 L8 14.5 H4.5 Z M15.5 9 A4.2 4.2 0 0 1 15.5 15 M18 6.5 A8 8 0 0 1 18 17.5",
        "battery": "M3.5 8 H18 V16 H3.5 Z M20.5 10.5 V13.5 M6 10.5 V13.5 M9 10.5 V13.5 M12 10.5 V13.5",
        "lock": "M6.5 11 H17.5 V19.5 H6.5 Z M8.5 11 V8 A3.5 3.5 0 0 1 15.5 8 V11",
        "user": "M8 8 A4 4 0 1 1 16 8 A4 4 0 1 1 8 8 Z M4.5 20 C5.5 15.8 8.4 14 12 14 C15.6 14 18.5 15.8 19.5 20",
        "panelFloat": "M3.5 5 H20.5 V19 H3.5 Z M7 15 H17 V16.5 H7 Z",
        "panelDock": "M3.5 5 H20.5 V19 H3.5 Z M3.5 15.5 H20.5",
        "eye": "M2.5 12 C5 7.5 8.2 5.5 12 5.5 C15.8 5.5 19 7.5 21.5 12 C19 16.5 15.8 18.5 12 18.5 C8.2 18.5 5 16.5 2.5 12 Z M9.5 12 A2.5 2.5 0 1 0 14.5 12 A2.5 2.5 0 1 0 9.5 12 Z",
        "sliders": "M5 7 H12 M16 7 H19 M5 17 H8 M12 17 H19 M14 4.5 V9.5 M10 14.5 V19.5",
        "write": "M5 19 H9 L19 9 L15 5 L5 15 Z M13 7 L17 11",
        "set": "M5 7 H12 M16 7 H19 M5 17 H8 M12 17 H19 M14 4.5 V9.5 M10 14.5 V19.5",
        "run": "M8 5.5 L18.5 12 L8 18.5 Z",
        "fedora": "M12 3 A9 9 0 0 1 21 12 A9 9 0 0 1 12 21 H3 V12 A9 9 0 0 1 12 3 Z M11 17 V9.8 A2.3 2.3 0 0 1 15.5 9 M8.5 12.5 H14",
        "refresh": "M19.5 12 A7.5 7.5 0 1 1 17 6.4 M19.5 4 V8.5 H15"
    })

    Shape {
        width: 24
        height: 24
        scale: root.size / 24
        transformOrigin: Item.TopLeft
        preferredRendererType: root.layered ? Shape.GeometryRenderer : Shape.CurveRenderer

        ShapePath {
            strokeColor: root.filled ? "transparent" : root.color
            strokeWidth: root.strokeWidth * 24 / Math.max(root.size, 1)
            fillColor: root.filled ? root.color : "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathSvg { path: root.paths[root.name] || "" }
        }
    }
}
