import QtQuick
import QtQuick.Controls.Basic as C

// A dropdown: a pill button that opens a small glass list.
// model: [{ value, label, tip }]
FocusScope {
    id: root
    property var model: []
    property var value
    property string tip: ""
    property bool glyphs: true             // show a curve glyph (value is a motion preset id) before each label
    signal activated(var value)

    readonly property int currentIndex: {
        for (let i = 0; i < model.length; i++)
            if (model[i].value === value)
                return i
        return -1
    }
    readonly property bool opened: popup.visible
    property bool _byMouse: false

    implicitWidth: 170
    implicitHeight: 36
    activeFocusOnTab: true
    onActiveFocusChanged: if (!activeFocus) _byMouse = false

    function open() { popup.cur = Math.max(0, currentIndex); popup.open() }
    function close() { popup.close() }

    Keys.onPressed: (e) => {
        if (e.key === Qt.Key_Space || e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Down || e.key === Qt.Key_Up) {
            _byMouse = false
            root.open()
            e.accepted = true
        }
    }

    HoverHandler { id: hover; cursorShape: root.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }
    LgToolTip { shown: root.tip.length > 0 && hover.hovered && !popup.visible; text: root.tip }

    Rectangle {
        id: track
        anchors.fill: parent
        radius: height / 2
        color: popup.visible ? Theme.wellHi : hover.hovered ? Theme.wellHi : Theme.well
        border.width: 1
        border.color: Theme.border
        opacity: root.enabled ? 1 : 0.45
        Behavior on color { ColorAnimation { duration: Theme.fast } }
    }

    Row {
        anchors.left: parent.left
        anchors.leftMargin: 14
        anchors.right: chevron.left
        anchors.rightMargin: 6
        anchors.verticalCenter: parent.verticalCenter
        spacing: 8
        opacity: root.enabled ? 1 : 0.45
        CurveGlyph {
            visible: root.glyphs && root.currentIndex >= 0
            preset: root.currentIndex >= 0 ? String(root.model[root.currentIndex].value) : ""
            color: Theme.textDim
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            width: parent.width - (root.glyphs ? 36 : 0)
            anchors.verticalCenter: parent.verticalCenter
            text: root.currentIndex >= 0 ? root.model[root.currentIndex].label : ""
            color: Theme.text
            font.pixelSize: Theme.fsBody
            font.weight: Font.Medium
            elide: Text.ElideRight
        }
    }
    Icon {
        id: chevron
        name: "chevronDown"
        size: 16
        color: Theme.textDim
        anchors.right: parent.right
        anchors.rightMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        rotation: popup.visible ? 180 : 0
        Behavior on rotation { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }
    }

    TapHandler {
        onTapped: { root._byMouse = true; root.forceActiveFocus(); popup.visible ? popup.close() : root.open() }
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: -3
        radius: height / 2
        color: "transparent"
        border.width: 2
        border.color: Theme.alpha(Theme.accent, 0.85)
        opacity: root.activeFocus && !root._byMouse ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
    }

    C.Popup {
        id: popup
        property int cur: 0
        property bool kbd: false
        readonly property real itemH: 36
        parent: root
        x: root.width - width
        padding: 6
        margins: 10
        width: Math.max(root.width, 210)
        height: list.implicitHeight + 12
        // Open under the button, or above it when there is no room below.
        y: {
            const win = C.Overlay.overlay
            if (!win) return root.height + 6
            const below = root.mapToItem(win, 0, root.height + 6 + height).y
            return below > win.height - 10 ? -height - 6 : root.height + 6
        }
        closePolicy: C.Popup.CloseOnEscape | C.Popup.CloseOnPressOutsideParent
        focus: true
        onOpened: { kbd = root.activeFocus && !root._byMouse; keys.forceActiveFocus() }

        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.fast }
            NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
        }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.fast } }

        // Fully opaque: the list sits over card text and the preview, and any
        // see-through here makes the rows hard to read.
        background: Item {
            // soft drop shadow: two faint rings, no effect layer needed
            Rectangle {
                x: -3; y: -1; width: parent.width + 6; height: parent.height + 8
                radius: 17
                color: Qt.rgba(0, 0, 0, Theme.dark ? 0.22 : 0.07)
            }
            Rectangle {
                x: -1; y: 1; width: parent.width + 2; height: parent.height + 4
                radius: 15
                color: Qt.rgba(0, 0, 0, Theme.dark ? 0.30 : 0.09)
            }
            Rectangle {
                anchors.fill: parent
                radius: 14
                color: Theme.dark ? Qt.rgba(0.105, 0.11, 0.135, 1) : Qt.rgba(0.985, 0.987, 0.993, 1)
                border.width: 1
                border.color: Theme.dark ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(0, 0, 0, 0.12)
            }
        }

        contentItem: FocusScope {
            id: keys
            implicitWidth: list.implicitWidth
            implicitHeight: list.implicitHeight
            Keys.onPressed: (e) => {
                kbd = true
                if (e.key === Qt.Key_Down) { cur = Math.min(root.model.length - 1, cur + 1); e.accepted = true }
                else if (e.key === Qt.Key_Up) { cur = Math.max(0, cur - 1); e.accepted = true }
                else if (e.key === Qt.Key_Home) { cur = 0; e.accepted = true }
                else if (e.key === Qt.Key_End) { cur = root.model.length - 1; e.accepted = true }
                else if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space) {
                    root.activated(root.model[cur].value)
                    popup.close()
                    e.accepted = true
                }
            }

            Column {
            id: list
            width: parent.width
            spacing: 0
            Repeater {
                model: root.model
                delegate: Item {
                    id: row
                    required property var modelData
                    required property int index
                    readonly property bool selected: index === root.currentIndex
                    readonly property bool lit: index === popup.cur
                    width: list.width
                    height: popup.itemH

                    Rectangle {
                        anchors.fill: parent
                        radius: 10
                        color: row.lit ? (Theme.dark ? Qt.rgba(1, 1, 1, 0.10) : Qt.rgba(0, 0, 0, 0.07)) : "transparent"
                        Behavior on color { ColorAnimation { duration: Theme.fast } }
                    }
                    CurveGlyph {
                        visible: root.glyphs
                        x: 10
                        anchors.verticalCenter: parent.verticalCenter
                        preset: String(row.modelData.value)
                        color: row.selected ? Theme.accentText : Theme.dark ? "#f4f5f9" : Theme.text
                    }
                    Text {
                        x: root.glyphs ? 48 : 12
                        anchors.verticalCenter: parent.verticalCenter
                        text: row.modelData.label
                        color: Theme.text
                        font.pixelSize: Theme.fsBody
                        font.weight: row.selected ? Font.DemiBold : Font.Medium
                    }
                    Icon {
                        visible: row.selected
                        name: "check"
                        size: 16
                        color: Theme.accentText
                        anchors.right: parent.right
                        anchors.rightMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    HoverHandler {
                        id: rowHover
                        cursorShape: Qt.PointingHandCursor
                        onHoveredChanged: if (hovered) { popup.kbd = false; popup.cur = row.index }
                    }
                    LgToolTip {
                        shown: popup.visible && (rowHover.hovered || (keys.activeFocus && row.lit && !rowHover.hovered && popup.kbd))
                        text: row.modelData.tip || ""
                        below: true
                    }
                    TapHandler {
                        onTapped: { root.activated(row.modelData.value); popup.close() }
                    }
                }
            }
            }
        }
    }
}
