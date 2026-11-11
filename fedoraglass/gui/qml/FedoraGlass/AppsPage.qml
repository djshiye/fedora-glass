import QtQuick
import QtQuick.Controls.Basic as C
import FedoraGlass.Core

// What this PC has first, grouped, each with an honest state and a switch. Parts for
// apps and extensions that aren't installed fold away into one quiet card at the end.
Item {
    id: page
    objectName: "appsPage"

    // Survives "Check again": the card is not rebuilt when the lists refresh.
    property bool missingOpen: false
    readonly property var installed: Backend.installedTargets
    readonly property var missing: Backend.missingTargets

    Item {
        id: intro
        width: parent.width
        height: Math.max(64, introText.implicitHeight + 16)
        Column {
            id: introText
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - checkAgain.width - 20
            spacing: 4
            Text { text: qsTr("Apps and surfaces"); color: Theme.text; font.pixelSize: Theme.fsHeading; font.weight: Font.Bold }
            Text {
                text: Backend.targetsReady
                      ? qsTr("%1 will be themed on Apply. Anything not installed is skipped, and Restore original undoes everything.").arg(Backend.activeTargetCount)
                      : qsTr("Checking what's installed…")
                width: parent.width
                wrapMode: Text.WordWrap
                color: Theme.textDim
                font.pixelSize: Theme.fsBody
            }
        }
        LgButton {
            id: checkAgain
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            kind: "secondary"
            text: qsTr("Check again")
            iconName: "refresh"
            enabled: Backend.targetsReady && !Backend.busy
            tip: qsTr("Look for newly installed apps and extensions")
            onClicked: Backend.refreshTargets()
        }
    }

    // loading
    Column {
        anchors.centerIn: parent
        spacing: 12
        visible: !Backend.targetsReady
        Spinner { size: 28; color: Theme.textDim; anchors.horizontalCenter: parent.horizontalCenter }
        Text { text: qsTr("Looking at your system…"); color: Theme.textDim; font.pixelSize: Theme.fsBody }
    }

    Flickable {
        id: list
        objectName: "appsList"
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
        NumberAnimation { id: reveal; target: list; property: "contentY"; duration: Theme.slow; easing.type: Easing.OutCubic }

        Column {
            id: groups
            width: list.width - 12
            spacing: 20

            // first run with nothing to theme
            Item {
                objectName: "appsEmpty"
                visible: Backend.targetsReady && page.installed.length === 0
                width: parent.width
                height: visible ? Math.max(160, list.height - (fold.visible ? fold.height + 40 : 0)) : 0
                Column {
                    anchors.centerIn: parent
                    spacing: 8
                    Icon { name: "apps"; size: 32; color: Theme.textFaint; anchors.horizontalCenter: parent.horizontalCenter }
                    Text { text: qsTr("No themable apps were found"); color: Theme.textDim; font.pixelSize: Theme.fsBody; anchors.horizontalCenter: parent.horizontalCenter }
                }
            }

            Repeater {
                model: page.installed
                delegate: Column {
                    id: group
                    required property var modelData
                    width: groups.width
                    spacing: 8
                    SectionTitle { group: true; text: group.modelData.groupLabel || group.modelData.group; leftPadding: 4 }
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

            // Everything this PC doesn't have, folded into one calm card.
            Card {
                id: fold
                objectName: "notInstalledCard"
                visible: page.missing.length > 0
                width: parent.width
                height: head.height + rows.height
                padding: 0
                color: Theme.alpha(Theme.surface, Theme.surface.a * 0.6)   // quieter than the cards above
                clip: true

                C.AbstractButton {
                    id: head
                    objectName: "notInstalled"
                    width: parent.width
                    height: 60
                    hoverEnabled: true
                    focusPolicy: Qt.StrongFocus
                    onClicked: page.toggleMissing()
                    Keys.onReturnPressed: page.toggleMissing()
                    Keys.onEnterPressed: page.toggleMissing()
                    Accessible.role: Accessible.Button
                    Accessible.name: page.missingOpen ? qsTr("Not installed here, %1, shown").arg(page.missing.length) : qsTr("Not installed here, %1, hidden").arg(page.missing.length)
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    background: Rectangle {
                        radius: Theme.rM
                        color: head.hovered ? Theme.hover : "transparent"
                        Behavior on color { ColorAnimation { duration: Theme.fast } }
                        FocusRing { target: head; radius: Theme.rM + 2; gap: 0 }
                    }
                    contentItem: Item {
                        Icon {
                            id: chev
                            x: 18
                            anchors.verticalCenter: parent.verticalCenter
                            name: "chevronRight"
                            size: 18
                            color: Theme.textDim
                            rotation: page.missingOpen ? 90 : 0
                            Behavior on rotation { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                        }
                        Column {
                            anchors.left: chev.right
                            anchors.leftMargin: 12
                            anchors.right: parent.right
                            anchors.rightMargin: 20
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2
                            Text {
                                objectName: "notInstalledTitle"
                                text: qsTr("Not installed here (%1)").arg(page.missing.length)
                                color: Theme.textDim
                                font.pixelSize: Theme.fsBody
                                font.weight: Font.DemiBold
                            }
                            Text {
                                width: parent.width
                                elide: Text.ElideRight
                                text: qsTr("Skipped on Apply. Install one, then choose Check again.")
                                color: Theme.textFaint
                                font.pixelSize: Theme.fsSmall + 1
                            }
                        }
                    }
                }

                Column {
                    id: rows
                    objectName: "notInstalledRows"
                    y: head.height
                    width: parent.width
                    height: page.missingOpen ? implicitHeight + 8 : 0
                    opacity: page.missingOpen ? 1 : 0
                    visible: height > 0.5
                    Behavior on height { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
                    Behavior on opacity { NumberAnimation { duration: Theme.normal } }
                    Repeater {
                        model: page.missing
                        delegate: Item {
                            id: mrow
                            required property var modelData
                            width: rows.width
                            height: Math.max(nameText.height, why.height) + 22
                            Rectangle { x: 20; width: parent.width - 40; height: 1; color: Theme.divider }
                            Text {
                                id: nameText
                                x: 48; y: 11
                                width: Math.min(220, parent.width * 0.34)
                                text: mrow.modelData.name || mrow.modelData.id
                                color: Theme.text
                                opacity: 0.85
                                elide: Text.ElideRight
                                font.pixelSize: 13
                                font.weight: Font.Medium
                            }
                            TextEdit {      // an install command stays selectable, to copy
                                id: why
                                x: nameText.x + nameText.width + 16
                                y: 11
                                width: parent.width - x - 20
                                text: mrow.modelData.install || mrow.modelData.reason || ""
                                readOnly: true
                                selectByMouse: (mrow.modelData.install || "").length > 0
                                activeFocusOnPress: false
                                wrapMode: TextEdit.Wrap
                                color: Theme.textDim
                                selectionColor: Theme.alpha(Theme.accent, 0.4)
                                selectedTextColor: Theme.text
                                font.pixelSize: 13
                            }
                        }
                    }
                }
            }
        }
    }

    function toggleMissing() {
        missingOpen = !missingOpen
        if (!missingOpen)
            return
        // Bring the opened list up into view rather than leaving it below the fold.
        const top = fold.y - 28
        const end = fold.y + head.height + rows.implicitHeight + 8 + 16 - list.height
        const want = Math.max(list.contentY, Math.min(top, end))
        if (want > list.contentY) {
            reveal.to = want
            reveal.restart()
        }
    }

    // Soft edges where the list scrolls under, so it's clear there is more.
    Rectangle {
        x: list.x; width: groups.width
        y: list.y; height: 24
        visible: list.visible && list.contentY > 1
        gradient: Gradient {
            GradientStop { position: 0; color: Theme.alpha(Theme.base, 0.9) }
            GradientStop { position: 1; color: Theme.alpha(Theme.base, 0) }
        }
    }
    Rectangle {
        x: list.x; width: groups.width
        y: list.y + list.height - height; height: 32
        visible: list.visible && list.contentY + list.height < list.contentHeight - 1
        gradient: Gradient {
            GradientStop { position: 0; color: Theme.alpha(Theme.base, 0) }
            GradientStop { position: 1; color: Theme.alpha(Theme.base, 0.92) }
        }
    }
}
