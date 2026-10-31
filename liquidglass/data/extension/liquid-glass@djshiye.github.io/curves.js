// The shapes of Liquid Glass's window and panel animations, as plain maths: no
// GNOME imports, so the tests can run it with gjs alone (tests/js/curves.test.js).
//
// Every curve maps time u (0 at the start, 1 at the end) to progress (0 → 1).
// Intensity (0..1) sets how lively a curve is: 0 settles without overshoot, 1
// overshoots by at most 15% of the distance travelled. Speed (0.5..2) divides
// the duration; at 1x nothing a click starts takes longer than 600 ms.

export const EVENTS = ['open', 'minimize', 'close', 'launch', 'hover'];

// What each event can be set to. 'gnome' hands the event back to GNOME's own
// animation, 'off' makes it instant. A close never bounces: it is a dismissal.
export const PRESETS = Object.freeze({
    open: ['gnome', 'spring', 'bounce', 'jelly', 'genie', 'scalefade', 'off'],
    minimize: ['gnome', 'spring', 'bounce', 'jelly', 'genie', 'scalefade', 'off'],
    close: ['gnome', 'scalefade', 'spring', 'genie', 'off'],
    launch: ['bounce', 'spring', 'jelly', 'off'],
    hover: ['spring', 'bounce', 'jelly', 'scalefade', 'off'],
});

export const DEFAULT_MOTION = Object.freeze({
    open: Object.freeze({preset: 'spring', intensity: 0.5, speed: 1}),
    minimize: Object.freeze({preset: 'genie', intensity: 0.5, speed: 1}),
    close: Object.freeze({preset: 'scalefade', intensity: 0.5, speed: 1}),
    launch: Object.freeze({preset: 'bounce', intensity: 0.5, speed: 1}),
    hover: Object.freeze({preset: 'spring', intensity: 0.5, speed: 1}),
});

export const MAX_OVERSHOOT = 0.15;
export const SPEED_MIN = 0.5;
export const SPEED_MAX = 2;
export const LAUNCH_CAP_MS = 5000;

// Duration of each preset at 1x, in ms.
const DURATION = {spring: 380, bounce: 550, jelly: 500, genie: 450, scalefade: 220};
const CLOSE_DURATION = {scalefade: 200, spring: 260, genie: 400};
const HOVER_IN = 220;
const HOVER_OUT = 180;
export const LAUNCH_PERIOD = 600;

function clamp(v, lo = 0, hi = 1) {
    return Math.min(hi, Math.max(lo, v));
}

function num(v, fallback, lo, hi) {
    return typeof v === 'number' && Number.isFinite(v) ? clamp(v, lo, hi) : fallback;
}

/** The animation settings from the config file: unknown names fall back to the defaults, numbers are clamped. */
export function cleanMotion(raw) {
    const src = raw && typeof raw === 'object' ? raw : {};
    const out = {};
    for (const ev of EVENTS) {
        const def = DEFAULT_MOTION[ev];
        const r = src[ev] && typeof src[ev] === 'object' ? src[ev] : {};
        out[ev] = {
            preset: PRESETS[ev].includes(r.preset) ? r.preset : def.preset,
            intensity: num(r.intensity, def.intensity, 0, 1),
            speed: num(r.speed, def.speed, SPEED_MIN, SPEED_MAX),
        };
    }
    return out;
}

/** How long an event takes, in ms, at the chosen speed. */
export function duration(event, preset, speed = 1) {
    const s = clamp(speed, SPEED_MIN, SPEED_MAX);
    let ms;
    if (preset === 'off' || preset === 'gnome')
        ms = 0;
    else if (event === 'hover')
        ms = HOVER_IN;
    else if (event === 'launch')
        ms = LAUNCH_PERIOD;
    else if (event === 'close')
        ms = CLOSE_DURATION[preset] ?? CLOSE_DURATION.scalefade;
    else
        ms = DURATION[preset] ?? DURATION.spring;
    return Math.round(ms / s);
}

export function hoverOutDuration(speed = 1) {
    return Math.round(HOVER_OUT / clamp(speed, SPEED_MIN, SPEED_MAX));
}

/** Overshoot past the end, as a share of the distance travelled. */
export function overshoot(intensity) {
    // 50% intensity gives about 6%, 100% gives 15% and never more.
    // A little under the cap: the curve's landing correction adds a hair on top.
    return 0.97 * MAX_OVERSHOOT * Math.pow(clamp(intensity), 1.32);
}

// A curve that ends exactly at 1: whatever a curve leaves unsettled at u = 1 is
// folded in over its last stretch, too little to see.
function landed(f) {
    const miss = 1 - f(1);
    return u => (u >= 1 ? 1 : u <= 0 ? 0 : f(u) + miss * u * u * u);
}

