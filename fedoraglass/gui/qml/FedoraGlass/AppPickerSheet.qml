import QtQuick
import QtQuick.Controls.Basic as C
import FedoraGlass.Core

// Pick the apps whose windows get no glass: every installed app, searchable, with a tick on
// the ones already on the list. A click puts an app on the list or takes it off.
Sheet {
    id: sheet
    objectName: "appPicker"
    title: qsTr("Apps without glass")
    subtitle: qsTr("Pick the apps whose windows should get no glass. Apply to use them.")
    iconName: "apps"
    initialFocusItem: field

    readonly property string query: field.text.trim().toLowerCase()
    readonly property var shown: {
        const q = query
        const all = Backend.installedApps
        // By name, or by the app's id (org.gimp.GIMP) for people who know it; never by ".desktop".
        return q === "" ? all : all.filter(a => a.name.toLowerCase().indexOf(q) >= 0
                                                || a.id.replace(/\.desktop$/, "").toLowerCase().indexOf(q) >= 0)
    }

    onAboutToShow: { field.text = ""; Backend.refreshInstalledApps() }

    buttons: [
        LgButton { objectName: "appPickerDone"; text: qsTr("Done"); kind: "primary"; onClicked: sheet.close() }
    ]

    Column {
        width: parent.width
        spacing: 12
        Rectangle {
            width: parent.width
            height: 38
            radius: Theme.rS
            color: field.activeFocus ? Theme.wellHi : Theme.well
            border.width: field.activeFocus ? 2 : 1
            border.color: field.activeFocus ? Theme.accent : Theme.border
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
                objectName: "appPickerSearch"
                x: 32
                width: parent.width - x - 8
                height: parent.height
                verticalAlignment: TextInput.AlignVCenter
                leftPadding: 4; rightPadding: 4
                placeholderText: qsTr("Search apps")
                placeholderTextColor: Theme.textFaint
                color: Theme.text
                selectionColor: Theme.alpha(Theme.accent, 0.4)
                selectedTextColor: Theme.text
                font.pixelSize: 14
                background: Item {}
                Accessible.name: qsTr("Search apps")
                Keys.onDownPressed: { if (apps.count) { apps.currentIndex = 0; apps.forceActiveFocus(Qt.TabFocusReason) } }
            }
        }

        Item {
            width: parent.width
            height: Math.min(380, Math.max(160, sheet.maxBodyHeight - 60))
            Text {
                anchors.centerIn: parent
                visible: apps.count === 0
                width: parent.width - 40
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                color: Theme.textFaint
                font.pixelSize: Theme.fsBody
                text: !Backend.installedAppsReady ? qsTr("Looking for your apps…")
                    : sheet.query !== "" ? qsTr("No app matches “%1”.").arg(field.text.trim())
                    : qsTr("No apps were found.")
            }
            ListView {
                id: apps
                objectName: "appPickerList"
                anchors.fill: parent
                clip: true
                model: sheet.shown
                boundsBehavior: Flickable.StopAtBounds
                keyNavigationEnabled: true
                C.ScrollBar.vertical: LgScrollBar {}
                Accessible.role: Accessible.List
                Accessible.name: qsTr("Installed apps")
                delegate: C.AbstractButton {
                    id: item
                    required property var modelData
                    required property int index
                    readonly property bool builtIn: modelData.builtIn === true
                    readonly property bool added: Backend.noGlassApps.some(r => r.key === modelData.id)
                    objectName: "appPick_" + modelData.id
                    width: apps.width - 8
                    height: 48
                    enabled: !builtIn
                    hoverEnabled: true
                    focusPolicy: Qt.StrongFocus
                    checkable: false
                    Accessible.role: Accessible.CheckBox
                    Accessible.checkable: true
                    Accessible.checked: item.added || builtIn
                    Accessible.name: builtIn ? qsTr("%1, always without glass").arg(modelData.name) : modelData.name
                    onClicked: Backend.toggleNoGlassApp(modelData.id)
                    Keys.onSpacePressed: Backend.toggleNoGlassApp(modelData.id)
                    HoverHandler { cursorShape: item.builtIn ? Qt.ArrowCursor : Qt.PointingHandCursor }
                    background: Rectangle {
                        radius: Theme.rS
                        color: item.down ? Theme.pressed : item.hovered || item.ListView.isCurrentItem && apps.activeFocus ? Theme.hover : "transparent"
                        FocusRing { target: item; radius: Theme.rS + 3 }
                    }
                    contentItem: Item {
                        AppIcon {
                            x: 8
                            anchors.verticalCenter: parent.verticalCenter
                            size: 30
                            source: item.modelData.icon
                            label: item.modelData.name
                            tileColor: Theme.accent
                            opacity: item.builtIn ? 0.55 : 1
                        }
                        Text {
                            x: 50
                            width: parent.width - x - mark.width - 20
                            anchors.verticalCenter: parent.verticalCenter
                            elide: Text.ElideRight
                            text: item.modelData.name
                            color: item.builtIn ? Theme.textFaint : Theme.text
                            font.pixelSize: Theme.fsBody
                            font.weight: Font.Medium
                        }
                        Item {
                            id: mark
                            anchors.right: parent.right
                            anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            width: item.builtIn ? always.implicitWidth : 24
                            height: 24
                            Text {
                                id: always
                                visible: item.builtIn
                                anchors.verticalCenter: parent.verticalCenter
                                text: qsTr("Always without glass")
                                color: Theme.textFaint
                                font.pixelSize: Theme.fsSmall
                            }
                            Rectangle {
                                visible: !item.builtIn
                                anchors.fill: parent
                                radius: 12
                                color: item.added ? Theme.accent : "transparent"
                                border.width: item.added ? 0 : 1.5
                                border.color: Theme.borderHi
                                Icon {
                                    visible: item.added
                                    anchors.centerIn: parent
                                    name: "check"
                                    size: 16
                                    strokeWidth: 2.2
                                    color: Theme.accentFg
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
