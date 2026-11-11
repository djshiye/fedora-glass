// Glass behind translucent app windows.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Meta from 'gi://Meta';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {SwitcherPopup} from 'resource:///org/gnome/shell/ui/switcherPopup.js';

import {GlassPane, copying} from './glass.js';
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

/**
 * Whether an app's windows get no glass: one the user listed in the Fedora Glass app
 * (skip, from shell-glass.json: desktop ids, WM classes, app ids), a built-in game or
 * video player, or Fedora Glass itself. ids: the window's, as appIds gives them.
 */
export function withoutGlass(ids, skip) {
    return ids.some(id => skip.includes(id) || NO_GLASS.test(id) || OWN_APP.test(id));
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

// The rect r less its four r×r corners, as two bands that cross: all it covers fully
// with rounded corners of radius r.
function bands(g, r) {
    return [{x: g.x + r, y: g.y, width: g.width - 2 * r, height: g.height},
        {x: g.x, y: g.y + r, width: g.width, height: g.height - 2 * r}].filter(q => q.width > 0 && q.height > 0);
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

// What is left of the rect r once the rects in `cover` are taken out of it, as rects
// that don't overlap; null when that would take more than `max` of them (not worth
// working out).
export function uncovered(r, cover, max = 64) {
    let left = r.width > 0 && r.height > 0 ? [r] : [];
    for (const c of cover) {
        if (!left.length)
            break;
        const next = [];
        for (const p of left) {
            const [px1, py1, cx1, cy1] = [p.x + p.width, p.y + p.height, c.x + c.width, c.y + c.height];
            if (c.width <= 0 || c.height <= 0 || c.x >= px1 || cx1 <= p.x || c.y >= py1 || cy1 <= p.y) {
                next.push(p);
                continue;
            }
            // The bands above and below c, then the parts left and right of it between them.
            if (c.y > p.y)
                next.push({x: p.x, y: p.y, width: p.width, height: c.y - p.y});
            if (cy1 < py1)
                next.push({x: p.x, y: cy1, width: p.width, height: py1 - cy1});
            const [y0, y1] = [Math.max(p.y, c.y), Math.min(py1, cy1)];
            if (c.x > p.x)
                next.push({x: p.x, y: y0, width: c.x - p.x, height: y1 - y0});
            if (cx1 < px1)
                next.push({x: cx1, y: y0, width: px1 - cx1, height: y1 - y0});
        }
        if (next.length > max)
            return null;
        left = next;
    }
    return left;
}

// Whether the windows lying above `win` on its screen hide all of it, together: full-screen
// windows, and windows whose glass is opaque (see WindowGlass.covers). Up to 1.5.22 only one
// full-screen or maximized window counted, so a window under a few others kept its glass,
// and was drawn under them, though nobody could see any of it.
function coveredBy(win, glassOf) {
    const ws = global.workspace_manager.get_active_workspace();
    const f = win.get_frame_rect();
    // A px of slack all round: a maximized window may sit a px off its screen's edge.
    const r = {x: f.x + 1, y: f.y + 1, width: f.width - 2, height: f.height - 2};
    if (r.width <= 0 || r.height <= 0)
        return false;
    const cover = [];
    let above = false;
    for (const a of global.get_window_actors()) {
        const w = a.meta_window;
        if (w === win) {
            above = true;
            continue;
        }
        if (!above || !w || gone(w) || w.minimized || !a.visible || a.opacity < 255 || !w.located_on_workspace(ws))
            continue;
        if (w.fullscreen)
            cover.push(w.get_frame_rect());
        else
            cover.push(...glassOf(a)?.covers() ?? []);
    }
    return cover.length > 0 && uncovered(r, cover)?.length === 0;
}

// Rects next to each other that make one rect together, as that one rect (uncovered cuts
// what is left into more pieces than it needs).
export function joined(rects) {
    const out = rects.map(q => ({...q}));
    for (let again = true; again;) {
        again = false;
        for (let i = 0; i < out.length && !again; i++) {
            for (let j = i + 1; j < out.length; j++) {
                const [a, b] = [out[i], out[j]];
                const below = a.x === b.x && a.width === b.width && (a.y + a.height === b.y || b.y + b.height === a.y);
                const beside = a.y === b.y && a.height === b.height && (a.x + a.width === b.x || b.x + b.width === a.x);
                if (!below && !beside)
                    continue;
                out[i] = {x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), width: below ? a.width : a.width + b.width,
                    height: below ? a.height + b.height : a.height};
                out.splice(j, 1);
                again = true;
                break;
            }
        }
    }
    return out;
}
// Each part drawn on its own draws the glass once more (a little work for the Shell), so
// more parts than this are drawn as up to this many strips across, each the rect around
// what shows of it.
const MAX_PARTS = 8;
export function fewParts(parts, r) {
    if (parts.length <= MAX_PARTS)
        return parts;
    const out = [];
    for (let i = 0; i < MAX_PARTS; i++) {
        const y0 = r.y + Math.floor(r.height * i / MAX_PARTS), y1 = r.y + Math.floor(r.height * (i + 1) / MAX_PARTS);
        let [x1, x2, t, b] = [Infinity, -Infinity, Infinity, -Infinity];
        for (const q of parts) {
            const [qt, qb] = [Math.max(q.y, y0), Math.min(q.y + q.height, y1)];
            if (qb <= qt)
                continue;
            [x1, x2, t, b] = [Math.min(x1, q.x), Math.max(x2, q.x + q.width), Math.min(t, qt), Math.max(b, qb)];
        }
        if (x2 > x1)
            out.push({x: x1, y: t, width: x2 - x1, height: b - t});
    }
    return out;
}

// Whether the actor is drawn where it lies, as it is: not scaled, moved or turned.
function plain(a) {
    return a.scale_x === 1 && a.scale_y === 1 && a.translation_x === 0 && a.translation_y === 0 &&
        a.rotation_angle_x === 0 && a.rotation_angle_y === 0 && a.rotation_angle_z === 0;
}

// The holder of a piece of a window's glass (see WindowGlass._build). Drawn on the screen,
// it leaves out what the opaque glass of windows above covers (see WindowGlass._paintBox),
// and so it does in the glass of the focused window, which copies the windows behind it
// in their order: a window dragged over 20 others drew all of their glass, under its own
// and again for each of the five pieces of its own glass, every frame (1.5.22). Anyone
// else's copy of the window (Alt+Tab, the overview, Dash to Panel's previews) and a
// picture of it (a window screenshot) still get all of it.
let Holder = null;     // made on first use
function holder() {
    Holder ??= GObject.registerClass({GTypeName: 'FedoraGlassHolder'}, class Holder extends Clutter.Actor {
        vfunc_paint(ctx) {
            let box = null;
            try {
                box = this._glass?._paintBox(this, ctx) ?? null;
            } catch {
                box = null;   // draw it all rather than not at all
            }
            if (box === false)
                return;
            if (!box) {
                super.vfunc_paint(ctx);
                return;
            }
            // Each part that shows, on its own: they never overlap, so nothing is drawn twice.
            const fb = ctx.get_framebuffer();
            for (const b of box) {
                fb.push_rectangle_clip(...b);
                try {
                    super.vfunc_paint(ctx);
                } finally {
                    fb.pop_clip();
                }
            }
        }
    });
    return new Holder({name: 'fedora-glass-holder', reactive: false, visible: false});
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
        this._ids = null;          // the app's ids (see appIds)
        this._coverKey = '';       // what it hid from the windows below when last asked (see _noteCover)
        this._coverRect = null;
        this.frame = null;         // its frame when last seen (see Windows._changed)
        for (const s of ['position-changed', 'size-changed', 'notify::fullscreen', 'notify::minimized',
            'notify::maximized-horizontally', 'notify::maximized-vertically', 'workspace-changed'])
            this._signals.on(this.win, s, () => this.queue());
        for (const s of ['notify::wm-class', 'notify::gtk-application-id']) {
            this._signals.on(this.win, s, () => {
                this._ids = null;
                this._applyLook();
                this.queue();
            });
        }
        this._signals.on(actor, 'destroy', () => this.destroy());
        // A closing window's actor outlives it while the close animation plays, but
        // Mutter asserts if the window is asked about its monitor once unmanaged.
        this._signals.on(this.win, 'unmanaging', () => this.destroy());
        this.update(owner.cfg.windows);
    }

    /**
     * The app's ids (WM class, its instance, application id, sandboxed app id). Asked for
     * on every sync, and each is a call into Mutter: kept until the window says one changed.
     */
    appIds() {
        this._ids ??= appIds(this.win);
        return this._ids;
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
        const card = glassFrame(w.get_frame_rect(), clientCard(this.appIds()), isMaximized(w));
        const r = Math.ceil(isMaximized(w) ? 0 : card.radius ?? this.settings.radius ?? 0);
        return bands(card.rect, r);
    }

    /**
     * What this window hides from the windows below it (see coveredBy): what its glass
     * covers fully, but nothing while it copies the windows behind it (the focused one:
     * they show through its blur) or while it moves (it would hide and show them again
     * on every step).
     */
    covers() {
        if (this._settle || this.owner.seesWindows(this.win))
            return [];
        return this.solidRects();
    }

    /**
     * What its glass covers while it is drawn (see Holder), from its actor's top left:
     * where its pane is now, all but the rounded corners. Nothing while it is see-through,
     * moved, turned or drawn through an effect (another extension's animation).
     */
    paintCover() {
        const a = this.actor, s = this._shape;
        if (!s || !this.shown || a.opacity < 255 || this.pane.opacity < 255 || !plain(a) ||
            a.get_effects().some(e => e !== a.get_effect(NO_CULL)))
            return [];
        const p = this.pane.pad;
        return bands({x: this._holder.x + p, y: this._holder.y + p, width: s.width, height: s.height},
            Math.ceil(s.r ?? 0));
    }

    /**
     * The parts of holder h to draw, in its own px: [[x1, y1, x2, y2], ...], which never
     * overlap; null for all of it, false for none (the opaque glass of the windows above
     * covers it all). On the screen,
     * all windows above count; in our own copy of this window (glass that shows the
     * windows behind it), those it draws over this one; in anyone else's copy, or in a
     * picture of the window (it has no redraw area), none do.
     */
    _paintBox(h, ctx) {
        if (!plain(this.actor))
            return null;
        let pane = null, at = this.actor;
        if (h.is_in_clone_paint()) {
            // In a pane, each window is drawn where its copy lies (see GlassPane._syncClones).
            // A window the pane doesn't copy itself is in someone else's copy (the overview's,
            // which the pane copies while the overview is open).
            at = copying.pane?._clones?.get(this.actor);
            if (!at)
                return null;
            pane = copying.pane;
        } else if (!ctx.get_redraw_clip()) {
            return null;
        }
        const [ox, oy] = [at.x + h.x, at.y + h.y];
        let r = {x: ox, y: oy, width: h.width, height: h.height};
        // A copy draws only what lies inside its pane (see GlassPane._clipClone), but Clutter
        // still draws all of the window for it: the rim's strips each drew every piece of
        // every window's glass behind them, nearly all of it outside the strip.
        const cb = pane ? at._clipBox : null;
        if (cb) {
            const [x1, y1] = [Math.max(r.x, at.x + cb[0]), Math.max(r.y, at.y + cb[1])];
            const [x2, y2] = [Math.min(r.x + r.width, at.x + cb[0] + cb[2]), Math.min(r.y + r.height, at.y + cb[1] + cb[3])];
            if (x2 <= x1 || y2 <= y1) {
                this.owner.paintStats.skipped++;
                return false;
            }
            r = {x: x1, y: y1, width: x2 - x1, height: y2 - y1};
        }
        const cover = this.owner.coverAbove(this.actor, pane) ?? [];
        const left = uncovered(r, cover);
        if (!left)
            return null;
        if (!left.length) {
            this.owner.paintStats.skipped++;
            return false;
        }
        const parts = fewParts(joined(left), r);
        if (parts.length === 1 && parts[0].x <= ox && parts[0].y <= oy &&
            parts[0].x + parts[0].width >= ox + h.width && parts[0].y + parts[0].height >= oy + h.height)
            return null;
        this.owner.paintStats.clipped++;
        return parts.map(q => [q.x - ox, q.y - oy, q.x + q.width - ox, q.y + q.height - oy]);
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
        const hold = p => {
            const h = holder();
            h._glass = this;
            h.add_child(p);
            p.setKeep(true);
            return h;
        };
        this._holder = hold(this.pane);
        // The rim only draws along the edge: four thin panes, top, bottom, left and
        // right, each copying and drawing only its own strip (top and bottom hold the
        // rounded corners). Up to 1.5.6 it was one pane the size of the window, shown
        // through four clipped copies; every change behind it then copied the backdrop
        // of the whole window and repainted all of the window, for a 3 px line.
        this.rims = [0, 1, 2, 3].map(() => new GlassPane('rim'));
        this._rimHolders = this.rims.map(hold);
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
            if (h)
                h._glass = null;
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
        const ids = this.appIds();
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
        const ids = this.appIds();
        if (withoutGlass(ids, s.skip))
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
        if (coveredBy(w, a => this.owner.glassOf(a)))
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
        } else {
            if (this._drop)
                GLib.source_remove(this._drop);
            this._drop = 0;
            this._build();
            this._attach(true);
            this._place();
        }
        this._noteCover(true);
    }

    /**
     * What this window hides from the windows below may have changed (its glass came or
     * went, it settled after moving): those it hid or hides now look again. `now`: from
     * inside a sync, where a sync queued would wait for the next frame.
     */
    _noteCover(now) {
        const rects = this._dead || gone(this.win) || this.win.minimized || !this.actor.visible ? [] : this.covers();
        const key = rects.map(q => `${q.x},${q.y},${q.width},${q.height}`).join(' ');
        if (key === this._coverKey)
            return;
        const was = this._coverRect;
        this._coverKey = key;
        this._coverRect = rects.length ? this.win.get_frame_rect() : null;
        this.owner.belowChanged(this, [was, this._coverRect], now);
    }

    _place() {
        const {pane, rims} = this;
        const w = this.win;
        const card = glassFrame(w.get_frame_rect(), clientCard(this.appIds()), isMaximized(w));
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
            // Settled: it hides the windows below again (see covers).
            if (!this._dead)
                this._noteCover(false);
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
        // Drawn on the screen, each piece of glass leaves out what the windows above cover
        // (see WindowGlass._paintBox): worked out once a frame.
        this._stack = null;
        this.paintStats = {clipped: 0, skipped: 0};    // read by the QA tools
        this._afterPaint = global.stage.connect('after-paint', () => (this._stack = null));
        // A window moved, raised or closed changes what the windows above it show.
        this._onWindows = win => (win ? this._changed(win) : this.sync());
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

    /**
     * One window moved, changed size, or was minimized or hidden. Up to 1.5.22 every
     * window's glass then worked out again whether it could be seen and what lay behind
     * it, each asking about every other window: for each step of a drag, with 20 windows
     * open, a few thousand calls into Mutter. Only these can change: the window itself,
     * the focused window (its glass shows the windows behind it), and the windows below
     * that it hid before or hides now (see coveredBy).
     */
    _changed(win) {
        let g = null;
        for (const x of this._glass.values()) {
            if (x.win === win)
                g = x;
        }
        if (!g || g._dead || gone(win)) {
            this.sync();
            return;
        }
        g.queue();
        const focus = global.display.focus_window;
        for (const x of this._glass.values()) {
            if (x.win === focus)
                x.queue();
        }
        const was = g.frame;
        g.frame = win.get_frame_rect();
        if (g._coverKey)
            this.belowChanged(g, [was, g._coverRect, g.frame], false);
    }

    /** The windows below g's that lie in any of rects look again whether they can be seen. */
    belowChanged(g, rects, now) {
        rects = rects.filter(Boolean);
        if (!rects.length)
            return;
        for (const a of global.get_window_actors()) {
            if (a === g.actor)
                break;     // bottom first: the rest are above it
            const x = this._glass.get(a);
            if (!x || x._dead || gone(x.win))
                continue;
            const f = x.win.get_frame_rect();
            if (!rects.some(r => r.x < f.x + f.width && r.x + r.width > f.x && r.y < f.y + f.height && r.y + r.height > f.y))
                continue;
            if (now)
                x.sync();
            else
                x.queue();
        }
    }

    /**
     * What the opaque glass of the windows above `actor` covers this frame (see
     * WindowGlass.paintCover), or null when it has none. With `pane`: only of the windows
     * that pane copies, which it draws over this one (see GlassPane.setSources).
     */
    coverAbove(actor, pane = null) {
        if (!this._stack) {
            const list = global.get_window_actors().map(a => ({actor: a, parent: a.get_parent(), rects: null}));
            this._stack = {list, index: new Map(list.map((e, i) => [e.actor, i])), above: new Map()};
        }
        const st = this._stack;
        const i = st.index.get(actor);
        if (i === undefined)
            return null;
        let memo = st.above.get(pane);
        if (!memo)
            st.above.set(pane, memo = new Map());
        let out = memo.get(i);
        if (out)
            return out;
        out = [];
        const parent = st.list[i].parent;
        for (let j = i + 1; j < st.list.length; j++) {
            const e = st.list[j];
            // On the screen a window is drawn where its actor is; in a pane, where its copy is.
            const at = pane ? pane._clones?.get(e.actor) : e.actor;
            if (!at?.visible || (!pane && e.parent !== parent))
                continue;
            e.rects ??= this._glass.get(e.actor)?.paintCover() ?? [];
            const [x, y] = [at.x, at.y];
            for (const q of e.rects)
                out.push({x: q.x + x, y: q.y + y, width: q.width, height: q.height});
        }
        memo.set(i, out);
        return out;
    }

    destroy() {
        if (this._afterPaint)
            global.stage.disconnect(this._afterPaint);
        this._afterPaint = 0;
        this._stack = null;
        windowWatch.current?.listeners.delete(this._onWindows);
        this._signals.clear();
        this._pending.forEach(p => p.clear());
        this._pending.clear();
        for (const g of [...this._glass.values()])
            g.destroy();
        this._glass.clear();
    }
}
