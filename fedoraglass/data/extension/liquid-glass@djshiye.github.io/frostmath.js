// Weather frost: how frosty the glass gets for the temperature outside. Plain maths
// with no GNOME imports, so the unit tests run it under Node (frost.js reads the
// weather and hands it here).
//
// The steps follow how warm it feels outdoors, dressed for the season:
//   just right (and warm, and hot)  the glass looks exactly as you set it
//   cool, below `cool` (18 °C)      a light mist of droplets that thickens as it gets colder
//   cold, below `cold` (10 °C)      fogged glass, the droplets biggest at the colder edges
//   freezing, below `freezing` (0)  the droplets freeze and frost grows in from the edges,
//                                   in the shape real ice takes in that weather (crystalFor)
// The three temperatures are the user's to move (the app's Weather frost card).

export const FROST_DEFAULTS = Object.freeze({
    enabled: false,         // opt-in: the glass never changes with the weather unless asked
    feelsLike: true,        // go by the "feels like" temperature (wind and humidity), else the air
    cool: 18,               // °C: below this the glass starts to mist over
    cold: 10,               // °C: below this it is frosted
    freezing: 0,            // °C: below this frost flakes grow on it
    amount: 1,              // 0.2..1, how far the frost goes at its coldest
});

// Where each step sits on the 0..1 frost scale: misty at the cool end, frosted at cold.
export const COOL_TOP = 0.5;
// Flakes start this strong at `freezing`, and are full this many °C below it.
export const FLAKES_START = 0.4;
export const FLAKES_SPAN = 10;

// What each threshold may be, in °C. Each stays at least 1 °C under the one above.
export const RANGES = Object.freeze({cool: [5, 26], cold: [-10, 20], freezing: [-30, 10]});

function num(v, fallback) {
    return typeof v === 'number' && Number.isFinite(v) ? v : fallback;
}

function clamp(v, lo, hi) {
    return Math.min(hi, Math.max(lo, v));
}

/** The weather frost settings as the extension uses them: anything odd falls back to the defaults. */
export function cleanFrost(raw) {
    const r = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
    const d = FROST_DEFAULTS;
    const cool = Math.round(clamp(num(r.cool, d.cool), ...RANGES.cool));
    const cold = Math.round(clamp(num(r.cold, d.cold), RANGES.cold[0], Math.min(RANGES.cold[1], cool - 1)));
    const freezing = Math.round(clamp(num(r.freezing, d.freezing), RANGES.freezing[0], Math.min(RANGES.freezing[1], cold - 1)));
    return {
        enabled: r.enabled === true,
        feelsLike: r.feelsLike !== false,
        cool, cold, freezing,
        amount: clamp(num(r.amount, d.amount), 0.2, 1),
    };
}

/**
 * How frosty the glass is at `tempC` (°C): {level, frost, flakes}, frost and flakes 0..1.
 * level: 'neutral', 'cool', 'cold' or 'freezing'. No temperature (null, NaN) is neutral.
 */
export function frostFor(tempC, cfg) {
    const c = cleanFrost(cfg);
    if (typeof tempC !== 'number' || !Number.isFinite(tempC) || tempC >= c.cool)
        return {level: 'neutral', frost: 0, flakes: 0};
    let level, frost, flakes = 0;
    if (tempC >= c.cold) {
        level = 'cool';
        // Just under `cool` it is already a mist you can see, not a hair's change.
        frost = 0.12 + (COOL_TOP - 0.12) * (c.cool - tempC) / (c.cool - c.cold);
    } else if (tempC > c.freezing) {
        level = 'cold';
        frost = COOL_TOP + (1 - COOL_TOP) * (c.cold - tempC) / (c.cold - c.freezing);
    } else {
        level = 'freezing';
        frost = 1;
        flakes = FLAKES_START + (1 - FLAKES_START) * clamp((c.freezing - tempC) / FLAKES_SPAN, 0, 1);
    }
    const k = (v) => Math.round(clamp(v, 0, 1) * c.amount * 1000) / 1000;
    return {level, frost: k(frost), flakes: k(flakes)};
}

const NO_ICE = Object.freeze({arm: 0, twig: 0, size: 0});

/**
 * One step of the change from `from` toward `to` (both {frost, flakes, ice}); t is 0..1 of
 * the way. The frost's shape (ice: {arm, twig, size}) changes along with it, so a new
 * shape grows out of the old one.
 */
