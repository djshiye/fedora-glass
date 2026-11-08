// Glass behind translucent app windows.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {GlassPane} from './glass.js';
import {screenEdges, windowWatch, wallpaper, Signals} from './common.js';

// ---- app windows -------------------------------------------------------------------
// Behind each translucent app window: the same glass as the menus, a lens along
// its edge and a rim that mirrors what really lies around it, under the window's
// own background, so its content is never covered. No colour bleed.
const WINDOW_TYPES = new Set([Meta.WindowType.NORMAL, Meta.WindowType.DIALOG, Meta.WindowType.MODAL_DIALOG,
    Meta.WindowType.UTILITY]);
// Games and video players: they paint their whole window, and every frame they
// show would re-render glass nobody sees.
const NO_GLASS = /^(steam_app_\d+|steam_proton|gamescope|mpv|vlc|celluloid|io\.github\.celluloid_player\.celluloid|totem|org\.gnome\.totem|org\.gnome\.showtime|com\.github\.rafostar\.clapper|io\.mpv\.mpv|org\.videolan\.vlc|retroarch|org\.libretro\.retroarch)$/i;
// A window that moved or changed size this long ago counts as still moving (see _moved).
const SETTLE_MS = 250;
// Fedora Glass's own window draws its glass, rim and shadow itself, and leaves a clear
// margin around them for its shadow. Mutter counts that margin as part of the window
// (a Qt window can't say where its frame really is), so glass here would draw a second,
// larger frame around the app.
const OWN_APP = /^(io\.github\.djshiye\.LiquidGlass|fedora-glass|Fedora Glass)$/;
const TERMINALS = /^(org\.gnome\.ptyxis|ptyxis|org\.gnome\.console|kgx|gnome-terminal-server|org\.gnome\.terminal)$/i;

function appIds(w) {
    return [w.get_wm_class(), w.get_wm_class_instance(), w.get_gtk_application_id(), w.get_sandboxed_app_id()]
        .filter(id => typeof id === 'string' && id.length);
}

function isMaximized(w) {
    if (typeof w.is_maximized === 'function')
        return w.is_maximized();
    return !!(w.maximized_horizontally && w.maximized_vertically);
}

// An unmanaged window (closing, its actor still animating) has no monitor left.
function gone(win) {
    return !win || win.get_monitor() < 0;
}

// A full-screen window (a game, a video) on top of a screen hides every window under
// it there: their glass would keep rendering for changes nobody can see.
function underFullscreen(actor, win) {
    const m = win.get_monitor();
    if (m < 0 || win.fullscreen || !Main.layoutManager.monitors[m]?.inFullscreen)
        return false;
    let above = false;
    for (const a of global.get_window_actors()) {
        if (a === actor) {
            above = true;
            continue;
        }
        const w = a.meta_window;
        if (above && w?.fullscreen && !w.minimized && w.get_monitor() === m)
            return true;
    }
    return false;
}

class WindowGlass {
    constructor(actor, owner) {
        this.actor = actor;
        this.win = actor.meta_window;
        this.owner = owner;
        // The glass under the window's own background, and over it a hairline of the
        // edge's reflection, outside anything the app draws.
        this.pane = new GlassPane();
        this._signals = new Signals();
        this._later = 0;
        // Each pane sits in a holder that keeps its finished picture. A window's glass
        // is big, and without it the lens would be drawn again for every frame that
        // repaints the window (the overview opening, a workspace switch, an app
        // streaming text); with it, it is drawn again only when what is behind the
        // window changes.
        const holder = p => {
            const h = new Clutter.Actor({name: 'fedora-glass-holder', reactive: false, visible: false,
                offscreen_redirect: Clutter.OffscreenRedirect.ALWAYS});
            h.add_child(p);
            return h;
        };
        this._holder = holder(this.pane);
        actor.insert_child_at_index(this._holder, 0);
        this._frameKey = '';
        this._settle = 0;
        // The rim only draws along the edge: four thin panes, top, bottom, left and
        // right, each copying and drawing only its own strip (top and bottom hold the
        // rounded corners). Up to 1.5.6 it was one pane the size of the window, shown
        // through four clipped copies; every change behind it then copied the backdrop
        // of the whole window and repainted all of the window, for a 3 px line.
        this.rims = [0, 1, 2, 3].map(() => new GlassPane('rim'));
        this._rimHolders = this.rims.map(r => {
            const h = holder(r);
            actor.add_child(h);
            return h;
        });
        for (const s of ['position-changed', 'size-changed', 'notify::fullscreen', 'notify::minimized',
            'notify::maximized-horizontally', 'notify::maximized-vertically', 'notify::wm-class'])
            this._signals.on(this.win, s, () => this.queue());
        this._signals.on(actor, 'destroy', () => this.destroy());
        // A closing window's actor outlives it while the close animation plays, but
        // Mutter asserts if the window is asked about its monitor once unmanaged.
        this._signals.on(this.win, 'unmanaging', () => this.destroy());
        for (const p of [this.pane, ...this.rims]) {
            this._signals.on(p, 'destroy', () => {
                if (p === this.pane)
                    this.pane = null;
                else if (this.rims)
                    this.rims = this.rims.filter(r => r !== p);    // the others go with the rest
                this.destroy();
            });
        }
        this.update(owner.cfg.windows);
    }

