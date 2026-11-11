// Helpers and shared state for the modules that put glass behind Shell surfaces.

import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {windowLanded} from './glass.js';
import {guarded} from './safety.js';

export const HOLD_MAX_MS = 100;   // a menu waits at most this long for its glass
const CORNERS = [St.Corner.TOPLEFT, St.Corner.TOPRIGHT, St.Corner.BOTTOMRIGHT, St.Corner.BOTTOMLEFT];
export const MOVES = ['notify::allocation', 'notify::visible', 'notify::opacity', 'notify::translation-x',
    'notify::translation-y', 'notify::scale-x', 'notify::scale-y', 'notify::mapped'];

export function radiiOf(actor) {
    try {
        const node = actor.get_theme_node();
        return CORNERS.map(c => node.get_border_radius(c));
    } catch {
        return [0, 0, 0, 0];   // not styled yet
    }
}

/** Which sides of a surface at stage rectangle (x, y, w, h) lie on its monitor's edge. */
export function screenEdges(actor, x, y, w, h) {
    const m = Main.layoutManager.findMonitorForActor(actor);
    if (!m)
        return [false, false, false, false];
    const near = (a, b) => Math.abs(a - b) < 1.5;
    return [near(x, m.x), near(y, m.y), near(x + w, m.x + m.width), near(y + h, m.y + m.height)];
}

/**
 * What a pane at stage rectangle (x, y, w, h) shows through: the wallpaper,
 * then the windows on the current workspace that overlap it, bottom first. A
 * clone of the whole window group would be simpler, but Mutter culls it to
 * the screen and it comes out empty, so each window is copied on its own.
 */
export function sourcesFor(behind, x, y, w, h) {
    if (Main.overview.visible)
        return [Main.layoutManager.overviewGroup];
    // Our own whole copy of the wallpaper, not the Shell's: the Shell's skips whatever an
    // opaque window covers, so with the wallpaper alone behind it (the lightest glass
    // level) a menu over a window had a hole there and showed that window sharp, as if
    // it had no glass at all.
    const out = [wallpaper.current?.actor ?? Main.layoutManager._backgroundGroup];
    if (behind === 'wallpaper')
        return out;
    // Only windows on the pane's own screen: the glass never shows across the seam
    // (see the edge clamp in glass.js), and a window there that repaints all the time
    // (a full-screen game or video next door) would re-render this pane for nothing.
    const mons = Main.layoutManager.monitors ?? [];
    const cx = x + w / 2, cy = y + h / 2;
    const m = mons.find(o => cx >= o.x && cx < o.x + o.width && cy >= o.y && cy < o.y + o.height);
    if (m) {
        const x1 = Math.min(x + w, m.x + m.width), y1 = Math.min(y + h, m.y + m.height);
        x = Math.max(x, m.x);
        y = Math.max(y, m.y);
        w = x1 - x;
        h = y1 - y;
    }
    const ws = global.workspace_manager.get_active_workspace();
    for (const actor of global.get_window_actors()) {
        const win = actor.meta_window;
        if (!actor.visible || !win || win.get_monitor() < 0 || win.minimized || !win.located_on_workspace(ws))
            continue;
        const r = win.get_buffer_rect();
        if (r.x < x + w && r.x + r.width > x && r.y < y + h && r.y + r.height > y)
            out.push(actor);
    }
    return out;
}

/** Tells every pane that shows windows when any window moves, restacks or switches workspace. */
export class WindowWatch {
    constructor() {
        this.listeners = new Set();
        this._signals = new Signals();
        this._windows = new Map();    // window actor -> its Signals
        // With the window that moved, changed size or was minimized or hidden, so a
        // listener can redo only what that window touches; without one, anything may
        // have changed (a restack, another workspace).
        const changed = (win = null) => this.listeners.forEach(fn => fn(win));
        this._signals.on(global.display, 'restacked', () => {
            this._watchAll();
            changed();
        });
        this._signals.on(global.workspace_manager, 'active-workspace-changed', () => changed());
        this._signals.on(global.display, 'window-created', () => this._watchAll());
        this._changed = changed;
        this._watchAll();
    }

    // Connects to windows not watched yet. Restacks come with every focus change, so
    // windows already watched keep their connections (1.5.3 remade them all each time).
    _watchAll() {
        const changed = this._changed;
        for (const actor of global.get_window_actors()) {
            const win = actor.meta_window;
            if (!win || this._windows.has(actor))
                continue;
            const sigs = new Signals();
            this._windows.set(actor, sigs);
            for (const sig of ['position-changed', 'size-changed', 'notify::minimized'])
                sigs.on(win, sig, () => changed(win));
            sigs.on(actor, 'notify::visible', () => changed(win));
            // Minimized windows keep their old place, so this is where the effect was.
            sigs.on(actor, 'effects-completed', () => windowLanded(win.get_buffer_rect()));
            // A closed window's actor is disposed: never touch it or its window again.
            sigs.on(actor, 'destroy', () => {
                sigs.forget(actor);
                sigs.forget(win);
                this._windows.delete(actor);
            });
        }
    }

    destroy() {
        this._signals.clear();
        for (const sigs of this._windows.values())
            sigs.clear();
        this._windows.clear();
        this.listeners.clear();
    }
}

// Shared between the modules: every live pane follower, and the one motion controller,
// wallpaper copy and window watcher while the extension is on.
export const windowWatch = {current: null};
export const followers = new Set();
// Menus grow out of the button that opened them and flow back into it on close.
export const grow = {enabled: true};
export const motion = {current: null};
export const wallpaper = {current: null};

export class Signals {
    constructor() {
        this._ids = [];
    }

    on(obj, signal, fn) {
        // An error in a handler is reported to safe mode instead of thrown into GNOME Shell.
        this._ids.push([obj, obj.connect(signal, guarded(signal, fn))]);
    }

    /** Drop obj's connections without disconnecting (it is being disposed). */
    forget(obj) {
        this._ids = this._ids.filter(([o]) => o !== obj);
    }

    clear() {
        for (const [obj, id] of this._ids) {
            try {
                obj.disconnect(id);
            } catch {}
        }
        this._ids = [];
    }
}

// What to copy for the content's light: the anchor, or, when it is an empty
// wrapper (quick settings sits in a 0×0 widget), its child that holds the target.
export function glowSource(anchor, target) {
    if (anchor.width > 1 && anchor.height > 1)
        return anchor;
    let a = target;
    while (a && a.get_parent() !== anchor)
        a = a.get_parent();
    return a ?? anchor;
}

// ---- the lock screen clock's place (lock.js) ----
const NOTES_GAP = 24;           // px between the clock (and its hint) and GNOME's notifications

/** Where GNOME's notifications start under the clock, or null when none show. */
export function notificationsTop(notes) {
    if (!notes?.visible)
        return null;
    const b = notes.get_allocation_box();
    return b.y2 - b.y1 > 0 ? b.y1 : null;
}

/**
 * The top of the clock placed in the middle of a screen H high. With notifications
 * showing below, it moves up just enough to keep clear of them (1.5.7 let the "Click or
 * press a key to unlock" hint run into the first one). Never above the screen.
 */
export function clockMiddle(H, clockH, notesTop) {
    let y = Math.round((H - clockH) / 2);
    if (notesTop !== null && notesTop !== undefined)
        y = Math.min(y, Math.round(notesTop - NOTES_GAP - clockH));
    return Math.max(0, y);
}
