// Glass behind translucent app windows.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Meta from 'gi://Meta';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {SwitcherPopup} from 'resource:///org/gnome/shell/ui/switcherPopup.js';

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
// Frameless Qt apps that draw their own window: a rounded card inside a clear margin
// for their own shadow (RGBeast, Wheelguard). Like Fedora Glass's own window, Mutter
// counts that margin as part of the window, so glass on the window's rectangle drew a
// second, larger frame around the card, plain to see over anything bright. Their glass
// goes on the card itself: the window's rectangle less the margin, with the card's
// corners. Maximized, they drop the margin and the corners.
const CLIENT_CARDS = [
    {app: /^(io\.github\.djshiye\.RGBeast|rgbeast|RGBeast)$/, margin: 14, radius: 15},
    {app: /^(io\.github\.djshiye\.Wheelguard|wheelguard-settings|Wheelguard)$/, margin: 14, radius: 18},
];
const TERMINALS = /^(org\.gnome\.ptyxis|ptyxis|org\.gnome\.console|kgx|gnome-terminal-server|org\.gnome\.terminal)$/i;

// Mutter skips drawing the parts of a window that an opaque window above it covers.
// The glass under the focused window copies the windows below it, and was copied with
// those parts missing whenever it was redrawn as part of the screen: behind a title bar
// that sees through (Slack, Electron apps), the blur then pulled in the wallpaper from
// under the window's solid body, and a glow came and went as the glass redrew (1.5.13).
// Mutter leaves out any window that carries an effect when it works out what is
// covered, so this empty one on the focused window keeps the windows below it whole.
let NoCull = null;    // made on first use
function noCull() {
    NoCull ??= GObject.registerClass({GTypeName: 'FedoraGlassNoCull'}, class NoCull extends Clutter.Effect {});
    return new NoCull();
}
const NO_CULL = 'fedora-glass-no-cull';

function appIds(w) {
    return [w.get_wm_class(), w.get_wm_class_instance(), w.get_gtk_application_id(), w.get_sandboxed_app_id()]
        .filter(id => typeof id === 'string' && id.length);
}

/** The card a frameless app draws inside its window ({margin, radius}), or null. */
export function clientCard(ids) {
    return CLIENT_CARDS.find(c => ids.some(id => c.app.test(id))) ?? null;
}

/**
 * Where the window's glass goes: its frame, or for an app that draws its own card in a
 * shadow margin, the card. {rect, radius}, radius null for the usual corners.
 */
