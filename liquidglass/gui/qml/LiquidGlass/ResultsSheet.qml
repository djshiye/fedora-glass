import QtQuick
import QtQuick.Controls.Basic as C

// What happened on Apply: applied, info, skipped, reverted and failed, with messages.
Sheet {
    id: sheet
    property var results: []
    function count(st) { return results.filter(r => r.status === st).length }
    readonly property int failedCount: count("failed")
    readonly property int appliedCount: count("applied")

    title: failedCount > 0 ? "Applied, with " + failedCount + " problem" + (failedCount === 1 ? "" : "s")
         : results.length === 0 ? "Settings saved" : "Liquid Glass is on"
    subtitle: results.length === 0 ? "No targets are available yet, so only the token files were written."
            : failedCount > 0 ? "Everything else was applied. The details are below."
            : "Some apps pick the new look up when they restart."
    iconName: failedCount > 0 ? "alert" : "okCircle"
    iconColor: failedCount > 0 ? Theme.warn : Theme.good
    buttons: [ LgButton { text: "Done"; kind: "primary"; onClicked: sheet.close() } ]

    function meta(st) {
        switch (st) {
        case "applied": return { icon: "okCircle", color: Theme.good, label: "Applied" }
        case "reverted": return { icon: "undo", color: Theme.textDim, label: "Restored" }
        case "info": return { icon: "info", color: Theme.accentText, label: "Note" }
        case "skipped": return { icon: "skipCircle", color: Theme.textFaint, label: "Skipped" }
        default: return { icon: "xCircle", color: Theme.bad, label: "Failed" }
        }
    }

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
                    radius: 13
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
                    // problems first, then what changed, then what was left alone
                    model: ["failed", "applied", "info", "reverted", "skipped"]
                           .map(st => sheet.results.filter(r => r.status === st))
                           .reduce((a, b) => a.concat(b), [])
                           .concat(sheet.results.filter(r => ["failed", "applied", "info", "reverted", "skipped"].indexOf(r.status) < 0))
                    delegate: Item {
                        required property var modelData
                        required property int index
                        readonly property var m: sheet.meta(modelData.status)
                        width: list.width
                        height: Math.max(40, txt.height + 18)
                        Rectangle { visible: index > 0; width: parent.width; height: 1; color: Theme.divider }
                        Icon { x: 2; y: 11; name: m.icon; size: 18; color: m.color }
                        Column {
                            id: txt
                            x: 32; y: 9
                            width: parent.width - 32 - status.width - 8
                            spacing: 2
                            Text { text: modelData.name; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium; width: parent.width; elide: Text.ElideRight }
                            TextEdit {
                                visible: (modelData.message || "").length > 0
                                width: parent.width
                                text: modelData.message || ""
                                readOnly: true
                                selectByMouse: true
                                wrapMode: TextEdit.Wrap
                                color: modelData.status === "failed" ? Theme.bad : Theme.textDim
                                selectionColor: Theme.alpha(Theme.accent, 0.4)
                                font.pixelSize: 12
                            }
                        }
                        Text {
                            id: status
                            anchors.right: parent.right
                            y: 11
                            text: m.label
                            color: m.color
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                        }
                    }
                }
            }
        }
    }
}
