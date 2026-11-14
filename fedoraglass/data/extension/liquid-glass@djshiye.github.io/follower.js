// A glass pane that follows one Shell surface: its rectangle, corners and opacity.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Graphene from 'gi://Graphene';
import Meta from 'gi://Meta';

import {GlassPane} from './glass.js';
import {HOLD_MAX_MS, MOVES, radiiOf, screenEdges, sourcesFor, windowWatch, followers, motion, Signals, glowSource, grow} from './common.js';

// What a frozen menu's style gets (see Follower._iceStyle).
const ICE_STYLE = ' box-shadow: none;';

/**
 * A pane that sits right below `anchor` (a child of a free-layout container
 * such as the Shell's UI group) and copies the on-screen rectangle, corner
 * radii and opacity of `target`, a descendant of `anchor`.
 */
export class Follower {
    /**
     * onlyBehind: show only windows that are really behind the surface, not those
     * that merely come near its edge. A docked panel sits beside every maximized
     * window on its screen: their colours, reflected into the glass at its edge, made
     * the panel on a screen with a maximized window lighter and tinted, so the panels
     * on two screens never matched.
     *
     * sources: what the glass shows instead of what is behind on screen (a function
     * returning actors). The overview's dash sits inside the overview, which the glass
     * can't copy from inside it, so it shows the wallpaper the overview blurs.
     * glow: what lights the glass instead of the anchor (the overview's dash, not the
     * whole overview with its windows).
     * plainParent: the anchor's parent is never moved, scaled or turned (the window group),
     * so a place in it is the stage place less its own. The window group cannot map stage
     * points into itself (transform_stage_point fails there), which left the glass hidden.
     */
    constructor(target, anchor, settings, onGone, {onlyBehind = false, sources = null, glow = null, plainParent = false} = {}) {
        this.target = target;
        this._plainParent = plainParent;
        this._onlyBehind = onlyBehind;
        this._sources = sources;
        this._glow = glow;
        this.anchor = anchor;
        this.settings = settings;
        this.pane = new GlassPane('glass');
        this.top = new GlassPane('reflections');
        this._iceWant = false;
        this.pane.setOnIce(frozen => this._iceStyle(frozen));
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
        // Dash to Panel moves a panel into a new container when a screen is unplugged
        // or turned off: the glass goes along (see sync).
        this._signals.on(anchor, 'parent-set', () => this.queue());
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
        // Already invisible (Dash to Panel's window previews map at 0 and fade in
        // themselves): nothing to hold back. Holding it would also take 0 as its own
        // opacity, so it never counted as shown, never let go and never got glass.
        if (this.target.opacity === 0)
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
        if (!pane || !top)
            return;
        const hide = () => {
            pane.hide();
            top.hide();
            this.rect = null;
            // A menu that flowed back into its button is its own size again once gone.
            if (this._shrunk) {
                this._shrunk = false;
                target.set_scale(1, 1);
            }
        };
        if (!parent) {
            // Taken off the stage without being destroyed: Extension List's button
            // tooltips are box pointers that leave the UI group (removeChrome) mid-fade
            // and come back on the next hover. The panes stay where they were, so hide
            // them, or empty glass boxes are left floating where the tooltips were.
            hide();
            return;
        }
        if (pane.get_parent() !== parent || top.get_parent() !== parent) {
            // The surface moved to another container (Dash to Panel rebuilds its
            // per-screen boxes when screens change, and keeps the panel): without
            // this the glass stayed behind in the old, detached box, and that panel
            // had no glass until the next restart.
            for (const p of [pane, top]) {
                p.get_parent()?.remove_child(p);
                parent.insert_child_below(p, anchor);
            }
        }
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
        let [ok, lx, ly] = parent.transform_stage_point(sx, sy);
        if (!ok && this._plainParent) {
            const [px, py] = parent.get_transformed_position();
            [ok, lx, ly] = [true, sx - px, sy - py];
        }
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
        // Closing, a menu that grew out of its button flows back into it as it fades.
        if (this._closing && this.condense && this._from) {
            this._applyGrow(opacity);
            this._shrunk = true;
        } else if (this._shrunk && !this._closing) {
            this._shrunk = false;
            this._applyGrow(1);
        }
        const p = pane.pad;
        const radii = radiiOf(target);
        // Growing or condensing (scaled), the glass keeps one place and one picture for
        // the whole animation (see GlassPane.place): its surface's own unscaled
        // rectangle, with room for the overshoot. Only the shape drawn changes.
        const room = this._scaledRoom(target, [sx, sy, w, h]);
        const [gx, gy, gw, gh] = room ?? [sx, sy, w, h];
        const [gok, glx, gly] = room ? parent.transform_stage_point(gx, gy) : [true, lx, ly];
        const still = !room || !gok;
        const reach = this._onlyBehind ? 0 : p;
        if (this._sources)
            pane.setSources(this._sources());
        else {
            pane.setSources(still
                ? sourcesFor(this.settings.behind, sx - reach, sy - reach, w + 2 * reach, h + 2 * reach)
                : sourcesFor(this.settings.behind, gx - reach, gy - reach, gw + 2 * reach, gh + 2 * reach));
        }
        // The light the content casts into the glass comes from the content itself.
        // Both panes are the anchor's siblings; never clone an actor into itself.
        const glow = this._glow ?? glowSource(anchor, target);
        const nested = top.contains(glow) || glow.contains(top) || glow.contains(pane);
        top.setSources(nested ? [] : [glow]);
        const edges = screenEdges(target, sx, sy, w, h);
        pane.setEdges(edges);
        top.setEdges(edges);
        if (still)
            pane.place(lx, ly, w, h, radii, sx, sy);
        else
            pane.place(glx, gly, gw, gh, radii, gx, gy, [sx, sy, w, h]);
        top.place(lx, ly, w, h, radii, sx, sy);
        this.rect = [sx, sy, w, h];
        pane.show();
        top.show();
        if (this._iceWant && !pane._shadeShed)
            this._iceStyle(true);
        // The glass is placed and shown before this frame paints: the surface may
        // show in the same frame, over glass that is already complete.
        this._release();
    }

