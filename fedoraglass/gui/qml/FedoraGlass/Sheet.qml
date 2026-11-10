import QtQuick
import QtQuick.Controls.Basic as C

// A modal sheet over a dimmed window: title, subtitle, body, buttons.
C.Popup {
    id: sheet
    property string title: ""
    property string subtitle: ""
    property string iconName: ""
    property color iconColor: Theme.accent
    default property alias body: bodyHolder.data
    property alias buttons: buttonRow.data
    property real maxBodyHeight: (parent ? parent.height : 600) * 0.62 - 160
    // An image in place of the round icon (the About sheet shows the app's own icon).
    property url iconSource: ""
    // What has the keyboard when the sheet opens. Left empty, it is the main safe button:
    // the last "primary" one in the button row, else the first "secondary"; never a
    // "danger" or "destructive" one, so Enter can't throw anything away.
    property Item initialFocusItem: null
    // Set by whoever opens the sheet from a key press, so the focus ring shows at once.
    property bool openedByKeyboard: false

    function _win() { return contentItem ? contentItem.Window.window : null }
    function _pressable(it) {
        return !!it && typeof it.click === "function" && it.autoRepeat !== undefined
               && it.enabled && it.visible
    }
    function _isVisualReason(r) {
        return r === Qt.TabFocusReason || r === Qt.BacktabFocusReason || r === Qt.ShortcutFocusReason
    }
    function _inside(it, root) {
        for (let p = it; p; p = p.parent)
            if (p === root)
                return true
        return false
    }
    function defaultFocusItem() {
        if (initialFocusItem && initialFocusItem.visible && initialFocusItem.enabled)
            return initialFocusItem
        const kids = buttonRow.children
        for (let i = kids.length - 1; i >= 0; i--)
            if (kids[i].kind === "primary" && _pressable(kids[i]))
                return kids[i]
        for (let i = 0; i < kids.length; i++)
            if (kids[i].kind === "secondary" && _pressable(kids[i]))
                return kids[i]
        return null
    }
    property Item _returnTo: null
    property int _returnReason: Qt.OtherFocusReason
    function _focusDefault() {
        if (!visible)
            return
        const it = defaultFocusItem()
        if (it)
            it.forceActiveFocus(openedByKeyboard ? Qt.TabFocusReason : Qt.OtherFocusReason)
    }
    property var _openedIn: null
    onAboutToShow: {
        const w = _win()
        _openedIn = w
        const cur = w ? w.activeFocusItem : null
        _returnTo = cur && w && cur !== w.contentItem ? cur : null
        _returnReason = cur && cur.focusReason !== undefined ? cur.focusReason : Qt.OtherFocusReason
        // Someone moving about with Tab sees the ring on the default button at once.
        if (cur && cur.visualFocus === true)
            openedByKeyboard = true
        Qt.callLater(_focusDefault)
    }
    onClosed: {
        openedByKeyboard = false
        const w = _openedIn         // closed, the sheet is out of the window
        const back = _returnTo
        _returnTo = null
        if (!w || !back || !back.visible || !back.enabled)
            return
        // Only while the keyboard is still with this sheet (or nowhere): a sheet that
        // opened meanwhile (Show changes, then the results) keeps it.
        const cur = w.activeFocusItem
        if (cur && cur !== w.contentItem && !_inside(cur, contentItem.parent))
            return
        back.forceActiveFocus(_isVisualReason(_returnReason) ? _returnReason : Qt.OtherFocusReason)
    }

    parent: C.Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(600, (parent ? parent.width : 800) - 64)
    modal: true
    focus: true
    padding: 0
    closePolicy: C.Popup.CloseOnEscape

    C.Overlay.modal: Rectangle {
        color: Theme.dark ? Qt.rgba(0, 0, 0, 0.45) : Qt.rgba(0.1, 0.12, 0.18, 0.22)
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
    }
    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.95; to: 1; duration: Theme.slow; easing.type: Easing.OutBack; easing.overshoot: 0.8 }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.fast }
        NumberAnimation { property: "scale"; from: 1; to: 0.97; duration: Theme.fast }
    }

    background: Item {
        Rectangle {
            anchors.fill: parent
            anchors.margins: -1
            anchors.topMargin: 6
            radius: Theme.rL + 2
            color: Qt.rgba(0, 0, 0, Theme.dark ? 0.35 : 0.10)
            opacity: 0.6
        }
        Rectangle {
            anchors.fill: parent
            radius: Theme.rL
            color: Theme.sheet
        }
    }

    contentItem: Column {
        spacing: 0
        // Keys the focused control left alone end up here. Enter presses the focused
        // button (Space already does), and the first other key shows where focus is.
        Keys.onPressed: (e) => {
            const w = sheet._win()
            const it = w ? w.activeFocusItem : null
            if ((e.key === Qt.Key_Return || e.key === Qt.Key_Enter)
                    && !(e.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier))) {
                if (sheet._pressable(it)) {
                    it.click()
                    e.accepted = true
                }
                return
            }
            if (it && it.visualFocus === false && sheet._inside(it, sheet.contentItem)
                    && e.key !== Qt.Key_Escape && !(e.modifiers & (Qt.ControlModifier | Qt.AltModifier))) {
                it.focus = false
                it.forceActiveFocus(Qt.TabFocusReason)
                e.accepted = true
            }
        }
        Item {
            width: parent.width
            height: head.height + 48
            Row {
                id: head
                x: 24; y: 24
                width: parent.width - 48
                spacing: 14
                Image {
                    visible: sheet.iconSource.toString().length > 0
                    width: 44; height: 44
                    source: sheet.iconSource
                    sourceSize: Qt.size(88, 88)
                    smooth: true
                    mipmap: true
                    anchors.verticalCenter: parent.verticalCenter
                }
                Rectangle {
                    visible: sheet.iconName.length > 0 && sheet.iconSource.toString().length === 0
                    width: 40; height: 40; radius: 20
                    color: Theme.alpha(sheet.iconColor, 0.16)
                    Icon { anchors.centerIn: parent; name: sheet.iconName; size: 20; color: sheet.iconColor }
                }
                Column {
                    width: parent.width - (sheet.iconSource.toString().length > 0 ? 58 : sheet.iconName.length > 0 ? 54 : 0)
                    spacing: 4
                    anchors.verticalCenter: parent.verticalCenter
                    Text {
                        width: parent.width
                        text: sheet.title
                        color: Theme.text
                        font.pixelSize: 18
                        font.weight: Font.Bold
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        visible: text.length > 0
                        width: parent.width
                        text: sheet.subtitle
                        color: Theme.textDim
                        font.pixelSize: Theme.fsBody
                        wrapMode: Text.WordWrap
                        lineHeight: 1.15
                    }
                }
            }
        }
        Item {
            id: bodyHolder
            x: 24
            width: parent.width - 48
            height: childrenRect.height
        }
        Item {
            width: parent.width
            height: 80
            Row {
                id: buttonRow
                anchors.right: parent.right
                anchors.rightMargin: 24
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8
            }
        }
    }
}
