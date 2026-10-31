// Window and panel animations picked in the Liquid Glass app: how windows open,
// minimize and restore, and close, how a taskbar icon bounces while its app
// starts, and how panel items respond to the pointer.
//
// Windows. GNOME's window manager connects its own handlers to the Shell's
// 'map', 'minimize', 'unminimize' and 'destroy' signals once at startup, with the
// functions bound, so they can't be wrapped. While any window event is set to
// something other than GNOME's own animation, ours takes those four signals:
// GNOME's handlers are blocked (never removed) and ours run instead, handing an
// event back to GNOME's own code whenever it is set to "GNOME default", the window
// isn't a plain app window, the overview is open or animations are off. Turning
// it off unblocks them again.
//
// Every window animation keeps GNOME's own bookkeeping (its _minimizing,
// _unminimizing and _destroying sets) and finishes through GNOME's *Done
// functions, so the window manager is always told the effect is over, exactly
// once. They run as Clutter transitions on the window actor, so GNOME's own
// "stop all effects on this window" (remove_all_transitions) stops ours too, and
// a watchdog finishes any that stalls. Nothing runs between animations.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import * as C from './curves.js';
import {Signals} from './common.js';
import {freezeSource, thawSource, holdPanes, releasePanes} from './glass.js';

const WM_SIGNALS = ['map', 'minimize', 'unminimize', 'destroy'];
// The parts of GNOME's window manager the window animations build on. They are
// private, so they are checked before anything is changed.
const WM_METHODS = ['_mapWindow', '_mapWindowDone', '_minimizeWindow', '_minimizeWindowDone', '_unminimizeWindow',
    '_unminimizeWindowDone', '_destroyWindow', '_destroyWindowDone', '_shouldAnimate', '_getAnimationWindowType'];
const WM_SETS = ['_mapping', '_minimizing', '_unminimizing', '_destroying', '_skippedActors'];
const COMPLETED = {open: 'completed_map', minimize: 'completed_minimize', unminimize: 'completed_unminimize',
    close: 'completed_destroy'};
const WATCHDOG_MIN_MS = 1500;
const RETARGET_MS = 120;     // a restore this soon after a minimize was cut short starts where it was
const FIELD = {'scale-x': 'scale_x', 'scale-y': 'scale_y', 'translation-x': 'translation_x',
    'translation-y': 'translation_y', 'opacity': 'opacity'};

function animationsOn() {
    // Read when each animation starts, so Reduce animation applies at once.
    return St.Settings.get().enable_animations;
}


const running = new Map();   // actor -> the animation running on it
const GENIE_FRAME_BUDGET_US = 20000;
const GENIE_BUDGET_FRAMES = 10;
const GENIE_SLOW_FRAMES = 3;
let frameBudget = true;
let genieFallbacks = 0;
let clampCount = 0;
const guards = new Map();    // window actor -> the genie copy standing in for it

/**
 * Run an animation on an actor: fns maps a property ('scale-x', 'opacity', ...)
 * to its value at time u (0..1). The actor keeps pivot point 0, 0 throughout;
 * scaling about another point is done with the translation. onDone(finished)
 * runs exactly once, when the animation completes or is stopped, and not at all
 * if another animation on the same actor replaces it.
 */
// Where an actor's translation may take it: a window stays on its monitor (it may
// go up to its own size past an edge, never further); anything else stays within
// the stage's size.
function bounds(actor) {
    const win = actor.meta_window;
    const mon = win && win.get_monitor() >= 0 ? Main.layoutManager.monitors[win.get_monitor()] : null;
    if (mon) {
        return {
            'translation-x': {lo: mon.x - actor.x - actor.width, hi: mon.x + mon.width - actor.x},
            'translation-y': {lo: mon.y - actor.y - actor.height, hi: mon.y + mon.height - actor.y},
        };
    }
    const [W, H] = global.stage.get_size();
    return {'translation-x': {lo: -W, hi: W}, 'translation-y': {lo: -H, hi: H}};
}

let clampLogged = false;

/** Every property function, guarded: no value out of range or NaN ever reaches an actor. */
function safeFns(actor, fns) {
    const b = bounds(actor);
    const out = {};
    for (const [prop, fn] of Object.entries(fns)) {
        if (!fn)
            continue;
        out[prop] = C.guarded(fn, prop, b[prop] ?? null, (p, v) => {
            clampCount++;
            if (!clampLogged)
                log(`Liquid Glass: an animation asked for ${p} = ${v}; held it in range (logged once)`);
            clampLogged = true;
        });
    }
    return out;
}

function animate(actor, ms, rawFns, onDone) {
    stop(actor, false, true);
    // A window in motion: glass that shows it from behind keeps its last picture.
    if (actor.meta_window)
        freezeSource(actor);
    const fns = safeFns(actor, rawFns);
    const anim = {actor, fns, onDone, transitions: [], watchdog: 0, done: false, timeline: null};
    running.set(actor, anim);
    actor.set_pivot_point(0, 0);
    // A timeline on the actor's own frame clock works out each frame from the time
    // since the start, so a long frame (a stall, a shader compile) only skips ahead
    // on the curve. (Clutter's key frame transitions run off the curve after a long
    // frame: a window could flip or blow up to several times its size.)
    const tl = new Clutter.Timeline({actor, duration: Math.max(1, ms)});
    anim.timeline = tl;
    tl.connect('new-frame', () => {
        if (anim.done)
            return;
        const u = Math.min(1, tl.get_elapsed_time() / Math.max(1, ms));
        anim.onTick?.();
        setAt(anim, u);
        anim.onFrame?.(u);
    });
    tl.connect('stopped', (_t, finished) => {
        if (running.get(actor) === anim && !anim.done)
            finish(anim, finished);
    });
    // GNOME ends a window's effects by removing its transitions (when the window is
    // minimized again, closed, or Mutter moves on): a do-nothing transition held on
    // the window lets that stop the timeline's animation too.
    if (actor.meta_window) {
        const hold = new Clutter.PropertyTransition({property_name: 'z-position', duration: ms * 4 + WATCHDOG_MIN_MS,
            remove_on_complete: true});
        hold.set_from(actor.z_position + 1e-7);
        hold.set_to(actor.z_position + 1e-7);
        hold.connect('stopped', () => {
            if (running.get(actor) === anim && !anim.done)
                finish(anim, false);
        });
        anim.transitions.push(['liquid-glass-hold', hold]);
        actor.add_transition('liquid-glass-hold', hold);
    }
    // A timeline only moves while the stage draws frames; if it ever stops, this finishes it.
    anim.watchdog = GLib.timeout_add(GLib.PRIORITY_DEFAULT, Math.max(WATCHDOG_MIN_MS, ms * 2), () => {
        anim.watchdog = 0;
        if (!anim.done)
            finish(anim, false);
        return GLib.SOURCE_REMOVE;
    });
    setAt(anim, 0);
    tl.start();
    return anim;
}

