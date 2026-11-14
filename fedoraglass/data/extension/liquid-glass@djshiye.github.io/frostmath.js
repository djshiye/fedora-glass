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

// The ice is alive while you use the glass: its vapour drifts and the light in it moves on
// a clock of its own (the shader's t, glass.js iceTick), which runs only while frozen glass
// is in use (the pointer on or near it, or a menu open), never with animations off.
// Steps a second at each quality level (speed.js): full, lighter, lightest (it lies still).
export const ICE_FPS = Object.freeze([30, 15, 0]);
// Glass at least this many px across its short side is a menu or a popup, open while it is
// shown; a bar (the panel, a dock) is only in use with the pointer near it.
export const ICE_BIG = 120;
// The clock wraps after an hour of use, so the shader never sees a number large enough to
// lose its fine steps.
export const ICE_WRAP = 3600;
// Seconds the clock takes to come to rest (or back up to speed): it slows down, it never jumps.
export const ICE_EASE = 0.4;

/** The clock's speed, 0..1, one step of dt seconds on from `speed`, towards 1 while in use. */
export function iceEase(speed, inUse, dt) {
    const s = clamp(num(speed, 0), 0, 1);
    const e = 1 - Math.exp(-Math.max(0, num(dt, 0)) / ICE_EASE);
    const next = s + ((inUse ? 1 : 0) - s) * e;
    return !inUse && next < 0.01 ? 0 : next;
}

