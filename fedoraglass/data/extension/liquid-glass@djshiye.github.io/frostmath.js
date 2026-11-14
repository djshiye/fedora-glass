// Weather frost: how frosty the glass gets for the temperature outside. Plain maths
// with no GNOME imports, so the unit tests run it under Node (frost.js reads the
// weather and hands it here).
//
// The steps follow how warm it feels outdoors, dressed for the season:
//   just right (and warm, and hot)  the glass looks exactly as you set it
//   cool, below `cool` (18 °C)      a light mist that thickens as it gets colder
//   cold, below `cold` (10 °C)      frosted glass, whiter towards the colder edges
//   freezing, below `freezing` (0)  the glass freezes over, its edges first: a skin of ice
//                                   you see less through, and stiff under a press
// Humid air frosts a little more than dry air, as on a real window (the dew point).
// The three temperatures are the user's to move (the app's Weather frost card).

export const FROST_DEFAULTS = Object.freeze({
    enabled: false,         // opt-in: the glass never changes with the weather unless asked
    feelsLike: true,        // go by the "feels like" temperature (wind and humidity), else the air
    cool: 18,               // °C: below this the glass starts to mist over
    cold: 10,               // °C: below this it is frosted
    freezing: 0,            // °C: below this the glass freezes over
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

// Frozen glass does not give like liquid glass. The further the glass has frozen over
// (flakes 0..1), the less liquid it is under a press: down to a quarter of your own
// "How liquid" once it is all ice, and never under the least that slider goes to (0.25).
export const FROZEN_STIFF = 0.75;
export function frozenLiquid(liquid, flakes) {
    return Math.max(0.25, liquid * (1 - FROZEN_STIFF * clamp(flakes, 0, 1)));
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
// Below freezing the glass freezes over, like a window on a winter morning or the top of
// a frozen pond (the two pictures Dino gave as the look to match):
//   - a skin of ice over the whole pane: wrinkles, bumps and a fine grain, lit from the
//     side so it has relief, never flat and never a drawn shape;
//   - the ice is cyan, deeper in some places than others, with a few thin veins where
//     two sheets of it met, and it hides much of what is behind;
//   - frost blooms white on it, thickest at the glass's edges where it is coldest, with
//     the skin's grain in it;
//   - it starts at the edges and is thin in the middle at first; the colder, the more of
//     the pane is under it.
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

// The skin of the ice, 0..1 high: wrinkles a finger wide, bumps, and a fine grain, each
// turned against the others so no grid shows. q: px on the glass, fixed to it.
float iceSkin(vec2 q) {
    vec2 a = vec2(0.8 * q.x - 0.6 * q.y, 0.6 * q.x + 0.8 * q.y);
    vec2 b = vec2(0.28 * q.x + 0.96 * q.y, -0.96 * q.x + 0.28 * q.y);
    vec2 d = vec2(0.6 * q.x + 0.8 * q.y, -0.8 * q.x + 0.6 * q.y);
    float wrinkle = abs(2.0 * iceNoise(a * 0.105) - 1.0);
    return 0.46 * wrinkle + 0.30 * iceNoise(b * 0.31 + 13.0) + 0.24 * iceNoise(d * 0.71 + 29.0);
}

// The ice at a point. x: how much of it lies here, 0..1; y: its skin's height; z: the
// skin's slope towards the light L; w: the broad clouds in it, 0..1.
// A pane freezes from its edges, the coldest glass: there the ice is whole as soon as it
// freezes, and the middle follows as it gets colder, unevenly, with no line between.
// c: px from the pane's middle; h: half its size; grow 0..1 how far it has frozen.
vec4 iceField(vec2 c, vec2 h, vec2 q, vec2 L, float grow) {
    float least = min(h.x, h.y);
    float sm = 0.22 * least;
    float u = -sm * log(exp(-(h.x - abs(c.x)) / sm) + exp(-(h.y - abs(c.y)) / sm));
    vec2 w = vec2(0.6 * q.x + 0.8 * q.y, -0.8 * q.x + 0.6 * q.y);
    float clouds = 0.6 * iceNoise(w * 0.017 + 5.0) + 0.4 * iceNoise(q * 0.047 + 9.0);
    float middle = smoothstep(0.0, 0.9, u / least + 0.5 * (clouds - 0.5));
    float cover = mix(smoothstep(0.0, 0.35, grow), smoothstep(0.3, 0.9, grow), middle);
    float s0 = iceSkin(q);
    float s1 = iceSkin(q - L * 1.3);
    return vec4(cover, s0, (s0 - s1) * 3.4, clouds);
}

// How far (px) what is behind is moved as it comes through the ice: scattered by its
// uneven skin, so nothing behind it keeps a sharp outline.
vec2 iceBend(vec4 f) {
    return (vec2(f.y, f.w) - 0.5) * 10.0 * f.x;
}

// The ice over under (what shows behind it, straight rgb). f: iceField; inside: px in
// from the glass's edge; lightGlass 0..1; shortSide: the pane's short side, px; lit: -1..1,
// how far this part of the pane lies towards the light.
vec3 iceLook(vec3 under, vec4 f, vec2 q, float inside, float lightGlass, float shortSide, float lit) {
    float cover = f.x;
    float clouds = smoothstep(0.22, 0.78, f.w);
    float roomy = smoothstep(24.0, 90.0, shortSide);     // 0 on a thin bar: no line along it
    // The ice itself: cyan, deeper where it is thick and in the skin's hollows, a shade
    // lighter on the side of the pane that faces the light. Dark glass gets a deep cyan
    // that white text still reads on, no brighter than a dark menu can show under its
    // veil and shadow (about half way up); light glass the pale blue of pond ice.
    vec3 deep = mix(vec3(0.03, 0.34, 0.45), vec3(0.42, 0.75, 0.93), lightGlass);
    vec3 pale = mix(vec3(0.05, 0.49, 0.51), vec3(0.70, 0.90, 0.98), lightGlass);
    float tone = 0.62 * clouds + mix(0.30, 1.5, lightGlass) * (f.y - 0.42) + 0.18 * lit + 0.14;
    vec3 col = mix(under, mix(deep, pale, clamp(tone, 0.0, 1.0)), 0.86 * cover);
    // Veins: a few thin lines where two sheets of ice met, wandering with the skin.
    vec2 vq = vec2(0.96 * q.x + 0.28 * q.y, -0.28 * q.x + 0.96 * q.y);
    float vn = iceNoise(vq * 0.026 + 21.0) + 0.22 * (f.y - 0.5);
    float vein = 1.0 - smoothstep(0.0, 0.034, abs(vn - 0.5));
    col = mix(col, deep * mix(0.78, 0.90, lightGlass), mix(0.30, 0.60, lightGlass) * vein * cover);
    // Light on the skin: its bumps and wrinkles stand out.
    col *= 1.0 + mix(0.16, 0.20, lightGlass) * clamp(f.z, -1.0, 1.0) * cover;
    // Frost blooms white on the ice: thickest at the glass's edges, patchy with the
    // clouds, and grainy with the skin, whose highest points are whitest.
    vec3 white = mix(vec3(0.42, 0.50, 0.51), vec3(0.86, 0.97, 1.0), lightGlass);
    float e = exp(-max(inside, 0.0) / clamp(0.07 * shortSide, 5.0, 20.0)) * roomy;
    float bloom = mix(0.05, 0.12, lightGlass) + mix(0.14, 0.46, lightGlass) * (clouds - 0.35) + 0.80 * e;
    bloom *= 0.55 + 0.9 * f.y;
    bloom += smoothstep(0.66, 0.80, f.y) * mix(0.18, 0.5, max(e, lightGlass));
    col = mix(col, white, clamp(bloom, 0.0, 0.92) * cover);
    // White text must stay readable on dark glass: away from the edge, where the text is,
    // the ice eases into a ceiling on its brightness, in its own colour.
    if (lightGlass < 0.5) {
        float Y = dot(col * col, vec3(0.2126, 0.7152, 0.0722));     // gamma 2: near enough, and cheap
        float top = mix(0.175, 0.60, e), knee = 0.6 * top;
        if (Y > knee)
            col *= sqrt((knee + (top - knee) * (1.0 - exp(-(Y - knee) / (top - knee)))) / Y);
    }
    // A fine white grain over it all, as frost has: single points, more of them where the
    // frost is thick, too small to get in the way of text.
    vec2 gq = vec2(0.8 * q.x + 0.6 * q.y, -0.6 * q.x + 0.8 * q.y);
    float grain = smoothstep(0.30, 0.80, iceNoise(gq * 1.1 + 41.0)) * smoothstep(0.30, 0.55, f.y);
    return mix(col, white, grain * (0.06 + 0.17 * clouds + 0.5 * e) * (1.0 - 0.5 * lightGlass) * cover);
}
`;
