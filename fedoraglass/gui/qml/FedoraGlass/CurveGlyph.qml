import QtQuick

// A tiny picture of a motion preset's curve: progress over time, drawn as a line.
Canvas {
    id: root
    property string preset: "spring"
    property color color: Theme.text
    implicitWidth: 28
    implicitHeight: 16
    width: implicitWidth
    height: implicitHeight
    opacity: preset === "gnome" ? 0.7 : 1
    antialiasing: true

    onPresetChanged: requestPaint()
    onColorChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    // Progress 0 (start) .. 1 (arrived) at time u in 0..1, for the glyph only.
    function curve(id, u) {
        switch (id) {
        case "spring": {
            const w = Math.PI / 0.38, o = 0.2, l = -Math.log(o) * w / Math.PI
            return 1 - Math.exp(-l * u) * (Math.cos(w * u) + (l / w) * Math.sin(w * u))
        }
        case "bounce": {
            const e = 0.5, hops = 3
            let total = 1
            for (let k = 1; k <= hops; k++) total += 2 * Math.pow(e, k)
            let t = u * total
            if (t < 1) return 1 - (1 - t * t)
            t -= 1
            for (let k = 1; k <= hops; k++) {
                const d = 2 * Math.pow(e, k)
                if (t < d) { const x = t / d * 2 - 1; return 1 - Math.pow(e, 2 * k) * (1 - x * x) }
                t -= d
            }
            return 1
        }
        case "jelly": {
            const w = Math.PI / 0.38, o = 0.07, l = -Math.log(o) * w / Math.PI
            const main = 1 - Math.exp(-l * u) * (Math.cos(w * u) + (l / w) * Math.sin(w * u))
            return main + 0.2 * Math.sin(2 * Math.PI * 2.2 * u) * Math.exp(-2.5 * u) * (1 - u)
        }
        case "genie": return u * u * u * (u * (u * 6 - 15) + 10)
        case "scalefade": return 1 - Math.pow(1 - u, 3.2)
        case "off": return u < 0.5 ? 0 : 1
        default: return 1 - Math.pow(1 - u, 3)      // gnome: plain ease-out
        }
    }

    onPaint: {
        const ctx = getContext("2d")
        ctx.reset()
        ctx.clearRect(0, 0, width, height)
        ctx.lineWidth = 1.5
        ctx.lineCap = "round"
        ctx.lineJoin = "round"
        ctx.strokeStyle = color
        const x0 = 2, x1 = width - 2
        const yBase = height - 2.5
        const rise = height - 7            // leaves headroom above the "arrived" line for overshoot
        const n = 48
        ctx.beginPath()
        for (let i = 0; i <= n; i++) {
            const u = i / n
            const x = x0 + (x1 - x0) * u
            const y = yBase - rise * curve(preset, u)
            if (preset === "off" && i > 0 && Math.abs(curve(preset, u) - curve(preset, (i - 1) / n)) > 0.5) {
                ctx.lineTo(x, yBase - rise * curve(preset, (i - 1) / n))
            }
            if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
        }
        ctx.stroke()
    }
}