/** The clock after dt seconds at `speed`: never a jump (dt is at most a tenth of a second). */
export function iceStep(t, dt, speed) {
    const next = clamp(num(t, 0), 0, ICE_WRAP) + clamp(num(dt, 0), 0, 0.1) * clamp(num(speed, 0), 0, 1);
    return next >= ICE_WRAP ? next - ICE_WRAP : next;
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
// a frozen pond (the two pictures Dino gave as the look to match), and it is alive:
//   - a skin of ice over the whole pane: wrinkles, bumps and a fine grain, lit from the
//     side so it has relief, never flat and never a drawn shape;
//   - the ice glows from within: light goes in at its edges and scatters inside, so it
//     is a luminous cyan, brightest by the edges, and light caught deep in it drifts
//     slowly; its clouds lie deeper than the skin and shift as you look from another side;
//   - frost: a white crust along the glass's edges, ragged, never a line, which glows and
//     catches the light in points that come and go as the pointer moves;
//   - cold vapour: a mist drifts over the ice and rolls off the glass's edges, furthest
//     below it (cold air sinks), lit by the ice;
//   - it starts at the edges and is thin in the middle at first; the colder, the more of
//     the pane is under it.
// t is seconds of a clock that runs only while the glass is in use (glass.js), so the
// vapour and the light in the ice move then, and lie still the rest of the time.
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

// Soft billows: three octaves of iceNoise, each turned against the last so no grid shows.
float iceFbm(vec2 p) {
    float s = 0.5 * iceNoise(p);
    p = vec2(0.8 * p.x - 0.6 * p.y, 0.6 * p.x + 0.8 * p.y) * 2.03 + 17.0;
    s += 0.25 * iceNoise(p);
    p = vec2(0.8 * p.x - 0.6 * p.y, 0.6 * p.x + 0.8 * p.y) * 2.03 + 17.0;
    s += 0.125 * iceNoise(p);
    return s / 0.875;
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

// Cold vapour: the air over ice is chilled until its water shows as a mist, and cold air
// is heavy, so the mist sinks and rolls off the glass in slow curls. q: px on the glass;
// t: seconds. How thick it is here, 0..1.
float iceVapour(vec2 q, float t) {
    vec2 p = q * 0.021;
    vec2 w = vec2(iceFbm(p * 0.55 + vec2(0.05 * t, -0.08 * t)),
                  iceFbm(p * 0.55 + vec2(5.2 - 0.04 * t, 1.3 - 0.11 * t)));
    float d = iceFbm(p + 2.2 * w + vec2(0.0, -0.16 * t));
    return smoothstep(0.46, 0.80, d);
}

// The frost at the glass's edges: a crust as wide as about a tenth of the pane (never on a
// thin bar), its inner edge ragged, not drawn. 0..1.
float iceCrust(vec2 q, float inside, float shortSide) {
    float wide = clamp(0.055 * shortSide, 5.0, 20.0) * smoothstep(24.0, 90.0, shortSide);
    vec2 r = vec2(0.8 * q.x + 0.6 * q.y, -0.6 * q.x + 0.8 * q.y);
    // Ragged at three sizes: it reaches well in along some stretches of the edge and is
    // barely there along others, so it never reads as a frame.
    float ragged = (iceNoise(r * 0.011 + 7.0) - 0.5) * 2.2 + (iceFbm(q * 0.06 + 3.0) - 0.5) * 1.5
                 + (iceNoise(r * 0.21 + 11.0) - 0.5) * 0.5;
    float d = 1.0 - smoothstep(0.0, 0.9, (inside - wide) / max(wide, 1.0) + 0.3 - ragged);
    // Not a flat band: frost is a crust of fine crystals, denser in some places than others.
    return d * (0.75 + 0.25 * iceNoise(r * 0.55 + 5.0));
}

// The ice over under (what shows behind it, straight rgb). f: iceField; q: px on the
// glass; inside: px in from its edge; lightGlass 0..1; shortSide: the pane's short side,
// px; lit: -1..1, how far this part lies towards the light; inward: px the ice's inside is
// seen shifted by (looking in at a slant); t: seconds, for the vapour.
vec3 iceLook(vec3 under, vec4 f, vec2 q, float inside, float lightGlass, float shortSide, float lit,
             vec2 inward, float t) {
    float cover = f.x;
    // Inside the ice: its clouds and veins lie deeper than the skin, so they shift a little
    // against it as you look in from another side.
    vec2 qd = q + inward;
    vec2 w = vec2(0.6 * qd.x + 0.8 * qd.y, -0.8 * qd.x + 0.6 * qd.y);
    float clouds = smoothstep(0.15, 0.85, 0.6 * iceNoise(w * 0.011 + 5.0) + 0.4 * iceNoise(qd * 0.031 + 9.0));
    // Light goes into the ice at its edges and scatters inside, so the ice glows from
    // within: brightest by the edges and on the side towards the light, deepest in the
    // middle, where the text is.
    float within = exp(-max(inside, 0.0) / clamp(0.22 * shortSide, 16.0, 90.0));
    vec3 deepC = mix(vec3(0.0, 0.22, 0.36), vec3(0.38, 0.72, 0.93), lightGlass);
    vec3 glowC = mix(vec3(0.06, 0.64, 0.80), vec3(0.80, 0.95, 1.0), lightGlass);
    // Light caught deep in the ice drifts slowly through it, so it never lies dead.
    float drift = iceFbm(qd * 0.009 + vec2(0.035 * t, -0.022 * t));
    float tone = 0.26 * clouds + mix(0.22, 1.0, lightGlass) * (f.y - 0.45) + 0.20 * lit + 0.55 * within
               + 0.45 * (drift - 0.45);
    vec3 col = mix(under, mix(deepC, glowC, clamp(tone, 0.0, 1.0)), 0.86 * cover);
    // Veins: a few thin lines where two sheets of ice met, deep inside it.
    vec2 vq = vec2(0.96 * qd.x + 0.28 * qd.y, -0.28 * qd.x + 0.96 * qd.y);
    float vn = iceNoise(vq * 0.022 + 21.0) + 0.22 * (f.y - 0.5);
    float vein = 1.0 - smoothstep(0.0, 0.03, abs(vn - 0.5));
    col = mix(col, deepC * mix(0.85, 0.92, lightGlass), mix(0.22, 0.45, lightGlass) * vein * cover);
    // The skin catches the light: its bumps and wrinkles stand out, a wet sheen on the
    // side of each that faces the light, which moves as the light does.
    col *= 1.0 + mix(0.14, 0.18, lightGlass) * clamp(f.z, -1.0, 1.0) * cover;
    col += vec3(0.45, 0.80, 1.0) * smoothstep(0.3, 1.0, f.z) * mix(0.07, 0.05, lightGlass) * cover;
    // Its glossy top mirrors the light as a broad soft gleam on the side the light is on,
    // gliding over the ice as the light moves.
    col += vec3(0.50, 0.85, 1.0) * smoothstep(0.15, 1.0, lit) * mix(0.07, 0.04, lightGlass) * (0.6 + 0.8 * f.y) * cover;
    // Frost: a white crust at the edges, and fine frost over the skin's high points.
    vec3 white = mix(vec3(0.40, 0.58, 0.64), vec3(0.90, 0.97, 1.0), lightGlass);
    float crust = iceCrust(q, inside, shortSide);
    float fine = smoothstep(0.55, 0.85, f.y) * mix(0.25, 0.45, lightGlass) + mix(0.04, 0.18, lightGlass) * clouds;
    col = mix(col, white, clamp(0.85 * crust + fine, 0.0, 0.92) * cover);
    // Vapour drifts over it by the cold edges, a soft mist that comes and goes.
    float mist = iceVapour(q, t) * (0.2 + 0.8 * within) * cover;
    col = mix(col, white, mist * mix(0.35, 0.40, lightGlass));
    // White text must stay readable on dark glass: away from the edge, where the text is,
    // the ice eases into a ceiling on its brightness, in its own colour. The frost is
    // brightest in the last few px of the edge, where no text lies, and dims as it reaches
    // further in (a menu's first line may lie on it), as real frost is thinner there.
    if (lightGlass < 0.5) {
        float Y = dot(col * col, vec3(0.2126, 0.7152, 0.0722));     // gamma 2: near enough, and cheap
        float top = mix(0.175, 0.60, crust * exp(-max(inside, 0.0) / 5.0)), knee = 0.6 * top;
        if (Y > knee)
            col *= sqrt((knee + (top - knee) * (1.0 - exp(-(Y - knee) / (top - knee)))) / Y);
    }
    // A fine grain over it all, as frost has: too small to get in the way of text.
    vec2 gq = vec2(0.8 * q.x + 0.6 * q.y, -0.6 * q.x + 0.8 * q.y);
    float grain = iceNoise(gq * 1.3 + 41.0) - 0.5;
    return col * (1.0 + 0.10 * grain * cover);
}

// The ice's own light on dark glass, added on top of it (the content's light layer, glass.js):
// the frost at the edges glows, light caught in the ice comes out there, lit vapour drifts
// by, and points of frost catch the light. Added light, rgb.
// content (0..1): how bright the pane's own text and icons are here, blurred (a line of
// text gives about 0.01 to 0.1 around it). None is added on or right around them, and the
// vapour's light thins out near them, so they read as before.
// L: towards the light, which follows the pointer, so the frost sparkles as it moves.
vec3 iceGlow(vec4 f, vec2 q, float inside, float shortSide, float lit, vec2 L, float t, float content) {
    float onIt = smoothstep(0.008, 0.05, content);
    float nearIt = smoothstep(0.006, 0.025, content);
    float crust = iceCrust(q, inside, shortSide);
    float near = exp(-max(inside, 0.0) / clamp(0.22 * shortSide, 16.0, 90.0));
    float mist = iceVapour(q, t);
    // Points of frost catch the light, each at its own angle: they sparkle as the light
    // moves. Only where the frost is.
    vec2 cell = floor(q / 2.0);
    float a = 6.2832 * iceHash(cell + 7.1) + 0.35 * t;
    float facing = max(dot(vec2(cos(a), sin(a)), L), 0.0);
    float sparkle = step(0.975, iceHash(cell + 3.7)) * pow(facing, 16.0) * crust;
    // The frost glows most at the very edge, where it is thickest, and its light spreads a
    // little into the ice around it; light caught deep in the ice drifts through it.
    float edge = exp(-max(inside, 0.0) / 4.0) * smoothstep(24.0, 90.0, shortSide);
    float outer = exp(-max(inside, 0.0) / 8.0);
    float drift = iceFbm(q * 0.009 + vec2(0.035 * t, -0.022 * t));
    // The vapour's light keeps to the edges too, where no text lies.
    float rim = exp(-max(inside, 0.0) / 12.0);
    float glow = (((0.22 + 0.10 * lit) * crust * (0.5 + 0.7 * f.y) + 0.45 * sparkle) * outer + 0.20 * edge) * (1.0 - onIt)
               + ((0.12 * mist + 0.05) * rim + 0.04 * near * smoothstep(0.45, 0.85, drift)) * (1.0 - 0.7 * nearIt) * (1.0 - onIt);
    return vec3(0.60, 0.90, 1.0) * glow * f.x;
}

// Outside the glass, below freezing: cold vapour rolling off it (it sinks, so it spills
// furthest below the glass) and the ice's light around it. away: px outside the edge;
// down: 0..1 how far this side faces down; lit: -1..1 towards the light. Premultiplied.
vec4 iceHalo(float away, vec2 q, float t, float down, float lit, float lightGlass, float grow) {
    float reach = mix(8.0, 16.0, down);
    float fall = exp(-away / reach);
    float v = iceVapour(q, t);
    float a = clamp(fall * (0.12 + 0.88 * v) * 0.5, 0.0, 0.5) * grow;
    // The ice's light on the vapour and the air right around it.
    float glow = exp(-away / 9.0) * (0.20 + 0.12 * lit) * grow * (1.0 - 0.6 * lightGlass);
    vec3 mc = mix(mix(vec3(0.55, 0.88, 1.0), vec3(0.80, 0.94, 1.0), smoothstep(0.0, 14.0, away)), vec3(0.92, 0.98, 1.0), lightGlass);
    return vec4(mc * a + vec3(0.25, 0.72, 1.0) * glow * (0.6 + 0.6 * v), a);
}
`;
