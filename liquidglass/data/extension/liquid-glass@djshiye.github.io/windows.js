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

class WindowGlass {
    constructor(actor, owner) {
        this.actor = actor;
        this.win = actor.meta_window;
        this.owner = owner;
        // The glass under the window's own background, and over it a hairline of the
        // edge's reflection, outside anything the app draws.
        this.pane = new GlassPane();
        this.rim = new GlassPane('rim');
        this._signals = new Signals();
        this._later = 0;
        // Each pane sits in a holder that keeps its finished picture. A window's glass
        // is big, and without it the lens would be drawn again for every frame that
        // repaints the window (the overview opening, a workspace switch); with it, it
        // is drawn again only when what is behind the window changes.
        this._holders = [this.pane, this.rim].map(p => {
            const h = new Clutter.Actor({name: 'liquid-glass-holder', reactive: false, visible: false,
                offscreen_redirect: Clutter.OffscreenRedirect.ALWAYS});
            h.add_child(p);
            return h;
        });
        actor.insert_child_at_index(this._holders[0], 0);
        // The rim only draws along the edge, so only four thin strips of its picture
        // are shown (copies clipped to each side); the holder itself stays unseen.
        actor.add_child(this._holders[1]);
        this._holders[1].opacity = 0;
        this._strips = [0, 1, 2, 3].map(() => {
            const c = new Clutter.Clone({source: this._holders[1], name: 'liquid-glass-rim-strip', reactive: false});
            actor.add_child(c);
            return c;
        });
        for (const s of ['position-changed', 'size-changed', 'notify::fullscreen', 'notify::minimized',
            'notify::maximized-horizontally', 'notify::maximized-vertically', 'notify::wm-class'])
            this._signals.on(this.win, s, () => this.queue());
        this._signals.on(actor, 'destroy', () => this.destroy());
        // A closing window's actor outlives it while the close animation plays, but
        // Mutter asserts if the window is asked about its monitor once unmanaged.
        this._signals.on(this.win, 'unmanaging', () => this.destroy());
        for (const k of ['pane', 'rim']) {
            this._signals.on(this[k], 'destroy', () => {
                this[k] = null;
                this.destroy();
            });
        }
        this.update(owner.cfg.windows);
    }

    update(settings) {
        this.settings = settings;
        if (!this.pane || !this.rim)
            return;
        const ids = appIds(this.win);
        const term = settings.terminalLook && ids.some(id => TERMINALS.test(id));
        const look = term ? settings.terminalLook : settings.look;
        this.pane.setLook(look);
        this.rim.setLook(look);
        this.sync();
    }

    _wanted() {
        const w = this.win, s = this.settings;
        if (!s.enabled || w.fullscreen || w.minimized || !WINDOW_TYPES.has(w.get_window_type()))
            return false;
        // A title bar drawn by the Shell is opaque: nothing would show.
        if (typeof w.is_client_decorated === 'function' && w.get_client_type?.() === Meta.WindowClientType.X11 &&
            !w.is_client_decorated())
            return false;
        const ids = appIds(w);
        return !ids.some(id => s.skip.includes(id) || NO_GLASS.test(id));
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
        if (this._later || !this.pane || !this.rim)
            return;
        this._later = global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
            this._later = 0;
            this.sync();
            return GLib.SOURCE_REMOVE;
        });
    }

    sync() {
        const {pane, rim} = this;
        if (!pane || !rim)
            return;
        // A closing window drops its glass on 'unmanaging'; one that has briefly lost
        // its monitor (a screen unplugged) just shows none until it has one again.
        if (gone(this.win) || !this._wanted()) {
            for (const p of [pane, rim]) {
                p.hide();
                p.setSources([]);
            }
            this._syncHolders();
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
        const p = Math.max(pane.pad, rim.pad);
        const sources = this._sources(frame.x - p, frame.y - p, frame.width + 2 * p, frame.height + 2 * p);
        // With edge reflections off the rim draws nothing: skip it and its cost.
        const rimOn = (rim._look?.highlight ?? 1) > 0;
        if (!rimOn) {
            rim.hide();
            rim.setSources([]);
        }
        // Each holder spans its pane exactly; the pane sits at its top left.
        const [hx, hy] = [frame.x - buf.x - p, frame.y - buf.y - p];
        const [hw, hh] = [frame.width + 2 * p, frame.height + 2 * p];
        this._holders.forEach(h => {
            h.set_position(hx, hy);
            h.set_size(hw, hh);
        });
        for (const g of rimOn ? [pane, rim] : [pane]) {
            g.setSources(sources);
            g.setEdges(edges);
            g.place(p, p, frame.width, frame.height, [r, r, r, r], frame.x, frame.y);
            g.set_position(Math.round(p - g.pad), Math.round(p - g.pad));
            g.show();
        }
        // Strips: top and bottom tall enough to hold the rounded corners.
        const t = Math.ceil(Math.max(r, 3)) + 2, [W, H] = [frame.width, frame.height];
        const clips = [[p - 2, p - 2, W + 4, t + 2], [p - 2, p + H - t, W + 4, t + 2],
            [p - 2, p + t, 6, H - 2 * t], [p + W - 4, p + t, 6, H - 2 * t]];
        this._strips.forEach((c, i) => {
            c.set_position(hx, hy);
            c.set_size(hw, hh);
            c.set_clip(...clips[i]);
        });
        this._syncHolders();
    }

    // An empty holder would ask for a 0×0 picture: hide it with its pane.
    _syncHolders() {
        this._holders.forEach((h, i) => (h.visible = !!(i ? this.rim : this.pane)?.visible));
        const rimShown = this._holders[1]?.visible ?? false;
        this._strips.forEach(c => (c.visible = rimShown));
    }

    destroy() {
        if (this._later)
            global.compositor.get_laters().remove(this._later);
        this._later = 0;
        this._signals.clear();
        const {pane, rim} = this;
        this.pane = this.rim = null;
        pane?.destroy();
        rim?.destroy();
        for (const h of [...this._strips, ...this._holders]) {
            try {
                h.destroy();
            } catch {}   // gone with the window
        }
        this._holders = this._strips = [];
        this.owner.forget(this.actor);
    }
}

export class Windows {
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
        // A window moved, raised or closed changes what the windows above it show.
        this._onWindows = () => this.sync();
        windowWatch.current?.listeners.add(this._onWindows);
        this._signals.on(global.display, 'notify::focus-window', () => this.sync());
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
        this._pending.clear();
        for (const g of [...this._glass.values()])
            g.destroy();
        this._glass.clear();
    }
}
