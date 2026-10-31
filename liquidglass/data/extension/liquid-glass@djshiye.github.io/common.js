// Helpers and shared state for the modules that put glass behind Shell surfaces.

import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {windowLanded} from './glass.js';

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
    const out = [Main.layoutManager._backgroundGroup];
    if (behind === 'wallpaper')
        return out;
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
        this._windows = new Signals();
        const changed = () => this.listeners.forEach(fn => fn());
        this._changed = changed;
        this._signals.on(global.display, 'restacked', () => {
            this._watchAll();
            changed();
        });
        this._signals.on(global.workspace_manager, 'active-workspace-changed', changed);
        this._signals.on(global.display, 'window-created', () => this._watchAll());
        this._watchAll();
    }

    _watchAll() {
        this._windows.clear();
        for (const actor of global.get_window_actors()) {
            const win = actor.meta_window;
            if (!win)
                continue;
            for (const sig of ['position-changed', 'size-changed', 'notify::minimized'])
                this._windows.on(win, sig, this._changed);
            this._windows.on(actor, 'notify::visible', this._changed);
            // Minimized windows keep their old place, so this is where the effect was.
            this._windows.on(actor, 'effects-completed', () => windowLanded(win.get_buffer_rect()));
            // A closed window's actor is disposed before the next restack: never touch it again.
            this._windows.on(actor, 'destroy', () => this._windows.forget(actor));
        }
    }

    destroy() {
        this._signals.clear();
        this._windows.clear();
        this.listeners.clear();
    }
}

// Shared between the modules: every live pane follower, and the one motion controller,
// wallpaper copy and window watcher while the extension is on.
export const windowWatch = {current: null};
export const followers = new Set();
export const motion = {current: null};
export const wallpaper = {current: null};

export class Signals {
    constructor() {
        this._ids = [];
    }

    on(obj, signal, fn) {
        this._ids.push([obj, obj.connect(signal, fn)]);
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