export function glassFrame(frame, card, maximized) {
    const {x, y, width, height} = frame;
    if (!card || maximized)
        return {rect: {x, y, width, height}, radius: null};
    const m = card.margin;
    if (width <= 2 * m + 2 || height <= 2 * m + 2)
        return {rect: {x, y, width, height}, radius: null};
    return {rect: {x: x + m, y: y + m, width: width - 2 * m, height: height - 2 * m}, radius: card.radius};
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

// Glass that can't be seen for this long (the window minimized, on another workspace,
// under a full-screen window or a maximized one) lets go of its pictures. A window's glass
// keeps four of them, each the size of the window: a maximized window's glass held about
// 240 MB on two 1440p screens at 125 %, minimized or not (1.5.17). It is made again, in one
// frame, as soon as the window can be seen.
const DROP_MS = 2000;

// The window lying above `win` on its screen that hides all of it, or null: a full-screen
// window, or a maximized one with its glass showing (its glass under it is opaque).
function coveredBy(win, glassOf, seesWindows) {
    const ws = global.workspace_manager.get_active_workspace();
    const f = win.get_frame_rect();
    let above = false;
    for (const a of global.get_window_actors()) {
        const w = a.meta_window;
        if (w === win) {
            above = true;
            continue;
        }
        if (!above || !w || gone(w) || w.minimized || !a.visible || a.opacity < 255 || !w.located_on_workspace(ws))
            continue;
        // A maximized window whose glass copies the windows behind it (the focused one)
        // shows them through its blur: they are not hidden.
        if (!w.fullscreen && !(isMaximized(w) && glassOf(a)?.shown && !seesWindows(w)))
            continue;
        const r = w.get_frame_rect();
        if (r.x <= f.x + 1 && r.y <= f.y + 1 && r.x + r.width >= f.x + f.width - 1 && r.y + r.height >= f.y + f.height - 1)
            return w;
    }
    return null;
}

// Sources nobody can see through the glass at (x, y, w, h) are left out: a grid of
// CELL px over it, from the top down, marks what the windows above already cover.
// sources: bottom first, {actor, need (the rect it paints), solid (rects it covers fully)}.
const CELL = 48;
export function visibleOnly(sources, x, y, w, h) {
    const nx = Math.max(1, Math.ceil(w / CELL)), ny = Math.max(1, Math.ceil(h / CELL));
    const covered = new Uint8Array(nx * ny);
    const span = (a0, a1, o, n) => [Math.max(0, Math.floor((a0 - o) / CELL)), Math.min(n, Math.ceil((a1 - o) / CELL))];
    const keep = [];
    for (let i = sources.length - 1; i >= 0; i--) {
        const {actor, need, solid} = sources[i];
        const [i0, i1] = span(need.x, need.x + need.width, x, nx);
        const [j0, j1] = span(need.y, need.y + need.height, y, ny);
        let seen = false;
        for (let j = j0; j < j1 && !seen; j++) {
            for (let k = i0; k < i1; k++) {
                if (!covered[j * nx + k]) {
                    seen = true;
                    break;
                }
            }
        }
        if (!seen)
            continue;
        keep.push(actor);
        // The cells lying wholly inside what this one covers (cells on the far edge
        // end at the glass's edge).
        for (const s of solid) {
            const k0 = Math.max(0, Math.ceil((s.x - x) / CELL)), j0s = Math.max(0, Math.ceil((s.y - y) / CELL));
            for (let j = j0s; j < ny; j++) {
                if (Math.min(y + (j + 1) * CELL, y + h) > s.y + s.height)
                    break;
                for (let k = k0; k < nx; k++) {
                    if (Math.min(x + (k + 1) * CELL, x + w) > s.x + s.width)
                        break;
                    covered[j * nx + k] = 1;
                }
            }
        }
    }
    return keep.reverse();
}

class WindowGlass {
    constructor(actor, owner) {
        this.actor = actor;
        this.win = actor.meta_window;
        this.owner = owner;
        this._signals = new Signals();
        this._pieceSignals = new Signals();
        this._later = 0;
        this._drop = 0;
        this._dead = false;
        // The glass under the window's own background (pane), and over it a hairline of
        // the edge's reflection, outside anything the app draws (rims): made when the
        // window can first be seen (see _build), let go of while it can't (see _hide).
        this.pane = null;
        this.rims = null;
        this._holder = null;
        this._rimHolders = [];
        this._frameKey = '';
        this._settle = 0;
        for (const s of ['position-changed', 'size-changed', 'notify::fullscreen', 'notify::minimized',
            'notify::maximized-horizontally', 'notify::maximized-vertically', 'notify::wm-class', 'workspace-changed'])
            this._signals.on(this.win, s, () => this.queue());
        this._signals.on(actor, 'destroy', () => this.destroy());
        // A closing window's actor outlives it while the close animation plays, but
        // Mutter asserts if the window is asked about its monitor once unmanaged.
        this._signals.on(this.win, 'unmanaging', () => this.destroy());
        this.update(owner.cfg.windows);
    }

    /** Whether the glass is on screen now (read by the windows above, see coveredBy). */
    get shown() {
        return !!this.pane?.visible && !!this._holder?.get_parent();
    }

    /**
     * What this window covers fully, as rects on the stage: its glass is opaque, so all
     * of its frame but the rounded corners. Nothing while it is see-through, moving or
     * shows no glass.
     */
    solidRects() {
        const a = this.actor, w = this.win;
        if (!this._shape || !this.shown || gone(w) || a.opacity < 255 || a.scale_x !== 1 || a.scale_y !== 1 ||
            a.translation_x !== 0 || a.translation_y !== 0 || this.pane.opacity < 255 ||
            ['opacity', 'scale-x', 'scale-y', 'translation-x', 'translation-y'].some(t => a.get_transition(t)))
            return [];
        // Where its glass is now (its own _place may not have run yet this frame); the
        // usual corners are the largest it has, so this never claims too much.
        const card = glassFrame(w.get_frame_rect(), clientCard(appIds(w)), isMaximized(w));
        const g = {...card.rect};
        const r = Math.ceil(isMaximized(w) ? 0 : card.radius ?? this.settings.radius ?? 0);
        return [{x: g.x + r, y: g.y, width: g.width - 2 * r, height: g.height},
            {x: g.x, y: g.y + r, width: g.width, height: g.height - 2 * r}].filter(q => q.width > 0 && q.height > 0);
    }

    _build() {
        if (this.pane)
            return;
        this.pane = new GlassPane();
        // Each pane sits in a holder that places it, and keeps its finished glass
        // (GlassPane.setKeep). A window's glass is big, and without that the lens
        // would be drawn again for every frame that repaints the window (a workspace
        // switch, an app streaming text); with it, it is drawn again only when what
        // is behind the window changes. Up to 1.5.18 the holder kept it as an
        // offscreen actor, at twice the screen's size under fractional scaling.
        const holder = p => {
            const h = new Clutter.Actor({name: 'fedora-glass-holder', reactive: false, visible: false});
            h.add_child(p);
            p.setKeep(true);
            return h;
        };
        this._holder = holder(this.pane);
        // The rim only draws along the edge: four thin panes, top, bottom, left and
        // right, each copying and drawing only its own strip (top and bottom hold the
        // rounded corners). Up to 1.5.6 it was one pane the size of the window, shown
        // through four clipped copies; every change behind it then copied the backdrop
        // of the whole window and repainted all of the window, for a 3 px line.
        this.rims = [0, 1, 2, 3].map(() => new GlassPane('rim'));
        this._rimHolders = this.rims.map(holder);
        for (const p of [this.pane, ...this.rims]) {
            this._pieceSignals.on(p, 'destroy', () => {
                // Torn down from outside (the window's actor going away): go with it.
                this._pieceSignals.clear();
                this.destroy();
            });
        }
        this._frameKey = '';
        this._applyLook();
    }

    /** Let go of the glass and its pictures. */
    _release() {
        if (this._drop)
            GLib.source_remove(this._drop);
        this._drop = 0;
        if (this._settle)
            GLib.source_remove(this._settle);
        this._settle = 0;
        this._pieceSignals.clear();
        const {pane, rims} = this;
        const holders = [this._holder, ...this._rimHolders];
        this.pane = this.rims = this._holder = null;
        this._rimHolders = [];
        this._frameKey = '';
        this._shape = null;
        pane?.destroy();
        rims?.forEach(r => r.destroy());
        for (const h of holders) {
            try {
                h?.destroy();
            } catch {}   // gone with the window
        }
    }

    /**
     * Put the glass into the window's actor, or take it out. Out of it while the window
     * is full screen: Mutter shows a full-screen window straight on the screen (direct
     * scanout, and variable refresh rate for games) only while the top child of its
     * actor is the window itself, and the rim, even hidden, sat above it (1.5.17).
     */
    _attach(on) {
        const holders = [this._holder, ...this._rimHolders].filter(Boolean);
        holders.forEach((h, i) => {
            const parent = h.get_parent();
            if (on && !parent) {
                if (i === 0)
                    this.actor.insert_child_at_index(h, 0);
                else
                    this.actor.add_child(h);
            } else if (!on && parent) {
                parent.remove_child(h);
            }
        });
    }

    update(settings) {
        this.settings = settings;
        if (this._dead)
            return;
        this._applyLook();
        // Laters: every window's glass knows the new settings before any of them asks
        // whether a window above still has glass that hides it (see coveredBy).
        this.queue();
    }

    _applyLook() {
        if (!this.pane || !this.settings)
            return;
        const ids = appIds(this.win);
        const term = this.settings.terminalLook && ids.some(id => TERMINALS.test(id));
        const look = term ? this.settings.terminalLook : this.settings.look;
        this.pane.setLook(look);
        this.rims.forEach(r => r.setLook(look));
    }

    /**
     * Why the window shows no glass now: null when it does; 'out' when its glass must
     * also leave its actor (see _attach); 'hidden' when nobody can see it, so the glass
     * may stay where it is until it lets go of its pictures.
     */
    _whyNot() {
        const w = this.win, s = this.settings;
        if (gone(w))
            return 'out';
        if (!s.enabled || w.fullscreen || !WINDOW_TYPES.has(w.get_window_type()))
            return 'out';
        if (underFullscreen(this.actor, w))
            return 'out';
        // A title bar drawn by the Shell is opaque: nothing would show.
        if (typeof w.is_client_decorated === 'function' && w.get_client_type?.() === Meta.WindowClientType.X11 &&
            !w.is_client_decorated())
            return 'out';
        const ids = appIds(w);
        if (ids.some(id => s.skip.includes(id) || NO_GLASS.test(id) || OWN_APP.test(id)))
            return 'out';
        if (w.minimized)
            return 'minimized';
        // The overview, Alt+Tab, the screenshot tool and a touchpad workspace swipe show
        // copies of windows from every workspace, covered ones too: keep their glass.
        if (this.owner.previewing)
            return null;
        // On another workspace, or under a maximized window: the glass stays as it is
        // for a moment (a workspace switch slides the windows out with their glass).
        if (!w.located_on_workspace(global.workspace_manager.get_active_workspace()))
            return 'hidden';
        if (coveredBy(w, a => this.owner.glassOf(a), c => this.owner.seesWindows(c)))
            return 'hidden';
        return null;
    }

    /**
     * What lies behind this window: the wallpaper and the windows below it that it
     * overlaps. Only the focused window sees other windows: each window that does
     * re-renders whenever one below it changes, and with several stacked the cost
     * adds up. The others show the wallpaper, which never changes.
     *
     * Of those, only what can be seen is copied: a window hidden behind windows nearer
     * the top (their glass makes them opaque) is left out. Each window copied is painted
     * again on every render, and during a drag that is every frame: with 20 windows
     * behind, a drag took five times as long a frame as with none (1.5.17).
     */
    _sources(x, y, w, h) {
        const out = [{actor: wallpaper.current?.actor ?? Main.layoutManager._backgroundGroup, need: {x, y, width: w, height: h}, solid: []}];
        if (this.settings.behind !== 'wallpaper' && global.display.focus_window === this.win) {
            const ws = global.workspace_manager.get_active_workspace();
            for (const actor of global.get_window_actors()) {
                if (actor === this.actor)
                    break;     // bottom first: everything after this is above it
                const win = actor.meta_window;
                if (!actor.visible || !win || gone(win) || win.minimized || !win.located_on_workspace(ws))
                    continue;
                const r = win.get_buffer_rect();
                if (r.x < x + w && r.x + r.width > x && r.y < y + h && r.y + r.height > y)
                    out.push({actor, need: r, solid: this.owner.glassOf(actor)?.solidRects() ?? []});
            }
        }
        // Under the panel nothing of this glass is seen: what windows show there doesn't count.
        const wa = this.win.get_work_area_current_monitor();
        const [vx, vy] = [Math.max(x, wa.x), Math.max(y, wa.y)];
        const [vw, vh] = [Math.min(x + w, wa.x + wa.width) - vx, Math.min(y + h, wa.y + wa.height) - vy];
        return vw > 0 && vh > 0 && this._inside(wa) ? visibleOnly(out, vx, vy, vw, vh) : visibleOnly(out, x, y, w, h);
    }

    // Whether the window's frame lies on its screen's work area (not across two screens).
    _inside(wa) {
        const f = this.win.get_frame_rect();
        return f.x >= wa.x - 1 && f.y >= wa.y - 1 && f.x + f.width <= wa.x + wa.width + 1 && f.y + f.height <= wa.y + wa.height + 1;
    }

    queue() {
        if (this._later || this._dead)
            return;
        this._later = global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
            this._later = 0;
            this.sync();
            return GLib.SOURCE_REMOVE;
        });
    }

    /** No glass to see: hide it (or take it out of the actor), and let it go a little later. */
    _hide(why) {
        this._keepBelowWhole(false);
        if (!this.pane)
            return;
        if (why !== 'hidden') {
            this._shape = null;
            for (const p of [this.pane, ...this.rims]) {
                p.hide();
                p.setSources([]);
            }
            this._syncHolder();
        }
        if (why === 'out')
            this._attach(false);
        if (!this._drop) {
            this._drop = GLib.timeout_add(GLib.PRIORITY_DEFAULT, DROP_MS, () => {
                this._drop = 0;
                // Still out of sight? Let go of the pictures; otherwise keep them.
                if (!this._dead && this._whyNot())
                    this._release();
                return GLib.SOURCE_REMOVE;
            });
        }
    }

    sync() {
        if (this._dead)
            return;
        // A closing window drops its glass on 'unmanaging'; one that has briefly lost
        // its monitor (a screen unplugged) just shows none until it has one again.
        const why = this._whyNot();
        if (why) {
            this._hide(why);
            if (why === 'hidden' && this.pane && this.pane.visible)
                this._place();   // as it was: it may still slide past during a workspace switch
            return;
        }
        if (this._drop)
            GLib.source_remove(this._drop);
        this._drop = 0;
        this._build();
        this._attach(true);
        this._place();
    }

    _place() {
        const {pane, rims} = this;
        const w = this.win;
        const card = glassFrame(w.get_frame_rect(), clientCard(appIds(w)), isMaximized(w));
        const frame = card.rect;
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
        const r = snapped ? 0 : card.radius ?? this.settings.radius;
        const p = pane.pad;
        const rp = rims[0].pad;
        const q = Math.max(p, rp);
        const sources = this._sources(frame.x - q, frame.y - q, frame.width + 2 * q, frame.height + 2 * q);
        const [W, H] = [frame.width, frame.height];
        this._shape = {x: frame.x, y: frame.y, width: W, height: H, r};
        const key = `${frame.x},${frame.y},${W},${H}`;
        const moved = key !== this._frameKey;
        if (moved) {
            if (this._frameKey)
                this._moved();
            this._frameKey = key;
        }
        // The holder spans its pane exactly; the pane sits at its top left.
        const [hx, hy] = [frame.x - buf.x - p, frame.y - buf.y - p];
        this._holder.set_position(hx, hy);
        this._holder.set_size(W + 2 * p, H + 2 * p);
        this._keepBelowWhole(sources.some(s => s.meta_window));
        // Restacked only when the window itself moved or changed size: this runs for
        // every window on every frame of any window's drag, and each restack makes the
        // pane lay out and render again, though nothing behind it changed.
        pane.setSources(sources, moved);
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
            g.setSources(sources, moved);
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
        if (!this.pane)
            return;
        for (const p of [this.pane, ...this.rims])
            p.setKeep(false);
        if (this._settle)
            GLib.source_remove(this._settle);
        this._settle = GLib.timeout_add(GLib.PRIORITY_DEFAULT, SETTLE_MS, () => {
            this._settle = 0;
            for (const p of this.pane ? [this.pane, ...this.rims] : [])
                p.setKeep(true);
            return GLib.SOURCE_REMOVE;
        });
    }

    /** Windows below this one are drawn whole, also where it covers them (see NoCull). */
    _keepBelowWhole(on) {
        const has = !!this.actor.get_effect(NO_CULL);
        if (on && !has)
            this.actor.add_effect_with_name(NO_CULL, noCull());
        else if (!on && has)
            this.actor.remove_effect_by_name(NO_CULL);
    }

    // An empty holder would ask for a 0×0 picture: hide it with its pane.
    _syncHolder() {
        if (!this._holder)
            return;
        this._holder.visible = !!this.pane?.visible;
        this._rimHolders.forEach((h, i) => (h.visible = !!this.rims?.[i]?.visible));
    }

    destroy() {
        if (this._dead)
            return;
        this._dead = true;
        if (this._later)
            global.compositor.get_laters().remove(this._later);
        this._later = 0;
        this._signals.clear();
        try {
            this._keepBelowWhole(false);
        } catch {}   // the window's actor is already gone
        this._release();
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
        // Glass let go of on another workspace is made again as that workspace comes in.
        this._signals.on(global.workspace_manager, 'active-workspace-changed', () => this.sync());
        // ...and for anything that shows copies of windows (see WindowGlass._whyNot).
        this.previewing = false;
        this._previews = new Set();
        const preview = (key, on) => {
            if (on)
                this._previews.add(key);
            else
                this._previews.delete(key);
            const now = this._previews.size > 0;
            if (now !== this.previewing) {
                this.previewing = now;
                this.sync();
            }
        };
        this._signals.on(Main.overview, 'showing', () => preview('overview', true));
        this._signals.on(Main.overview, 'hidden', () => preview('overview', false));
        if (Main.screenshotUI)
            this._signals.on(Main.screenshotUI, 'notify::visible', () => preview('screenshot', Main.screenshotUI.visible));
        this._signals.on(Main.uiGroup, 'child-added', (_g, c) => c instanceof SwitcherPopup && preview(c, true));
        this._signals.on(Main.uiGroup, 'child-removed', (_g, c) => preview(c, false));
        const swipe = Main.wm?._workspaceAnimation?._swipeTracker;
        if (swipe) {
            this._signals.on(swipe, 'begin', () => preview('swipe', true));
            this._signals.on(swipe, 'end', () => preview('swipe', false));
        }
    }

    _add(actor) {
        if (!actor || this._glass.has(actor) || !actor.meta_window)
            return;
        this._glass.set(actor, new WindowGlass(actor, this));
    }

    forget(actor) {
        this._glass.delete(actor);
    }

    /** Whether this window's glass copies the windows behind it (see WindowGlass._sources). */
    seesWindows(win) {
        return this.cfg.windows?.behind !== 'wallpaper' && global.display.focus_window === win;
    }

    /** The glass of a window actor, if it has any. */
    glassOf(actor) {
        return this._glass.get(actor) ?? null;
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
