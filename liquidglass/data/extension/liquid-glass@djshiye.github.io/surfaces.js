// Puts glass panes behind Shell surfaces and keeps them in step: the top bar
// or Dash to Panel, every popup menu (quick settings, calendar, ArcMenu and
// app menus), notification banners, the volume OSD, Alt+Tab, app windows and
// the overview background.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Graphene from 'gi://Graphene';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {BoxPointer} from 'resource:///org/gnome/shell/ui/boxpointer.js';

import {GlassPane, moving, stopMoving} from './glass.js';

const CORNERS = [St.Corner.TOPLEFT, St.Corner.TOPRIGHT, St.Corner.BOTTOMRIGHT, St.Corner.BOTTOMLEFT];
const MOVES = ['notify::allocation', 'notify::visible', 'notify::opacity', 'notify::translation-x',
    'notify::translation-y', 'notify::scale-x', 'notify::scale-y', 'notify::mapped'];

function radiiOf(actor) {
    try {
        const node = actor.get_theme_node();
        return CORNERS.map(c => node.get_border_radius(c));
    } catch {
        return [0, 0, 0, 0];   // not styled yet
    }
}

/** Which sides of a surface at stage rectangle (x, y, w, h) lie on its monitor's edge. */
function screenEdges(actor, x, y, w, h) {
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
function sourcesFor(behind, x, y, w, h) {
    if (Main.overview.visible)
        return [Main.layoutManager.overviewGroup];
    const out = [Main.layoutManager._backgroundGroup];
    if (behind === 'wallpaper')
        return out;
    const ws = global.workspace_manager.get_active_workspace();
    for (const actor of global.get_window_actors()) {
        const win = actor.meta_window;
        if (!actor.visible || !win || win.minimized || !win.located_on_workspace(ws))
            continue;
        const r = win.get_buffer_rect();
        if (r.x < x + w && r.x + r.width > x && r.y < y + h && r.y + r.height > y)
            out.push(actor);
    }
    return out;
}

/** Tells every pane that shows windows when any window moves, restacks or switches workspace. */
class WindowWatch {
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

export const windowWatch = {current: null};

class Signals {
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
function glowSource(anchor, target) {
    if (anchor.width > 1 && anchor.height > 1)
        return anchor;
    let a = target;
    while (a && a.get_parent() !== anchor)
        a = a.get_parent();
    return a ?? anchor;
}

/**
 * A pane that sits right below `anchor` (a child of a free-layout container
 * such as the Shell's UI group) and copies the on-screen rectangle, corner
 * radii and opacity of `target`, a descendant of `anchor`.
 */
class Follower {
    constructor(target, anchor, settings, onGone) {
        this.target = target;
        this.anchor = anchor;
        this.settings = settings;
        this.pane = new GlassPane('glass');
        this.top = new GlassPane('reflections');
        this._signals = new Signals();
        this._later = 0;
        this._onGone = onGone;
        this.rect = null;         // [x, y, w, h] on the stage, while shown
        this._held = null;        // the target's own opacity, while it waits for its glass
        this._holdId = 0;
        followers.add(this);

        for (let a = target; a && a !== anchor.get_parent(); a = a.get_parent())
            MOVES.forEach(s => this._signals.on(a, s, () => this.queue()));
        this._signals.on(target, 'style-changed', () => this.queue());
        // Never show a surface before its glass: hold it until the pane has painted.
        this._signals.on(target, 'notify::mapped', () => (target.mapped ? this._hold() : this._release()));
        // An open menu holds a grab, so presses reach it but not the stage.
        this._signals.on(anchor, 'captured-event', (_a, event) => {
            motion.current?.event(event);
            return Clutter.EVENT_PROPAGATE;
        });
        this._signals.on(target, 'destroy', () => this.destroy());
        this._signals.on(anchor, 'destroy', () => this.destroy());
        this._signals.on(this.pane, 'destroy', () => {
            this.pane = null;     // its parent went first
            this.destroy();
        });
        this._signals.on(this.top, 'destroy', () => {
            this.top = null;
            this.destroy();
        });
        this._onWindows = () => {
            if (this.settings.behind === 'windows' && this.target.mapped)
                this.queue();
        };
        windowWatch.current?.listeners.add(this._onWindows);
        // glass, then the content's light, then the content: the glow sits behind
        // icons and toggles, never on top of them.
        anchor.get_parent().insert_child_below(this.pane, anchor);
        anchor.get_parent().insert_child_below(this.top, anchor);
        this.update(settings);
    }

    _hold() {
        if (this._held !== null || !this.settings.enabled || this.pane?.visible)
            return;
        this._held = this.target.opacity;
        this.target.opacity = 0;
        // Whatever happens, never leave a menu invisible.
        this._holdId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
            this._holdId = 0;
            this._release();
            return GLib.SOURCE_REMOVE;
        });
    }

    _release() {
        if (this._holdId)
            GLib.source_remove(this._holdId);
        this._holdId = 0;
        if (this._held === null)
            return;
        const o = this._held;
        this._held = null;
        try {
            this.target.opacity = o;
        } catch {}   // already gone
    }

    update(settings) {
        this.settings = settings;
        this.pane?.setLook(settings.look);
        this.top?.setLook(settings.look);
        this.sync();
    }

    queue() {
        if (this._later)
            return;
        this._later = global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
            this._later = 0;
            this.sync();
            return GLib.SOURCE_REMOVE;
        });
    }

    sync() {
        const {target, anchor, pane, top} = this;
        const parent = anchor.get_parent();
        if (!pane || !top || !parent || pane.get_parent() !== parent || top.get_parent() !== parent)
            return;
        const hide = () => {
            pane.hide();
            top.hide();
            this.rect = null;
        };
        if (!this.settings.enabled || !target.mapped || target.width < 2 || target.height < 2) {
            hide();
            return;
        }
        if (top.get_next_sibling() !== anchor)
            parent.set_child_below_sibling(top, anchor);
        if (pane.get_next_sibling() !== top)
            parent.set_child_below_sibling(pane, top);

        const [sx, sy] = target.get_transformed_position();
        // Size from the allocation, which is what is painted: width/height (and so
        // get_transformed_size()) fall back to the preferred size while a relayout is
        // pending, and the volume OSD prefers twice the height it gets.
        const box = target.get_allocation_box();
        const far = target.apply_transform_to_point(new Graphene.Point3D({x: box.get_width(), y: box.get_height(), z: 0}));
        const [w, h] = [far.x - sx, far.y - sy];
        const [ok, lx, ly] = parent.transform_stage_point(sx, sy);
        // A menu that has just opened is mapped a frame before it is allocated.
        if (!ok || ![sx, sy, w, h, lx, ly].every(Number.isFinite)) {
            hide();
            return;
        }
        let opacity = 1;
        for (let a = target; a && a !== parent; a = a.get_parent())
            opacity *= (a === target && this._held !== null ? this._held : a.opacity) / 255;
        pane.opacity = top.opacity = Math.round(opacity * 255);
        const p = pane.pad;
        const radii = radiiOf(target);
        pane.setSources(sourcesFor(this.settings.behind, sx - p, sy - p, w + 2 * p, h + 2 * p));
        // The light the content casts into the glass comes from the content itself.
        // Both panes are the anchor's siblings; never clone an actor into itself.
        const glow = glowSource(anchor, target);
        const nested = top.contains(glow) || glow.contains(top) || glow.contains(pane);
        top.setSources(nested ? [] : [glow]);
        const edges = screenEdges(target, sx, sy, w, h);
        pane.setEdges(edges);
        top.setEdges(edges);
        pane.place(lx, ly, w, h, radii, sx, sy);
        top.place(lx, ly, w, h, radii, sx, sy);
        const appearing = !pane.visible;
        this.rect = [sx, sy, w, h];
        pane.show();
        top.show();
        if (appearing)
            motion.current?.opened(this);
        if (this._held !== null) {
            // Show the surface on the frame after its glass first paints.
            pane.onNextPaint(() => {
                const laters = global.compositor.get_laters();
                laters.add(Meta.LaterType.BEFORE_REDRAW, () => {
                    this._release();
                    return GLib.SOURCE_REMOVE;
                });
            });
        }
    }

    setMotion(m) {
        // The rim light is drawn by the content's light layer; the glass only gives.
        const {sx, sy, k, ...shape} = m;
        this.pane?.setMotion(shape);
        this.top?.setMotion(m);
        // A menu condenses into place as it opens: a little small, then its size.
        if (this.condense && m.open !== undefined && this.target) {
            const sc = 0.96 + 0.04 * Math.min(m.open, 1.0) + 0.02 * Math.max(0, m.open - 1);
            this.target.set_pivot_point(0.5, 0.5);
            this.target.set_scale(sc, sc);
        }
    }

    destroy() {
        if (this._later)
            global.compositor.get_laters().remove(this._later);
        this._later = 0;
        followers.delete(this);
        motion.current?.forget(this);
        this._signals.clear();
        // Only now, so that putting the target back queues nothing.
        this._release();
        if (this.condense) {
            try {
                this.target.set_scale(1, 1);
            } catch {}
        }
        windowWatch.current?.listeners.delete(this._onWindows);
        const {pane, top} = this;
        this.pane = this.top = null;
        pane?.destroy();
        top?.destroy();
        if (this._onGone) {
            this._onGone(this);
            this._onGone = null;
        }
    }
}

