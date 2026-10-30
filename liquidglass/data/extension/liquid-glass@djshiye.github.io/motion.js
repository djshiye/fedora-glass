// Motion: a light that follows the pointer, and press and open springs.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import St from 'gi://St';

import {moving} from './glass.js';
import {followers} from './common.js';

// ---- motion: a light that follows the pointer, press and open springs --------------
// Nothing runs while the pointer is still: a pointer event schedules one step
// before the next redraw, and steps go on only while a spring is still moving.
const PRESS_SCALE = 0.985;  // a pressed button or menu item, at the bottom of its give
// What gives under a press: panel buttons, Dash to Panel app icons, menu items, toggles.
const PRESSABLE = ['panel-button', 'overview-tile', 'show-apps', 'popup-menu-item', 'arcmenu-menu-item',
    'quick-toggle', 'quick-menu-toggle', 'icon-button', 'button'];
const REACH = 220;          // px around a pane where the pointer lights its rim

export class Motion {
    constructor() {
        this._state = new Map();    // follower -> springs
        this._pointer = null;
        this._later = 0;
        this._last = 0;
        this._settings = St.Settings.get();
        // Reduce animation can change at any time: follow it at once, pointer still or not.
        this._animId = this._settings.connect('notify::enable-animations', () => this._kick());
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
            // GNOME 50 events carry no source: ask the stage which actor got it.
            this._pressItem(global.stage.get_event_actor(event));
            const [x, y] = event.get_coords();
            for (const f of followers) {
                const r = f.rect;
                if (r && this._look(f).motion > 0 && x >= r[0] && y >= r[1] && x < r[0] + r[2] && y < r[1] + r[3])
                    this._st(f).pressT = 1;
            }
            this._watchRelease(type === Clutter.EventType.TOUCH_BEGIN);
            this._kick();
        } else if (type === Clutter.EventType.BUTTON_RELEASE || type === Clutter.EventType.TOUCH_END ||
                   type === Clutter.EventType.TOUCH_CANCEL) {
            this._released();
        }
    }

    // A menu or drag grab can swallow the release: while anything is pressed, look
    // at the buttons themselves, so nothing stays pressed. A touch has no button
    // state to look at; it lets go after 600 ms at most.
    _watchRelease(touch) {
        if (this._relId)
            GLib.source_remove(this._relId);
        const t0 = GLib.get_monotonic_time();
        const held = Clutter.ModifierType.BUTTON1_MASK | Clutter.ModifierType.BUTTON2_MASK |
            Clutter.ModifierType.BUTTON3_MASK;
        this._relId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 50, () => {
            const up = touch ? GLib.get_monotonic_time() - t0 > 600000 : !(global.get_pointer()[2] & held);
            if (!up)
                return GLib.SOURCE_CONTINUE;
            this._relId = 0;
            this._released();
            return GLib.SOURCE_REMOVE;
        });
    }

    _released() {
        if (this._relId)
            GLib.source_remove(this._relId);
        this._relId = 0;
        for (const st of this._state.values())
            st.pressT = 0;
        if (this._item)
            this._item.to = 1;
        this._kick();
    }

    // The button or menu item under a press gives a little, like the glass under it.
    _pressItem(source) {
        if (!this._animate)
            return;
        let a = source;
        while (a && !(a.reactive && PRESSABLE.some(c => a.has_style_class_name?.(c))))
            a = a.get_parent();
        if (!a || !followers.size || ![...followers].some(f => f.anchor.contains(a)))
            return;   // only on glass surfaces
        if (this._item?.actor !== a) {
            this._settleItem();
            const id = a.connect('destroy', () => {
                if (this._item?.actor === a)
                    this._item = null;
            });
            a.set_pivot_point(0.5, 0.5);
            this._item = {actor: a, id, s: 1, v: 0, to: 1};
        }
        this._item.to = PRESS_SCALE;
    }

    _settleItem() {
        const it = this._item;
        this._item = null;
        if (!it)
            return;
        try {
            it.actor.set_scale(1, 1);
            it.actor.disconnect(it.id);
        } catch {}   // already gone
    }

    _stepItem(dt) {
        const it = this._item;
        if (!it)
            return false;
        if (!this._animate) {
            this._settleItem();
            return false;
        }
        [it.s, it.v] = spring(it.s, it.v, it.to, 1370, 44, dt);
        if (it.to === 1 && Math.abs(1 - it.s) + Math.abs(it.v) < 1e-4) {
            this._settleItem();
            return false;
        }
        it.actor.set_scale(it.s, it.s);
        return true;
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
            if (!r) {
                // Hidden: let go at once, so it never reopens still pressed.
                const st = this._state.get(f);
                if (st)
                    [st.press, st.pressV, st.pressT] = [0, 0, 0];
                continue;
            }
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
        if (this._stepItem(dt))
            moving = true;
        if (moving)
            this._kick();
        else
            this._last = 0;
    }

    destroy() {
        if (this._later)
            global.compositor.get_laters().remove(this._later);
        this._later = 0;
        if (this._relId)
            GLib.source_remove(this._relId);
        this._relId = 0;
        global.stage.disconnect(this._stage);
        this._cursor.disconnect(this._cursorId);
        this._settings.disconnect(this._animId);
        this._settleItem();
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
