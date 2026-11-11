import QtQuick
import FedoraGlass.Core

// Speed: how the glass quality is chosen, what the desktop is drawing right now, and a
// short check that measures how smoothly each level runs on this PC.
Card {
    id: root
    objectName: "speedCard"
    height: implicitHeight

    readonly property var levelNames: ({ full: qsTr("full"), lighter: qsTr("lighter"), lightest: qsTr("lightest") })
    readonly property var rows: [
        { level: "full", label: qsTr("Full glass") },
        { level: "lighter", label: qsTr("Lighter") },
        { level: "lightest", label: qsTr("Lightest") }
    ]
    readonly property string checkState: Backend.speedState
    readonly property var result: Backend.speedResult
    readonly property string pick: result.pick || ""
    readonly property bool running: checkState === "running"

    function verdictColor(v) { return v === "smooth" ? Theme.good : v === "ok" ? Theme.warn : Theme.bad }
    function verdictWord(v) { return v === "smooth" ? qsTr("Smooth") : v === "ok" ? qsTr("A little uneven") : qsTr("Slow") }
    function phaseFor(level) {
        const list = result.phases || []
        for (let i = 0; i < list.length; i++)
            if (list[i].level === level) return list[i]
        return null
    }
    function fpsText(p) {
        const n = Math.round(Number(p.fps) || 0)
        return n === 1 ? qsTr("1 frame a second") : qsTr("%1 frames a second").arg(n)
    }
    readonly property string statusText: {
        const lv = levelNames[Backend.speedLevel] || ""
        if (lv === "") return ""
        if (Backend.speedReason === "slow")
            return qsTr("Right now: %1 glass, because frames were dropping. It tries full glass again in a few minutes.").arg(lv)
        if (Backend.speedReason === "battery")
            return Backend.speedPower === "saver"
                   ? qsTr("Right now: %1 glass, because Power Saver is on.").arg(lv)
                   : qsTr("Right now: %1 glass, because you're on battery.").arg(lv)
        if (Backend.speedReason === "retry")
            return qsTr("Right now: trying full glass again.")
        return qsTr("Right now: %1 glass.").arg(lv)
    }
    readonly property string summaryText: {
        if (pick === "") return ""
        const p = phaseFor(pick)
        if (p && p.verdict === "slow")
            return pick === "full" ? qsTr("Full glass was the fastest here, but every level dropped frames.")
                 : pick === "lighter" ? qsTr("Lighter glass was the fastest here, but every level dropped frames.")
                 : qsTr("Lightest glass was the fastest here, but every level dropped frames.")
        if (pick === "full" && p && p.verdict === "smooth") return qsTr("Full glass runs smoothly on this PC.")
        if (pick === "full") return qsTr("Full glass is the best fit for this PC.")
        return pick === "lighter" ? qsTr("Lighter glass is the best fit for this PC.") : qsTr("Lightest glass is the best fit for this PC.")
    }
    readonly property string failText: {
        if (checkState === "noanswer")
            return qsTr("The desktop didn't answer. Make sure Fedora Glass is turned on, then try again.")
        if (checkState === "failed")
            return result.error === "noglass"
                ? qsTr("There's no glass on screen to measure. Turn on glass for the panel, menus or windows first.")
                : qsTr("The check couldn't run. Try again in a moment.")
        return ""
    }

    Column {
        width: parent.width
        spacing: 12
        // One row: what decides the quality, the choice, and the check.
        Item {
            width: parent.width
            height: Math.max(headCol.implicitHeight, 40)
            readonly property bool narrow: width < 460
            Column {
                id: headCol
                anchors.left: parent.left
                anchors.right: controls.left
                anchors.rightMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2
                Row {
                    spacing: 10
                    Text { text: qsTr("Speed"); color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium; anchors.verticalCenter: parent.verticalCenter }
                    ResetButton {
                        objectName: "cardReset"
                        readonly property var keys: ["glass_quality", "lighter_on_battery"]
                        visible: Backend.changedFromDefault.some((k) => keys.indexOf(k) >= 0)
                        anchors.verticalCenter: parent.verticalCenter
                        text: qsTr("Reset")
                        tip: qsTr("Back to Auto, and lighter glass on battery (Apply to use them)")
                        onClicked: Backend.resetSettings(keys)
                    }
                }
                Text {
                    visible: !parent.parent.narrow
                    width: parent.width
                    wrapMode: Text.WordWrap
                    color: Theme.textFaint
                    font.pixelSize: Theme.fsSmall
                    text: qsTr("Auto picks the best glass your PC can run smoothly")
                }
            }
            Row {
                id: controls
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6
                LgDropdown {
                    objectName: "speedQuality"
                    width: 132
                    glyphs: false
                    model: [{ value: "auto", label: qsTr("Auto"), tip: qsTr("Full glass, made lighter by itself when frames start dropping. It tries full glass again a few minutes later.") },
                            { value: "full", label: qsTr("Full"), tip: qsTr("Every effect, all the time.") },
                            { value: "lighter", label: qsTr("Lighter"), tip: qsTr("Fewer colour samples at the edges and fewer redraws for windows behind. Hard to tell apart from full.") },
                            { value: "lightest", label: qsTr("Lightest"), tip: qsTr("Lighter, and the glass shows only your wallpaper, not the windows behind it. Easiest on the graphics card.") }]
                    value: Backend.glassQuality
                    tip: qsTr("Glass quality")
                    onActivated: (v) => Backend.glassQuality = v
                    Accessible.name: qsTr("Glass quality")
                }
                LgButton {
                    objectName: "speedCheck"
                    id: checkBtn
                    kind: "flat"
                    text: qsTr("Check speed")
                    leftPadding: 10; rightPadding: 10
                    enabled: Backend.glassLive && !root.running
                    busy: root.running
                    tip: Backend.glassLive ? qsTr("Measure how smoothly each level draws here (about 20 seconds)")
                                           : Backend.glassProblemNote !== "" ? Backend.glassProblemNote
                                           : qsTr("Apply, then restart your PC once to start the glass.")
                    onClicked: Backend.checkSpeed()
                    Accessible.name: qsTr("Check speed")
                }
            }
        }
        SwitchRow {
            objectName: "lighterOnBattery"
            label: qsTr("Lighter glass on battery")
            caption: qsTr("On battery or in Power Saver, use lighter glass. It goes back when you plug in.")
            checked: Backend.lighterOnBattery
            tip: qsTr("Saves battery. Lighter glass is hard to tell apart from full glass. It is never heavier than the quality you picked.")
            onToggled: (on) => Backend.lighterOnBattery = on
        }
        Text {
            objectName: "speedStatus"
            visible: Backend.glassLive && root.statusText !== ""
            width: parent.width
            wrapMode: Text.WordWrap
            color: Theme.textDim
            font.pixelSize: Theme.fsSmall
            text: root.statusText
        }
        Text {
            objectName: "speedDrag"
            visible: Backend.glassLive && Backend.speedDrag !== ""
            width: parent.width
            wrapMode: Text.WordWrap
            color: Theme.textDim
            font.pixelSize: Theme.fsSmall
            text: Backend.speedDrag
        }
        Text {
            visible: root.running
            width: parent.width
            wrapMode: Text.WordWrap
            color: Theme.textDim
            font.pixelSize: Theme.fsSmall
            text: qsTr("Checking… this takes about 20 seconds. The glass may look a little plainer for a moment.")
        }
        Text {
            objectName: "speedFail"
            visible: root.failText !== ""
            width: parent.width
            wrapMode: Text.WordWrap
            color: Theme.textDim
            font.pixelSize: Theme.fsSmall
            text: root.failText
        }
        Column {
            objectName: "speedResult"
            visible: root.checkState === "done"
            width: parent.width
            spacing: 10
            Repeater {
                model: root.rows
                delegate: Row {
                    id: line
                    required property var modelData
                    readonly property var phase: root.phaseFor(modelData.level)
                    visible: phase !== null
                    width: parent.width
                    spacing: 10
                    Rectangle {
                        width: 10; height: 10; radius: 5
                        anchors.verticalCenter: parent.verticalCenter
                        color: line.phase ? root.verdictColor(line.phase.verdict) : "transparent"
                    }
                    Text {
                        width: 84
                        text: line.modelData.label
                        color: Theme.text
                        font.pixelSize: Theme.fsBody
                        font.weight: Font.Medium
                    }
                    Text {
                        width: parent.width - 84 - 10 - 10 - 20
                        elide: Text.ElideRight
                        color: Theme.textDim
                        font.pixelSize: Theme.fsSmall
                        text: line.phase ? qsTr("%1, %2").arg(root.fpsText(line.phase)).arg(root.verdictWord(line.phase.verdict).toLocaleLowerCase()) : ""
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                color: Theme.text
                font.pixelSize: Theme.fsBody
                text: root.summaryText
            }
            LgButton {
                objectName: "speedUse"
                visible: root.pick !== "" && root.pick !== Backend.glassQuality && Backend.glassQuality !== "auto"
                kind: "secondary"
                text: root.pick === "full" ? qsTr("Use full glass") : root.pick === "lighter" ? qsTr("Use lighter glass") : qsTr("Use lightest glass")
                onClicked: Backend.useQuality(root.pick)
            }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                color: Theme.textFaint
                font.pixelSize: Theme.fsSmall
                text: qsTr("The check redraws all the glass every frame, harder than everyday use.")
            }
        }
    }
}
