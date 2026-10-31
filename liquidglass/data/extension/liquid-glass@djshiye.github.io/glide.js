// One hover highlight per Dash to Panel taskbar that glides from icon to icon.
//
// Dash to Panel paints a separate highlight on each hovered icon, so moving along
// the taskbar makes highlights blink on and off. Here one soft tile lives in each
// panel instead: it fades in under the first icon the pointer reaches, follows
// the pointer from icon to icon on a spring, and fades out when the pointer leaves
// the taskbar. Dash to Panel's own hover colour is set to clear while this runs
// (the app does that), so there is never a second highlight.
//
// The tile is a child of the Dash to Panel panel actor, under its icons and over
// its background. That panel does not always lay out extra children, so the tile
// gives itself its allocation (a box at 0,0 of its size) and is moved with translations:
// moving it costs a redraw and nothing else, and it stays shown at opacity 0 when
// idle, so showing and hiding never asks the panel for a layout. Nothing runs while the pointer is
// still: steps are scheduled before the next redraw only while a tile is moving.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';

import {Signals} from './common.js';
import {springStep as spring} from './curves.js';

const FADE_IN_MS = 120;
const FADE_OUT_MS = 200;
const LEAVE_GRACE_MS = 90;     // crossing the gap between two icons is not leaving
const STIFFNESS = 700;         // with DAMPING: a glide that settles in about 250 ms, ~1% overshoot
const DAMPING = 46;

function animationsOn() {
    return St.Settings.get().enable_animations;
}

function panels() {
    const dtp = global.dashToPanel?.panels;
    return Array.isArray(dtp) ? dtp : [];
}

function iconsOf(panel) {
    try {
        return panel.taskbar?._getAppIcons?.() ?? [];
    } catch {
        return [];
    }
}

// What Dash to Panel would have highlighted: the icon's container.
function highlightOf(icon) {
    return icon._container ?? icon;
}

class Tile {
    constructor(panel, look) {
        this.panel = panel;
        this.actor = new St.Widget({
            name: 'liquid-glass-hover-glide',
            reactive: false,
            x_expand: false,
            y_expand: false,
            x_align: Clutter.ActorAlign.START,
            y_align: Clutter.ActorAlign.START,
            opacity: 0,
        });
        this.size = [0, 0];
        this.allocLater = 0;
        // Anything that asks for a new layout (a style change, a theme change)
        // would leave it unallocated: give it its box again before the next frame.
        this.relayoutId = this.actor.connect('queue-relayout', () => this.queueAllocate());
        this.restyle(look);
        // Under the icons (this.panel) and over the panel's own background.
        panel.insert_child_at_index(this.actor, 0);
        this.allocate();
        this.pos = null;           // [x, y, w, h] now, in the panel's coordinates
        this.vel = [0, 0, 0, 0];
        this.goal = null;
        this.icon = null;          // the icon under the pointer, or null
        this.alpha = 0;            // 0..1, the fade
        this.alphaTo = 0;
        this.leaveId = 0;
        this.goneId = 0;
        this.gone = false;
    }

    restyle(look) {
        this.actor.set_style(`background-color: ${look.color}; border-radius: ${look.radius}px;`);
    }

    // Its size is also set as its natural size: when the panel does lay out its
    // children (its BinLayout), the tile then gets the same box at 0,0.
    allocate() {
        if (this.gone)
            return;
        const [w, h] = this.size;
        if (this.actor.width !== w || this.actor.height !== h)
            this.actor.set_size(w, h);
        this.actor.allocate(new Clutter.ActorBox({x1: 0, y1: 0, x2: w, y2: h}));
    }

    queueAllocate() {
        if (this.allocLater || this.gone)
            return;
        this.allocLater = global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
            this.allocLater = 0;
            this.allocate();
            return GLib.SOURCE_REMOVE;
        });
    }

    // Where the tile goes for `icon`, or null if that cannot be known now.
    target(icon) {
        const a = highlightOf(icon);
        if (!a?.get_stage?.() || !a.mapped)
            return null;
        const [sx, sy] = a.get_transformed_position();
        const [w, h] = a.get_transformed_size();
        const [ok, x, y] = this.panel.transform_stage_point(sx, sy);
        if (!ok || ![x, y, w, h].every(Number.isFinite) || w < 2 || h < 2)
            return null;
        return [x, y, w, h];
    }

    destroy() {
        if (this.leaveId)
            GLib.source_remove(this.leaveId);
        this.leaveId = 0;
        if (this.allocLater)
            global.compositor.get_laters().remove(this.allocLater);
        this.allocLater = 0;
        if (this.goneId)
            this.panel.disconnect(this.goneId);
        this.goneId = 0;
        if (this.relayoutId && !this.gone)
            this.actor.disconnect(this.relayoutId);
        this.relayoutId = 0;
        if (!this.gone)
            this.actor.destroy();
        this.gone = true;
    }
}

