import QtQuick
import QtQuick.Controls.Basic as C
import FedoraGlass.Core

// "See changes": first what you changed and haven't applied yet, in plain words and by
// page ("Frost: 45% → 60%"), each a click away from its control. Below, folded, every
// file and setting Apply writes, per part of the desktop.
Sheet {
    id: sheet
    objectName: "changesSheet"
    property var plan: []
    property var pages: []              // the sidebar's pages: [{ id, label }]
    signal jump(string page, string name)
    readonly property int total: {
        let n = 0
        for (const p of plan) n += p.actions.length
        return n
    }
    // Only while the sheet shows (from aboutToShow on): closed, it needn't follow every slider tick.
    property bool _showing: false
    readonly property var changes: _showing ? Backend.changeList : []
    // The changes by page, in sidebar order: [{ page, label, rows }].
    readonly property var groups: {
        const out = []
        const order = pages.map(p => p.id)
        for (const r of changes) {
            let g = out.find(x => x.page === r.page)
            if (!g) {
                const info = pages.find(p => p.id === r.page)
                g = { page: r.page, label: info ? info.label : r.page, rows: [] }
                out.push(g)
            }
            g.rows.push(r)
        }
        out.sort((a, b) => order.indexOf(a.page) - order.indexOf(b.page))
        return out
    }
    property bool detailsOpen: false
    onAboutToShow: {
        _showing = true
        detailsOpen = changes.length === 0
    }
    onVisibleChanged: if (!visible) _showing = false
    title: qsTr("What Apply will change")
    subtitle: changes.length === 0
        ? qsTr("You haven't changed anything since your last Apply. Apply puts the same look on your desktop again.")
        : (changes.length === 1 ? qsTr("1 change not applied yet. Click one to go to it.") : qsTr("%1 changes not applied yet. Click one to go to it.").arg(changes.length))
    iconName: "list"
    buttons: [
        LgButton { text: qsTr("Close"); kind: "secondary"; onClicked: sheet.close() },
        LgButton {
            text: qsTr("Apply")
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
                model: sheet.groups
                delegate: Column {
                    id: pg
                    required property var modelData
                    width: col.width
                    spacing: 6
                    Text {
                        text: pg.modelData.label
                        color: Theme.textDim
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                        font.letterSpacing: 0.2
                    }
                    Rectangle {
                        width: parent.width
                        height: rowsCol.height + 8
                        radius: Theme.rS
                        color: Theme.well
                        Column {
                            id: rowsCol
                            x: 4; y: 4
                            width: parent.width - 8
                            Repeater {
                                model: pg.modelData.rows
                                delegate: C.AbstractButton {
                                    id: change
                                    required property var modelData
                                    objectName: "change_" + modelData.key
                                    readonly property bool canJump: modelData.name.length > 0
                                    width: rowsCol.width
                                    height: Math.max(36, what.implicitHeight + 14)
                                    enabled: canJump
                                    hoverEnabled: true
                                    focusPolicy: Qt.StrongFocus
                                    Accessible.name: qsTr("%1: %2 to %3").arg(modelData.label).arg(modelData.before).arg(modelData.after)
                                    Accessible.description: canJump ? qsTr("Go to this setting") : ""
                                    onClicked: { sheet.close(); sheet.jump(modelData.page, modelData.name) }
                                    HoverHandler { cursorShape: change.canJump ? Qt.PointingHandCursor : Qt.ArrowCursor }
                                    background: Rectangle {
                                        radius: Theme.rXs
                                        color: change.down ? Theme.pressed : change.hovered ? Theme.hover : "transparent"
                                        FocusRing { target: change; radius: Theme.rXs + 2; gap: 1 }
                                    }
                                    contentItem: Item {
                                        Text {
                                            id: what
                                            x: 10
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: parent.width - x - values.width - 16
                                            text: change.modelData.label
                                            color: Theme.text
                                            font.pixelSize: Theme.fsBody
                                            wrapMode: Text.WordWrap
                                        }
                                        Row {
                                            id: values
                                            anchors.right: parent.right
                                            anchors.rightMargin: 6
                                            anchors.verticalCenter: parent.verticalCenter
                                            spacing: 8
                                            Text {
                                                anchors.verticalCenter: parent.verticalCenter
                                                width: Math.min(implicitWidth, 150)
                                                elide: Text.ElideRight
                                                text: change.modelData.before
                                                color: Theme.textFaint
                                                font.pixelSize: Theme.fsBody
                                                font.features: { "tnum": 1 }
                                            }
                                            Text { anchors.verticalCenter: parent.verticalCenter; text: "→"; color: Theme.textFaint; font.pixelSize: Theme.fsBody }
                                            Text {
                                                anchors.verticalCenter: parent.verticalCenter
                                                width: Math.min(implicitWidth, 170)
                                                elide: Text.ElideRight
                                                text: change.modelData.after
                                                color: Theme.text
                                                font.pixelSize: Theme.fsBody
                                                font.weight: Font.DemiBold
                                                font.features: { "tnum": 1 }
                                            }
                                            Icon {
                                                anchors.verticalCenter: parent.verticalCenter
                                                visible: change.canJump
                                                opacity: change.hovered || change.visualFocus ? 1 : 0.35
                                                name: "chevronRight"; size: 15; strokeWidth: 2; color: Theme.textDim
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            // Every file and setting Apply writes: there to check, folded out of the way.
            C.AbstractButton {
                id: detailsHead
                objectName: "changeDetails"
                width: col.width
                height: 34
                hoverEnabled: true
                focusPolicy: Qt.StrongFocus
                onClicked: sheet.detailsOpen = !sheet.detailsOpen
                Accessible.name: qsTr("Files and settings Apply writes")
                HoverHandler { cursorShape: Qt.PointingHandCursor }
                background: Rectangle {
                    radius: Theme.rXs
                    color: detailsHead.hovered ? Theme.hover : "transparent"
                    FocusRing { target: detailsHead; radius: Theme.rXs + 2; gap: 1 }
                }
                contentItem: Row {
                    spacing: 6
                    leftPadding: 2
                    Icon {
                        anchors.verticalCenter: parent.verticalCenter
                        name: "chevronRight"; size: 16; color: Theme.textDim
                        rotation: sheet.detailsOpen ? 90 : 0
                        Behavior on rotation { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: qsTr("Files and settings Apply writes")
                        color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.DemiBold
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: sheet.total === 0 ? qsTr("none: no part that is switched on is installed here")
                            : sheet.plan.length === 1 ? qsTr("%1 in 1 place, each backed up first").arg(sheet.total)
                            : qsTr("%1 in %2 places, each backed up first").arg(sheet.total).arg(sheet.plan.length)
                        // Longer languages: cut with "…" at the sheet's edge instead of running past it.
                        width: Math.max(0, Math.min(implicitWidth, detailsHead.width - x - 8))
                        elide: Text.ElideRight
                        color: Theme.textFaint
                        font.pixelSize: 12
                    }
                }
            }
            Repeater {
                model: sheet.detailsOpen ? sheet.plan : []
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
                            radius: Theme.rXs
                            color: grpHead.hovered ? Theme.hover : "transparent"
                            FocusRing { target: grpHead; radius: Theme.rXs + 2; gap: 1 }
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
                                text: grp.n === 0 ? qsTr("nothing to change") : grp.n === 1 ? qsTr("1 change") : qsTr("%1 changes").arg(grp.n)
                                color: Theme.textFaint
                                font.pixelSize: 12
                            }
                        }
                    }
                    // What these lines do, in one plain sentence, above the raw lines.
                    Text {
                        objectName: "plain_" + grp.modelData.id
                        visible: grp.open && text.length > 0
                        x: 24
                        width: parent.width - x
                        text: grp.modelData.plain || ""
                        color: Theme.textDim
                        font.pixelSize: Theme.fsSmall
                        wrapMode: Text.WordWrap
                    }
                    Rectangle {
                        visible: grp.open
                        width: parent.width
                        height: lines.height + 16
                        radius: Theme.rS
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
