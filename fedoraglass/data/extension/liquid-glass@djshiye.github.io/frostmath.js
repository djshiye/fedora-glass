// Weather frost: how frosty the glass gets for the temperature outside. Plain maths
// with no GNOME imports, so the unit tests run it under Node (frost.js reads the
// weather and hands it here).
//
// The steps follow how warm it feels outdoors, dressed for the season:
//   just right (and warm, and hot)  the glass looks exactly as you set it
//   cool, below `cool` (18 °C)      a light mist that thickens as it gets colder
//   cold, below `cold` (10 °C)      frosted glass, whiter towards the colder edges
//   freezing, below `freezing` (0)  the glass ices over from its edges, more the colder
// Humid air frosts a little more than dry air, as on a real window (the dew point).
// The three temperatures are the user's to move (the app's Weather frost card).

export const FROST_DEFAULTS = Object.freeze({
    enabled: false,         // opt-in: the glass never changes with the weather unless asked
    feelsLike: true,        // go by the "feels like" temperature (wind and humidity), else the air
    cool: 18,               // °C: below this the glass starts to mist over
    cold: 10,               // °C: below this it is frosted
    freezing: 0,            // °C: below this the glass ices over from its edges
    amount: 1,              // 0.2..1, how far the frost goes at its coldest
});

// Where each step sits on the 0..1 frost scale: misty at the cool end, frosted at cold.
export const COOL_TOP = 0.5;
// The ice ("flakes", kept as the name) starts this strong at `freezing`, and is full this
// many °C below it.
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
 * dewC, the dew point (°C) when the weather has one: dry air frosts a little less.
 */
export function frostFor(tempC, cfg, dewC = null) {
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
    const h = humidity(tempC, dewC);
    const k = (v) => Math.round(clamp(v * h, 0, 1) * c.amount * 1000) / 1000;
    return {level, frost: k(frost), flakes: k(flakes)};
}

// How wet the air is, 0..1, when the dew point is far under the temperature (dry) up to
// close to it (humid): mist and frost form from the water in the air, so dry air makes
// less. A usual winter day (or no dew point) leaves the frost as the steps say.
export const WET_DEFAULT = 0.6;

/** How wet the air is, 0..1, from the gap between the temperature and its dew point. */
export function wetness(tempC, dewC) {
    if (typeof dewC !== 'number' || !Number.isFinite(dewC) || typeof tempC !== 'number' || !Number.isFinite(tempC))
        return WET_DEFAULT;
    return Math.round(clamp(1 - Math.max(0, tempC - dewC) / 8, 0.15, 1) * 1000) / 1000;
}

// 0.89 in very dry air, 1 on a usual day, 1.1 when the air is about to fog.
function humidity(tempC, dewC) {
    return 0.85 + 0.25 * wetness(tempC, dewC);
}

/** One step of the change from `now` toward `target` (both {frost, flakes}); t is 0..1 of the way. */
export function between(from, to, t) {
    const e = t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t);
    return {frost: from.frost + (to.frost - from.frost) * e, flakes: from.flakes + (to.flakes - from.flakes) * e};
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

// The frost as the shader draws it: the desktop (glass.js) and the app's preview
// (shaders/glass.frag) use this same text, word for word (a test checks), so the preview
// frosts exactly like the desktop. Lengths are desktop px. Plain GLSL that both GLSL 1.10
// (GNOME Shell) and 4.40 (the app) take.
export const ICE_GLSL = `
// ---- weather frost (frostmath.js) ----
// A hash with no sin(), so it is the same on every GPU (Dave Hoskins, MIT).
float iceHash(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

float iceNoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(iceHash(i), iceHash(i + vec2(1.0, 0.0)), u.x),
               mix(iceHash(i + vec2(0.0, 1.0)), iceHash(i + vec2(1.0, 1.0)), u.x), u.y);
}

// How thick the ice is, 0..1, below freezing. A window ices over from its edges, the
// coldest glass, and thickest in the corners, where two edges meet; the ice's inner edge
// is soft and a little uneven, never a pattern. Its crystals are far too small to see one
// by one: together they are a smooth frosted sheen. c: px from the pane's middle; h: half
// its size; inside: px in from the edge; q: px on the glass, fixed to it; reach: how far
// in the ice can grow; grow 0..1 how far it has.
float iceGlaze(vec2 c, vec2 h, float inside, vec2 q, float reach, float grow) {
    // Distance in from the edges, softly rounded where two meet: so the ice runs round the
    // corners in a curve, thicker there, with no seam.
    float sm = 0.35 * reach;
    float u = -sm * log(exp(-(h.x - abs(c.x)) / sm) + exp(-(h.y - abs(c.y)) / sm));
    u = max(u, inside - sm);
    float n = 0.7 * iceNoise(q * 0.02) + 0.3 * iceNoise(q * 0.05);
    float edge = (0.3 + 0.45 * n) * reach * (0.35 + 0.65 * grow);
    return 1.0 - smoothstep(0.1 * edge, edge + 6.0, u);
}
`;
