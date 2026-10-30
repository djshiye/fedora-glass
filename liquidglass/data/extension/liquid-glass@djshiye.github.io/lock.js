// Glass on the lock screen: the screen is one sheet of frosted glass over the
// wallpaper, the password sits on a glass card, and on unlock the sheet slides
// up into the desktop.
//
// What may show through: the wallpaper only. Every pane here copies our own
// copy of the wallpaper (Wallpaper, in the Shell's UI group); nothing from the
// session behind the lock (windows, the panel, notifications) is ever copied.
// The panes take no input, no key focus and no grab. GNOME's own lock screen
// background stays where it is, under the glass, so if anything here fails the
// lock screen is simply GNOME's own.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Graphene from 'gi://Graphene';
import Meta from 'gi://Meta';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {GlassPane} from './glass.js';
import {Signals} from './common.js';
import {Wallpaper} from './wallpaper.js';

const SLIDE_MAX_MS = 1500;      // the longest slide the settings allow
const STALL_MS = 100;           // a frame later than this means the desktop was busy waking up
const HOLD_MAX_MS = 1200;       // never hold the slide back longer than this in all
const CARD_PAD = 28;            // px of glass around the password prompt
const CLOCK_STYLES = {
    bold: {time: 'font-size: 96pt; font-weight: 800;', date: 'font-weight: 600;'},
    thin: {time: 'font-size: 92pt; font-weight: 200;', date: 'font-weight: 400;'},
};

// The sheet is calm: no pointer light, no motion, no colour bleed. Its ceiling
// keeps the white clock readable on any wallpaper: at most linear Y 0.13, which
// is 5.8:1 against white.
const SHEET_CEILING = 0.13;
// The card sits a little deeper than the sheet on bright wallpapers (6.6:1), so the
// name, the messages and GNOME's lighter password field on it stay readable too.
const CARD_CEILING = 0.11;

function sheetLook(c) {
    return {blur: c.blur, refraction: 34, bend: 40, depth: 0.2, dispersion: 0.25, saturation: 1.35,
        brightness: c.dim, tint: c.tint, highlight: 0.5, bleed: 0, pointerLight: 0, motion: 0,
        adapt: 0, shadow: 0, ceiling: SHEET_CEILING, solid: 1};
}

function cardLook(c) {
    const [r, g, b, a] = c.tint;
    return {...sheetLook(c), refraction: 22, bend: 26, depth: 0.3,
        brightness: Math.min(1, c.dim + 0.12), tint: [r, g, b, Math.min(1, a * 0.6)], highlight: 0.55,
        ceiling: CARD_CEILING, solid: 0};
}

/**
 * The spring's curve: the glass gathers itself (dips a little) and lifts away.
 * Bounce 0 lifts straight off; 1 gives the deepest dip. Returns the two cubic
 * Bézier control points, as in CSS cubic-bezier().
 */
export function springCurve(bounce) {
    const b = Math.max(0, Math.min(1, bounce));
    return [[0.3, -0.5 * b], [0.2, 1]];
}

