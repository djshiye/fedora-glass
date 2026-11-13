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
//
// Below freezing the glass is under a sheet of ice, and ice is told from mist by its
// optics, not by being white (clear "glaze" ice against white "rime"):
//   - it has thickness: most at the glass's edges and corners, ending in a rounded front;
//   - what is behind bends as it comes through, most at that front (ice's index is 1.31);
//   - its top is wet and glassy, so the front catches the light in a soft highlight;
//   - clear ice is a cool blue (it takes the red out of light), and only where it is
//     thickest and full of caught air, right at the edge, is it white.
// No pattern in it: one smooth sheet with a soft, uneven front.
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

// How thick the ice is, 0..1. A window ices over from its edges, the coldest glass, and
// thickest in the corners, where two edges meet. The sheet thins a little on its way in
// and ends in a rounded front, a little uneven, never a pattern. On a thin bar (a panel)
// there is no room for a front: there the ice just thins out towards the middle.
// c: px from the pane's middle; h: half its size; q: px on the glass, fixed to it;
// reach: how far in the ice can grow; grow 0..1 how far it has.
float iceSheet(vec2 c, vec2 h, vec2 q, float reach, float grow) {
    // Distance in from the edges, softly rounded where two meet: so the ice runs round the
    // corners in a curve, thicker there, with no seam.
    float sm = 0.35 * reach;
    float u = -sm * log(exp(-(h.x - abs(c.x)) / sm) + exp(-(h.y - abs(c.y)) / sm));
    float n = 0.7 * iceNoise(q * 0.009) + 0.3 * iceNoise(q * 0.021);
    float edge = (0.6 + 0.28 * n) * reach * (0.35 + 0.65 * grow);
    float roomy = smoothstep(12.0, 44.0, reach);
    float front = 1.0 - smoothstep(edge - mix(0.9 * edge, clamp(0.32 * edge, 5.0, 13.0), roomy), edge + 2.0, u);
    float body = 1.0 - 0.45 * smoothstep(-0.3 * edge, edge, u);
    return front * body;
}

// The ice at a point: x its thickness 0..1, yz how that changes per px (its slope).
vec3 iceField(vec2 c, vec2 h, vec2 q, float reach, float grow) {
    float t0 = iceSheet(c, h, q, reach, grow);
    float tx = iceSheet(c + vec2(2.0, 0.0), h, q + vec2(2.0, 0.0), reach, grow);
    float ty = iceSheet(c + vec2(0.0, 2.0), h, q + vec2(0.0, 2.0), reach, grow);
    return vec3(t0, (tx - t0) * 0.5, (ty - t0) * 0.5);
}

const float ICE_DEEP = 16.0;     // px: the ice at its thickest, drawn deeper than life

// How far (px) what is behind is moved as it comes through the ice: bent at its sloping
// top, more the more ice lies under the slope.
vec2 iceBend(vec3 f) {
    return -f.yz * ICE_DEEP * (4.0 + ICE_DEEP * f.x) * 0.5;
}

// The ice over under (what shows behind it, straight rgb). f: iceField; L: towards the
// light; lightGlass 0..1; inside: px in from the glass's edge; reach: as for iceSheet;
// lit: -1..1, how far this part of the pane lies towards the light.
vec3 iceLook(vec3 under, vec3 f, vec2 L, float lightGlass, float inside, float reach, float lit) {
    float T = f.x;
    vec3 N = normalize(vec3(-f.yz * ICE_DEEP, 1.0));
    float on = smoothstep(0.0, 0.12, T);
    float roomy = smoothstep(12.0, 44.0, reach);     // 0 on a thin bar: no lines along it
    // Clear ice is a cool blue: it takes the red out of the light that crosses it. Its
    // polished top is a shade lighter on the side of the pane that faces the light.
    vec3 deep = mix(vec3(0.40, 0.67, 1.0), vec3(0.52, 0.76, 1.0), lightGlass);
    vec3 col = mix(under, deep, (0.26 + 0.07 * lit * (1.0 - lightGlass)) * T);
    // At the glass's edge the ice is thickest and full of caught air: a white crust that
    // fades fast into the clear ice. A bright line at the very edge only where there is
    // room for it; a thin bar keeps the soft part alone.
    float crust = (0.6 * exp(-inside / 6.0) * roomy + 0.32 * exp(-inside / (0.35 * reach + 2.0))) * on;
    col = vec3(1.0) - (vec3(1.0) - col) * (vec3(1.0) - vec3(0.86, 0.94, 1.0) * crust);
    // The rounded front: lighter where it faces the light. Past it on the far side the
    // light that crossed it gathers in a faint line (dark glass) or leaves a soft shade
    // (light glass, which has no room left to get lighter).
    float facing = dot(N.xy, L);
    float edgy = on * roomy;
    col *= 1.0 + mix(0.45, 0.2, lightGlass) * max(facing, 0.0) * edgy;
    float lee = smoothstep(0.12, 0.6, -facing) * edgy;
    col *= 1.0 - 0.09 * lee * lightGlass;
    vec3 gather = vec3(0.80, 0.90, 1.0) * 0.14 * lee * (1.0 - lightGlass);
    // Its wet, glassy top catches the light: one soft highlight along the front.
    vec3 H = normalize(normalize(vec3(L * 0.75, 0.66)) + vec3(0.0, 0.0, 1.0));
    float nh = max(dot(N, H), 0.0);
    float shine = (0.9 * pow(nh, 70.0) + 0.1 * pow(nh, 12.0)) * mix(1.0, 0.6, lightGlass) * edgy;
    return vec3(1.0) - (vec3(1.0) - col) * (vec3(1.0) - gather) * (vec3(1.0) - vec3(0.95, 0.98, 1.0) * min(shine, 1.0));
}
`;
