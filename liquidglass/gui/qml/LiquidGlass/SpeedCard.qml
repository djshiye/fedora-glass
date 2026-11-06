import QtQuick
import LiquidGlass.Core

// Speed: how the glass quality is chosen, what the desktop is drawing right now, and a
// short check that measures how smoothly each level runs on this PC.
Card {
    id: root
    objectName: "speedCard"
    height: implicitHeight

    readonly property var levelNames: ({ full: "full", lighter: "lighter", lightest: "lightest" })
    readonly property var rows: [
        { level: "full", label: "Full glass" },
        { level: "lighter", label: "Lighter" },
        { level: "lightest", label: "Lightest" }
    ]
    readonly property string checkState: Backend.speedState
    readonly property var result: Backend.speedResult
    readonly property string pick: result.pick || ""
    readonly property bool running: checkState === "running"

    function verdictColor(v) { return v === "smooth" ? Theme.good : v === "ok" ? Theme.warn : Theme.bad }
    function verdictWord(v) { return v === "smooth" ? "Smooth" : v === "ok" ? "A little uneven" : "Slow" }
    function phaseFor(level) {
        const list = result.phases || []
        for (let i = 0; i < list.length; i++)
            if (list[i].level === level) return list[i]
        return null
    }
    function fpsText(p) {
        const n = Math.round(Number(p.fps) || 0)
        return n + (n === 1 ? " frame a second" : " frames a second")
    }
    readonly property string statusText: {
        const lv = levelNames[Backend.speedLevel] || ""
        if (lv === "") return ""
        if (Backend.speedReason === "slow")
            return "Right now: " + lv + " glass, because frames were dropping. It tries full glass again in a few minutes."
        if (Backend.speedReason === "retry")
            return "Right now: trying full glass again."
        return "Right now: " + lv + " glass."
    }
    readonly property string summaryText: {
        if (pick === "") return ""
        const p = phaseFor(pick)
        if (p && p.verdict === "slow")
            return (pick === "full" ? "Full" : pick === "lighter" ? "Lighter" : "Lightest")
                   + " glass was the fastest here, but every level dropped frames."
        if (pick === "full" && p && p.verdict === "smooth") return "Full glass runs smoothly on this PC."
        if (pick === "full") return "Full glass is the best fit for this PC."
        return (pick === "lighter" ? "Lighter" : "Lightest") + " glass is the best fit for this PC."
    }
    readonly property string failText: {
        if (checkState === "noanswer")
            return "The desktop didn't answer. Make sure Fedora Glass is turned on, then try again."
        if (checkState === "failed")
            return result.error === "noglass"
                ? "There's no glass on screen to measure. Turn on glass for the panel, menus or windows first."
                : "The check couldn't run. Try again in a moment."
        return ""
    }

    Column {
        width: parent.width
        spacing: 16
        SectionTitle {
            text: "Speed"
            caption: "Fedora Glass can measure how smoothly the glass draws on this PC, and draw lighter glass when your graphics card can't keep up."
        }
        Column {
            width: parent.width
            spacing: 8
            Text { text: "Glass quality"; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
            Segmented {
                objectName: "speedQuality"
                width: parent.width
                model: [{ value: "auto", label: "Auto", tip: "Full glass, made lighter by itself when frames start dropping. It tries full glass again a few minutes later." },
                        { value: "full", label: "Full", tip: "Every effect, all the time." },
                        { value: "lighter", label: "Lighter", tip: "Fewer colour samples at the edges and fewer redraws for windows behind. Hard to tell apart from full." },
                        { value: "lightest", label: "Lightest", tip: "Lighter, and the glass shows only your wallpaper, not the windows behind it. Easiest on the graphics card." }]
                value: Backend.glassQuality
                onActivated: (v) => Backend.glassQuality = v
                Accessible.name: "Glass quality"
            }
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
        Row {
            width: parent.width
            spacing: 12
            LgButton {
                objectName: "speedCheck"
                id: checkBtn
                kind: "secondary"
                text: "Check speed"
                enabled: Backend.glassLive && !root.running
                tip: Backend.glassLive ? "" : "Apply, then restart your PC once to start the glass."
                onClicked: Backend.checkSpeed()
                Accessible.name: "Check speed"
            }
            Spinner {
                visible: root.running
                size: 18
                color: Theme.textDim
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                visible: root.running
                width: parent.width - checkBtn.width - 18 - 24
                anchors.verticalCenter: parent.verticalCenter
                wrapMode: Text.WordWrap
                color: Theme.textDim
                font.pixelSize: Theme.fsSmall
                text: "Checking… this takes about 20 seconds. The glass may look a little plainer for a moment."
            }
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
                        text: line.phase ? root.fpsText(line.phase) + ", " + root.verdictWord(line.phase.verdict).toLowerCase() : ""
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
                text: "Use " + (root.pick === "full" ? "full glass" : root.pick)
                onClicked: Backend.useQuality(root.pick)
            }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                color: Theme.textFaint
                font.pixelSize: Theme.fsSmall
                text: "The check redraws all the glass every frame, harder than everyday use."
            }
        }
    }
}