function setAt(anim, u) {
    for (const [prop, fn] of Object.entries(anim.fns))
        anim.actor[FIELD[prop]] = prop === 'opacity' ? Math.round(Math.min(255, Math.max(0, fn(u)))) : fn(u);
}

function finish(anim, finished) {
    if (anim.done)
        return;
    anim.done = true;
    if (anim.watchdog)
        GLib.source_remove(anim.watchdog);
    anim.watchdog = 0;
    const {actor} = anim;
    if (running.get(actor) === anim) {
        running.delete(actor);
        thawSource(actor);
    }
    try {
        if (!finished)
            anim.cut = Object.fromEntries(Object.keys(anim.fns).map(p => [p, actor[FIELD[p]]]));
        for (const [name] of anim.transitions)
            actor.remove_transition(name);
        anim.timeline?.stop();
        // Land on the end state, then hand over.
        setAt(anim, 1);
    } catch (e) {
        logError(e, 'Liquid Glass: finishing an animation');
    }
    try {
        anim.onDone?.(finished, anim);
    } catch (e) {
        logError(e, 'Liquid Glass: after an animation');
    }
}

/** Stop the animation on an actor. With jump, it lands on its end state and reports done. */
function stop(actor, jump = true, replacing = false) {
    const anim = running.get(actor) ?? guards.get(actor);
    if (!anim)
        return;
    if (!replacing && anim.actor === actor)
        thawSource(actor);
    if (jump) {
        finish(anim, false);
        return;
    }
    if (anim.actor !== actor) {
        finish(anim, false);   // a genie copy: always lands and reports
        return;
    }
    // Replaced by a new animation: drop it without reporting.
    running.delete(actor);
    anim.done = true;
    if (anim.watchdog)
        GLib.source_remove(anim.watchdog);
    anim.watchdog = 0;
    for (const [name] of anim.transitions) {
        try {
            actor.remove_transition(name);
        } catch {}
    }
    anim.timeline?.stop();
}

/** Where the actor is drawn now, as scale and translation about pivot 0, 0. */
function visual(actor) {
    const [px, py] = actor.get_pivot_point();
    const {width: w, height: h} = actor;
    return {
        sx: actor.scale_x, sy: actor.scale_y, op: actor.opacity,
        tx: actor.translation_x + px * w * (1 - actor.scale_x),
        ty: actor.translation_y + py * h * (1 - actor.scale_y),
    };
}

const lerp = (a, b, t) => a + (b - a) * t;

/**
 * Scale about the centre from `from` (a visual state) to scale s1 at translation
 * (dx, dy) of the scaled box's top-left, following the curve; jelly wobbles it.
 */
function moveFns(actor, from, to, curve, wob, opacity) {
    const {width: w, height: h} = actor;
    const sx = u => lerp(from.sx, to.sx, curve(u)) * (1 + wob(u));
    const sy = u => lerp(from.sy, to.sy, curve(u)) * (1 - wob(u));
    // Keep the box's centre on a straight path while it scales.
    const cx0 = from.tx + w * from.sx / 2, cy0 = from.ty + h * from.sy / 2;
    const cx1 = to.tx + w * to.sx / 2, cy1 = to.ty + h * to.sy / 2;
    const path = to.path ?? curve;
    return {
        'scale-x': sx,
        'scale-y': sy,
        'translation-x': u => lerp(cx0, cx1, path(u)) - w * sx(u) / 2,
        'translation-y': u => lerp(cy0, cy1, path(u)) - h * sy(u) / 2,
        'opacity': opacity,
    };
}

/** A window that fills its monitor, or sits against an edge, must not grow past it. */
function againstEdge(win) {
    if (win.is_monitor_sized?.() || win.get_maximized?.())
        return true;
    // Mutter aborts if asked for the work area of a window with no monitor yet (one just mapped).
    const mon = win.get_monitor();
    if (mon < 0 || mon >= Main.layoutManager.monitors.length)
        return true;
    const f = win.get_frame_rect();
    const wa = Main.layoutManager.getWorkAreaForMonitor(mon);
    return f.x <= wa.x + 1 || f.y <= wa.y + 1 || f.x + f.width >= wa.x + wa.width - 1 ||
        f.y + f.height >= wa.y + wa.height - 1;
}

function capped(fn, cap) {
    return cap ? u => Math.min(1, fn(u)) : fn;
}

// ---- genie ------------------------------------------------------------------------