/**
 * A damped spring released from rest: one visible overshoot at the default
 * intensity, settling well inside the duration. peak is when it first passes 1.
 */
export function spring(intensity, peak = 0.38) {
    const o = overshoot(intensity);
    if (o < 0.002) {
        // Critically damped: the quickest settle with no overshoot.
        const a = 9;
        return landed(u => 1 - Math.exp(-a * u) * (1 + a * u));
    }
    const w = Math.PI / peak;
    const l = -Math.log(o) * w / Math.PI;
    return landed(u => 1 - Math.exp(-l * u) * (Math.cos(w * u) + l / w * Math.sin(w * u)));
}

/**
 * A ball dropped onto its end point: it never passes 1, and hops back up two or
 * three times, each lower and shorter than the one before.
 */
export function bounce(intensity) {
    const e = 0.25 + 0.35 * clamp(intensity);   // how much of its speed each hop keeps
    const hops = 5;
    let total = 1;
    for (let k = 1; k <= hops; k++)
        total += 2 * Math.pow(e, k);
    const t0 = 1 / total;   // the first fall
    return landed(u => {
        if (u < t0)
            return (u / t0) * (u / t0);
        let start = t0;
        for (let k = 1; k <= hops; k++) {
            const d = 2 * t0 * Math.pow(e, k);
            if (u < start + d) {
                const x = (u - start - d / 2) / (d / 2);   // -1 → 1 over the hop
                return 1 - Math.pow(e, 2 * k) * (1 - x * x);
            }
            start += d;
        }
        return 1;
    });
}

/**
 * Jelly: squash and stretch around a soft spring. Returns the main progress and
 * the wobble: width grows by (1 + wobble) while height shrinks by (1 - wobble).
 */
export function jelly(intensity) {
    const i = clamp(intensity);
    const main = spring(i * 0.45);
    const amp = 0.12 * i;    // 6% at the default, within the 15% cap
    const wobble = u => (u <= 0 || u >= 1 ? 0 : amp * Math.sin(2 * Math.PI * 1.8 * u) * Math.exp(-3 * u) * (1 - u));
    return {main, wobble};
}

/** A CSS-style cubic Bézier easing, x1/y1/x2/y2 as in cubic-bezier(). */
export function bezier(x1, y1, x2, y2) {
    const bx = t => 3 * x1 * t * (1 - t) * (1 - t) + 3 * x2 * t * t * (1 - t) + t * t * t;
    const by = t => 3 * y1 * t * (1 - t) * (1 - t) + 3 * y2 * t * t * (1 - t) + t * t * t;
    return u => {
        if (u <= 0)
            return 0;
        if (u >= 1)
            return 1;
        let lo = 0, hi = 1, t = u;
        for (let n = 0; n < 24; n++) {
            t = (lo + hi) / 2;
            if (bx(t) < u)
                lo = t;
            else
                hi = t;
        }
        return by(t);
    };
}

export const easeOut = bezier(0.2, 0.8, 0.2, 1);
export const easeInOut = bezier(0.45, 0, 0.25, 1);
export const easeIn = bezier(0.4, 0, 1, 1);

/** The main progress curve for a preset (jelly's main part; genie and scale-and-fade ease). */
export function curve(preset, intensity) {
    switch (preset) {
    case 'spring':
        return spring(intensity);
    case 'bounce':
        return bounce(intensity);
    case 'jelly':
        return jelly(intensity).main;
    case 'genie':
        return easeInOut;
    default:
        return easeOut;
    }
}

/** A function of u that is 0 at both ends: the jelly wobble, or nothing. */
export function wobble(preset, intensity) {
    return preset === 'jelly' ? jelly(intensity).wobble : () => 0;
}

/** How small a window starts when it opens (and ends when it closes), by preset. */
export function startScale(preset, intensity) {
    const i = clamp(intensity);
    switch (preset) {
    case 'scalefade':
        return 1 - 0.04 - 0.08 * i;
    case 'bounce':
        return 1 - 0.12 - 0.12 * i;
    default:
        return 1 - 0.10 - 0.15 * i;
    }
}

/**
 * Panel hover: how much the item grows and how far it lifts, in px. 8% at the
 * default; past it the growth flattens, so even with a full overshoot and the jelly
 * squash on top an icon stays under 115%.
 */
export function hoverTarget(intensity) {
    const i = clamp(intensity);
    const grow = i <= 0.5 ? 0.16 * i : 0.08 + 0.08 * (i - 0.5);
    return {scale: 1 + grow, lift: 4 * i};
}

/** How much of the jelly squash a hovered icon gets: a hint of it, not a wobble. */
export const HOVER_SQUASH = 0.2;

/**
 * One hop of the taskbar icon while an app starts, over u in 0..1: how far up
 * it is (0..1 of the hop height), and its squash (wobble, as in jelly).
 */
