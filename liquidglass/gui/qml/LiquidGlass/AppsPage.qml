import QtQuick
import QtQuick.Controls.Basic as C
import LiquidGlass.Core

// Every target the engine knows, grouped, with an honest state and a switch.
Item {
    id: page

    Item {
        id: intro
        width: parent.width
        height: 64
        Column {
            anchors.verticalCenter: parent.verticalCenter
            spacing: 4
            Text { text: "Apps and surfaces"; color: Theme.text; font.pixelSize: Theme.fsHeading; font.weight: Font.Bold }
            Text {
                text: Backend.targetsReady
                      ? Backend.activeTargetCount + " will be themed on Apply. Anything not installed is skipped, and Restore original undoes everything."
                      : "Checking what's installed…"
                color: Theme.textDim
                font.pixelSize: Theme.fsBody
            }
        }
        LgButton {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            kind: "secondary"
            text: "Check again"
            iconName: "refresh"
            enabled: Backend.targetsReady && !Backend.busy
            tip: "Look for newly installed apps and extensions"
            onClicked: Backend.refreshTargets()
        }
    }

    // loading
    Column {
        anchors.centerIn: parent
        spacing: 12
        visible: !Backend.targetsReady
        Spinner { size: 28; color: Theme.textDim; anchors.horizontalCenter: parent.horizontalCenter }
        Text { text: "Looking at your system…"; color: Theme.textDim; font.pixelSize: Theme.fsBody }
    }
    Column {
        anchors.centerIn: parent
        spacing: 8
        visible: Backend.targetsReady && Backend.targets.length === 0
        Icon { name: "apps"; size: 32; color: Theme.textFaint; anchors.horizontalCenter: parent.horizontalCenter }
        Text { text: "No themable apps were found"; color: Theme.textDim; font.pixelSize: Theme.fsBody; anchors.horizontalCenter: parent.horizontalCenter }
    }

    Flickable {
        id: list
        anchors.top: intro.bottom
        anchors.topMargin: 8
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.rightMargin: -12
        contentHeight: groups.height + 16
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        visible: Backend.targetsReady
        opacity: Backend.targetsReady ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
        C.ScrollBar.vertical: LgScrollBar {}

        Column {
            id: groups
            width: list.width - 12
            spacing: 20
            Repeater {
                model: Backend.targets
                delegate: Column {
                    id: group
                    required property var modelData
                    width: groups.width
                    spacing: 8
                    SectionTitle { text: group.modelData.group; leftPadding: 4 }
                    Card {
                        width: parent.width
                        height: implicitHeight
                        padding: 0
                        Column {
                            width: parent.width
                            Repeater {
                                model: group.modelData.items
                                delegate: TargetRow {
                                    required property var modelData
                                    required property int index
                                    width: parent.width
                                    item: modelData
                                    first: index === 0
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