// Each pixel of the copy looks up where in the window it comes from: rows nearer the
// icon travel first, and each row narrows towards the icon (curves.js genieWarp is
// the same maths run forwards). Inverting it per pixel needs no mesh.
const GENIE_SHADER = `
uniform sampler2D tex;
uniform float tex_w, tex_h, org_x, org_y;
uniform float win_x, win_y, win_w, win_h, ico_x, ico_y, ico_w, ico_h;
uniform float progress, pinch, vertical, toward;

float rowAt(float along, out float rb) {
    float near = toward > 0.5 ? along : 1.0 - along;
    float r = clamp(progress * 2.0 - (1.0 - near), 0.0, 1.0);
    rb = 1.0 - pow(1.0 - r, pinch);
    return r * r * (3.0 - 2.0 * r);
}

void main() {
    vec2 px = cogl_tex_coord_in[0].st * vec2(tex_w, tex_h) - vec2(org_x, org_y);
    bool v = vertical > 0.5;
    float pa = v ? px.y : px.x, pb = v ? px.x : px.y;
    float wa0 = v ? win_y : win_x, wal = v ? win_h : win_w, wb0 = v ? win_x : win_y, wbl = v ? win_w : win_h;
    float ia0 = v ? ico_y : ico_x, ial = v ? ico_h : ico_w, ib0 = v ? ico_x : ico_y, ibl = v ? ico_w : ico_h;
    // Which row of the window lands here: rows keep their order, so search.
    float lo = 0.0, hi = 1.0, rb = 0.0;
    float a0 = 0.0, a1 = 0.0;
    float rb0;
    float ra0 = rowAt(0.0, rb0);
    a0 = wa0 + (ia0 - wa0) * ra0;
    float ra1 = rowAt(1.0, rb0);
    a1 = wa0 + wal + (ia0 + ial - wa0 - wal) * ra1;
    if (pa < min(a0, a1) - 0.5 || pa > max(a0, a1) + 0.5) {
        cogl_color_out = vec4(0.0);
        return;
    }
    for (int i = 0; i < 14; i++) {   // to 1/16384 of the window: under a px
        float m = 0.5 * (lo + hi);
        float ra = rowAt(m, rb);
        float a = wa0 + m * wal + (ia0 + m * ial - wa0 - m * wal) * ra;
        if (a < pa) lo = m; else hi = m;
    }
    float along = 0.5 * (lo + hi);
    rowAt(along, rb);
    // Across the row the warp is a straight scale towards the icon: undo it.
    float k = 1.0 - rb + rb * ibl / wbl;
    float b = (pb - rb * (ib0 - wb0 * ibl / wbl)) / max(k, 1e-4);
    float across = (b - wb0) / wbl;
    float edge = min(across, 1.0 - across) * wbl * k;   // px from the side, after the warp
    if (edge < -1.0) {
        cogl_color_out = vec4(0.0);
        return;
    }
    vec2 src = v ? vec2(b, wa0 + along * wal) : vec2(wa0 + along * wal, b);
    vec4 c = texture2D(tex, (src + vec2(org_x, org_y)) / vec2(tex_w, tex_h));
    cogl_color_out = c * clamp(edge + 1.0, 0.0, 1.0) * cogl_color_in.a;
}
`;

const GenieEffect = GObject.registerClass(
class LiquidGlassGenie extends Clutter.ShaderEffect {
    _init(win, icon, intensity) {
        super._init();
        // Per instance: a static (per-class) shader shares its uniforms between
        // copies on GNOME 50, so two overlapping minimizes would cross-wire.
        this.set_shader_source(GENIE_SHADER);
        this._frame = '';
        const vertical = Math.abs(icon.y + icon.height / 2 - win.y - win.height / 2) >=
            Math.abs(icon.x + icon.width / 2 - win.x - win.width / 2);
        const toward = vertical ? icon.y + icon.height / 2 > win.y + win.height / 2
            : icon.x + icon.width / 2 > win.x + win.width / 2;
        this._set({win_x: win.x, win_y: win.y, win_w: win.width, win_h: win.height,
            ico_x: icon.x, ico_y: icon.y, ico_w: Math.max(1, icon.width), ico_h: Math.max(1, icon.height),
            pinch: C.geniePinch(intensity), vertical: vertical ? 1 : 0, toward: toward ? 1 : 0, progress: 0});
    }

    _set(values) {
        // A whole number would reach GL as an int uniform; nudge it to a float.
        for (const [k, v] of Object.entries(values))
            this.set_uniform_value(k, Number.isInteger(v) ? v + 1e-6 : v);
    }

    setProgress(p) {
        this.progress = p;   // read by the QA tools
        this._set({progress: p});
        this.queue_repaint();
    }

    vfunc_paint_target(node, paintContext) {
        // As in glass.js: map the texture onto the actor exactly.
        const t = this.get_texture();
        const a = this.get_actor();
        if (t && a) {
            const [w, h] = [t.get_width(), t.get_height()];
            const key = `${w}x${h}/${a.width}x${a.height}`;
            if (key !== this._frame) {
                this._frame = key;
                this._set({tex_w: w, tex_h: h, org_x: Math.ceil((w - a.width) / 2), org_y: Math.ceil((h - a.height) / 2)});
            }
        }
        super.vfunc_paint_target(node, paintContext);
    }
});

/**
 * The genie warp, drawn on a copy of the window: the window itself stays in place,
 * unseen, until the effect is over. p runs from p0 to p1. The copy sits just above
 * the windows and under the panels, so it pours into and out of the icon from
 * behind the panel, as the real window does, and nothing changes order at the end.
 */