export function between(from, to, t) {
    const e = t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t);
    const a = from.ice ?? NO_ICE, b = to.ice ?? NO_ICE;
    const m = (x, y) => x + (y - x) * e;
    return {
        frost: m(from.frost, to.frost), flakes: m(from.flakes, to.flakes),
        ice: {arm: m(a.arm, b.arm), twig: m(a.twig, b.twig), size: m(a.size, b.size)},
    };
}

// Extra blur the frost adds, px, in a few steps: each step re-blurs every pane once,
// so a change of frost re-blurs at most three times however long it takes.
export const FROST_BLUR = 18;
export function frostBlur(frost) {
    return Math.round(clamp(frost, 0, 1) * 3) * (FROST_BLUR / 3);
}

// How often GNOME's weather is asked for fresh numbers, and how long a reading counts
// once it can't be refreshed (offline): after that the glass goes back to your look.
export const REFRESH_US = 30 * 60 * 1e6;
export const STALE_US = 3 * 3600 * 1e6;

/** Whether fresh numbers are due, by the wall clock (it keeps running while the PC sleeps). */
export function refreshDue(lastUs, nowUs) {
    return !lastUs || nowUs - lastUs >= REFRESH_US || nowUs < lastUs;
}

/** Whether a reading taken at `atUs` is too old to frost the glass by. */
export function stale(atUs, nowUs) {
    return !atUs || nowUs - atUs >= STALE_US || nowUs < atUs - 60e6;
}

// ---- the ice's shape: how frost really grows ------------------------------------------
// Ice is hexagonal, so every branch of a frost crystal runs along one of six directions,
// 60° apart. Which shape it grows into is set by the temperature (Nakaya's diagram, as
// measured by Libbrecht), and how branched by how humid the air is (how far the vapour is
// over saturation): the more humid, the more side branches grow on the branches.
//   0 to -4 °C     thin hexagonal plates: short, broad frost
//   -4 to -10 °C   needles and columns: long, straight needles with a few short spurs
//   -10 to -22 °C  plates again, past a point branching into dendrites: feathery ferns
//                  (the classic window frost, fullest around -15 °C)
//   below -22 °C   small columns: dense, short frost
// The air temperature decides, never "feels like" (wind chill is felt by people, not ice).
export const HABITS = Object.freeze({
    plates: {arm: 0.5, twig: 0.15, size: 0.6},
    needles: {arm: 0.12, twig: 0, size: 1},
    ferns: {arm: 1, twig: 1, size: 1},
    columns: {arm: 0.3, twig: 0, size: 0.45},
});
// How humid the air is when GNOME's weather has no dew point: a usual winter day.
export const WET_DEFAULT = 0.6;

function ramp(a, b, v) {
    const t = clamp((v - a) / (b - a), 0, 1);
    return t * t * (3 - 2 * t);
}

/** How wet the air is, 0..1, from the gap between the air temperature and its dew point. */
export function wetness(tempC, dewC) {
    if (typeof dewC !== 'number' || !Number.isFinite(dewC) || typeof tempC !== 'number' || !Number.isFinite(tempC))
        return WET_DEFAULT;
    return Math.round(clamp(1 - Math.max(0, tempC - dewC) / 8, 0.15, 1) * 1000) / 1000;
}

/**
 * The shape frost grows into at `tempC` (air, °C) with dew point `dewC` (or null):
 * {shape, arm, twig, size}. arm: how long the side branches are, 0..1; twig: branches on
 * those; size: how big the frost grows, 0..1. Shapes blend over a couple of degrees.
 */
export function crystalFor(tempC, dewC = null) {
    const t = typeof tempC === 'number' && Number.isFinite(tempC) ? Math.min(tempC, -1) : -6;
    const needles = ramp(-3, -5, t) * (1 - ramp(-9, -11, t));
    const ferns = ramp(-9, -11, t) * (1 - ramp(-21, -23, t));
    const columns = ramp(-21, -23, t);
    const plates = Math.max(0, 1 - needles - ferns - columns);
    const w = {plates, needles, ferns, columns};
    const shape = Object.keys(w).reduce((a, b) => (w[b] > w[a] ? b : a));
    const mix = k => Object.keys(w).reduce((s, h) => s + w[h] * HABITS[h][k], 0);
    const wet = wetness(tempC, dewC);
    const r = v => Math.round(clamp(v, 0, 1) * 1000) / 1000;
    return {
        shape,
        arm: r(mix('arm') * (0.55 + 0.45 * wet)),
        twig: r(mix('twig') * wet),
        size: r(mix('size') * (0.75 + 0.25 * wet)),
    };
}

