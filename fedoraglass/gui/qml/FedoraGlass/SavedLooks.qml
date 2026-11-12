import QtQuick
import QtQuick.Controls.Basic as C
import FedoraGlass.Core

// The user's own looks, after the built-in ones on Home: a row of tiles, each with a menu
// (update with the editor's settings, rename, save as a file, delete), and the sheets and
// file dialogs for saving, renaming, sharing and adding a look. Saving under a name a look
// has already asks first. Picking one changes the editor only; Apply still applies it.
Column {
    id: root
    objectName: "savedLooks"
    property real tileW: 120
    readonly property var looks: Backend.savedLooks
    // Read once here for every tile, not twice per tile on every slider tick.
    readonly property string activeLook: Backend.activeLook
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
        text: qsTr("Your looks")
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
            selected: root.activeLook === modelData.id
            tip: qsTr("Your look. Pick it to see it here; Apply puts it on your desktop.")
            rovingGroup: list
            rovingStop: selected || (index === 0 && root.activeLook === "")
            onClicked: Backend.useLook(modelData.id)
            onActiveFocusChanged: if (activeFocus) list.positionViewAtIndex(index, ListView.Contain)
            onMenuRequested: (from) => {
                menu.lookId = modelData.id
                menu.lookName = modelData.name
                const p = from.mapToItem(root, 0, from.height + 4)
                menu.x = Math.min(p.x, root.width - menu.width)
                // Under the tile, or above it when the window ends first.
                const ov = C.Overlay.overlay
                const low = ov ? from.mapToItem(ov, 0, from.height + 4 + menu.height).y > ov.height - 10 : false
                menu.y = low ? from.mapToItem(root, 0, -menu.height - 4).y : p.y
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
        width: 250
        padding: 6
        focus: true
        closePolicy: C.Popup.CloseOnEscape | C.Popup.CloseOnPressOutside
        background: PopupGlass { owner: menu; radius: Theme.rM; blurRadius: 40; tintAlphaDark: 0.84; tintAlphaLight: 0.88 }
        contentItem: Column {
            MenuRow {
                objectName: "lookUpdate"
                iconName: "refresh"; text: qsTr("Update with current settings")
                // Nothing to update while the editor holds this look already.
                enabled: root.activeLook !== menu.lookId
                onClicked: { menu.close(); Backend.updateLook(menu.lookId) }
            }
            MenuRow {
                objectName: "lookRename"
                iconName: "write"; text: qsTr("Rename…")
                onClicked: { menu.close(); nameSheet.lookId = menu.lookId; nameSheet.open() }
            }
            MenuRow {
                objectName: "lookExport"
                iconName: "download"; text: qsTr("Save as a file…")
                onClicked: {
                    menu.close()
                    root._openExport(menu.lookId)
                }
            }
            MenuRow {
                objectName: "lookDelete"
                iconName: "trash"; text: qsTr("Delete…"); danger: true
                onClicked: { menu.close(); deleteSheet.lookId = menu.lookId; deleteSheet.lookName = menu.lookName; deleteSheet.open() }
            }
        }
    }
    component MenuRow: C.AbstractButton {
        id: row
        property string iconName: ""
        property bool danger: false
        width: 238
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
            opacity: row.enabled ? 1 : 0.45
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
        title: renaming ? qsTr("Rename your look") : qsTr("Save this look")
        subtitle: renaming ? ""
            : qsTr("It joins the looks on Home, to pick again or share. A look keeps the colours, the glass, motion, the lock screen's look and the pointer. Your choice of apps and this PC's own settings stay out of it.")
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
            // A look with this name already: ask, rather than a second tile with its name.
            const same = renaming ? "" : Backend.lookNamed(nameField.text)
            if (same.length) {
                replaceSheet.lookId = same
                replaceSheet.lookName = (root.looks.find(l => l.id === same) || {}).name || nameField.text.trim()
                replaceSheet.typed = nameField.text
                replaceSheet.openedByKeyboard = nameSheet.openedByKeyboard || nameField.activeFocus
                replaceSheet.open()
                // Closing, the replace sheet gives the keyboard back to what opened this one.
                replaceSheet._returnTo = nameSheet._returnTo
                replaceSheet._returnReason = nameSheet._returnReason
                nameSheet._returnTo = null
                nameSheet.close()
                return
            }
            const ok = renaming ? Backend.renameLook(lookId, nameField.text) : Backend.saveLook(nameField.text)
            if (ok.length) nameSheet.close()
        }
        buttons: [
            LgButton { text: qsTr("Cancel"); kind: "secondary"; onClicked: nameSheet.close() },
            LgButton {
                id: saveButton
                objectName: "lookNameSave"
                text: nameSheet.renaming ? qsTr("Rename") : qsTr("Save")
                kind: "primary"
                iconName: "check"
                enabled: nameField.text.trim().length > 0
                onClicked: nameSheet.done()
            }
        ]
        Column {
            width: parent.width
            spacing: 8
            Text { text: qsTr("Name"); color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
            C.TextField {
                id: nameField
                objectName: "lookNameField"
                width: parent.width
                height: 40
                leftPadding: 14
                rightPadding: 14
                color: Theme.text
                placeholderText: qsTr("For example: Evening blue")
                placeholderTextColor: Theme.textFaint
                selectionColor: Theme.alpha(Theme.accent, 0.4)
                selectedTextColor: Theme.text
                font.pixelSize: Theme.fsBody
                maximumLength: 40
                Accessible.name: qsTr("Look name")
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

    // ---- a look with that name already ---------------------------------------------------------
    Sheet {
        id: replaceSheet
        objectName: "lookReplaceSheet"
        property string lookId: ""
        property string lookName: ""
        property string typed: ""
        readonly property string bothName: visible ? Backend.uniqueLookName(typed) : ""
        title: qsTr("Replace “%1”?").arg(lookName)
        subtitle: qsTr("You already have a look with this name. Replace puts this look in its place; Keep both saves it as “%1”.").arg(bothName)
        iconName: "alert"
        iconColor: Theme.warn
        width: Math.min(540, (parent ? parent.width : 800) - 64)
        // Enter keeps both: nothing is lost.
        initialFocusItem: keepBoth
        buttons: [
            LgButton { objectName: "lookReplaceCancel"; text: qsTr("Cancel"); kind: "secondary"; onClicked: replaceSheet.close() },
            LgButton {
                id: keepBoth
                objectName: "lookKeepBoth"
                text: qsTr("Keep both")
                kind: "secondary"
                onClicked: {
                    const name = replaceSheet.bothName
                    replaceSheet.close()
                    Backend.saveLook(name)
                }
            },
            LgButton {
                objectName: "lookReplace"
                text: qsTr("Replace")
                kind: "primary"
                iconName: "check"
                onClicked: {
                    replaceSheet.close()
                    Backend.replaceLook(replaceSheet.lookId)
                }
            }
        ]
        Item { width: 1; height: 1 }
    }

    // ---- delete -----------------------------------------------------------------------------
    Sheet {
        id: deleteSheet
        objectName: "lookDeleteSheet"
        property string lookId: ""
        property string lookName: ""
        title: qsTr("Delete “%1”?").arg(lookName)
        subtitle: qsTr("Only the saved look goes. Your desktop keeps the look you applied.")
        iconName: "trash"
        iconColor: Theme.bad
        width: Math.min(520, (parent ? parent.width : 800) - 64)
        buttons: [
            LgButton { text: qsTr("Cancel"); kind: "secondary"; onClicked: deleteSheet.close() },
            LgButton {
                objectName: "lookDeleteConfirm"
                text: qsTr("Delete")
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
        title: ({ "import": qsTr("This look can't be added"), "export": qsTr("The look wasn't saved as a file") })[what]
               || qsTr("The look wasn't saved")
        iconName: "alert"
        iconColor: Theme.warn
        width: Math.min(520, (parent ? parent.width : 800) - 64)
        buttons: [ LgButton { text: qsTr("OK"); kind: "primary"; onClicked: problemSheet.close() } ]
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
            problemSheet.subtitle = qsTr("Saving looks as files needs Qt's file dialogs, which aren't installed. On Ubuntu and Debian, install qml6-module-qtquick-dialogs.")
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