function genie(actor, iconRect, p0, p1, ms, intensity, onDone) {
    const win = {x: actor.x, y: actor.y, width: actor.width, height: actor.height};
    const box = C.union(win, iconRect);
    const holder = new Clutter.Actor({name: 'liquid-glass-genie', reactive: false,
        x: box.x, y: box.y, width: box.width, height: box.height});
    const clone = new Clutter.Clone({source: actor, reactive: false,
        x: win.x - box.x, y: win.y - box.y, width: win.width, height: win.height});
    holder.add_child(clone);
    const local = r => ({x: r.x - box.x, y: r.y - box.y, width: r.width, height: r.height});
    const effect = new GenieEffect(local(win), local(iconRect), intensity);
    effect.setProgress(p0);
    holder.add_effect_with_name('liquid-glass-genie', effect);
    const ui = Main.layoutManager.uiGroup;
    ui.add_child(holder);
    const windows = global.window_group?.get_parent() === ui ? global.window_group : null;
    if (windows)
        ui.set_child_above_sibling(holder, windows);
    // Going in it speeds up a little towards the icon; coming out it slows as it lands.
    const ease = p1 > p0 ? u => Math.pow(u, 1.2) : C.easeOut;
    const fade = p1 > p0 ? 0.88 : 0.12;   // the last bit melts into the icon
    const opacity = u => {
        const p = lerp(p0, p1, ease(u));
        return 255 * Math.min(1, Math.max(0, (1 - p) / (1 - fade) * 1));
    };
    // The window itself stays unseen while the copy plays. An unseen actor gets no
    // frames, so the copy runs the clock; a guard on the window lets GNOME stopping
    // the window's effects stop this too.
    actor.opacity = 0;
    const guard = new Clutter.PropertyTransition({property_name: 'opacity', duration: ms * 4 + WATCHDOG_MIN_MS,
        remove_on_complete: true});
    guard.set_from(0);
    guard.set_to(0);
    let anim = null;
    const fns = {'opacity': u => opacity(u)};
    freezeSource(actor);
    anim = animate(holder, ms, fns, (finished, a) => {
        guards.delete(actor);
        thawSource(actor);
        try {
            actor.remove_transition('liquid-glass-guard');
        } catch {}
        try {
            holder.destroy();
        } catch {}
        onDone(finished, a);
    });
    guards.set(actor, anim);
    guard.connect('stopped', () => {
        if (!anim.done)
            finish(anim, false);
    });
    actor.add_transition('liquid-glass-guard', guard);
    anim.onFrame = u => effect.setProgress(lerp(p0, p1, ease(u)));
    // If the shader is too heavy for this machine (3 of the first 10 frames over
    // budget), the rest of this one animation scales the copy towards the icon instead.
    const budget = {last: 0, frames: 0, slow: 0};
    const fallBack = () => {
        genieFallbacks++;
        holder.remove_effect(effect);
        const w0 = local(win), w1 = local(iconRect);
        clone.set_pivot_point(0, 0);
        anim.onFrame = u => {
            const q = lerp(p0, p1, ease(u));
            clone.set_scale(lerp(1, w1.width / w0.width, q), lerp(1, w1.height / w0.height, q));
            clone.set_translation(lerp(0, w1.x - w0.x, q), lerp(0, w1.y - w0.y, q), 0);
        };
    };
    anim.onTick = () => {
        if (!frameBudget || budget.frames >= GENIE_BUDGET_FRAMES)
            return;
        const now = GLib.get_monotonic_time();
        // The first frame also builds the shader: it isn't counted.
        if (budget.last && now - budget.last > GENIE_FRAME_BUDGET_US && ++budget.slow === GENIE_SLOW_FRAMES)
            fallBack();
        budget.last = now;
        budget.frames++;
    };
    effect.setProgress(p0);
    return anim;
}

// ---- windows ------------------------------------------------------------------------

class WindowAnimations {
    constructor(owner) {
        this._owner = owner;
        this._blocked = [];     // GNOME's own handlers, blocked while ours run
        this._ids = [];
        this._cut = new WeakMap();   // actor -> where its minimize was cut short, and when
        this._stocked = new WeakSet();   // actors whose current event GNOME's own code took
    }

    get motion() {
        return this._owner.motion;
    }

    sync() {
        const want = ['open', 'minimize', 'close'].some(ev => this.motion[ev].preset !== 'gnome');
        if (want && !this._ids.length)
            this._install();
        else if (!want && this._ids.length)
            this._uninstall();
    }

    _install() {
        const missing = [...WM_METHODS.filter(n => typeof Main.wm?.[n] !== 'function'),
            ...WM_SETS.filter(n => typeof Main.wm?.[n]?.has !== 'function')];
        if (missing.length) {
            if (!this._warned)
                log(`Liquid Glass: this GNOME has no ${missing.join(', ')}; leaving window animations to GNOME`);
            this._warned = true;
            return;
        }
        const wm = global.window_manager;
        const found = [];
        for (const name of WM_SIGNALS) {
            // GNOME's window manager connected first, at startup: its handler is the first one.
            const id = GObject.signal_handler_find(wm, {signalId: name});
            if (!id) {
                log(`Liquid Glass: GNOME's '${name}' window handler wasn't found; leaving window animations to GNOME`);
                return;
            }
            found.push(id);
        }
        for (const id of found)
            GObject.signal_handler_block(wm, id);
        this._blocked = found;
        this._ids = [
            wm.connect('map', (shellwm, actor) => this._run('open', shellwm, actor)),
            wm.connect('minimize', (shellwm, actor) => this._run('minimize', shellwm, actor)),
            wm.connect('unminimize', (shellwm, actor) => this._run('unminimize', shellwm, actor)),
            wm.connect('destroy', (shellwm, actor) => this._run('close', shellwm, actor)),
        ];
    }

    _uninstall() {
        const wm = global.window_manager;
        for (const id of this._ids)
            wm.disconnect(id);
        this._ids = [];
        for (const id of this._blocked) {
            try {
                GObject.signal_handler_unblock(wm, id);
            } catch {}
        }
        this._blocked = [];
    }

    // GNOME's own handling for this event, with or without its animation.
    _stock(kind, shellwm, actor, animated) {
        const wm = Main.wm;
        if (!animated)
            wm._skippedActors.add(actor);
        const fn = {open: '_mapWindow', minimize: '_minimizeWindow', unminimize: '_unminimizeWindow',
            close: '_destroyWindow'}[kind];
        const ret = wm[fn](shellwm, actor);
        this._stocked.add(actor);   // GNOME has the event now
        return ret;
    }