    update(settings) {
        this.settings = settings;
        if (!this.pane || !this.rims)
            return;
        const ids = appIds(this.win);
        const term = settings.terminalLook && ids.some(id => TERMINALS.test(id));
        const look = term ? settings.terminalLook : settings.look;
        this.pane.setLook(look);
        this.rims.forEach(r => r.setLook(look));
        this.sync();
    }

    _wanted() {
        const w = this.win, s = this.settings;
        if (!s.enabled || w.fullscreen || w.minimized || !WINDOW_TYPES.has(w.get_window_type()))
            return false;
        if (underFullscreen(this.actor, w))
            return false;
        // A title bar drawn by the Shell is opaque: nothing would show.
        if (typeof w.is_client_decorated === 'function' && w.get_client_type?.() === Meta.WindowClientType.X11 &&
            !w.is_client_decorated())
            return false;
        const ids = appIds(w);
        return !ids.some(id => s.skip.includes(id) || NO_GLASS.test(id) || OWN_APP.test(id));
    }

    /**
     * What lies behind this window: the wallpaper and the windows below it that it
     * overlaps. Only the focused window sees other windows: each window that does
     * re-renders whenever one below it changes, and with several stacked the cost
     * adds up. The others show the wallpaper, which never changes.
     */
    _sources(x, y, w, h) {
        const out = [wallpaper.current?.actor ?? Main.layoutManager._backgroundGroup];
        if (this.settings.behind === 'wallpaper' || global.display.focus_window !== this.win)
            return out;
        const ws = global.workspace_manager.get_active_workspace();
        for (const actor of global.get_window_actors()) {
            if (actor === this.actor)
                break;     // bottom first: everything after this is above it
            const win = actor.meta_window;
            if (!actor.visible || !win || gone(win) || win.minimized || !win.located_on_workspace(ws))
                continue;
            const r = win.get_buffer_rect();
            if (r.x < x + w && r.x + r.width > x && r.y < y + h && r.y + r.height > y)
                out.push(actor);
        }
        return out;
    }