// The frost as the shader draws it: the desktop (glass.js) and the app's preview
// (shaders/glass.frag) use this same text, word for word (a test checks), so the preview
// frosts exactly like the desktop. Lengths are desktop px. Plain GLSL that both GLSL 1.10
// (GNOME Shell) and 4.40 (the app) take.
export const ICE_GLSL = `
// ---- weather frost: how ice really forms on cold glass (frostmath.js) ----
// A hash with no sin(), so it is the same on every GPU (Dave Hoskins, MIT).
float iceHash(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

// px to a line from the origin along +x, len long (p in the line's own frame).
float iceSeg(vec2 p, float len) {
    return length(vec2(p.x - clamp(p.x, 0.0, len), p.y));
}

// One frost feather, grown from the origin along +x: a stem len long with side branches
// at 60 degrees (ice is hexagonal: every branch runs along one of its six axes), longest
// part-way along and shorter to both ends, like a leaf. arm: how long the branches are;
// twig: branches on the branches, at 60 degrees again. px to the ice's edge (< 0 on it).
float iceFeather(vec2 p, float len, float gap, float arm, float twig, float seed) {
    float w = mix(0.95, 0.4, clamp(p.x / max(len, 1.0), 0.0, 1.0));
    float d = iceSeg(p, len) - w;
    if (arm < 0.02 || p.x < -2.0 || p.x > len + arm * 0.5 * len)
        return d;
    float side = p.y < 0.0 ? 1.0 : 0.0;
    float ay = abs(p.y);
    float off = side * 0.5 * gap;
    float k = floor((p.x - 0.57735 * ay - off) / gap + 0.5);
    float xb = k * gap + off;
    if (xb <= 0.0 || xb >= len)
        return d;
    float r = iceHash(vec2(k + seed, side + 3.7 * seed));
    float lb = arm * min(1.2 * xb, 0.75 * (len - xb)) * (0.55 + 0.45 * r);
    vec2 q = vec2(0.5 * (p.x - xb) + 0.866025 * ay, 0.866025 * (p.x - xb) - 0.5 * ay);
    d = min(d, iceSeg(q, lb) - 0.8 * w);
    if (twig < 0.02 || lb < 2.0 * gap || q.x < 0.0 || q.x > lb + 2.0)
        return d;
    float g2 = 0.55 * gap;
    float s2 = q.y < 0.0 ? 1.0 : 0.0;
    float ty = abs(q.y);
    float o2 = s2 * 0.5 * g2;
    float k2 = floor((q.x - 0.57735 * ty - o2) / g2 + 0.5);
    float xt = k2 * g2 + o2;
    if (xt <= 0.0 || xt >= lb)
        return d;
    float lt = twig * 0.6 * min(xt, lb - xt) * (0.5 + 0.5 * iceHash(vec2(k2 + 17.0 * r, s2 + seed)));
    vec2 t = vec2(0.5 * (q.x - xt) + 0.866025 * ty, 0.866025 * (q.x - xt) - 0.5 * ty);
    return min(d, iceSeg(t, lt) - 0.6 * w);
}

// Frost grows in from one edge: along it, s px; in from it, u px. Window frost starts at
// the edges, the coldest part of the glass, from specks on it (dust, fine scratches; some
// of nature's best ice seeds are pollen and bacteria). Not every speck seeds: more do as
// it gets colder. Each feather leans a little and sweeps in a gentle curve.
float iceEdge(float s, float u, float sid, float reach, float grow, float arm, float twig, float size) {
    float g = mix(12.0, 24.0, size);
    float gap = mix(9.0, 4.2, arm);
    float i0 = floor(s / g);
    float best = 1e4;
    for (int j = -1; j <= 1; j++) {
        vec2 id = vec2(i0 + float(j), sid);
        if (iceHash(id * 1.7 + 0.3) > 0.35 + 0.5 * grow)
            continue;
        float r2 = iceHash(id * 2.3 + 5.1);
        float r3 = iceHash(id * 3.1 + 9.7);
        float len = reach * (0.45 + 0.55 * r3) * grow;
        if (len < 2.0)
            continue;
        vec2 dv = vec2(s - (id.x + 0.15 + 0.7 * r2) * g, u);
        float a = (r2 - 0.5) * 1.3;
        vec2 dir = vec2(sin(a), cos(a));
        vec2 p = vec2(dot(dv, dir), dir.x * dv.y - dir.y * dv.x);
        p.y += (r3 - 0.5) * mix(0.1, 0.8, arm) * p.x * p.x / len;     // needles grow straight
        best = min(best, iceFeather(p, len, gap, arm, twig, id.x * 0.37 + sid));
    }
    return best;
}

// A crystal that grew on its own from a speck near the edge: six arms, branched like the
// ferns in fern weather, a small hexagonal plate near 0 degrees C. Needles and columns
// make none: they only grow on the frost that is there.
float iceStar(vec2 q, float grow, float arm, float size) {
    vec2 cell = floor(q / 30.0);
    if (iceHash(cell + 11.0) > 0.16 * grow * smoothstep(0.2, 0.5, arm))
        return 1e4;
    vec2 d = q - (cell + 0.25 + 0.5 * vec2(iceHash(cell + 3.1), iceHash(cell + 5.7))) * 30.0;
    float R = (3.0 + 5.0 * iceHash(cell + 8.9)) * (0.45 + 0.55 * size) * (0.5 + 0.5 * grow);
    float r = length(d);
    if (r > R + 2.0)
        return 1e4;
    float a = atan(d.y, d.x) + 6.2832 * iceHash(cell + 1.3);
    float a6 = mod(a + 0.5236, 1.0472) - 0.5236;
    vec2 p = r * vec2(cos(a6), sin(a6));
    float star = iceFeather(p, R, max(1.5, 0.3 * R), arm, 0.0, cell.x + 0.1 * cell.y);
    float plate = r * cos(a6) - R * mix(0.5, 0.12, arm);      // a hexagon's flat side
    return min(star, max(plate, -plate - 0.8));               // the plate's outline
}

// The frost on a pane: px to the nearest ice (< 0 on it). c: px from the pane's middle;
// h: half its size; q: px on the glass, fixed to it. reach: how far in the frost grows
// at its fullest; grow 0..1 how far it has.
float iceFrost(vec2 c, vec2 h, vec2 q, float reach, float grow, float arm, float twig, float size, bool few) {
    float ux = h.x - abs(c.x);
    float uy = h.y - abs(c.y);
    float d = 1e4;
    float pad = reach + 8.0;
    if (uy < pad)
        d = iceEdge(c.x + h.x, uy, c.y < 0.0 ? 1.0 : 2.0, reach, grow, arm, twig, size);
    if (ux < pad)
        d = min(d, iceEdge(c.y + h.y, ux, c.x < 0.0 ? 3.0 : 4.0, reach, grow, arm, twig, size));
    if (!few && min(h.x, h.y) > 30.0 && min(ux, uy) < 1.4 * reach)
        d = min(d, iceStar(q, grow, arm, size));
    return d;
}

// Fog on cold glass is droplets (breath figures): too small to see one by one at first,
// growing and merging as it gets colder, biggest towards the colder edge. Each droplet is a
// little lens: dark at its rim, where light bends away, with a bright point on the side
// facing the light. Returns (how much of a droplet is here, its shade -1..1).
vec2 iceDew(vec2 q, float cell, float big, vec2 L) {
    vec2 i0 = floor(q / cell);
    float best = 9.0;
    vec2 bd = vec2(0.0);
    float br = 1.0;
    for (int y = -1; y <= 1; y++) {
        for (int x = -1; x <= 1; x++) {
            vec2 id = i0 + vec2(float(x), float(y));
            vec2 at = (id + 0.2 + 0.6 * vec2(iceHash(id + 1.7), iceHash(id + 4.3))) * cell;
            float rad = cell * big * (0.2 + 0.32 * iceHash(id + 7.9));
            vec2 d = (q - at) / rad;
            float e = length(d);
            if (e < best) {
                best = e;
                bd = d;
                br = rad;
            }
        }
    }
    float on = clamp((1.0 - best) * br + 0.5, 0.0, 1.0);
    float ring = smoothstep(0.5, 0.95, best);
    float spot = 1.0 - smoothstep(0.0, 0.42, length(bd - 0.45 * L));
    return vec2(on, on * (spot - 0.7 * ring));
}

// Ice is clear: frost is white because each of its tiny flat faces mirrors the light. One
// face in a few catches it straight back and glints; which ones moves with the light.
float iceGlint(vec2 q, vec2 L) {
    vec2 cell = floor(q / 2.0);
    if (iceHash(cell + 21.0) < 0.82)
        return 0.0;
    float a = 6.2832 * iceHash(cell + 23.0);
    return pow(max(dot(vec2(cos(a), sin(a)), L), 0.0), 16.0);
}
`;