    _choice(kind, actor) {
        const wm = Main.wm;
        const ev = kind === 'unminimize' ? 'minimize' : kind;
        const m = this.motion[ev];
        if (m.preset === 'gnome' || m.preset === 'off')
            return m.preset;
        // Everything GNOME wouldn't animate, or animates its own way, stays with GNOME.
        if (!animationsOn() || wm._skippedActors.has(actor) || !wm._shouldAnimate() || !actor.get_texture?.() ||
            !actor.meta_window || wm._getAnimationWindowType(actor) !== Meta.WindowType.NORMAL)
            return 'gnome';
        // Still in an earlier effect (Mutter normally ends it first).
        if (wm._minimizing.has(actor) || wm._unminimizing.has(actor) || wm._mapping.has(actor) ||
            wm._destroying.has(actor))
            return 'skip';
        return m.preset;
    }

    // End whatever effect the window is still in, through GNOME's own done
    // path, so Mutter hears it finished before the next one starts.
    _finishEarlier(shellwm, actor) {
        const wm = Main.wm;
        stop(actor, false);
        if (wm._mapping.has(actor))
            wm._mapWindowDone(shellwm, actor);
        if (wm._minimizing.has(actor))
            wm._minimizeWindowDone(shellwm, actor);
        if (wm._unminimizing.has(actor))
            wm._unminimizeWindowDone(shellwm, actor);
        if (wm._destroying.has(actor))
            wm._destroyWindowDone(shellwm, actor);
    }

    _run(kind, shellwm, actor) {
        let choice = null;
        this._stocked.delete(actor);
        try {
            choice = this._choice(kind, actor);
            if (choice === 'skip') {
                this._finishEarlier(shellwm, actor);
                choice = this._choice(kind, actor);
                if (choice === 'skip')
                    choice = 'off';   // never leave the event unhandled
            }
            if (choice === 'gnome' || choice === 'off') {
                this._stock(kind, shellwm, actor, choice === 'gnome');
                return;
            }
            const ev = kind === 'unminimize' ? 'minimize' : kind;
            const m = this.motion[ev];
            this[`_${kind}`](shellwm, actor, m);
        } catch (e) {
            logError(e, `Liquid Glass: ${kind} animation`);
            this._rescue(kind, shellwm, actor, choice);
        }
    }

    // Something went wrong: make sure the window's effect still finishes. Whatever
    // already holds the event finishes it; if nothing does, GNOME's own code takes
    // it without animating, and if even that fails, Mutter is told it is done.
    _rescue(kind, shellwm, actor, choice) {
        const wm = Main.wm;
        try {
            stop(actor, false);
        } catch {}
        try {
            if (kind === 'open' && wm._mapping?.has(actor))
                wm._mapWindowDone(shellwm, actor);
            else if (kind === 'minimize' && wm._minimizing?.has(actor))
                wm._minimizeWindowDone(shellwm, actor);
            else if (kind === 'unminimize' && wm._unminimizing?.has(actor))
                wm._unminimizeWindowDone(shellwm, actor);
            else if (kind === 'close' && wm._destroying?.has(actor))
                wm._destroyWindowDone(shellwm, actor);
            else if (!this._stocked.has(actor))
                this._stock(kind, shellwm, actor, false);
        } catch (e) {
            logError(e, `Liquid Glass: GNOME couldn't finish the ${kind} (${choice ?? 'no choice'}); ending it`);
            try {
                shellwm[COMPLETED[kind]](actor);
            } catch (e2) {
                logError(e2, 'Liquid Glass: ending a window effect');
            }
        }
        try {
            reset(actor);
        } catch {}
    }

    _iconRect(actor) {
        const [ok, geom] = actor.meta_window.get_icon_geometry();
        if (ok && geom.width > 0 && geom.height > 0)
            return {x: geom.x, y: geom.y, width: geom.width, height: geom.height};
        return null;
    }

    // With no taskbar icon for the window: the middle of the bottom of its screen, where the panel is.
    _fallbackRect(actor) {
        const mon = Main.layoutManager.monitors[actor.meta_window.get_monitor()] ?? Main.layoutManager.primaryMonitor;
        const s = 48;
        let y = mon.y + mon.height - s;
        const dtp = global.dashToPanel?.panels?.find(p => p.monitor === mon);
        if (dtp?.panelBox) {
            const [, py] = dtp.panelBox.get_transformed_position();
            if (Number.isFinite(py) && py < mon.y + mon.height / 2)
                y = mon.y;   // the panel is at the top
        }
        return {x: mon.x + mon.width / 2 - s / 2, y, width: s, height: s};
    }

    // ---- open ----
    _open(shellwm, actor, m) {
        // GNOME's own map handling first (dimming for dialogs and so on), without its animation.
        this._stock('open', shellwm, actor, false);
        const win = actor.meta_window;
        const ms = C.duration('open', m.preset, m.speed);
        const icon = m.preset === 'genie' ? this._iconRect(actor) : null;
        if (m.preset === 'genie' && icon && !win.is_monitor_sized()) {
            genie(actor, icon, 1, 0, ms, m.intensity, () => reset(actor));
            return;
        }
        const preset = m.preset === 'genie' ? 'spring' : m.preset;
        const s0 = C.startScale(preset, m.intensity);
        const {width: w, height: h} = actor;
        const from = {sx: s0, sy: s0, tx: w * (1 - s0) / 2, ty: h * (1 - s0) / 2};
        const curve = capped(C.curve(preset, m.intensity), againstEdge(win));
        const fade = C.easeOut;
        // Never fully clear: an actor at opacity 0 gets no frames, and its animation would stall.
        actor.opacity = 1;
        animate(actor, ms, moveFns(actor, from, {sx: 1, sy: 1, tx: 0, ty: 0}, curve,
            C.wobble(preset, m.intensity), u => Math.max(1, 255 * fade(Math.min(1, u * 2.2)))), () => reset(actor));
    }

