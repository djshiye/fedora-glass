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

    // The list is as wide as its longest name asks for: never narrower than the button or 210 px, and
    // never wider than listMax, where a longer name is cut. Measured in the picked row's heavier
    // weight, so a name fits whether it is the picked one or not.
    property real listMax: 400
    FontMetrics { id: rowFont; font.pixelSize: Theme.fsBody; font.weight: Font.DemiBold }
    readonly property real _listWants: {
        let widest = 0
        for (let i = 0; i < model.length; i++)
            widest = Math.max(widest, rowFont.advanceWidth(String(model[i].label)))
        // the name's left edge, the name, room for the check mark, the list's own padding
        return (glyphs ? 48 : 12) + Math.ceil(widest) + 38 + 2 * popup.padding
    }

    implicitWidth: 170
    implicitHeight: 36
    activeFocusOnTab: true
    // For screen readers: a combo box, named where it is used, saying the current choice.
    Accessible.role: Accessible.ComboBox
    Accessible.description: currentIndex >= 0 ? model[currentIndex].label : ""
    Accessible.onPressAction: open()
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
        radius: Theme.rS
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
            textFormat: Text.PlainText
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
        radius: Theme.rS + 3
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
        // Keeps clear of the window's transparent shadow edge as well as of the window.
        readonly property real edge: 10 + (root.Window.window && root.Window.window.margin !== undefined ? root.Window.window.margin : 0)
        margins: edge
        width: Math.max(root.width, 210, Math.min(root._listWants, root.listMax))
        // As tall as the names need, or as tall as the room on the side it opens to: a long list scrolls.
        // The rows are not made until the list shows, so their height is counted from the model.
        readonly property real wanted: root.model.length * itemH + 12
        property real room: 0
        height: Math.min(wanted, room > 0 ? room : (C.Overlay.overlay ? Math.max(itemH, C.Overlay.overlay.height - 2 * edge) : 100000))
        // Open under the button, or above it when there is no room below. Worked out each time it
        // opens: a binding would not see the page scroll under it.
        y: root.height + 6
        function place() {
            const win = C.Overlay.overlay
            const want = wanted
            room = 0
            let up = false
            if (win) {
                const top = root.mapToItem(win, 0, 0).y
                const below = win.height - edge - (top + root.height + 6)
                const above = top - 6 - edge
                if (want > below) {
                    up = above > below
                    const avail = Math.floor(up ? above : below)
                    room = avail >= want ? 0 : Math.max(itemH, avail)
                }
            }
            y = up ? -height - 6 : root.height + 6
        }
        // Puts the row the keys are on inside the visible part of a long list.
        function reveal() {
            const view = height - 12
            const top = cur * itemH
            if (top < scroller.contentY) scroller.contentY = top
            else if (top + itemH > scroller.contentY + view) scroller.contentY = top + itemH - view
        }
        onAboutToShow: { place(); scroller.contentY = 0; reveal() }
        closePolicy: C.Popup.CloseOnEscape | C.Popup.CloseOnPressOutsideParent
        focus: true
        onOpened: { kbd = root.activeFocus && !root._byMouse; keys.forceActiveFocus() }

        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.fast }
            NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
        }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.fast } }

        // Glass, but frosted hard (blur 40, tint 0.76 dark / 0.80 light; text keeps at least 6:1 even over pure white or black): the list
        // sits over card text and the preview, and the rows must stay readable.
        background: PopupGlass {
            owner: popup
            radius: Theme.rM
            blurRadius: 40
            tintAlphaDark: 0.76
            tintAlphaLight: 0.80
            shadowBlur: 26
            shadowY: 8
        }

        contentItem: FocusScope {
            id: keys
            implicitWidth: list.implicitWidth
            implicitHeight: list.implicitHeight
            Keys.onPressed: (e) => {
                popup.kbd = true
                if (e.key === Qt.Key_Down) { popup.cur = Math.min(root.model.length - 1, popup.cur + 1); popup.reveal(); e.accepted = true }
                else if (e.key === Qt.Key_Up) { popup.cur = Math.max(0, popup.cur - 1); popup.reveal(); e.accepted = true }
                else if (e.key === Qt.Key_Home) { popup.cur = 0; popup.reveal(); e.accepted = true }
                else if (e.key === Qt.Key_End) { popup.cur = root.model.length - 1; popup.reveal(); e.accepted = true }
                else if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space) {
                    root.activated(root.model[popup.cur].value)
                    popup.close()
                    e.accepted = true
                }
            }

            // A long list (many saved looks) scrolls inside the window.
            Flickable {
            id: scroller
            anchors.fill: parent
            contentWidth: width
            contentHeight: root.model.length * popup.itemH
            clip: contentHeight > height
            interactive: contentHeight > height
            boundsBehavior: Flickable.StopAtBounds
            C.ScrollBar.vertical: LgScrollBar {}
            Column {
            id: list
            width: scroller.width
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
                    Accessible.role: Accessible.ListItem
                    Accessible.name: modelData.label
                    Accessible.selected: selected
                    Accessible.onPressAction: { root.activated(modelData.value); popup.close() }

                    Rectangle {
                        anchors.fill: parent
                        radius: Theme.rXs
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
                        // Room up to the check mark (or the right padding), so a long name is cut, not run under it.
                        width: row.width - x - (row.selected ? 38 : 12)
                        anchors.verticalCenter: parent.verticalCenter
                        textFormat: Text.PlainText
                        text: row.modelData.label
                        color: Theme.text
                        font.pixelSize: Theme.fsBody
                        font.weight: row.selected ? Font.DemiBold : Font.Medium
                        elide: Text.ElideRight
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
}