// ---- motion: a light that follows the pointer, press and open springs --------------
// Nothing runs while the pointer is still: a pointer event schedules one step
// before the next redraw, and steps go on only while a spring is still moving.
const followers = new Set();
const motion = {current: null};
const REACH = 220;          // px around a pane where the pointer lights its rim

class Motion {
    constructor() {
        this._state = new Map();    // follower -> springs
        this._pointer = null;
        this._later = 0;
        this._last = 0;
        this._settings = St.Settings.get();
        // The cursor tracker reports every pointer move, also ones the stage's
        // event chain never sees.
        this._cursor = global.backend.get_cursor_tracker();
        this._cursorId = this._cursor.connect('position-invalidated', () => {
            const [x, y] = global.get_pointer();
            this._pointer = [x, y];
            this._kick();
        });
        this._stage = global.stage.connect('captured-event', (_s, event) => {
            this.event(event);
            return Clutter.EVENT_PROPAGATE;
        });
    }

    get _animate() {
        return this._settings.enable_animations;
    }

    _look(f) {
        return f.settings?.look ?? {};
    }

    _st(f) {
        let st = this._state.get(f);
        if (!st) {
            st = {x: null, y: null, k: 0, press: 0, pressV: 0, pressT: 0, open: 1, openV: 0};
            this._state.set(f, st);
        }
        return st;
    }