export function launchHop(preset) {
    switch (preset) {
    case 'spring':
        // A smooth bob.
        return {lift: u => Math.sin(Math.PI * u) ** 2, squash: () => 0};
    case 'jelly':
        return {lift: u => Math.sin(Math.PI * u), squash: u => (u < 0.15 ? 0.6 * Math.sin(Math.PI * u / 0.15) : 0)};
    default:
        // A ball: up and down under gravity.
        return {lift: u => 4 * u * (1 - u), squash: () => 0};
    }
}

export function launchHeight(intensity) {
    return 12 * clamp(intensity);
}

// ---- genie ----------------------------------------------------------------------------

export function geniePinch(intensity) {
    return 1.5 + 2 * clamp(intensity);
}

// How far along its way a row of the window is, at progress p; near is 1 for the
// row facing the icon. Rows nearest the icon go first. Returns [along, across]:
// the move towards the icon, and how far the row has narrowed to the icon's width.
function genieRow(near, p, pinch) {
    const r = clamp(p * 2 - (1 - near));
    return [r * r * (3 - 2 * r), 1 - Math.pow(1 - r, pinch)];
}

/**
 * Where a point of the window goes in the genie warp at progress p (0 = the
 * window as it is, 1 = all of it inside the icon). The sides curve in towards
 * the icon like a funnel. The shader in animations.js runs this backwards.
 * win and icon are {x, y, width, height}; returns [x, y].
 */
export function genieWarp(px, py, p, win, icon, intensity = 0.5) {
    const wcx = win.x + win.width / 2, wcy = win.y + win.height / 2;
    const icx = icon.x + icon.width / 2, icy = icon.y + icon.height / 2;
    const vertical = Math.abs(icy - wcy) >= Math.abs(icx - wcx);
    // a: along the way to the icon; b: across it.
    const [pa, pb, wa0, wal, wb0, wbl, ia0, ial, ib0, ibl, toward] = vertical
        ? [py, px, win.y, win.height, win.x, win.width, icon.y, icon.height, icon.x, icon.width, icy > wcy]
        : [px, py, win.x, win.width, win.y, win.height, icon.x, icon.width, icon.y, icon.height, icx > wcx];
    const along = (pa - wa0) / wal;              // 0..1 down the window
    const [ra, rb] = genieRow(toward ? along : 1 - along, p, geniePinch(intensity));
    const across = (pb - wb0) / wbl;
    const a = pa + (ia0 + along * ial - pa) * ra;
    const b = pb + (ib0 + across * ibl - pb) * rb;
    return vertical ? [b, a] : [a, b];
}

// ---- the last line of defence ----------------------------------------------------------

export const SCALE_MIN = 0.01;   // never flat, never flipped
export const SCALE_MAX = 1 + MAX_OVERSHOOT;   // nothing ever grows past 115%

/**
 * Make one animation property function safe to hand to Clutter: time outside 0..1
 * (a huge frame gap) is pinned to the ends, NaN time counts as the end, and a value
 * that is not finite or out of range is pulled back. bounds: {lo, hi} for that
 * property, or null for none. onClamp() is called whenever a value had to be pulled.
 */
export function guarded(fn, prop, bounds, onClamp = () => {}) {
    const rest = prop === 'opacity' ? 255 : prop.startsWith('scale') ? 1 : 0;
    const [lo, hi] = prop.startsWith('scale') ? [SCALE_MIN, SCALE_MAX]
        : prop === 'opacity' ? [0, 255] : bounds ? [bounds.lo, bounds.hi] : [-Infinity, Infinity];
    const end = (() => {
        const v = fn(1);
        return Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : rest;
    })();
    return u => {
        const t = Number.isFinite(u) ? Math.min(1, Math.max(0, u)) : 1;
        const v = fn(t);
        if (!Number.isFinite(v)) {
            onClamp(prop, v);
            return end;
        }
        if (v < lo || v > hi) {
            onClamp(prop, v);
            return Math.min(hi, Math.max(lo, v));
        }
        return v;
    };
}

/** The smallest rectangle holding both. */
export function union(a, b) {
    const x = Math.min(a.x, b.x), y = Math.min(a.y, b.y);
    return {x, y, width: Math.max(a.x + a.width, b.x + b.width) - x, height: Math.max(a.y + a.height, b.y + b.height) - y};
}

/**
 * One step of a damped spring towards `to` (stiffness k, damping c), integrated in
 * 8 ms sub-steps so long frames stay stable. Used by the press and open springs
 * (motion.js) and the gliding taskbar highlight (glide.js).
 */
export function springStep(x, v, to, k, c, dt) {
    const steps = Math.max(1, Math.ceil(dt / 0.008));
    const h = dt / steps;
    for (let i = 0; i < steps; i++) {
        v += (k * (to - x) - c * v) * h;
        x += v * h;
    }
    return [x, v];
}