    // ---- minimize ----
    _minimize(shellwm, actor, m) {
        const wm = Main.wm;
        const win = actor.meta_window;
        wm._minimizing.add(actor);
        const done = (finished, anim) => {
            if (!finished && anim?.cut)
                this._cut.set(actor, {at: GLib.get_monotonic_time(), state: visual(actor), cut: anim.cut});
            actor.translation_x = actor.translation_y = 0;
            wm._minimizeWindowDone(shellwm, actor);   // resets the rest and tells the window manager
            if (finished)
                this._owner.panel?.landed(win);
        };
        const ms = C.duration('minimize', m.preset, m.speed);
        const icon = this._iconRect(actor) ?? this._fallbackRect(actor);
        if (win.is_monitor_sized()) {
            animate(actor, ms, {'opacity': u => 255 * (1 - C.easeOut(u))}, done);
            return;
        }
        if (m.preset === 'genie') {
            genie(actor, icon, 0, 1, ms, m.intensity, done);
            return;
        }
        const from = visual(actor);
        // The window travels in without passing the icon; the preset shapes its size,
        // which can dip below the icon's and come back (the bounce lands in the icon).
        const curve = m.preset === 'scalefade' ? C.easeInOut : C.curve(m.preset, m.intensity);
        const to = {sx: icon.width / actor.width, sy: icon.height / actor.height,
            tx: icon.x - actor.x, ty: icon.y - actor.y, path: u => Math.min(1, curve(u))};
        const fns = moveFns(actor, from, to, curve, C.wobble(m.preset, m.intensity),
            u => from.op * (1 - C.easeIn(Math.max(0, (u - 0.55) / 0.45))));
        animate(actor, ms, fns, done);
    }

    // ---- restore ----
    _unminimize(shellwm, actor, m) {
        const wm = Main.wm;
        const win = actor.meta_window;
        wm._unminimizing.add(actor);
        const done = () => {
            actor.translation_x = actor.translation_y = 0;
            wm._unminimizeWindowDone(shellwm, actor);
        };
        const ms = C.duration('minimize', m.preset, m.speed);
        const icon = this._iconRect(actor) ?? this._fallbackRect(actor);
        if (win.is_monitor_sized()) {
            actor.opacity = 1;
            actor.show();
            animate(actor, ms, {'opacity': u => Math.max(1, 255 * C.easeOut(u))}, done);
            return;
        }
        if (m.preset === 'genie') {
            actor.show();
            genie(actor, icon, 1, 0, ms, m.intensity, done);
            return;
        }
        // Restored right after a minimize was cut short: carry on from where it was.
        const cut = this._cut.get(actor);
        this._cut.delete(actor);
        const recent = cut && (GLib.get_monotonic_time() - cut.at) / 1000 < RETARGET_MS;
        const from = recent
            ? {sx: cut.cut['scale-x'], sy: cut.cut['scale-y'], tx: cut.cut['translation-x'], ty: cut.cut['translation-y'],
                op: cut.cut.opacity}
            : {sx: icon.width / actor.width, sy: icon.height / actor.height, tx: icon.x - actor.x, ty: icon.y - actor.y,
                op: 0};
        from.tx = from.tx ?? 0;
        from.ty = from.ty ?? 0;
        const curve = capped(m.preset === 'scalefade' ? C.easeOut : C.curve(m.preset, m.intensity), againstEdge(win));
        const fns = moveFns(actor, from, {sx: 1, sy: 1, tx: 0, ty: 0, path: u => Math.min(1, curve(u))}, curve,
            C.wobble(m.preset, m.intensity), u => Math.max(1, lerp(from.op ?? 0, 255, C.easeOut(Math.min(1, u * 2.5)))));
        // Start on the first frame where it was, not where GNOME left it.
        for (const [prop, fn] of Object.entries(safeFns(actor, fns)))
            actor[FIELD[prop]] = prop === 'opacity' ? Math.round(fn(0)) : fn(0);
        actor.set_pivot_point(0, 0);
        actor.show();
        animate(actor, ms, fns, done);
    }

    // ---- close ----
    _close(shellwm, actor, m) {
        const wm = Main.wm;
        const win = actor.meta_window;
        // What GNOME's own destroy handler does before animating a plain window.
        win.disconnectObject?.(actor);
        wm._destroying.add(actor);
        const done = () => wm._destroyWindowDone(shellwm, actor);
        const ms = C.duration('close', m.preset, m.speed);
        if (m.preset === 'genie') {
            const icon = this._iconRect(actor);
            if (icon && !win.is_monitor_sized()) {
                genie(actor, icon, 0, 1, ms, m.intensity, done);
                return;
            }
        }
        const from = visual(actor);
        const s1 = m.preset === 'spring' ? C.startScale('spring', m.intensity) : C.startScale('scalefade', m.intensity);
        const {width: w, height: h} = actor;
        const to = {sx: s1, sy: s1, tx: w * (1 - s1) / 2, ty: h * (1 - s1) / 2};
        // A close settles without bouncing.
        const curve = m.preset === 'spring' ? C.spring(0) : C.easeOut;
        animate(actor, ms, moveFns(actor, from, to, curve, () => 0,
            u => from.op * (1 - C.easeOut(u))), done);
    }

    /** Reduce animation was turned on, or we're being turned off: every window lands now. */
    finishAll() {
        for (const actor of [...running.keys()])
            stop(actor, true);
    }

    destroy() {
        try {
            this.finishAll();
        } finally {
            this._uninstall();
        }
    }
}

function reset(actor) {
    try {
        actor.set_pivot_point(0, 0);
        actor.set_scale(1, 1);
        actor.translation_x = actor.translation_y = 0;
        actor.opacity = 255;
    } catch {}   // gone
}

// ---- the panel: hover and launch bounce -------------------------------------------

/** Where the taskbar and panel items are, under Dash to Panel or GNOME's own top bar. */
function panels() {
    const dtp = global.dashToPanel?.panels;
    return Array.isArray(dtp) && dtp.length ? dtp : [];
}

function appIcons() {
    const out = [];
    for (const p of panels()) {
        try {
            out.push(...(p.taskbar?._getAppIcons?.() ?? []));
        } catch {}
    }
    return out;
}