    /**
     * While the target is scaled (growing, condensing, flowing back), the stage
     * rectangle that holds it at every step of the animation: its unscaled place,
     * 4 % bigger round its middle for the springs' overshoot. Null when it is not
     * scaled, or the scaled surface would not fit (then the glass follows it frame by
     * frame, as before).
     */
    _scaledRoom(target, [sx, sy, w, h]) {
        const [kx, ky] = target.get_scale();
        if (Math.abs(kx - 1) < 1e-4 && Math.abs(ky - 1) < 1e-4)
            return null;
        const parent = target.get_parent();
        if (!parent)
            return null;
        const box = target.get_allocation_box();
        const [px, py] = parent.get_transformed_position();
        const [bw, bh] = [box.get_width(), box.get_height()];
        const [mx, my] = [Math.ceil(bw * 0.02) + 1, Math.ceil(bh * 0.02) + 1];
        const r = [Math.floor(px + box.x1 + target.translation_x) - mx, Math.floor(py + box.y1 + target.translation_y) - my,
            Math.ceil(bw) + 2 * mx, Math.ceil(bh) + 2 * my];
        if (!r.every(Number.isFinite) || r[2] < 2 || r[3] < 2)
            return null;
        const fits = sx >= r[0] && sy >= r[1] && sx + w <= r[0] + r[2] && sy + h <= r[1] + r[3];
        return fits ? r : null;
    }