    event(event) {
        const type = event.type();
        if (type === Clutter.EventType.BUTTON_PRESS || type === Clutter.EventType.TOUCH_BEGIN) {
            const [x, y] = event.get_coords();
            for (const f of followers) {
                const r = f.rect;
                if (r && this._look(f).motion > 0 && x >= r[0] && y >= r[1] && x < r[0] + r[2] && y < r[1] + r[3])
                    this._st(f).pressT = 1;
            }
            this._kick();
        } else if (type === Clutter.EventType.BUTTON_RELEASE || type === Clutter.EventType.TOUCH_END ||
                   type === Clutter.EventType.TOUCH_CANCEL) {
            for (const st of this._state.values())
                st.pressT = 0;
            this._kick();
        }
    }

    opened(f) {
        if (!this._animate || !(this._look(f).motion > 0))
            return;
        const st = this._st(f);
        st.open = 0;          // the bevel condenses from flat, with a little overshoot
        st.openV = 0;
        f.setMotion({open: 0});
        this._kick();
    }

    forget(f) {
        this._state.delete(f);
    }

    _kick() {
        if (this._later)
            return;
        this._later = global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
            this._later = 0;
            this._step();
            return GLib.SOURCE_REMOVE;
        });
    }

    _step() {
        const now = GLib.get_monotonic_time() / 1e6;
        const dt = Math.min(0.033, Math.max(0.001, this._last ? now - this._last : 0.016));
        this._last = now;
        const animate = this._animate;
        let moving = false;
        for (const f of followers) {
            const r = f.rect;
            if (!r)
                continue;
            const L = this._look(f);
            const st = this._st(f);
            // The pointer lights the rim nearest to it while it is near the pane.
            const w = animate ? L.pointerLight ?? 0 : 0;
            let tk = 0;
            let [tx, ty] = [st.x, st.y];
            if (w > 0 && this._pointer) {
                [tx, ty] = this._pointer;
                const dx = Math.max(r[0] - tx, 0, tx - r[0] - r[2]);
                const dy = Math.max(r[1] - ty, 0, ty - r[1] - r[3]);
                tk = Math.min(1, w * 1.6) * Math.max(0, 1 - Math.hypot(dx, dy) / REACH);
            }
            if (st.x === null || st.k < 0.01)
                [st.x, st.y] = [tx, ty];     // a light that is off jumps; a lit one glides
            const e = 1 - Math.exp(-dt / 0.04);
            const fade = 1 - Math.exp(-dt / 0.08);
            const prev = [st.x, st.y, st.k, st.press, st.open];
            if (tx !== null) {
                st.x += (tx - st.x) * e;
                st.y += (ty - st.y) * e;
            }
            st.k += (tk - st.k) * fade;
            // Press and open: springs with a small overshoot.
            if (animate) {
                [st.press, st.pressV] = spring(st.press, st.pressV, st.pressT, 1370, 44, dt);   // ~180 ms
                [st.open, st.openV] = spring(st.open, st.openV, 1, 900, 36, dt);           // ~220 ms
            } else {
                [st.press, st.pressV, st.open, st.openV] = [0, 0, 1, 0];
            }
            const settled = (tx === null || Math.abs(tx - st.x) + Math.abs(ty - st.y) < 0.5) &&
                Math.abs(tk - st.k) < 0.005 &&
                Math.abs(st.pressT - st.press) + Math.abs(st.pressV) < 0.002 &&
                Math.abs(1 - st.open) + Math.abs(st.openV) < 0.002;
            if (settled) {
                [st.x, st.y, st.k, st.press, st.open] = [tx, ty, tk, st.pressT, 1];
                st.pressV = st.openV = 0;
            } else {
                moving = true;
            }
            const now_ = [st.x, st.y, st.k, st.press, st.open];
            // Only what shows: an unlit pointer moving about costs nothing.
            const lit = st.k > 0.003 || prev[2] > 0.003;
            if (now_.some((v, i) => (i > 1 || lit) && Math.abs(v - prev[i]) > (i < 2 ? 0.25 : 1e-3)))
                f.setMotion({sx: st.x ?? 0, sy: st.y ?? 0, k: st.k, press: st.press, open: st.open});
        }
        if (moving)
            this._kick();
        else
            this._last = 0;
    }

    destroy() {
        if (this._later)
            global.compositor.get_laters().remove(this._later);
        this._later = 0;
        global.stage.disconnect(this._stage);
        this._cursor.disconnect(this._cursorId);
        for (const f of followers)
            f.setMotion({k: 0, press: 0, open: 1});
        this._state.clear();
    }
}