export class LockGlass {
    constructor(cfg) {
        this.cfg = cfg.lock;
        this._signals = new Signals();
        this._dialogSignals = new Signals();
        this._dialog = null;
        this._sheets = [];
        this._card = null;
        this._later = 0;
        this._ended = false;
        this._styled = [];
        this._safe(() => {
            const group = Main.screenShield?._lockDialogGroup;
            if (group) {
                // GNOME makes the unlock dialog when the screen locks, and may make it again.
                // It is in the group before it is built: look once it is.
                this._signals.on(group, 'child-added', () => {
                    if (this._addLater)
                        return;
                    this._addLater = global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
                        this._addLater = 0;
                        this._safe(() => this._attach());
                        return GLib.SOURCE_REMOVE;
                    });
                });
            }
            this._attach();
        });
    }

    // Anything that goes wrong takes the glass away and leaves GNOME's own lock screen.
    _safe(fn) {
        try {
            fn();
        } catch (e) {
            console.error(`Liquid Glass: lock screen glass turned off: ${e}`);
            this._detach();
        }
    }

    _attach() {
        const dialog = Main.screenShield?._dialog;
        if (this._ended || !this.cfg.enabled || !dialog || dialog === this._dialog || !dialog._backgroundGroup)
            return;
        this._detach();
        this._dialog = dialog;
        this._dialogSignals.on(dialog, 'destroy', () => {
            this._dialog = null;     // our panes went with it
            this._sheets = [];
            this._card = null;
            this._detach();
            if (this._ended)
                this.destroy();
        });
        this._wall = new Wallpaper();
        const above = dialog._backgroundGroup;
        for (const m of Main.layoutManager.monitors) {
            const sheet = new GlassPane('full');
            sheet.setLook(sheetLook(this.cfg));
            dialog.insert_child_above(sheet, above);
            sheet.setSources([this._wall.actor]);
            // The sheet fills its screen: no rim while it rests there.
            sheet.setEdges([true, true, true, true]);
            // Stage position as if the lock screen were in place, so the wallpaper in it
            // lines up with the real one however far the sheet has slid.
            sheet.place(m.x, m.y, m.width, m.height, [0, 0, 0, 0], m.x, m.y);
            sheet.show();
            this._sheets.push(sheet);
        }
        if (this.cfg.card) {
            this._card = new GlassPane('full');
            this._card.setLook(cardLook(this.cfg));
            this._card.setSources([this._wall.actor]);
            dialog.insert_child_above(this._card, this._sheets[this._sheets.length - 1]);
            const box = dialog._promptBox;
            for (const s of ['notify::opacity', 'notify::visible', 'notify::allocation', 'notify::scale-x',
                'notify::translation-y', 'child-added', 'child-removed'])
                this._dialogSignals.on(box, s, () => this._queue());
            this._dialogSignals.on(dialog._stack, 'notify::allocation', () => this._queue());
        }
        this._styleClock();
        this._queue();
    }

    _queue() {
        if (this._later || !this._dialog)
            return;
        this._later = global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
            this._later = 0;
            this._safe(() => this._sync());
            return GLib.SOURCE_REMOVE;
        });
    }

    _sync() {
        const dialog = this._dialog;
        if (!dialog)
            return;
        this._placeClock();
        const card = this._card;
        if (!card)
            return;
        const box = dialog._promptBox;
        const prompt = box?.get_first_child();
        if (!prompt || !box.visible || box.opacity === 0 || prompt.width < 2) {
            card.hide();
            return;
        }
        const [px, py] = prompt.get_transformed_position();
        const [pw, ph] = prompt.get_transformed_size();
        if (![px, py, pw, ph].every(Number.isFinite)) {
            card.hide();
            return;
        }
        // Where it would be with the lock screen in place (see the sheet).
        const ty = Main.screenShield._lockDialogGroup?.translation_y ?? 0;
        const [x, y, w, h] = [px - CARD_PAD, py - ty - CARD_PAD, pw + 2 * CARD_PAD, ph + 2 * CARD_PAD];
        const [ok, lx, ly] = dialog.transform_stage_point(px - CARD_PAD, py - CARD_PAD);
        if (!ok) {
            card.hide();
            return;
        }
        const r = Math.min(32, h / 2);
        card.place(lx, ly, w, h, [r, r, r, r], x, y);
        card.opacity = box.opacity;
        card.show();
    }

    // Clock look and place: only how GNOME's own clock is drawn and where it sits.
    _styleClock() {
        const clock = this._dialog?._clock;
        const style = CLOCK_STYLES[this.cfg.clockStyle];
        if (!clock || !style)
            return;
        for (const [label, css] of [[clock._time, style.time], [clock._date, style.date]]) {
            if (!label)
                continue;
            this._styled.push([label, label.get_style()]);
            label.set_style(css);
        }
    }

    _placeClock() {
        const stack = this._dialog?._stack;
        if (!stack || this.cfg.clockPosition === 'gnome')
            return;
        const box = stack.get_allocation_box();
        const parent = stack.get_parent();
        const H = parent?.height ?? 0;
        if (!H)
            return;
        // The clock and the password prompt share one place, so they move together.
        const want = this.cfg.clockPosition === 'top' ? Math.round(H * 0.07)
            : Math.round((H - (box.y2 - box.y1)) / 2);
        stack.translation_y = want - box.y1;
    }

    /** The screen is unlocked: the sheet slides up into the desktop. */
    unlocking() {
        this._ended = true;
        if (!this._dialog) {
            this.destroy();
            return;
        }
        // Whatever happens, never hold on past the slide.
        this._endId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, SLIDE_MAX_MS + HOLD_MAX_MS + 1500, () => {
            this._endId = 0;
            this.destroy();
            return GLib.SOURCE_REMOVE;
        });
        // GNOME starts its own slide right after this; shape that one, never replace
        // it, so it always finishes what GNOME does when it ends. Shape it before its
        // first frame, so none of it is missed.
        this._slideIdle = GLib.idle_add(GLib.PRIORITY_HIGH, () => {
            this._slideIdle = 0;
            this._safe(() => this._shapeSlide());
            return GLib.SOURCE_REMOVE;
        });
    }

    _shapeSlide() {
        // The sheet's bottom edge is glass now that it moves.
        this._sheets.forEach(s => s.setEdges([true, true, true, false]));
        const t = Main.screenShield?._lockDialogGroup?.get_transition('translation-y');
        if (!t || !St.Settings.get().enable_animations)
            return;
        if (this.cfg.slide !== 'gnome') {
            t.set_duration(Math.max(150, Math.min(SLIDE_MAX_MS, this.cfg.slideMs)));
            if (this.cfg.slide === 'spring') {
                const [[x1, y1], [x2, y2]] = springCurve(this.cfg.bounce);
                t.set_cubic_bezier_progress(new Graphene.Point({x: x1, y: y1}), new Graphene.Point({x: x2, y: y2}));
            } else {
                t.set_progress_mode(Clutter.AnimationMode.EASE_OUT_CUBIC);
            }
        }
        // The desktop comes back to life while the glass slides, and that can hold up a
        // frame or two. Pick up the slide where it was rather than jump to its end, so it
        // is seen; never by more than HOLD_MAX_MS in all.
        let last = 0, held = 0;
        this._slide = t;
        this._slideFrame = t.connect('new-frame', (_t, elapsed) => {
            const gap = elapsed - last;
            if (gap > STALL_MS && held < HOLD_MAX_MS) {
                const back = Math.min(gap - 16, HOLD_MAX_MS - held);
                held += back;
                elapsed -= back;
                t.advance(elapsed);
            }
            last = elapsed;
        });
    }

    update(cfg) {
        this.cfg = cfg.lock;
        if (this._ended)
            return;
        this._safe(() => {
            // Simplest and safest: take it all away and put it back with the new look.
            const dialog = Main.screenShield?._dialog;
            this._detach();
            if (dialog && this.cfg.enabled)
                this._attach();
        });
    }

    _detach() {
        if (this._later)
            global.compositor.get_laters().remove(this._later);
        this._later = 0;
        this._dialogSignals.clear();
        for (const [label, css] of this._styled) {
            try {
                label.set_style(css);
            } catch {}   // gone with the dialog
        }
        this._styled = [];
        try {
            if (this._dialog?._stack)
                this._dialog._stack.translation_y = 0;
        } catch {}
        for (const p of [...this._sheets, this._card]) {
            try {
                p?.destroy();
            } catch {}
        }
        this._sheets = [];
        this._card = null;
        this._dialog = null;
        this._wall?.destroy();
        this._wall = null;
    }

    destroy() {
        if (this._endId)
            GLib.source_remove(this._endId);
        this._endId = 0;
        if (this._slideIdle)
            GLib.source_remove(this._slideIdle);
        this._slideIdle = 0;
        if (this._slideFrame)
            this._slide.disconnect(this._slideFrame);
        this._slideFrame = 0;
        this._slide = null;
        if (this._addLater)
            global.compositor.get_laters().remove(this._addLater);
        this._addLater = 0;
        this._signals.clear();
        this._detach();
        this._ended = true;
    }
}
