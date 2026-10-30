import QtQuick
import QtQuick.Controls.Basic as C
import LiquidGlass.Core

// "Show changes": every action Apply would take, per target, before it runs.
Sheet {
    id: sheet
    property var plan: []
    readonly property int total: {
        let n = 0
        for (const p of plan) n += p.actions.length
        return n
    }
    title: "What Apply will change"
    subtitle: total === 0 ? "Nothing: no enabled target is available on this system."
                          : total + " change" + (total === 1 ? "" : "s") + " in " + plan.length + " place" + (plan.length === 1 ? "" : "s")
                            + ". Each one is backed up first, and Restore original undoes all of it."
    iconName: "list"
    buttons: [
        LgButton { text: "Close"; kind: "secondary"; onClicked: sheet.close() },
        LgButton {
            text: "Apply"
            kind: "primary"
            iconName: "check"
            enabled: !Backend.busy
            onClicked: { sheet.close(); Backend.apply() }
        }
    ]

    Flickable {
        width: parent.width
        height: Math.min(contentHeight, sheet.maxBodyHeight)
        contentHeight: col.height
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        C.ScrollBar.vertical: LgScrollBar {}
        Column {
            id: col
            width: parent.width - 8
            spacing: 14
            Repeater {
                model: sheet.plan
                delegate: Column {
                    id: grp
                    required property var modelData
                    readonly property int n: modelData.actions.length
                    property bool open: n > 0 && n <= 4
                    width: col.width
                    spacing: 6
                    C.AbstractButton {
                        id: grpHead
                        width: parent.width
                        height: 30
                        enabled: grp.n > 0
                        hoverEnabled: true
                        focusPolicy: Qt.StrongFocus
                        onClicked: grp.open = !grp.open
                        Accessible.name: grp.modelData.name
                        HoverHandler { cursorShape: grp.n > 0 ? Qt.PointingHandCursor : Qt.ArrowCursor }
                        background: Rectangle {
                            radius: 8
                            color: grpHead.hovered ? Theme.hover : "transparent"
                            FocusRing { target: grpHead; radius: 10; gap: 1 }
                        }
                        contentItem: Row {
                            spacing: 6
                            leftPadding: 2
                            Icon {
                                visible: grp.n > 0
                                anchors.verticalCenter: parent.verticalCenter
                                name: "chevronRight"; size: 16; color: Theme.textDim
                                rotation: grp.open ? 90 : 0
                                Behavior on rotation { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                            }
                            Text { anchors.verticalCenter: parent.verticalCenter; text: grp.modelData.name; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.DemiBold }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: grp.n === 0 ? "nothing to change" : grp.n + (grp.n === 1 ? " change" : " changes")
                                color: Theme.textFaint
                                font.pixelSize: 12
                            }
                        }
                    }
                    Rectangle {
                        visible: grp.open
                        width: parent.width
                        height: lines.height + 16
                        radius: 12
                        color: Theme.well
                        Column {
                            id: lines
                            x: 12; y: 8
                            width: parent.width - 24
                            spacing: 6
                            Repeater {
                                model: grp.open ? grp.modelData.actions : []
                                delegate: Item {
                                    id: act
                                    required property var modelData
                                    property bool full: false
                                    width: lines.width
                                    height: Math.max(18, line.height)
                                    Icon {
                                        y: 1
                                        name: act.modelData.kind === "WriteFile" ? "write" : act.modelData.kind === "GSet" || act.modelData.kind === "GReset" ? "set" : "run"
                                        size: 15
                                        color: Theme.textDim
                                    }
                                    Text {
                                        id: line
                                        x: 24
                                        width: parent.width - 24
                                        text: act.modelData.text
                                        color: Theme.text
                                        wrapMode: Text.WrapAnywhere
                                        maximumLineCount: act.full ? 1000 : 2
                                        elide: Text.ElideRight
                                        font.family: Theme.mono
                                        font.pixelSize: 12
                                    }
                                    TapHandler { enabled: line.truncated || act.full; onTapped: act.full = !act.full }
                                    HoverHandler { enabled: line.truncated || act.full; cursorShape: Qt.PointingHandCursor }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