export class HoverGlide {
    constructor() {
        this._look = {enabled: false, color: 'rgba(255,255,255,0.08)', radius: 8};
        this._tiles = new Map();      // panel -> Tile
        this._watched = new Map();    // icon -> {signals, panel}
        this._signals = new Signals();
        this._later = 0;
        this._last = 0;
        this._refreshId = 0;
        this._settings = St.Settings.get();
        this._animId = this._settings.connect('notify::enable-animations', () => this.settle());
    }

    update(look) {
        const was = this._look.enabled;
        this._look = look;
        if (!look.enabled) {
            this._teardown();
            return;
        }
        for (const t of this._tiles.values())
            t.restyle(look);
        if (!was)
            this._connectSources();
        this._refresh();
    }

    _connectSources() {
        if (global.dashToPanel?.connect)
            this._signals.on(global.dashToPanel, 'panels-created', () => this._queueRefresh());
        // Taskbar icons come and go with apps.
        this._signals.on(Shell.AppSystem.get_default(), 'installed-changed', () => this._queueRefresh());
        this._signals.on(Shell.WindowTracker.get_default(), 'tracked-windows-changed', () => this._queueRefresh());
    }

    _queueRefresh() {
        if (this._refreshId)
            return;
        this._refreshId = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this._refreshId = 0;
            if (this._look.enabled)
                this._refresh();
            return GLib.SOURCE_REMOVE;
        });
    }

    // Match the tiles to the panels, and the watched icons to the taskbars.
    _refresh() {
        const live = panels().filter(p => p instanceof Clutter.Actor);
        for (const [panel, tile] of [...this._tiles]) {
            if (!live.includes(panel)) {
                tile.destroy();
                this._tiles.delete(panel);
            }
        }
        const icons = new Map();
        for (const panel of live) {
            if (!this._tiles.has(panel)) {
                let tile;
                try {
                    tile = new Tile(panel, this._look);
                } catch (e) {
                    console.error(`Liquid Glass: no hover glide on a panel: ${e}`);
                    continue;
                }
                this._tiles.set(panel, tile);
                // The panel takes the tile with it: only forget it.
                tile.goneId = panel.connect('destroy', () => {
                    tile.goneId = 0;
                    tile.gone = true;
                    tile.destroy();
                    this._tiles.delete(panel);
                });
            }
            for (const icon of iconsOf(panel))
                icons.set(icon, panel);
        }
        for (const icon of [...this._watched.keys()]) {
            if (icons.get(icon) !== this._watched.get(icon).panel)
                this._unwatch(icon);
        }
        for (const [icon, panel] of icons) {
            if (this._watched.has(icon))
                continue;
            const signals = new Signals();
            signals.on(icon, 'notify::hover', () => this._hover(icon));
            signals.on(icon, 'destroy', () => {
                signals.forget(icon);
                this._unwatch(icon);
            });
            this._watched.set(icon, {signals, panel});
        }
    }

    _unwatch(icon) {
        const w = this._watched.get(icon);
        if (!w)
            return;
        this._watched.delete(icon);
        w.signals.clear();
        const tile = this._tiles.get(w.panel);
        if (tile?.icon === icon)
            this._leave(tile);
    }

    _hover(icon) {
        const w = this._watched.get(icon);
        const tile = w && this._tiles.get(w.panel);
        if (!tile)
            return;
        if (!icon.hover) {
            if (tile.icon === icon)
                this._leaveSoon(tile);
            return;
        }
        const goal = tile.target(icon);
        if (!goal)
            return;
        if (tile.leaveId) {
            GLib.source_remove(tile.leaveId);
            tile.leaveId = 0;
        }
        tile.icon = icon;
        tile.goal = goal;
        // Arriving from nothing: appear where the pointer is, never glide in from an old spot.
        if (!tile.pos || tile.alpha < 0.02 || !animationsOn()) {
            tile.pos = [...goal];
            tile.vel = [0, 0, 0, 0];
        }
        tile.alphaTo = 1;
        this._kick();
    }

    _leaveSoon(tile) {
        if (tile.leaveId)
            return;
        tile.leaveId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, LEAVE_GRACE_MS, () => {
            tile.leaveId = 0;
            if (!tile.icon?.hover)
                this._leave(tile);
            return GLib.SOURCE_REMOVE;
        });
    }

    _leave(tile) {
        if (tile.leaveId) {
            GLib.source_remove(tile.leaveId);
            tile.leaveId = 0;
        }
        tile.icon = null;
        tile.alphaTo = 0;
        this._kick();
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
        const animate = animationsOn();
        let moving = false;
        for (const tile of this._tiles.values()) {
            // Follow the icon if the taskbar moved it (an app opened or closed).
            if (tile.icon) {
                const g = tile.target(tile.icon);
                if (g)
                    tile.goal = g;
            }
            if (tile.goal && tile.pos) {
                for (let i = 0; i < 4; i++) {
                    if (animate)
                        [tile.pos[i], tile.vel[i]] = spring(tile.pos[i], tile.vel[i], tile.goal[i], STIFFNESS, DAMPING, dt);
                    else
                        [tile.pos[i], tile.vel[i]] = [tile.goal[i], 0];
                }
                const still = tile.pos.every((p, i) => Math.abs(p - tile.goal[i]) < 0.3 && Math.abs(tile.vel[i]) < 2);
                if (still) {
                    tile.pos = [...tile.goal];
                    tile.vel = [0, 0, 0, 0];
                } else {
                    moving = true;
                }
            }
            if (animate) {
                const step = dt * 1000 / (tile.alphaTo > tile.alpha ? FADE_IN_MS : FADE_OUT_MS);
                tile.alpha = tile.alphaTo > tile.alpha ? Math.min(tile.alphaTo, tile.alpha + step)
                    : Math.max(tile.alphaTo, tile.alpha - step);
            } else {
                tile.alpha = tile.alphaTo;
            }
            if (tile.alpha !== tile.alphaTo)
                moving = true;
            this._place(tile);
        }
        if (moving)
            this._kick();
        else
            this._last = 0;
    }

    _place(tile) {
        const a = tile.actor;
        if (tile.alpha <= 0 || !tile.pos) {
            a.opacity = 0;
            return;
        }
        const [x, y, w, h] = tile.pos.map(Math.round);
        if (tile.size[0] !== w || tile.size[1] !== h) {
            tile.size = [w, h];
            tile.allocate();
        }
        a.translation_x = x;
        a.translation_y = y;
        // Ease the fade so it reads as a soft arrival, not a linear ramp.
        const e = tile.alphaTo > 0 ? 1 - (1 - tile.alpha) ** 2 : tile.alpha ** 2;
        a.opacity = Math.round(255 * e);
    }

    // Reduce animation, lock, or the extension going away: land at once.
    settle() {
        for (const tile of this._tiles.values()) {
            if (tile.goal)
                tile.pos = [...tile.goal];
            tile.vel = [0, 0, 0, 0];
            tile.alpha = tile.alphaTo;
            this._place(tile);
        }
    }

    _teardown() {
        // Icons first: letting go of a hovered icon schedules a fade, dropped just below.
        this._signals.clear();
        for (const icon of [...this._watched.keys()])
            this._unwatch(icon);
        if (this._later)
            global.compositor.get_laters().remove(this._later);
        this._later = 0;
        this._last = 0;
        if (this._refreshId)
            GLib.source_remove(this._refreshId);
        this._refreshId = 0;
        for (const tile of this._tiles.values())
            tile.destroy();
        this._tiles.clear();
    }

    destroy() {
        this._teardown();
        if (this._animId)
            this._settings.disconnect(this._animId);
        this._animId = 0;
    }

    // For QA: the tiles' state.
    qaState() {
        return [...this._tiles.values()].map(t => ({
            pos: t.pos?.map(v => Math.round(v * 10) / 10) ?? null,
            goal: t.goal?.map(Math.round) ?? null,
            alpha: Math.round(t.alpha * 100) / 100,
            visible: t.actor.opacity > 0,
            moving: Boolean(this._later),
        }));
    }
}