// One step of a damped spring towards `to` (stiffness k, damping c).
function spring(x, v, to, k, c, dt) {
    const steps = Math.ceil(dt / 0.008);
    const h = dt / steps;
    for (let i = 0; i < steps; i++) {
        v += (k * (to - x) - c * v) * h;
        x += v * h;
    }
    return [x, v];
}

// ---- top bar and Dash to Panel ------------------------------------------------
class Panels {
    constructor(cfg) {
        this.cfg = cfg;
        this._followers = [];
        this._signals = new Signals();
        this._dtpId = 0;
        this._rescanId = 0;
        this._signals.on(Main.extensionManager, 'extension-state-changed', () => this.rescanSoon());
        this.rescan();
    }

    _panels() {
        const dtp = global.dashToPanel;
        if (dtp?.panels?.length) {
            if (dtp !== this._dtp && typeof dtp.connect === 'function') {
                // Dash to Panel makes a new object each time it is enabled.
                this._disconnectDtp();
                try {
                    this._dtpId = dtp.connect('panels-created', () => this.rescanSoon());
                    this._dtp = dtp;
                } catch {
                    this._dtpId = 0;
                }
            }
            return dtp.panels.filter(p => p.panel && p.panelBox?.get_parent())
                .map(p => [p.panel, p.panelBox]);
        }
        const box = Main.layoutManager.panelBox;
        return box?.get_parent() ? [[Main.panel, box]] : [];
    }

    _disconnectDtp() {
        if (this._dtp && this._dtpId) {
            try {
                this._dtp.disconnect(this._dtpId);
            } catch {}
        }
        this._dtp = null;
        this._dtpId = 0;
    }

    rescanSoon() {
        if (this._rescanId)
            return;
        this._rescanId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 400, () => {
            this._rescanId = 0;
            this.rescan();
            return GLib.SOURCE_REMOVE;
        });
    }

    rescan() {
        this._followers.forEach(f => f.destroy());
        this._followers = [];
        for (const [target, anchor] of this._panels()) {
            this._followers.push(new Follower(target, anchor, this.cfg.parts.panel,
                f => (this._followers = this._followers.filter(x => x !== f))));
        }
    }

    update(cfg) {
        this.cfg = cfg;
        this._followers.forEach(f => f.update(cfg.parts.panel));
    }

    sync() {
        this._followers.forEach(f => f.queue());
    }

    destroy() {
        if (this._rescanId)
            GLib.source_remove(this._rescanId);
        this._disconnectDtp();
        this._signals.clear();
        this._followers.forEach(f => f.destroy());
        this._followers = [];
    }
}