    queue() {
        if (this._later || !this.pane || !this.rims)
            return;
        this._later = global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
            this._later = 0;
            this.sync();
            return GLib.SOURCE_REMOVE;
        });
    }

    sync() {
        const {pane, rims} = this;
        if (!pane || !rims)
            return;
        // A closing window drops its glass on 'unmanaging'; one that has briefly lost
        // its monitor (a screen unplugged) just shows none until it has one again.
        if (gone(this.win) || !this._wanted()) {
            for (const p of [pane, ...rims]) {
                p.hide();
                p.setSources([]);
            }
            this._syncHolder();
            return;
        }
        const w = this.win;
        const frame = w.get_frame_rect();
        const buf = w.get_buffer_rect();
        // Maximized and tiled windows have square corners and no rim on the sides
        // that meet the screen, the panel or the next tile; a floating window loses
        // only the sides that sit exactly on the screen edge.
        const wa = w.get_work_area_current_monitor();
        const near = (a, b) => Math.abs(a - b) < 1.5;
        const onWa = [near(frame.x, wa.x), near(frame.y, wa.y), near(frame.x + frame.width, wa.x + wa.width),
            near(frame.y + frame.height, wa.y + wa.height)];
        const snapped = isMaximized(w) || (onWa[1] && onWa[3]) || (onWa[0] && onWa[2]);
        const scr = screenEdges(this.actor, frame.x, frame.y, frame.width, frame.height);
        const edges = snapped ? onWa.map((e, i) => e || scr[i]) : scr;
        const r = snapped ? 0 : this.settings.radius;
        const p = pane.pad;
        const rp = rims[0].pad;
        const q = Math.max(p, rp);
        const sources = this._sources(frame.x - q, frame.y - q, frame.width + 2 * q, frame.height + 2 * q);
        const [W, H] = [frame.width, frame.height];
        const key = `${frame.x},${frame.y},${W},${H}`;
        if (key !== this._frameKey) {
            if (this._frameKey)
                this._moved();
            this._frameKey = key;
        }
        // The holder spans its pane exactly; the pane sits at its top left.
        const [hx, hy] = [frame.x - buf.x - p, frame.y - buf.y - p];
        this._holder.set_position(hx, hy);
        this._holder.set_size(W + 2 * p, H + 2 * p);
        pane.setSources(sources);
        pane.setEdges(edges);
        pane.place(p, p, W, H, [r, r, r, r], frame.x, frame.y);
        pane.show();
        // The rim's strips, in the px of the whole rim (W + 2 rp by H + 2 rp): top and
        // bottom tall enough to hold the rounded corners, the sides a few px into the
        // window. Each reaches rp out past the edge, which the rim mirrors.
        const t = Math.ceil(Math.max(r, 3)) + 2;
        const parts = [[0, 0, W + 2 * rp, rp + t], [0, rp + H - t, W + 2 * rp, rp + t],
            [0, rp + t, rp + 4, H - 2 * t], [rp + W - 4, rp + t, rp + 4, H - 2 * t]];
        // With edge reflections off the rim draws nothing: skip it and its cost.
        const rimOn = (rims[0]._look?.highlight ?? 1) > 0;
        rims.forEach((g, i) => {
            const [ax, ay, aw, ah] = parts[i];
            if (!rimOn || aw < 1 || ah < 1) {
                g.hide();
                g.setSources([]);
                return;
            }
            // Its holder sits on the strip; the pane at the holder's top left.
            this._rimHolders[i].set_position(Math.round(frame.x - buf.x - rp) + ax, Math.round(frame.y - buf.y - rp) + ay);
            this._rimHolders[i].set_size(aw, ah);
            g.setPart(parts[i]);
            g.setSources(sources);
            g.setEdges(edges);
            g.place(rp - ax, rp - ay, W, H, [r, r, r, r], frame.x, frame.y);
            g.show();
        });
        this._syncHolder();
    }

    /**
     * The window is moving or changing size: its glass renders anew every frame, so
     * a kept copy of it would only be one more full-size copy to make each frame (a
     * fifth of a frame on software rendering). Keep none until it has settled.
     */
    _moved() {
        if (!this._holder)
            return;
        for (const h of [this._holder, ...this._rimHolders]) {
            if (h.offscreen_redirect !== 0)
                h.offscreen_redirect = 0;
        }
        if (this._settle)
            GLib.source_remove(this._settle);
        this._settle = GLib.timeout_add(GLib.PRIORITY_DEFAULT, SETTLE_MS, () => {
            this._settle = 0;
            for (const h of this._holder ? [this._holder, ...this._rimHolders] : [])
                h.offscreen_redirect = Clutter.OffscreenRedirect.ALWAYS;
            return GLib.SOURCE_REMOVE;
        });
    }

    // An empty holder would ask for a 0×0 picture: hide it with its pane.
    _syncHolder() {
        this._holder.visible = !!this.pane?.visible;
        this._rimHolders.forEach((h, i) => (h.visible = !!this.rims?.[i]?.visible));
    }

    destroy() {
        if (this._later)
            global.compositor.get_laters().remove(this._later);
        this._later = 0;
        if (this._settle)
            GLib.source_remove(this._settle);
        this._settle = 0;
        this._signals.clear();
        const {pane, rims} = this;
        this.pane = this.rims = null;
        pane?.destroy();
        rims?.forEach(r => r.destroy());
        for (const h of [this._holder, ...this._rimHolders ?? []]) {
            try {
                h?.destroy();
            } catch {}   // gone with the window
        }
        this._holder = null;
        this._rimHolders = [];
        this.owner.forget(this.actor);
    }
}

export class Windows {
    constructor(cfg) {
        this.cfg = cfg;
        this._glass = new Map();
        this._signals = new Signals();
        this._pending = new Set();    // Signals waiting for a new window's first show
        this._signals.on(global.display, 'window-created', (_d, win) => {
            // The actor exists once the window is shown for the first time. Only that
            // first time: a handler kept for the window's whole life would pile up,
            // one per window ever opened, until the glass is turned off.
            const ids = new Signals();
            const done = () => {
                ids.clear();
                this._pending.delete(ids);
            };
            ids.on(win, 'shown', () => {
                done();
                this._add(win.get_compositor_private());
            });
            ids.on(win, 'unmanaged', done);
            this._pending.add(ids);
        });
        global.get_window_actors().forEach(a => this._add(a));
        // A window moved, raised or closed changes what the windows above it show.
        this._onWindows = () => this.sync();
        windowWatch.current?.listeners.add(this._onWindows);
        this._signals.on(global.display, 'notify::focus-window', () => this.sync());
        // A game or video going full screen pauses the glass of the windows it covers.
        this._signals.on(global.display, 'in-fullscreen-changed', () => this.sync());
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

    sync() {
        for (const g of this._glass.values())
            g.queue();
    }

    destroy() {
        windowWatch.current?.listeners.delete(this._onWindows);
        this._signals.clear();
        this._pending.forEach(p => p.clear());
        this._pending.clear();
        for (const g of [...this._glass.values()])
            g.destroy();
        this._glass.clear();
    }
}
