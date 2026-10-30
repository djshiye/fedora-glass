import QtQuick
import LiquidGlass.Core

// Motion: how windows open, minimize and close, and how the panel answers the pointer.
// One row per event with a preset dropdown, an optional intensity/speed area, and a preview
// at the top that plays the chosen animation with the same curves the Shell extension uses.
Card {
    id: root
    objectName: "motionCard"
    height: implicitHeight

    readonly property var events: [
        { ev: "open",     label: "Open",                 caption: "Windows appearing, from the taskbar or anywhere" },
        { ev: "minimize", label: "Minimize and restore", caption: "Into and out of the taskbar icon" },
        { ev: "close",    label: "Close",                caption: "" },
        { ev: "launch",   label: "App starting",         caption: "The taskbar icon bounces until the window shows" },
        { ev: "hover",    label: "Panel hover",          caption: "Taskbar icons, tray and clock" }
    ]
    readonly property var presetLabels: ({
        gnome: "GNOME default", spring: "Spring", bounce: "Bounce", jelly: "Jelly",
        genie: "Genie", scalefade: "Scale and fade", off: "Off" })
    readonly property var presetTips: ({
        gnome: "GNOME's own animation for this",
        spring: "Springs into place with one soft overshoot",
        bounce: "Lands and hops two or three times, smaller each time",
        jelly: "Squashes and stretches like jelly as it settles",
        genie: "Pours into the taskbar icon and back out, like a genie",
        scalefade: "A quick, calm zoom and fade",
        off: "No animation: it happens at once" })

    property string expandedEv: ""

    function setting(ev) {
        const m = Backend.motion[ev]
        return m ? m : { preset: "off", intensity: 0.5, speed: 1 }
    }
    function modelFor(ev) {
        const ids = Backend.motionPresets[ev] || []
        return ids.map(id => ({ value: id, label: presetLabels[id] || id, tip: presetTips[id] || "" }))
    }

    // ---- curves (progress 0 -> 1, may overshoot) ------------------------------------
    function clamp01(x) { return Math.max(0, Math.min(1, x)) }
    function spring(u, I) {
        if (u >= 1) return 1
        if (u <= 0) return 0
        const o = 0.15 * Math.pow(I, 1.32)
        if (o < 0.002) return 1 - Math.exp(-9 * u) * (1 + 9 * u)
        const w = Math.PI / 0.38, l = -Math.log(o) * w / Math.PI
        return 1 - Math.exp(-l * u) * (Math.cos(w * u) + (l / w) * Math.sin(w * u))
    }
    function bounce(u, I) {
        if (u >= 1) return 1
        if (u <= 0) return 0
        const e = 0.25 + 0.35 * I, t0 = 1
        let total = t0
        for (let k = 1; k <= 5; k++) total += 2 * t0 * Math.pow(e, k)
        let t = u * total
        if (t < t0) { const f = t / t0; return f * f }
        t -= t0
        for (let k = 1; k <= 5; k++) {
            const d = 2 * t0 * Math.pow(e, k)
            if (t < d) { const x = t / d * 2 - 1; return 1 - Math.pow(e, 2 * k) * (1 - x * x) }
            t -= d
        }
        return 1
    }
    function bezier(u) {            // cubic-bezier(0.2, 0.8, 0.2, 1)
        if (u <= 0) return 0
        if (u >= 1) return 1
        let lo = 0, hi = 1, s = u
        for (let i = 0; i < 22; i++) {
            s = (lo + hi) / 2
            const x = 3 * (1 - s) * (1 - s) * s * 0.2 + 3 * (1 - s) * s * s * 0.2 + s * s * s
            if (x < u) lo = s; else hi = s
        }
        return 3 * (1 - s) * (1 - s) * s * 0.8 + 3 * (1 - s) * s * s + s * s * s
    }
    function easeOut(u) { return 1 - Math.pow(1 - clamp01(u), 3) }
    function smoother(u) { u = clamp01(u); return u * u * u * (u * (u * 6 - 15) + 10) }
    // The main progress curve of a preset.
    function curve(preset, u, I) {
        switch (preset) {
        case "spring": return spring(u, I)
        case "bounce": return bounce(u, I)
        case "jelly": return spring(u, I * 0.45)
        case "genie": return smoother(u)
        case "scalefade": return bezier(u)
        case "off": return u >= 1 ? 1 : 0
        default: return easeOut(u)
        }
    }
    function baseDur(ev, preset) {
        if (ev === "hover") return 220
        if (ev === "close") return ({ scalefade: 200, spring: 260, genie: 400 })[preset] || 200
        return ({ spring: 380, bounce: 550, jelly: 500, genie: 450, scalefade: 220 })[preset] || 250
    }
    function startScale(preset, I) {
        if (preset === "scalefade") return 1 - 0.04 - 0.08 * I
        if (preset === "bounce") return 1 - 0.12 - 0.12 * I
        if (preset === "gnome") return 0.825
        return 1 - 0.10 - 0.15 * I
    }

    // ---- the preview timeline -------------------------------------------------------
    property string pvEvent: "open"
    property string pvPreset: "spring"
    property real pvI: 0.5
    property real pvSpeed: 1
    property real pvT: 1                 // 0..1 over the whole sequence; 1 = everything at rest

    readonly property real pvDur: baseDur(pvEvent, pvPreset) / Math.max(0.25, pvSpeed)
    readonly property real pvPeriod: 600 / Math.max(0.25, pvSpeed)
    readonly property real pvTotal: {
        const d = pvDur
        switch (pvEvent) {
        case "open": return 150 + d + 400
        case "minimize": return 200 + d + 400 + d + 400
        case "close": return 200 + d + 500 + 150 + 350
        case "launch": return 200 + (pvPreset === "off" ? 300 : 3 * pvPeriod) + 250 + 400
        default: return 150 + d + 400 + d + 250
        }
    }
    readonly property var fr: frame(pvT * pvTotal)

    function play(ev, preset, intensity, speed) {
        pvEvent = ev
        pvPreset = preset
        pvI = intensity
        pvSpeed = speed
        anim.stop()
        pvT = 0
        anim.duration = pvTotal
        anim.start()
    }
    function playEvent(ev) {
        const m = setting(ev)
        play(ev, m.preset, m.intensity, m.speed)
    }

    // Progress of a stage that starts at `start` and runs `dur` ms.
    function prog(ms, start, dur) {
        if (pvPreset === "off" || dur <= 0) return ms >= start ? 1 : 0
        return curve(pvPreset, clamp01((ms - start) / dur), pvI)
    }
    function frame(ms) {
        const I = pvI, d = pvDur, p = pvPreset
        const f = { sx: 1, sy: 1, m: 0, op: 1, iconS: 1, iconLift: 0, iconSy: 1 }
        if (pvEvent === "open") {
            const q = prog(ms, 150, d), ss = startScale(p, I)
            const u = p === "off" ? (ms >= 150 ? 1 : 0) : clamp01((ms - 150) / (d * 0.45))
            const w = p === "jelly" ? 0.12 * I * Math.sin(2 * Math.PI * 1.8 * clamp01((ms - 150) / d)) * Math.exp(-3 * clamp01((ms - 150) / d)) * (1 - clamp01((ms - 150) / d)) : 0
            const s = ss + (1 - ss) * q
            f.sx = s * (1 + w); f.sy = s * (1 - w)
            f.op = u
        } else if (pvEvent === "minimize") {
            const back = 200 + d + 400
            const m = ms < back ? prog(ms, 200, d) : 1 - prog(ms, back, d)
            const mc = clamp01(m)
            f.m = Math.max(-0.05, Math.min(1.08, m))
            if (p === "genie") {
                f.sx = Math.max(0.06, 1 - 0.94 * clamp01(m * 1.9))
                f.sy = 1 - 0.8 * mc * mc
                f.op = 1 - clamp01((mc - 0.88) / 0.12)
            } else {
                f.sx = f.sy = Math.max(0.05, 1 - 0.85 * m)
                f.op = 1 - clamp01((mc - 0.5) / 0.45)
            }
            if (p === "off") f.op = ms < 200 || ms >= back ? 1 : 0
        } else if (pvEvent === "close") {
            const re = 200 + d + 500
            if (ms < re) {
                const q = prog(ms, 200, d), ss = startScale(p, I)
                const s = Math.max(0.05, 1 - (1 - ss) * q)
                f.sx = f.sy = s
                f.op = p === "off" ? (ms >= 200 ? 0 : 1) : 1 - clamp01((ms - 200) / (d * 0.7))
            } else {
                f.op = clamp01((ms - re) / 150)
            }
        } else if (pvEvent === "launch") {
            const hops = p === "off" ? 0 : 3
            const openAt = 200 + (hops ? hops * pvPeriod : 300)
            const x = (ms - 200) / pvPeriod
            if (hops && x >= 0 && x < hops) {
                const k = Math.floor(x), v = x - k
                const arc = p === "bounce" ? 4 * v * (1 - v) : Math.sin(Math.PI * v)
                f.iconLift = 12 * I * arc * (1 - 0.18 * k)
                if (p === "jelly") f.iconSy = 1 + 0.12 * I * arc - 0.28 * I * Math.pow(1 - arc, 7)
            }
            const w = easeOut((ms - openAt) / 250)
            f.sx = f.sy = 0.85 + 0.15 * w
            f.op = clamp01((ms - openAt) / 125)
        } else {
            const back = 150 + d + 400
            const m = ms < back ? prog(ms, 150, d) : 1 - prog(ms, back, d)
            f.iconS = 1 + 0.16 * I * m
            f.iconLift = 4 * I * m
        }
        return f
    }

    NumberAnimation { id: anim; target: root; property: "pvT"; from: 0; to: 1; easing.type: Easing.Linear }

    // Play the preview shortly after a slider stops moving.
    property string _pendingEv: ""
    Timer {
        id: settle
        interval: 350
        onTriggered: if (root._pendingEv !== "") root.playEvent(root._pendingEv)
    }

    // ---- notes ----------------------------------------------------------------------
    component Note: Rectangle {
        property string iconName: "info"
        property color iconColor: Theme.accentText
        property string message: ""
        default property alias extra: extraCol.data
        width: parent ? parent.width : 300
        height: noteCol.implicitHeight + 24
        radius: 12
        color: Theme.well
        Column {
            id: noteCol
            x: 14; y: 12
            width: parent.width - 28
            spacing: 10
            Row {
                width: parent.width
                spacing: 10
                Icon { name: parent.parent.parent.iconName; color: parent.parent.parent.iconColor; size: 18 }
                Text {
                    width: parent.width - 28
                    wrapMode: Text.WordWrap
                    color: Theme.textDim
                    font.pixelSize: Theme.fsSmall
                    lineHeight: 1.15
                    text: parent.parent.parent.message
                }
            }
            Column {
                id: extraCol
                x: 28
                visible: implicitHeight > 0
            }
        }
    }

    Column {
        width: parent.width
        spacing: 16

        SectionTitle { text: "Motion" }
        Text {
            width: parent.width
            wrapMode: Text.WordWrap
            color: Theme.textFaint
            font.pixelSize: Theme.fsSmall
            text: "How windows open, minimize and close, and how the panel answers your pointer."
        }

        Note {
            objectName: "motionReduceNote"
            visible: !Backend.systemAnimations
            message: "Reduce animation is on in GNOME Settings, so none of these play. Turn it off in Settings › Accessibility to see them."
        }

        // ---- preview ----
        Rectangle {
            id: pv
            objectName: "motionPreview"
            width: parent.width
            height: 120
            radius: 14
            color: Theme.well
            clip: true

            readonly property real winW: 112
            readonly property real winH: 62
            readonly property real winCx: width / 2
            readonly property real winCy: 14 + winH / 2
            readonly property real panelW: 132
            readonly property real panelH: 24
            readonly property real panelX: (width - panelW) / 2
            readonly property real panelY: height - panelH - 8
            readonly property real iconCx: panelX + 14
            readonly property real iconCy: panelY + panelH / 2

            Text {
                x: 12; y: 10
                text: root.pvEvent === "minimize" ? "Minimize and restore" : root.pvEvent === "launch" ? "App starting" : root.pvEvent === "hover" ? "Panel hover" : root.pvEvent === "close" ? "Close" : "Open"
                color: Theme.textFaint
                font.pixelSize: 11
                font.weight: Font.Medium
            }

            // the little window
            Item {
                id: win
                width: pv.winW
                height: pv.winH
                x: pv.winCx - width / 2 + (pv.iconCx - pv.winCx) * root.fr.m
                y: pv.winCy - height / 2 + (pv.iconCy - pv.winCy) * root.fr.m
                opacity: root.fr.op
                transform: Scale { origin.x: win.width / 2; origin.y: win.height / 2; xScale: root.fr.sx; yScale: root.fr.sy }
                Rectangle {
                    anchors.fill: parent
                    radius: 9
                    color: Theme.dark ? Qt.rgba(0.2, 0.21, 0.26, 1) : "white"
                    border.width: 1
                    border.color: Theme.borderHi
                    Rectangle {
                        width: parent.width; height: 16
                        radius: 9
                        color: Theme.dark ? Qt.rgba(1, 1, 1, 0.10) : Qt.rgba(0, 0, 0, 0.07)
                        Rectangle { width: parent.width; height: 9; anchors.bottom: parent.bottom; color: parent.color }
                        Row {
                            x: 8; anchors.verticalCenter: parent.verticalCenter
                            spacing: 4
                            Repeater { model: 3; Rectangle { width: 5; height: 5; radius: 2.5; color: Theme.textFaint } }
                        }
                    }
                    Column {
                        x: 10; y: 26
                        spacing: 6
                        Rectangle { width: 64; height: 5; radius: 2.5; color: Theme.alpha(Theme.accent, 0.7) }
                        Rectangle { width: 86; height: 5; radius: 2.5; color: Theme.wellHi }
                        Rectangle { width: 48; height: 5; radius: 2.5; color: Theme.wellHi }
                    }
                }
            }

            // the little panel
            Rectangle {
                x: pv.panelX; y: pv.panelY
                width: pv.panelW; height: pv.panelH
                radius: height / 2
                color: Theme.dark ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(0, 0, 0, 0.10)
                border.width: 1
                border.color: Theme.border
                Repeater {
                    model: 4
                    delegate: Rectangle {
                        id: dot
                        required property int index
                        readonly property bool first: index === 0
                        width: 14; height: 14
                        radius: 4.5
                        x: 7 + index * 26
                        y: (parent.height - height) / 2 - (first ? root.fr.iconLift : 0)
                        color: first ? Theme.accent : Theme.dark ? Qt.rgba(1, 1, 1, 0.38) : Qt.rgba(0, 0, 0, 0.30)
                        transform: Scale {
                            origin.x: dot.width / 2; origin.y: dot.height
                            xScale: dot.first ? root.fr.iconS : 1
                            yScale: dot.first ? root.fr.iconS * root.fr.iconSy : 1
                        }
                    }
                }
            }
        }

        // ---- one row per event ----
        Column {
            id: rows
            width: parent.width
            Repeater {
                model: root.events
                delegate: Column {
                    id: row
                    required property var modelData
                    required property int index
                    readonly property string ev: modelData.ev
                    readonly property var cfg: root.setting(ev)
                    readonly property bool open: root.expandedEv === ev
                    readonly property bool adjustable: cfg.preset !== "off" && cfg.preset !== "gnome"
                    width: rows.width

                    Item {
                        id: head
                        // Side by side when the card is wide; the controls drop under the label when it is narrow.
                        readonly property bool wide: width >= 480
                        width: parent.width
                        height: wide ? Math.max(60, labelCol.implicitHeight + 20)
                                     : labelCol.implicitHeight + 10 + ctl.height + 16

                        Column {
                            id: labelCol
                            x: 0
                            y: head.wide ? (head.height - height) / 2 : 14
                            width: head.wide ? parent.width - ctl.width - 12 : parent.width
                            spacing: 2
                            Text { width: parent.width; text: row.modelData.label; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium; elide: Text.ElideRight }
                            Text {
                                visible: row.modelData.caption.length > 0
                                width: parent.width
                                text: row.modelData.caption
                                color: Theme.textFaint
                                font.pixelSize: Theme.fsSmall
                                wrapMode: Text.WordWrap
                            }
                        }
                        Row {
                            id: ctl
                            x: head.wide ? parent.width - width : 0
                            y: head.wide ? (head.height - height) / 2 : labelCol.y + labelCol.height + 10
                            spacing: 6
                            LgDropdown {
                                objectName: "motionDropdown-" + row.ev
                                width: head.wide ? 170 : head.width - 76
                                anchors.verticalCenter: parent.verticalCenter
                                model: root.modelFor(row.ev)
                                value: row.cfg.preset
                                tip: root.presetTips[row.cfg.preset] || ""
                                Accessible.name: row.modelData.label + " animation"
                                onActivated: (v) => {
                                    Backend.setMotion(row.ev, "preset", v)
                                    root.play(row.ev, v, row.cfg.intensity, row.cfg.speed)
                                }
                            }
                            LgButton {
                                objectName: "motionPlay-" + row.ev
                                kind: "flat"
                                iconName: "run"
                                implicitHeight: 32
                                leftPadding: 0; rightPadding: 0
                                anchors.verticalCenter: parent.verticalCenter
                                tip: "Play a preview"
                                Accessible.name: "Play a preview of " + row.modelData.label
                                onClicked: root.playEvent(row.ev)
                            }
                            LgButton {
                                objectName: "motionExpand-" + row.ev
                                kind: "flat"
                                iconName: row.open ? "chevronDown" : "chevronRight"
                                implicitHeight: 32
                                leftPadding: 0; rightPadding: 0
                                anchors.verticalCenter: parent.verticalCenter
                                tip: "Intensity and speed"
                                Accessible.name: "Intensity and speed for " + row.modelData.label
                                onClicked: root.expandedEv = row.open ? "" : row.ev
                            }
                        }
                    }

                    // Intensity and speed, opening smoothly under the row.
                    Item {
                        width: parent.width
                        height: row.open ? panelBox.height + 18 : 0
                        clip: true
                        visible: height > 0
                        Behavior on height { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
                        Rectangle {
                            id: panelBox
                            y: 4
                            width: parent.width
                            height: inner.implicitHeight + 28
                            radius: 12
                            color: Theme.well
                            opacity: row.open ? 1 : 0
                            Behavior on opacity { NumberAnimation { duration: Theme.normal } }
                            Column {
                                id: inner
                                x: 16; y: 14
                                width: parent.width - 32
                                spacing: 12
                                Text {
                                    visible: !row.adjustable
                                    width: parent.width
                                    wrapMode: Text.WordWrap
                                    color: Theme.textFaint
                                    font.pixelSize: Theme.fsSmall
                                    text: row.cfg.preset === "off" ? "Nothing plays, so there is nothing to adjust."
                                                                   : "GNOME's own animation keeps its own timing."
                                }
                                LabeledSlider {
                                    objectName: "motionIntensity-" + row.ev
                                    width: parent.width
                                    label: "Intensity"
                                    enabled: row.adjustable
                                    from: 0; to: 1; stepSize: 0.01
                                    value: row.cfg.intensity
                                    onMoved: (v) => { Backend.setMotion(row.ev, "intensity", v); root._pendingEv = row.ev; settle.restart() }
                                    tip: "How lively it is: how far it overshoots or bounces before settling. Left settles calmly; right is bouncier."
                                }
                                LabeledSlider {
                                    objectName: "motionSpeed-" + row.ev
                                    width: parent.width
                                    label: "Speed"
                                    enabled: row.adjustable
                                    from: 0.5; to: 2; stepSize: 0.05
                                    value: row.cfg.speed
                                    format: (v) => v.toFixed(1) + "×"
                                    onMoved: (v) => { Backend.setMotion(row.ev, "speed", v); root._pendingEv = row.ev; settle.restart() }
                                    tip: "How fast it plays. Left is slower; right is faster."
                                }
                            }
                        }
                    }

                    Rectangle {
                        visible: row.index < root.events.length - 1
                        width: parent.width
                        height: 1
                        color: Theme.divider
                    }
                }
            }
        }

        // ---- Dash to Panel ----
        Note {
            objectName: "motionDtpNote"
            readonly property bool off: Backend.motionDtpHoverOff
            visible: off || (Backend.dtpHoverAnimates && root.setting("hover").preset !== "off")
            iconName: off ? "check" : "info"
            iconColor: off ? Theme.good : Theme.accentText
            message: off ? "Dash to Panel's own hover animation turns off when you Apply."
                         : "Dash to Panel animates its own icons on hover, so taskbar icons use its animation. The tray and clock use this one."
            LgButton {
                objectName: "motionDtpButton"
                kind: parent.parent.parent.off ? "flat" : "secondary"
                implicitHeight: 32
                leftPadding: 14; rightPadding: 14
                text: parent.parent.parent.off ? "Keep Dash to Panel's" : "Use Liquid Glass hover"
                tip: parent.parent.parent.off ? "Leaves Dash to Panel's own hover animation on."
                                              : "Turns Dash to Panel's own hover animation off when you Apply. Restore original turns it back on."
                tipBelow: true
                onClicked: Backend.motionDtpHoverOff = !parent.parent.parent.off
            }
        }

        LgButton {
            objectName: "motionReset"
            x: -14
            kind: "flat"
            implicitHeight: 32
            leftPadding: 14; rightPadding: 14
            text: "Reset motion"
            iconName: "refresh"
            enabled: !Backend.motionIsDefault
            tip: "Go back to the default animations"
            onClicked: Backend.resetMotion()
        }
    }
}