// The part of an item that moves: inside what Dash to Panel or GNOME positions,
// so the click area stays where it is.
function inner(item) {
    return item._iconContainer ?? item.get_first_child?.() ?? null;
}

function statusButtons() {
    const out = new Set();
    const areas = [Main.panel?.statusArea, ...panels().map(p => p.statusArea)];
    for (const area of areas) {
        for (const b of Object.values(area ?? {})) {
            if (b instanceof St.Widget && b.has_style_class_name?.('panel-button') && !b.has_style_class_name('panel-button-hidden'))
                out.add(b);
        }
    }
    return [...out];
}

class PanelAnimations {
    constructor(owner) {
        this._owner = owner;
        this._signals = new Signals();
        this._watched = new Map();    // item -> {signals, target}
        this._launching = new Map();  // app -> {icons, timer, start}
        this._apps = Shell.AppSystem.get_default();
        this._appSignals = new Signals();
        this._dtpId = 0;
        this._refreshLater = 0;
    }

    get motion() {
        return this._owner.motion;
    }

    sync() {
        const hover = this.motion.hover.preset !== 'off';
        const launch = this.motion.launch.preset !== 'off';
        if (hover)
            this._watchHover();
        else
            this._unwatchHover();
        if (launch && !this._appSignals._ids.length)
            this._appSignals.on(this._apps, 'app-state-changed', (_s, app) => this._appState(app));
        else if (!launch && this._appSignals._ids.length) {
            this._appSignals.clear();
            for (const app of [...this._launching.keys()])
                this._endLaunch(app, false);
        }
        // Dash to Panel builds its panels again when its settings change.
        if ((hover || launch) && !this._dtpId && global.dashToPanel?.connect)
            this._dtpId = global.dashToPanel.connect('panels-created', () => this._queueRefresh());
    }

    _queueRefresh() {
        if (this._refreshLater)
            return;
        this._refreshLater = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this._refreshLater = 0;
            if (this.motion.hover.preset !== 'off') {
                this._unwatchHover();
                this._watchHover();
            }
            return GLib.SOURCE_REMOVE;
        });
    }

    // ---- hover ----
    _watchHover() {
        const items = [...appIcons(), ...statusButtons()];
        const keep = new Set(items);
        for (const item of [...this._watched.keys()]) {
            if (!keep.has(item))
                this._unwatch(item);
        }
        for (const item of items) {
            if (this._watched.has(item))
                continue;
            const target = inner(item);
            if (!target)
                continue;
            const signals = new Signals();
            signals.on(item, 'notify::hover', () => this._hover(item));
            const w = {signals, target, gone: false};
            // ArcMenu rebuilds its button by destroying it: its inner widget goes
            // first, and touching it after that only fills the log.
            signals.on(target, 'destroy', () => {
                signals.forget(target);
                w.gone = true;
                stop(target, false);
            });
            signals.on(item, 'destroy', () => {
                signals.forget(item);
                this._unwatch(item);
            });
            this._watched.set(item, w);
        }
        // New taskbar icons come and go with apps: look again when they do.
        if (!this._taskbarIds) {
            this._taskbarIds = new Signals();
            this._taskbarIds.on(this._apps, 'installed-changed', () => this._queueRefresh());
            this._taskbarIds.on(Shell.WindowTracker.get_default(), 'tracked-windows-changed', () => this._queueRefresh());
        }
    }

    _unwatch(item) {
        const w = this._watched.get(item);
        if (!w)
            return;
        this._watched.delete(item);
        w.signals.clear();
        if (w.gone)
            return;
        stop(w.target, false);
        reset(w.target);
    }

    _unwatchHover() {
        for (const item of [...this._watched.keys()])
            this._unwatch(item);
        this._taskbarIds?.clear();
        this._taskbarIds = null;
    }

    // Dash to Panel has its own hover animation; when it is on, its icons are left to it.
    _dtpAnimates(item) {
        return item._container?.has_style_class_name?.('animate-appicon-hover') ?? false;
    }

    _hover(item) {
        const w = this._watched.get(item);
        if (!w || w.gone || this._launchingIcon(item))
            return;
        const m = this.motion.hover;
        if (!animationsOn() || m.preset === 'off' || this._dtpAnimates(item)) {
            stop(w.target, false);
            reset(w.target);
            return;
        }
        const t = w.target;
        if (!t.get_stage())
            return;
        const on = item.hover;
        const goal = on ? C.hoverTarget(m.intensity) : {scale: 1, lift: 0};
        const from = visual(t);
        const {width: tw, height: th} = t;
        const curve = on ? C.curve(m.preset, m.intensity) : C.spring(m.preset === 'scalefade' ? 0 : m.intensity * 0.5);
        const jelly = C.wobble(m.preset, m.intensity);
        const wob = on ? u => C.HOVER_SQUASH * jelly(u) : () => 0;
        const to = {sx: goal.scale, sy: goal.scale, tx: tw * (1 - goal.scale) / 2, ty: th * (1 - goal.scale) / 2 - goal.lift};
        const ms = on ? C.duration('hover', m.preset, m.speed) : C.hoverOutDuration(m.speed);
        const fns = moveFns(t, from, to, curve, wob, null);
        delete fns.opacity;
        animate(t, ms, fns, null);
    }

    // ---- launch ----
    _launchingIcon(item) {
        for (const l of this._launching.values()) {
            if (l.icons.includes(item))
                return true;
        }
        return false;
    }

    _appState(app) {
        if (app.state === Shell.AppState.STARTING)
            this._startLaunch(app);
        else if (this._launching.has(app))
            this._endLaunch(app, true);
    }

    _startLaunch(app) {
        if (this._launching.has(app) || !animationsOn())
            return;   // one bounce per app at a time
        const icons = appIcons().filter(i => i.app === app && inner(i)?.get_stage());
        if (!icons.length)
            return;
        const l = {icons, start: GLib.get_monotonic_time(), timer: 0};
        this._launching.set(app, l);
        // Never longer than 5 s, even if the app never shows a window.
        l.timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, C.LAUNCH_CAP_MS, () => {
            l.timer = 0;
            this._endLaunch(app, true);
            return GLib.SOURCE_REMOVE;
        });
        for (const icon of icons)
            this._hop(app, inner(icon));
    }

    _hop(app, target) {
        const l = this._launching.get(app);
        if (!l || !target.get_stage())
            return;
        const m = this.motion.launch;
        const hop = C.launchHop(m.preset);
        const height = C.launchHeight(m.intensity);
        const {width: w, height: h} = target;
        const sq = u => 0.08 * hop.squash(u);
        const fns = {
            'scale-x': u => 1 + sq(u),
            'scale-y': u => 1 - sq(u),
            'translation-x': u => -w * sq(u) / 2,
            'translation-y': u => h * sq(u) - height * hop.lift(u),
        };
        animate(target, C.duration('launch', m.preset, m.speed), fns, finished => {
            if (finished && this._launching.get(app) === l)
                this._hop(app, target);
        });
    }

    _endLaunch(app, settle) {
        const l = this._launching.get(app);
        if (!l)
            return;
        this._launching.delete(app);
        if (l.timer)
            GLib.source_remove(l.timer);
        l.timer = 0;
        for (const icon of l.icons) {
            const t = inner(icon);
            if (!t)
                continue;
            if (!settle || !animationsOn() || !t.get_stage()) {
                stop(t, false);
                reset(t);
                continue;
            }
            // Land softly from wherever the hop is.
            const fns = moveFns(t, visual(t), {sx: 1, sy: 1, tx: 0, ty: 0}, C.spring(0.3), () => 0, null);
            delete fns.opacity;
            animate(t, C.hoverOutDuration(this.motion.launch.speed) * 1.4, fns, () => reset(t));
        }
    }

    /** A window just landed in its taskbar icon: the icon gives a little. */
    landed(win) {
        const m = this.motion.minimize;
        if (!animationsOn() || !['bounce', 'jelly', 'spring'].includes(m.preset))
            return;
        const app = Shell.WindowTracker.get_default().get_window_app(win);
        for (const icon of appIcons().filter(i => i.app === app)) {
            const t = inner(icon);
            if (!t?.get_stage() || running.has(t))
                continue;
            const {width: w, height: h} = t;
            const amp = 0.1 * m.intensity;
            const wob = C.wobble('jelly', 1);
            const sq = m.preset === 'jelly' ? u => 0.6 * m.intensity * wob(u) : u => -amp * Math.sin(Math.PI * u) * (1 - u);
            const dip = m.preset === 'bounce' ? u => 3 * m.intensity * Math.abs(Math.sin(2 * Math.PI * u)) * (1 - u) : () => 0;
            // The panel's glass keeps its picture while the icon gives (see glass.js holdPanes).
            holdPanes(t);
            animate(t, 320 / m.speed, {
                'scale-x': u => 1 + sq(u),
                'scale-y': u => 1 - sq(u),
                'translation-x': u => -w * sq(u) / 2,
                'translation-y': u => h * sq(u) - dip(u),
            }, () => {
                releasePanes(t);
                reset(t);
            });
        }
    }

    finishAll() {
        for (const app of [...this._launching.keys()])
            this._endLaunch(app, false);
        for (const w of this._watched.values()) {
            if (w.gone)
                continue;
            stop(w.target, false);
            reset(w.target);
        }
    }

    destroy() {
        if (this._refreshLater)
            GLib.source_remove(this._refreshLater);
        this._refreshLater = 0;
        if (this._dtpId) {
            try {
                global.dashToPanel?.disconnect(this._dtpId);
            } catch {}
        }
        this._dtpId = 0;
        this._appSignals.clear();
        this.finishAll();
        this._unwatchHover();
        this._signals.clear();
    }
}