// ---- popup menus, notification banners, OSD and the window switcher ----------------
// Which part of the Shell a menu belongs to, for its own look.
function partOf(bp) {
    const sa = Main.panel.statusArea;
    if (bp === sa.quickSettings?.menu?.actor)
        return 'quicksettings';
    if (bp === sa.dateMenu?.menu?.actor)
        return 'calendar';
    if (bp.has_style_class_name?.('arcmenu-menu'))
        return 'arcmenu';
    return 'quicksettings';      // app menus and the rest look like quick settings
}

class Popups {
    constructor(cfg) {
        this.cfg = cfg;
        this._followers = new Map();   // surface -> Follower
        this._signals = new Signals();
        const ui = Main.layoutManager.uiGroup;
        this._laters = new Set();
        // Some pop-ups (Alt+Tab) are added before they finish building, so look a moment later.
        this._signals.on(ui, 'child-added', (_p, child) => {
            const laters = global.compositor.get_laters();
            // Tooltips and the like can be gone before the later runs.
            const gone = child.connect('destroy', () => {
                laters.remove(id);
                this._laters.delete(id);
            });
            const id = laters.add(Meta.LaterType.BEFORE_REDRAW, () => {
                this._laters.delete(id);
                child.disconnect(gone);
                this._consider(child);
                return GLib.SOURCE_REMOVE;
            });
            this._laters.add(id);
        });
        ui.get_children().forEach(c => this._consider(c));
        // Banners come and go inside the message tray.
        const tray = Main.messageTray, bin = tray?._bannerBin;
        if (bin) {
            this._signals.on(bin, 'child-added', (_b, banner) => this._follow(banner, tray, 'calendar'));
            bin.get_children().forEach(b => this._follow(b, tray, 'calendar'));
        }
    }

    _consider(child) {
        if (child.name === 'liquid-glass-pane')
            return;
        // Menus: a BoxPointer, or one wrapped in a widget (quick settings).
        const bp = child instanceof BoxPointer ? child
            : child.get_children?.().find(c => c instanceof BoxPointer) ?? null;
        if (bp) {
            this._follow(bp.bin?.get_child?.(), child, partOf(bp));
            return;
        }
        // Volume and brightness pop-ups.
        const osd = child.get_children?.().find(c => c.has_style_class_name?.('osd-window'));
        if (osd) {
            this._follow(osd, child, 'quicksettings');
            return;
        }
        // Alt+Tab and friends.
        if (child._switcherList)
            this._follow(child._switcherList, child, 'quicksettings');
    }

    _follow(surface, anchor, part = 'menus') {
        if (!surface || this._followers.has(surface))
            return;
        const f = new Follower(surface, anchor, this._settings(part), () => this._followers.delete(surface));
        f.part = part;
        f.condense = true;
        this._followers.set(surface, f);
    }

    _settings(part) {
        return this.cfg.parts[part] ?? this.cfg.menus;
    }

    update(cfg) {
        this.cfg = cfg;
        for (const f of this._followers.values())
            f.update(this._settings(f.part));
    }

    sync() {
        for (const f of this._followers.values())
            f.queue();
    }

    destroy() {
        this._signals.clear();
        const laters = global.compositor.get_laters();
        this._laters.forEach(id => laters.remove(id));
        this._laters.clear();
        for (const f of [...this._followers.values()])
            f.destroy();
        this._followers.clear();
    }
}

// ---- app windows -------------------------------------------------------------------
const WINDOW_TYPES = new Set([Meta.WindowType.NORMAL, Meta.WindowType.DIALOG, Meta.WindowType.MODAL_DIALOG,
    Meta.WindowType.UTILITY]);

class WindowGlass {
    constructor(actor, owner) {
        this.actor = actor;
        this.win = actor.meta_window;
        this.owner = owner;
        this.pane = new GlassPane();
        this._signals = new Signals();
        actor.insert_child_at_index(this.pane, 0);
        for (const s of ['position-changed', 'size-changed', 'notify::fullscreen',
            'notify::maximized-horizontally', 'notify::maximized-vertically', 'notify::wm-class'])
            this._signals.on(this.win, s, () => this.sync());
        this._signals.on(actor, 'destroy', () => this.destroy());
        this._signals.on(this.pane, 'destroy', () => {
            this.pane = null;
            this.destroy();
        });
        this.update(owner.cfg.windows);
    }

