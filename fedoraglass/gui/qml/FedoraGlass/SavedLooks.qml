import QtQuick
import QtQuick.Controls.Basic as C
import FedoraGlass.Core

// The user's own looks, after the built-in ones on Home: a row of tiles, each with a menu
// (rename, save as a file, delete), and the sheets and file dialogs for saving, renaming,
// sharing and adding a look. Picking one changes the editor only; Apply still applies it.
Column {
    id: root
    objectName: "savedLooks"
    property real tileW: 120
    readonly property var looks: Backend.savedLooks
    readonly property bool menuOpen: menu.opened
    readonly property bool problemOpen: problemSheet.opened
    readonly property string problemText: problemSheet.subtitle
    spacing: 8
    visible: looks.length > 0

    // ---- what the Look card's buttons call ---------------------------------------------
    function saveNew() {
        nameSheet.lookId = ""
        nameSheet.open()
    }
    function importFile() { _openImport() }

    Text {
        text: "Your looks"
        color: Theme.textDim
        font.pixelSize: 13
        font.weight: Font.DemiBold
        font.letterSpacing: 0.2
    }
    ListView {
        id: list
        objectName: "savedLooksRow"
        width: parent.width
        height: 104 - 16
        orientation: ListView.Horizontal
        spacing: 10
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentWidth > width
        model: root.looks
        C.ScrollBar.horizontal: LgScrollBar {}
        delegate: LookTile {
            required property var modelData
            required property int index
            objectName: "savedLook_" + modelData.id
            width: root.tileW
            thumbHeight: 44
            name: modelData.name
            frost: modelData.frost
            tintHex: modelData.tint
            accentHex: modelData.accent
            hasMenu: true
            selected: Backend.activeLook === modelData.id
            tip: "Your look. Pick it to see it here; Apply puts it on your desktop."
            rovingGroup: list
            rovingStop: selected || (index === 0 && Backend.activeLook === "")
            onClicked: Backend.useLook(modelData.id)
            onActiveFocusChanged: if (activeFocus) list.positionViewAtIndex(index, ListView.Contain)
            onMenuRequested: (from) => {
                menu.lookId = modelData.id
                menu.lookName = modelData.name
                const p = from.mapToItem(root, 0, from.height + 4)
                menu.x = Math.min(p.x, root.width - menu.width)
                menu.y = p.y
                menu.open()
            }
        }
    }

    // ---- a saved look's menu ----------------------------------------------------------
    C.Popup {
        id: menu
        objectName: "lookMenu"
        property string lookId: ""
        property string lookName: ""
        width: 210
        padding: 6
        focus: true
        closePolicy: C.Popup.CloseOnEscape | C.Popup.CloseOnPressOutside
        background: PopupGlass { owner: menu; radius: Theme.rM; blurRadius: 40; tintAlphaDark: 0.84; tintAlphaLight: 0.88 }
        contentItem: Column {
            MenuRow {
                objectName: "lookRename"
                iconName: "write"; text: "Rename…"
                onClicked: { menu.close(); nameSheet.lookId = menu.lookId; nameSheet.open() }
            }
            MenuRow {
                objectName: "lookExport"
                iconName: "download"; text: "Save as a file…"
                onClicked: {
                    menu.close()
                    root._openExport(menu.lookId)
                }
            }
            MenuRow {
                objectName: "lookDelete"
                iconName: "trash"; text: "Delete…"; danger: true
                onClicked: { menu.close(); deleteSheet.lookId = menu.lookId; deleteSheet.lookName = menu.lookName; deleteSheet.open() }
            }
        }
    }
    component MenuRow: C.AbstractButton {
        id: row
        property string iconName: ""
        property bool danger: false
        width: 198
        height: 36
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        Accessible.name: text
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        background: Rectangle {
            radius: Theme.rXs
            color: row.down ? Theme.pressed : row.hovered || row.visualFocus ? Theme.hover : "transparent"
        }
        contentItem: Row {
            leftPadding: 10
            spacing: 10
            Icon { anchors.verticalCenter: parent.verticalCenter; name: row.iconName; size: 16; color: row.danger ? Theme.bad : Theme.textDim }
            Text { anchors.verticalCenter: parent.verticalCenter; text: row.text; color: row.danger ? Theme.bad : Theme.text; font.pixelSize: Theme.fsBody }
        }
    }

    // ---- name a new look, or rename one --------------------------------------------------
    Sheet {
        id: nameSheet
        objectName: "lookNameSheet"
        property string lookId: ""          // "" for a new look
        readonly property bool renaming: lookId.length > 0
        title: renaming ? "Rename your look" : "Save this look"
        subtitle: renaming ? ""
            : "It joins the looks on Home, to pick again or share. A look keeps the colours, the glass, motion, the lock screen's look and the pointer. Your choice of apps and this PC's own settings stay out of it."
        iconName: renaming ? "write" : "plus"
        width: Math.min(540, (parent ? parent.width : 800) - 64)
        initialFocusItem: nameField
        onAboutToShow: {
            const cur = renaming ? (root.looks.find(l => l.id === lookId) || {}).name || "" : Backend.suggestLookName()
            nameField.text = cur
            nameField.selectAll()
        }
        function done() {
            if (!saveButton.enabled)
                return
            const ok = renaming ? Backend.renameLook(lookId, nameField.text) : Backend.saveLook(nameField.text)
            if (ok.length) nameSheet.close()
        }
        buttons: [
            LgButton { text: "Cancel"; kind: "secondary"; onClicked: nameSheet.close() },
            LgButton {
                id: saveButton
                objectName: "lookNameSave"
                text: nameSheet.renaming ? "Rename" : "Save"
                kind: "primary"
                iconName: "check"
                enabled: nameField.text.trim().length > 0
                onClicked: nameSheet.done()
            }
        ]
        Column {
            width: parent.width
            spacing: 8
            Text { text: "Name"; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
            C.TextField {
                id: nameField
                objectName: "lookNameField"
                width: parent.width
                height: 40
                leftPadding: 14
                rightPadding: 14
                color: Theme.text
                placeholderText: "For example: Evening blue"
                placeholderTextColor: Theme.textFaint
                selectionColor: Theme.alpha(Theme.accent, 0.4)
                selectedTextColor: Theme.text
                font.pixelSize: Theme.fsBody
                maximumLength: 40
                Accessible.name: "Look name"
                Keys.onReturnPressed: nameSheet.done()
                Keys.onEnterPressed: nameSheet.done()
                background: Rectangle {
                    radius: Theme.rS
                    color: Theme.well
                    border.width: nameField.activeFocus ? 2 : 1
                    border.color: nameField.activeFocus ? Theme.alpha(Theme.accent, 0.85) : Theme.border
                }
            }
        }
    }

    // ---- delete -----------------------------------------------------------------------------
    Sheet {
        id: deleteSheet
        objectName: "lookDeleteSheet"
        property string lookId: ""
        property string lookName: ""
        title: "Delete “" + lookName + "”?"
        subtitle: "Only the saved look goes. Your desktop keeps the look you applied."
        iconName: "trash"
        iconColor: Theme.bad
        width: Math.min(520, (parent ? parent.width : 800) - 64)
        buttons: [
            LgButton { text: "Cancel"; kind: "secondary"; onClicked: deleteSheet.close() },
            LgButton {
                objectName: "lookDeleteConfirm"
                text: "Delete"
                kind: "destructive"
                iconName: "trash"
                onClicked: { deleteSheet.close(); Backend.deleteLook(deleteSheet.lookId) }
            }
        ]
        Item { width: 1; height: 1 }
    }

    // ---- something went wrong with a look file ---------------------------------------------
    Sheet {
        id: problemSheet
        objectName: "lookProblemSheet"
        property string what: ""
        title: ({ "import": "This look can't be added", "export": "The look wasn't saved as a file" })[what]
               || "The look wasn't saved"
        iconName: "alert"
        iconColor: Theme.warn
        width: Math.min(520, (parent ? parent.width : 800) - 64)
        buttons: [ LgButton { text: "OK"; kind: "primary"; onClicked: problemSheet.close() } ]
        Item { width: 1; height: 1 }
    }
    property string _doing: ""
    Connections {
        target: Backend
        function onLookProblem(message) {
            problemSheet.what = root._doing
            problemSheet.subtitle = message
            problemSheet.open()
        }
    }

    // ---- files ---------------------------------------------------------------------------------
    // The file dialogs come from QtQuick.Dialogs, a separate package on some systems: loaded
    // only when asked for, so Home works without it and only the files part says what's missing.
    Loader {
        id: dialogs
        objectName: "lookDialogs"
        active: false
        source: "LookFileDialogs.qml"
        onStatusChanged: if (status === Loader.Error) {
            problemSheet.what = root._doing
            problemSheet.subtitle = "Saving looks as files needs Qt's file dialogs, which aren't installed. On Ubuntu and Debian, install qml6-module-qtquick-dialogs."
            problemSheet.open()
        }
    }
    function _dialogs() {
        dialogs.active = true
        return dialogs.status === Loader.Ready ? dialogs.item : null
    }
    function _openImport() {
        root._doing = "import"
        const d = _dialogs()
        if (d) d.openImport()
    }
    function _openExport(lookId) {
        root._doing = "export"
        const d = _dialogs()
        if (d) d.openExport(lookId)
    }
    Connections {
        target: dialogs.item
        ignoreUnknownSignals: true
        function onImportPicked(url) { root._doing = "import"; Backend.importLook(url); root._doing = "" }
        function onExportPicked(lookId, url) { root._doing = "export"; Backend.exportLook(lookId, url); root._doing = "" }
    }
}
