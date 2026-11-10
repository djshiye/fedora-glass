import QtQuick
import QtQuick.Controls.Basic as C
import "searchindex.js" as Index

// The app's one menu: the app name, search, and every page one click away.
// Advanced and About and restore sit at the bottom, out of the way.
Item {
    id: root
    property var pages: []              // [{ id, label, icon, bottom }]
    property string current: "home"
    signal picked(string id)
    signal found(string page, string name)
    signal homeClicked()
    readonly property alias searchField: field
    readonly property var pageLabels: {
        const m = {}
        for (const p of pages) m[p.id] = p.label
        return m
    }
    function focusSearch(text) {
        field.forceActiveFocus(Qt.ShortcutFocusReason)
        if (text !== undefined) { field.text = text; field.cursorPosition = text.length }
        else field.selectAll()
    }

    Rectangle {     // the sidebar's own faint glass, a shade apart from the page
        anchors.fill: parent
        color: Theme.dark ? Qt.rgba(1, 1, 1, 0.025) : Qt.rgba(1, 1, 1, 0.35)
    }
    Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.divider }

    // ---- the app name: drags the window, and goes Home on a click ------------------
    C.AbstractButton {
        id: brand
        objectName: "aboutButton"
        x: 12; y: 14
        width: parent.width - 24
        height: 44
        hoverEnabled: true
        focusPolicy: Qt.TabFocus
        Accessible.name: "Fedora Glass: home"
        onClicked: root.homeClicked()
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        background: Rectangle {
            radius: Theme.rS
            color: brand.down ? Theme.pressed : brand.hovered ? Theme.hover : "transparent"
            Behavior on color { ColorAnimation { duration: Theme.fast } }
            FocusRing { target: brand; radius: Theme.rS + 3 }
        }
        contentItem: Item {
            Row {
                x: 8
                anchors.verticalCenter: parent.verticalCenter
                spacing: 11
                Image {
                    width: 28; height: 28
                    source: appIconUrl
                    sourceSize: Qt.size(56, 56)
                    smooth: true
                    mipmap: true
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: "Fedora Glass"
                    color: Theme.text
                    font.pixelSize: Theme.fsTitle + 1
                    font.weight: Font.Bold
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }
    }

    // ---- search ---------------------------------------------------------------
    property var results: Index.search(field.text, pageLabels, 7)
    property int hit: 0
    onResultsChanged: hit = 0
    function choose(i) {
        const e = results[i]
        if (!e)
            return
        field.text = ""
        field.focus = false
        root.found(e.page, e.name)
    }

    Rectangle {
        id: searchBox
        x: 12; y: 70
        width: parent.width - 24
        height: 38
        radius: Theme.rS
        color: field.activeFocus ? Theme.wellHi : Theme.well
        border.width: field.activeFocus ? 2 : 1
        border.color: field.activeFocus ? Theme.accent : Theme.border
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        Icon {
            x: 11
            anchors.verticalCenter: parent.verticalCenter
            name: "search"
            size: 16
            strokeWidth: 2
            color: Theme.textFaint
        }
        C.TextField {
            id: field
            objectName: "searchField"
            x: 32
            width: parent.width - x - (clearBtn.visible ? 30 : 8)
            height: parent.height
            verticalAlignment: TextInput.AlignVCenter
            leftPadding: 4; rightPadding: 4
            placeholderText: "Search settings"
            placeholderTextColor: Theme.textFaint
            color: Theme.text
            selectionColor: Theme.alpha(Theme.accent, 0.4)
            selectedTextColor: Theme.text
            font.pixelSize: 14
            background: Item {}
            Accessible.name: "Search settings"
            Keys.onDownPressed: root.hit = Math.min(root.results.length - 1, root.hit + 1)
            Keys.onUpPressed: root.hit = Math.max(0, root.hit - 1)
            Keys.onReturnPressed: root.choose(root.hit)
            Keys.onEnterPressed: root.choose(root.hit)
            Keys.onEscapePressed: { if (text.length) text = ""; else focus = false }
        }
        C.AbstractButton {
            id: clearBtn
            visible: field.text.length > 0
            anchors.right: parent.right
            anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            width: 24; height: 24
            focusPolicy: Qt.NoFocus
            Accessible.name: "Clear search"
            onClicked: { field.text = ""; field.forceActiveFocus() }
            background: Rectangle { radius: 12; color: clearBtn.hovered ? Theme.hover : "transparent" }
            contentItem: Item { Icon { anchors.centerIn: parent; name: "close"; size: 14; strokeWidth: 2; color: Theme.textDim } }
        }
    }

    // ---- the pages ------------------------------------------------------------------
    component NavItem: C.AbstractButton {
        id: nav
        required property var modelData
        readonly property bool selected: root.current === modelData.id
        objectName: "nav_" + modelData.id
        width: root.width - 24
        x: 12
        height: 40
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        Accessible.name: modelData.label
        Accessible.role: Accessible.PageTab
        Accessible.selected: selected
        onClicked: root.picked(modelData.id)
        LgToolTip { shown: nav.hovered && !!nav.modelData.tip && !nav.pressed; text: nav.modelData.tip || "" }
        background: Rectangle {
            radius: Theme.rS
            color: nav.selected ? Theme.wellHi : nav.down ? Theme.pressed : nav.hovered ? Theme.hover : "transparent"
            Behavior on color { ColorAnimation { duration: Theme.fast } }
            FocusRing { target: nav; radius: Theme.rS + 3 }
        }
        contentItem: Item {
            Icon {
                id: navIcon
                x: 12
                anchors.verticalCenter: parent.verticalCenter
                name: nav.modelData.icon
                size: 18
                strokeWidth: 1.8
                color: nav.selected ? Theme.text : Theme.textDim
            }
            Text {
                anchors.left: navIcon.right
                anchors.leftMargin: 12
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: nav.modelData.label
                elide: Text.ElideRight
                color: nav.selected ? Theme.text : Theme.textDim
                font.pixelSize: Theme.fsBody
                font.weight: nav.selected ? Font.DemiBold : Font.Normal
            }
        }
    }

    Column {
        y: searchBox.y + searchBox.height + 14
        width: parent.width
        spacing: 2
        Repeater {
            model: root.pages.filter(p => !p.bottom)
            delegate: NavItem {}
        }
    }
    Column {
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 14
        width: parent.width
        spacing: 2
        Repeater {
            model: root.pages.filter(p => p.bottom)
            delegate: NavItem {}
        }
    }

    // ---- results, floating over the page ------------------------------------------------
    Rectangle {
        id: resultsBox
        objectName: "searchResults"
        visible: field.activeFocus && field.text.trim().length > 0
        x: 12
        y: searchBox.y + searchBox.height + 8
        z: 100
        width: 420
        height: list.height + 16
        radius: Theme.rM
        color: Theme.sheet
        border.width: 1
        border.color: Theme.borderHi
        Rectangle {     // soft drop shadow, without a shader
            z: -1
            anchors.fill: parent
            anchors.margins: -1
            anchors.topMargin: 4
            radius: parent.radius + 1
            color: Qt.rgba(0, 0, 0, Theme.dark ? 0.35 : 0.12)
        }
        Column {
            id: list
            x: 8; y: 8
            width: parent.width - 16
            Text {
                visible: root.results.length === 0
                width: parent.width
                padding: 12
                text: "No setting matches \"" + field.text.trim() + "\""
                color: Theme.textDim
                font.pixelSize: 13
                wrapMode: Text.WordWrap
            }
            Repeater {
                model: root.results
                delegate: Rectangle {
                    id: res
                    required property var modelData
                    required property int index
                    width: list.width
                    height: 48
                    radius: Theme.rS - 2
                    color: index === root.hit ? Theme.wellHi : resMouse.containsMouse ? Theme.hover : "transparent"
                    Column {
                        x: 12
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 1
                        Text { text: res.modelData.label; color: Theme.text; font.pixelSize: 14; font.weight: Font.DemiBold }
                        Text { text: root.pageLabels[res.modelData.page] || ""; color: Theme.textFaint; font.pixelSize: 12 }
                    }
                    MouseArea {
                        id: resMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onEntered: root.hit = res.index
                        onPressed: root.choose(res.index)
                    }
                }
            }
        }
    }
}
