import QtQuick
import QtQuick.Controls.Basic as C
import FedoraGlass.Core

// What happened on Apply: applied, info, skipped, reverted and failed, with messages.
Sheet {
    id: sheet
    objectName: "resultsSheet"
    property var results: []
    onResultsChanged: skippedOpen = false
    function count(st) { return results.filter(r => r.status === st).length }
    readonly property int failedCount: count("failed")
    readonly property int appliedCount: count("applied")

    // A restart is only needed when the glass is applied but GNOME isn't running it yet,
    // or a Shell part waits for it. Themed apps alone (or the glass already running) need
    // none. The backend works it out after every Apply (Backend.restartNeeded, which the
    // footer shows too); these results saying so on their own count as well.
    function restartNeeded(rs) {
        // A glass that can't start (extensions off, an unsupported GNOME, an error) isn't
        // fixed by a restart: the note says what is.
        if (Backend.glassBlocked) return false
        return Backend.restartNeeded || (!Backend.glassLive && rs.some(r =>
            (r.id === "glass" && r.status === "applied") || (r.status === "info" && r.message.indexOf("Finishes after you restart") === 0)))
    }
    readonly property bool needsRestart: results.length > 0 && restartNeeded(results)
    title: failedCount > 0 ? "Applied, with " + failedCount + " problem" + (failedCount === 1 ? "" : "s")
         : results.length === 0 ? "Settings saved"
         : needsRestart ? "Applied. Restart your PC to finish"
         : Backend.glassBlocked ? "Applied, but the glass can't start"
         : Backend.glassLive ? "Fedora Glass is on" : "Your new look is applied"
    subtitle: results.length === 0 ? "Nothing to theme was found yet, so only your settings were saved."
            : failedCount > 0 ? "Everything else was applied. The details are below."
            : needsRestart && Backend.glassProblem === "old" ? Backend.glassProblemNote
            : Backend.glassBlocked ? Backend.glassProblemNote
            : needsRestart ? "GNOME starts the glass when your PC starts. Open apps pick up the new look when you reopen them."
            : "Open apps pick up the new look when you reopen them."
    iconName: failedCount > 0 || Backend.glassBlocked ? "alert" : "okCircle"
    iconColor: failedCount > 0 || Backend.glassBlocked ? Theme.warn : Theme.good
    // A stray Enter must never start a restart: with one pending, the sheet opens on "Later".
    initialFocusItem: needsRestart ? laterButton : null
    buttons: [
        LgButton {
            id: laterButton
            objectName: "restartLater"
            visible: sheet.needsRestart
            text: "Later"
            kind: "secondary"
            onClicked: sheet.close()
        },
        LgButton {
            // One main button: "Restart now…" when a restart finishes the job, else "Done".
            objectName: sheet.needsRestart ? "restartNow" : "resultsDone"
            text: sheet.needsRestart ? "Restart now…" : "Done"
            iconName: sheet.needsRestart ? "power" : ""
            kind: "primary"
            tip: sheet.needsRestart ? "GNOME asks before it restarts, so you can save your work first." : ""
            onClicked: {
                const restart = sheet.needsRestart
                sheet.close()
                if (restart) Backend.restartPC()
            }
        }
    ]

    function meta(st) {
        switch (st) {
        case "applied": return { icon: "okCircle", color: Theme.good, label: "Applied" }
        case "reverted": return { icon: "undo", color: Theme.textDim, label: "Restored" }
        case "info": return { icon: "info", color: Theme.accentText, label: "Note" }
        case "skipped": return { icon: "skipCircle", color: Theme.textFaint, label: "Skipped" }
        default: return { icon: "xCircle", color: Theme.bad, label: "Failed" }
        }
    }

    // Problems first, then what changed, then what was left alone.
    readonly property var order: ["failed", "applied", "info", "reverted", "skipped"]
    readonly property var ordered: order.map(st => results.filter(r => r.status === st))
                                        .reduce((a, b) => a.concat(b), [])
                                        .concat(results.filter(r => order.indexOf(r.status) < 0))
    // Parts that aren't installed here can be many (one per app): three or more fold
    // into one row at the end, which opens to list them. The list itself stays the same
    // when it opens (the skipped rows show or hide), so the folded row keeps the focus.
    readonly property var skippedRows: results.filter(r => r.status === "skipped")
    readonly property bool foldSkipped: skippedRows.length >= 3
    property bool skippedOpen: false
    readonly property var rows: !foldSkipped ? ordered
        : ordered.filter(r => r.status !== "skipped").concat([{ fold: true }]).concat(skippedRows)
    readonly property int shownRows: foldSkipped && !skippedOpen ? rows.length - skippedRows.length : rows.length

    Column {
        width: parent.width
        spacing: 12

        Row {
            spacing: 8
            visible: sheet.results.length > 0
            Repeater {
                model: ["applied", "info", "skipped", "reverted", "failed"].filter(s => sheet.count(s) > 0)
                delegate: Rectangle {
                    required property string modelData
                    readonly property var m: sheet.meta(modelData)
                    height: 26
                    width: chipRow.width + 20
                    radius: height / 2
                    color: Theme.alpha(m.color, 0.14)
                    Row {
                        id: chipRow
                        anchors.centerIn: parent
                        spacing: 6
                        Icon { name: m.icon; size: 14; color: m.color; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: sheet.count(modelData) + " " + m.label.toLowerCase(); color: m.color; font.pixelSize: 12; font.weight: Font.DemiBold; anchors.verticalCenter: parent.verticalCenter }
                    }
                }
            }
        }

        Flickable {
            objectName: "resultsList"
            width: parent.width
            height: Math.min(contentHeight, sheet.maxBodyHeight - 40)
            contentHeight: list.height
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            C.ScrollBar.vertical: LgScrollBar {}
            Column {
                id: list
                width: parent.width - 8
                Repeater {
                    model: sheet.rows
                    delegate: Item {
                        id: row
                        required property var modelData
                        required property int index
                        readonly property bool isFold: modelData.fold === true
                        readonly property bool underFold: sheet.foldSkipped && !isFold && modelData.status === "skipped"
                        readonly property var m: sheet.meta(isFold ? "skipped" : modelData.status)
                        visible: !underFold || sheet.skippedOpen
                        width: list.width
                        height: !visible ? 0 : isFold ? 40 : Math.max(40, txt.height + 18)
                        Rectangle { visible: row.index > 0; width: parent.width; height: 1; color: Theme.divider }

                        // The folded "not installed here" row.
                        C.AbstractButton {
                            id: foldButton
                            objectName: "skippedFold"
                            visible: row.isFold
                            anchors.fill: parent
                            anchors.topMargin: 1
                            hoverEnabled: true
                            focusPolicy: Qt.StrongFocus
                            Accessible.name: foldText.text
                            Accessible.role: Accessible.Button
                            onClicked: sheet.skippedOpen = !sheet.skippedOpen
                            Keys.onReturnPressed: clicked()
                            Keys.onEnterPressed: clicked()
                            HoverHandler { cursorShape: Qt.PointingHandCursor }
                            background: Rectangle {
                                radius: Theme.rXs
                                color: foldButton.hovered ? Theme.hover : "transparent"
                                FocusRing { target: foldButton; radius: Theme.rXs + 2; gap: 1 }
                            }
                            contentItem: Item {
                                Icon { x: 2; anchors.verticalCenter: parent.verticalCenter; name: "skipCircle"; size: 18; color: Theme.textFaint }
                                Text {
                                    id: foldText
                                    objectName: "skippedFoldText"
                                    x: 32
                                    width: parent.width - x - foldChevron.width - 12
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: sheet.skippedRows.length + " parts not installed here, skipped"
                                    color: Theme.textDim
                                    font.pixelSize: Theme.fsBody
                                    elide: Text.ElideRight
                                }
                                Icon {
                                    id: foldChevron
                                    anchors.right: parent.right
                                    anchors.rightMargin: 2
                                    anchors.verticalCenter: parent.verticalCenter
                                    name: "chevronRight"; size: 16; color: Theme.textDim
                                    rotation: sheet.skippedOpen ? 90 : 0
                                    Behavior on rotation { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                                }
                            }
                        }

                        // A result.
                        Icon { visible: !row.isFold; x: row.underFold ? 14 : 2; y: 11; name: row.m.icon; size: 18; color: row.m.color }
                        Column {
                            id: txt
                            visible: !row.isFold
                            x: row.underFold ? 44 : 32; y: 9
                            width: parent.width - x - status.width - 8
                            spacing: 2
                            Text { text: row.modelData.name || ""; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium; width: parent.width; elide: Text.ElideRight }
                            TextEdit {
                                visible: (row.modelData.message || "").length > 0
                                width: parent.width
                                text: row.modelData.message || ""
                                readOnly: true
                                selectByMouse: true
                                wrapMode: TextEdit.Wrap
                                color: row.modelData.status === "failed" ? Theme.bad : Theme.textDim
                                selectionColor: Theme.alpha(Theme.accent, 0.4)
                                font.pixelSize: 12
                            }
                        }
                        Text {
                            id: status
                            visible: !row.isFold
                            anchors.right: parent.right
                            y: 11
                            text: row.m.label
                            color: row.m.color
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                        }
                    }
                }
            }
        }
    }
}