    /**
     * Frozen over (weather frost), a menu sheds the theme's drop shadow. St lays it under
     * the whole of the menu's box, under its veil, so a dark menu showed its glass at under
     * half its brightness and the ice could never glow there; around it, it covered the
     * vapour rolling off the ice, which now makes the menu's edge. Only menus (whose look
     * says they have such a shadow, `shade`), never the panel, and only while frozen:
     * thawed, the style is as it was. Other code may restyle the surface meanwhile, so
     * only our own few words are added and taken out again.
     */
    _iceStyle(frozen) {
        this._iceWant = frozen;
        const t = this.target;
        try {
            const style = t?.get_style?.() ?? '';
            const shed = style.includes(ICE_STYLE);
            // peek: a menu never shown yet has no style worked out; it is looked at again
            // when it shows (sync).
            if (frozen && !shed && (this.settings?.look?.shade ?? 0) > 0 && t.peek_theme_node?.()?.get_box_shadow?.())
                t.set_style(style + ICE_STYLE);
            else if (!frozen && shed)
                t.set_style(style.replace(ICE_STYLE, '') || null);
            this.pane?.setShadeShed((t?.get_style?.() ?? '').includes(ICE_STYLE));
        } catch {
            // The surface is gone: nothing to put back.
        }
    }

    setMotion(m) {
        // The pointer brightens the glass's own rim reflection; the content's light
        // layer only gives with a press.
        const {k, ...shape} = m;
        this.pane?.setMotion(m);
        // The ice's light (weather frost) follows the pointer over the content as well.
        this.top?.setMotion(k === undefined ? shape : {...shape, iceK: k});
        // A menu condenses into place as it opens: a little small, then its size.
        // One opened from a button grows out of that button instead.
        if (this.condense && m.open !== undefined && this.target) {
            if (m.open <= 0)
                this._from = this._growFrom();
            if (m.open === 1) {
                // Landed: exactly full size, and anything GNOME measured through our
                // scale while the menu grew is measured again.
                this.target.set_scale(1, 1);
                this.onFullSize?.();
            } else if (!this._applyGrow(m.open)) {
                const sc = 0.96 + 0.04 * Math.min(m.open, 1.0) + 0.02 * Math.max(0, m.open - 1);
                this.target.set_pivot_point(0.5, 0.5);
                this.target.set_scale(sc, sc);
            }
            // Follow the new size in this same frame. This runs from a later
            // itself, and the motion may have just settled, so a queued sync
            // could wait for a frame that never comes.
            if (this.pane?.visible)
                this.sync();
        }
    }

    /**
     * Where the menu grows from: the button that opened it, as a pivot inside the
     * menu (0..1) and the button's size as a share of the menu's. Null when there
     * is no button, it is not on screen, or growing is off.
     */
    _growFrom() {
        if (!grow.enabled || !this.source)
            return null;
        try {
            const src = this.source();
            const t = this.target;
            if (!src?.mapped || !t)
                return null;
            const [bx, by] = src.get_transformed_position();
            const [bw, bh] = src.get_transformed_size();
            // The menu's own place, without the scale we set on it.
            const box = t.get_allocation_box();
            const [px, py] = t.get_parent().get_transformed_position();
            const [tx, ty, tw, th] = [px + box.x1, py + box.y1, box.get_width(), box.get_height()];
            if (![bx, by, bw, bh, tx, ty, tw, th].every(Number.isFinite) || tw < 8 || th < 8 || bw < 1 || bh < 1)
                return null;
            const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
            return {
                px: clamp((bx + bw / 2 - tx) / tw, 0, 1),
                py: clamp((by + bh / 2 - ty) / th, 0, 1),
                fx: clamp(bw / tw, 0.12, 1),
                fy: clamp(bh / th, 0.08, 1),
            };
        } catch {
            return null;
        }
    }

    /** Shape the menu at k (0 the button, 1 the menu; past 1 the spring's overshoot). */
    _applyGrow(k) {
        const g = this._from;
        if (!g)
            return false;
        const c = Math.max(0, Math.min(k, 1));
        // Width leads and height follows a little, like a drop pulling away.
        const ex = 1 - (1 - c) * (1 - c);
        const sx = g.fx + (1 - g.fx) * ex + 0.015 * Math.max(0, k - 1);
        const sy = g.fy + (1 - g.fy) * c + 0.03 * Math.max(0, k - 1);
        this.target.set_pivot_point(g.px, g.py);
        this.target.set_scale(sx, sy);
        return true;
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
        this._iceStyle(false);
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