export class Animations {
    constructor(cfg) {
        this.motion = cfg.animations;
        this.windows = new WindowAnimations(this);
        this.panel = new PanelAnimations(this);
        this._settings = St.Settings.get();
        // Reduce animation: everything lands where it is going, at once.
        this._animId = this._settings.connect('notify::enable-animations', () => {
            if (!animationsOn())
                this.finishAll();
        });
        this.update(cfg);
    }

    update(cfg) {
        this.motion = cfg.animations;
        this.windows.sync();
        this.panel.sync();
    }

    finishAll() {
        this.windows.finishAll();
        this.panel.finishAll();
        for (const actor of [...running.keys()])
            stop(actor, true);
    }

    destroy() {
        // GNOME's own window handlers come back first, whatever happens after.
        try {
            this.windows.destroy();
        } finally {
            try {
                if (this._animId)
                    this._settings.disconnect(this._animId);
                this._animId = 0;
                this.panel.destroy();
            } finally {
                for (const actor of [...running.keys()])
                    stop(actor, true);
            }
        }
    }
}

// For QA: how many genie animations fell back to scaling, and a switch for the
// frame budget (frame strips on software rendering would always trip it).
export function qaGenie(budget = null) {
    if (budget !== null)
        frameBudget = Boolean(budget);
    return {fallbacks: genieFallbacks, budget: frameBudget, clamps: clampCount};
}

// For QA: how many animations are running now (0 when idle).
export function runningCount() {
    return running.size;
}

// For QA frame strips on slow (software) rendering: hold every running animation
// at time u, so each frame can be captured exactly. qaRelease() lets them land.
export function qaSeek(u) {
    for (const actor of guards.keys())
        actor.get_transition('liquid-glass-guard')?.pause();
    for (const anim of running.values()) {
        if (anim.watchdog)
            GLib.source_remove(anim.watchdog);
        anim.watchdog = 0;
        for (const [, t] of anim.transitions)
            t.pause();
        anim.timeline?.pause();
        setAt(anim, u);
        anim.onFrame?.(u);
    }
}

export function qaRelease() {
    for (const actor of [...running.keys()])
        stop(actor, true);
}