    update(settings) {
        this.settings = settings;
        if (!this.pane)
            return;
        this.pane.setLook(settings.look);
        this.pane.setSources([Main.layoutManager._backgroundGroup]);
        this.sync();
    }

    _wanted() {
        const w = this.win, s = this.settings;
        if (!s.enabled || w.fullscreen || !WINDOW_TYPES.has(w.get_window_type()))
            return false;
        const ids = [w.get_wm_class(), w.get_wm_class_instance(), w.get_gtk_application_id(), w.get_sandboxed_app_id()];
        return !ids.some(id => id && s.skip.includes(id));
    }

    sync() {
        if (!this.pane)
            return;
        if (!this._wanted()) {
            this.pane.hide();
            return;
        }
        const frame = this.win.get_frame_rect();
        const buf = this.win.get_buffer_rect();
        const maxed = this.win.maximized_horizontally && this.win.maximized_vertically;
        const r = maxed ? 0 : this.settings.radius;
        this.pane.place(frame.x - buf.x, frame.y - buf.y, frame.width, frame.height, [r, r, r, r], frame.x, frame.y);
        this.pane.show();
    }

    destroy() {
        this._signals.clear();
        const pane = this.pane;
        this.pane = null;
        pane?.destroy();
        this.owner.forget(this.actor);
    }
}

class Windows {
    constructor(cfg) {
        this.cfg = cfg;
        this._glass = new Map();
        this._signals = new Signals();
        this._pending = new Signals();
        this._signals.on(global.display, 'window-created', (_d, win) => {
            // The actor exists once the window is shown for the first time.
            this._pending.on(win, 'shown', () => this._add(win.get_compositor_private()));
        });
        global.get_window_actors().forEach(a => this._add(a));
    }

    _add(actor) {
        if (!actor || this._glass.has(actor) || !actor.meta_window)
            return;
        this._glass.set(actor, new WindowGlass(actor, this));
    }

    forget(actor) {
        this._glass.delete(actor);
    }

    update(cfg) {
        this.cfg = cfg;
        for (const g of this._glass.values())
            g.update(cfg.windows);
    }

    destroy() {
        this._signals.clear();
        this._pending.clear();
        for (const g of [...this._glass.values()])
            g.destroy();
        this._glass.clear();
    }
}

// ---- overview background ---------------------------------------------------------------
class OverviewBackdrop {
    constructor(cfg) {
        this.actor = new Clutter.Actor({name: 'liquid-glass-overview', clip_to_allocation: true, reactive: false});
        this.actor.add_constraint(new Clutter.BindConstraint({source: global.stage, coordinate: Clutter.BindCoordinate.ALL}));
        this._clone = new Clutter.Clone({source: Main.layoutManager._backgroundGroup});
        this.actor.add_child(this._clone);
        this._blur = new Shell.BlurEffect({mode: Shell.BlurMode.ACTOR});
        this.actor.add_effect(this._blur);
        Main.layoutManager.overviewGroup.insert_child_at_index(this.actor, 0);
        this.update(cfg);
    }

    update(cfg) {
        const o = cfg.overview;
        this.actor.visible = o.enabled;
        this._blur.radius = o.blur;
        this._blur.brightness = o.brightness;
    }

    destroy() {
        this.actor.destroy();
    }
}

export class GlassManager {
    constructor(cfg) {
        this.cfg = cfg;
        windowWatch.current = new WindowWatch();
        motion.current = new Motion();
        this._parts = [new Panels(cfg), new Popups(cfg), new Windows(cfg), new OverviewBackdrop(cfg)];
        this._signals = new Signals();
        // Behind the panel and menus is the overview while it is open, the windows otherwise.
        for (const s of ['showing', 'shown', 'hiding', 'hidden'])
            this._signals.on(Main.overview, s, () => this._parts.forEach(p => p.sync?.()));
        // A window dragged or resized behind the glass re-renders it every frame.
        this._signals.on(global.display, 'grab-op-begin', () => moving(true));
        this._signals.on(global.display, 'grab-op-end', () => moving(false));
    }

    update(cfg) {
        this.cfg = cfg;
        this._parts.forEach(p => p.update(cfg));
    }

    destroy() {
        this._signals.clear();
        stopMoving();
        motion.current?.destroy();
        motion.current = null;
        this._parts.forEach(p => p.destroy());
        this._parts = [];
        windowWatch.current?.destroy();
        windowWatch.current = null;
    }
}
