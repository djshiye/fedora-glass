import QtQuick
import QtQuick.Controls.Basic as C
import FedoraGlass.Core

// Apps without glass: the user's own list of apps whose windows get no glass behind them,
// with Add (a picker of the installed apps) and Remove, and the ones that never get it.
Card {
    id: root
    objectName: "noGlassCard"
    height: implicitHeight
    readonly property var rows: Backend.noGlassApps
    readonly property QtObject picker: picker

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
                text: qsTr("Apps without glass")
                caption: qsTr("Their windows get no glass behind them. Handy for apps that draw their own solid windows.")
                resetKeys: ["no_glass_apps"]
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
                        height: 52
                        Rectangle {
                            visible: row.index > 0
                            x: 16; width: parent.width - 32; height: 1
                            color: Theme.divider
                        }
                        AppIcon {
                            x: 14
                            anchors.verticalCenter: parent.verticalCenter
                            size: 30
                            source: row.modelData.icon
                            label: row.modelData.name
                            tileColor: Theme.accent
                        }
                        Text {
                            x: 56
                            width: parent.width - x - removeBtn.width - 24
                            anchors.verticalCenter: parent.verticalCenter
                            elide: Text.ElideRight
                            text: row.modelData.name
                            color: Theme.text
                            font.pixelSize: Theme.fsBody
                            font.weight: Font.Medium
                        }
                        LgButton {
                            id: removeBtn
                            objectName: "noGlassRemove"
                            anchors.right: parent.right
                            anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            implicitHeight: 32
                            kind: "flat"
                            text: qsTr("Remove")
                            leftPadding: 12; rightPadding: 12
                            tip: qsTr("Give %1 glass again (Apply to use it)").arg(row.modelData.name)
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
