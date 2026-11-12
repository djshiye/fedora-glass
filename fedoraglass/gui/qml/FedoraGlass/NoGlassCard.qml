import QtQuick
import QtQuick.Controls.Basic as C
import FedoraGlass.Core

// Apps with their own glass: the user's own list of apps, each with its choice: no glass (a plain
// solid background), more solid glass or clearer glass behind its windows. Add (a picker of the
// installed apps), Remove, and the ones that never get glass.
Card {
    id: root
    objectName: "noGlassCard"
    height: implicitHeight
    readonly property var rows: Backend.noGlassApps
    readonly property QtObject picker: picker
    // The choices of a row, in the order the user reads them.
    readonly property var glassChoices: [
        { value: "none", label: qsTr("No glass"), tip: qsTr("A plain solid background, also lighter on the graphics card") },
        { value: "solid", label: qsTr("More solid"), tip: qsTr("Thicker frost, easier to read over a busy wallpaper") },
        { value: "clearer", label: qsTr("Clearer"), tip: qsTr("Thinner frost, more of the desktop shows through") }
    ]
    // A row whose choice was changed from the keyboard: the list is made again, and its new
    // row takes the focus back, so the arrow keys keep working.
    property string _refocus: ""

    // Names and icons for the rows come from the installed apps, read off the UI thread.
    Component.onCompleted: Backend.refreshInstalledApps()

    Column {
        width: parent.width
        spacing: 14
        Item {
            width: parent.width
            height: Math.max(title.implicitHeight, addBtn.height)
            SectionTitle {
                id: title
                width: parent.width - addBtn.width - 16
                anchors.verticalCenter: parent.verticalCenter
                text: qsTr("Apps with their own glass")
                caption: qsTr("Choose how much glass is behind each app's windows. The app's own colours stay as they are.")
                resetKeys: ["no_glass_apps", "app_glass"]
                resetTip: qsTr("Take every app off this list")
            }
            LgButton {
                id: addBtn
                objectName: "noGlassAdd"
                anchors.right: parent.right
                anchors.top: parent.top
                kind: "secondary"
                iconName: "plus"
                text: qsTr("Add app")
                leftPadding: 14; rightPadding: 16
                tip: qsTr("Pick an installed app")
                onClicked: { picker.openedByKeyboard = visualFocus; picker.open() }
                Accessible.name: qsTr("Add an app without glass")
            }
        }

        Rectangle {
            objectName: "noGlassAppWindowsOff"
            visible: !Backend.blurAppWindows
            width: parent.width
            height: offText.implicitHeight + 20
            radius: Theme.rS
            color: Theme.well
            Row {
                x: 12; y: 10
                width: parent.width - 24
                spacing: 10
                Icon { name: "info"; size: 16; color: Theme.accentText }
                Text {
                    id: offText
                    width: parent.width - 26
                    wrapMode: Text.WordWrap
                    color: Theme.textDim
                    font.pixelSize: Theme.fsSmall
                    text: qsTr("Glass behind app windows is off on the Glass page, so no app gets it right now.")
                }
            }
        }

        // The list: one row per app, with its icon, its name and Remove.
        Rectangle {
            objectName: "noGlassList"
            width: parent.width
            height: root.rows.length ? list.height : empty.implicitHeight + 28
            radius: Theme.rS
            color: Theme.well
            Text {
                id: empty
                objectName: "noGlassEmpty"
                visible: root.rows.length === 0
                x: 16
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - 32
                wrapMode: Text.WordWrap
                color: Theme.textFaint
                font.pixelSize: Theme.fsSmall
                text: qsTr("No apps added. Every window gets glass, except the ones below.")
            }
            Column {
                id: list
                width: parent.width
                Repeater {
                    model: root.rows
                    delegate: Item {
                        id: row
                        required property var modelData
                        required property int index
                        objectName: "noGlassRow_" + modelData.key
                        width: list.width
                        // Two lines: the app and Remove, then its choice under its name.
                        height: 92
                        Rectangle {
                            visible: row.index > 0
                            x: 16; width: parent.width - 32; height: 1
                            color: Theme.divider
                        }
                        Component.onCompleted: if (root._refocus === modelData.key) { root._refocus = ""; choice.forceActiveFocus(Qt.TabFocusReason) }
                        AppIcon {
                            x: 14
                            y: 12
                            size: 30
                            source: row.modelData.icon
                            label: row.modelData.name
                            tileColor: Theme.accent
                        }
                        Text {
                            x: 56
                            width: parent.width - x - removeBtn.width - 24
                            anchors.verticalCenter: removeBtn.verticalCenter
                            elide: Text.ElideRight
                            text: row.modelData.name
                            color: Theme.text
                            font.pixelSize: Theme.fsBody
                            font.weight: Font.Medium
                        }
                        Segmented {
                            id: choice
                            objectName: "noGlassChoice"
                            x: 56
                            y: 50
                            width: Math.min(330, row.width - x - 16)
                            compact: true
                            fit: true
                            model: root.glassChoices
                            value: row.modelData.glass
                            Accessible.name: qsTr("Glass for %1").arg(row.modelData.name)
                            onActivated: (v) => {
                                if (v === row.modelData.glass)
                                    return
                                if (choice.activeFocus)
                                    root._refocus = row.modelData.key
                                Backend.setAppGlass(row.modelData.key, v)
                            }
                        }
                        LgButton {
                            id: removeBtn
                            objectName: "noGlassRemove"
                            anchors.right: parent.right
                            anchors.rightMargin: 8
                            y: 11
                            implicitHeight: 32
                            kind: "flat"
                            text: qsTr("Remove")
                            leftPadding: 12; rightPadding: 12
                            tip: qsTr("Give %1 normal glass again (Apply to use it)").arg(row.modelData.name)
                            onClicked: Backend.removeNoGlassApp(row.modelData.key)
                            Accessible.name: qsTr("Remove %1").arg(row.modelData.name)
                        }
                    }
                }
            }
        }

        // The ones the extension always leaves alone, so nobody wonders why Steam has no glass.
        Row {
            width: parent.width
            spacing: 10
            Icon { name: "info"; size: 16; color: Theme.textFaint }
            Text {
                objectName: "noGlassBuiltIn"
                width: parent.width - 26
                wrapMode: Text.WordWrap
                color: Theme.textFaint
                font.pixelSize: Theme.fsSmall
                lineHeight: 1.1
                text: qsTr("Always without glass: %1").arg(Backend.noGlassBuiltIn)
            }
        }
    }

    AppPickerSheet { id: picker }
}
