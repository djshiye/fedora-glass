.pragma library

// One Tab stop for a row of chips or swatches (the "roving tab stop"): Tab lands on
// the chosen one, the arrow keys, Home and End move along the row, Tab leaves it.
// Members are the group's children whose `rovingGroup` is that group.

function members(group) {
    const out = []
    const kids = group.children
    for (let i = 0; i < kids.length; i++) {
        const c = kids[i]
        if (c.rovingGroup === group && c.visible && c.enabled)
            out.push(c)
    }
    // Reading order: row by row, then left to right (a Flow wraps).
    out.sort((a, b) => Math.abs(a.y - b.y) > a.height / 2 ? a.y - b.y : a.x - b.x)
    return out
}

// The item in the row above (dir -1) or below (dir 1) nearest to `item` across.
function _vertical(items, item, dir) {
    const cx = item.x + item.width / 2
    let rowY = null
    for (const c of items) {
        const dy = c.y - item.y
        if (dir * dy > item.height / 2 && (rowY === null || dir * (c.y - rowY) < 0))
            rowY = c.y
    }
    if (rowY === null)
        return null
    let best = null
    for (const c of items) {
        if (Math.abs(c.y - rowY) > item.height / 2)
            continue
        if (!best || Math.abs(c.x + c.width / 2 - cx) < Math.abs(best.x + best.width / 2 - cx))
            best = c
    }
    return best
}

// Moves focus inside the group for a key press. True when the key was used.
function handleKey(item, e) {
    const group = item.rovingGroup
    if (!group || (e.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier | Qt.ShiftModifier)))
        return false
    const items = members(group)
    const i = items.indexOf(item)
    if (i < 0)
        return false
    let to = null
    switch (e.key) {
    case Qt.Key_Left: to = items[i - 1]; break
    case Qt.Key_Right: to = items[i + 1]; break
    case Qt.Key_Home: to = items[0]; break
    case Qt.Key_End: to = items[items.length - 1]; break
    case Qt.Key_Up:
    case Qt.Key_Down: {
        const dir = e.key === Qt.Key_Up ? -1 : 1
        // One row: up and down step along it; a wrapped row moves to the row above or below.
        to = _vertical(items, item, dir)
        if (!to && items.every(c => Math.abs(c.y - item.y) <= item.height / 2))
            to = items[i + dir]
        break
    }
    default:
        return false
    }
    if (to && to !== item) {
        to.forceActiveFocus(Qt.TabFocusReason)
        if (to.rovingSelects)
            to.click()
    }
    return true
}
