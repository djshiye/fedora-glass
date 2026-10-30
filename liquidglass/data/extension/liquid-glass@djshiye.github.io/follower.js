// A glass pane that follows one Shell surface: its rectangle, corners and opacity.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Graphene from 'gi://Graphene';
import Meta from 'gi://Meta';

import {GlassPane} from './glass.js';
import {HOLD_MAX_MS, MOVES, radiiOf, screenEdges, sourcesFor, windowWatch, followers, motion, Signals, glowSource} from './common.js';

/**
 * A pane that sits right below `anchor` (a child of a free-layout container
 * such as the Shell's UI group) and copies the on-screen rectangle, corner
 * radii and opacity of `target`, a descendant of `anchor`.
 */
export class Follower {
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
        this._holdPaint = 0;
        this._opacity = 1;
        this._closing = false;
        this._faded = false;
        followers.add(this);
        try {
            this._build(target, anchor, settings);
        } catch (e) {
            // Half-built: take it all down again, which also shows the target.
            this.destroy();
            throw e;
        }
    }

    _build(target, anchor, settings) {
        for (let a = target; a && a !== anchor.get_parent(); a = a.get_parent())
            MOVES.forEach(s => this._signals.on(a, s, () => this.queue()));
        this._signals.on(target, 'style-changed', () => this.queue());
        // Never show a surface before its glass: hold it until the pane is up.
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
        // Whatever happens, never leave a menu invisible: if its glass is not up
        // after HOLD_MAX_MS, show the menu anyway. On a slow machine a
        // frame can take longer than that, so give the glass one frame at least.
        let frames = 0, expired = false;
        const giveUp = () => {
            if (this._faded)
                return;   // still invisible: wait until there is something to show
            global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
                this._release();
                return GLib.SOURCE_REMOVE;
            });
            global.stage.queue_redraw();
        };
        this._holdPaint = global.stage.connect('after-paint', () => {
            frames++;
            if (frames >= 4 || expired)
                giveUp();
        });
        this._holdId = GLib.timeout_add(GLib.PRIORITY_HIGH, HOLD_MAX_MS, () => {
            this._holdId = 0;
            expired = true;
            if (frames >= 1)
                giveUp();
            return GLib.SOURCE_REMOVE;
        });
    }

    _release() {
        if (this._holdId)
            GLib.source_remove(this._holdId);
        this._holdId = 0;
        if (this._holdPaint)
            global.stage.disconnect(this._holdPaint);
        this._holdPaint = 0;
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

        // A menu that is appearing starts condensing now, so that its first frame
        // already has the starting size.
        const appearing = !pane.visible;
        if (appearing)
            motion.current?.opened(this);
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
        // Opening, the glass is complete from its first frame and only the content
        // fades in over it, so nothing sharp behind shows through. Closing, the
        // glass fades with the content, so it is never left bare without its veil.
        let opacity = 1;
        for (let a = target; a && a !== parent; a = a.get_parent())
            opacity *= (a === target && this._held !== null ? this._held : a.opacity) / 255;
        // Fully faded (a menu about to fade in, or done fading out): no glass, and a
        // held menu keeps waiting for it, since nothing of it could show anyway.
        this._faded = opacity <= 0;
        if (this._faded) {
            hide();
            return;
        }
        if (opacity >= 1 || !pane.visible)
            this._closing = false;
        else if (opacity < this._opacity - 1e-3)
            this._closing = true;
        this._opacity = opacity;
        pane.opacity = top.opacity = this._closing ? Math.round(opacity * 255) : 255;
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
        this.rect = [sx, sy, w, h];
        pane.show();
        top.show();
        // The glass is placed and shown before this frame paints: the surface may
        // show in the same frame, over glass that is already complete.
        this._release();
    }

    setMotion(m) {
        // The pointer brightens the glass's own rim reflection; the content's light
        // layer only gives with a press.
        const {k, ...shape} = m;
        this.pane?.setMotion(m);
        this.top?.setMotion(shape);
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
