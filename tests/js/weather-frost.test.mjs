// Weather frost (frostmath.js, frost.js): how frosty the glass gets for the temperature
// outside, that it reads only GNOME's own weather, eases between steps, and leaves the
// glass exactly as set when it is off or warm enough.
import assert from 'node:assert/strict';
import {test} from 'node:test';

const timers = new Map();
let nextId = 1;
let now = 0;
globalThis.fake = {
    fs: new Map(),
    now: () => now,
    realNow: () => now,
    timeouts: {
        add: (ms, fn) => {
            const id = nextId++;
            timers.set(id, {ms, fn});
            return id;
        },
        remove: id => timers.delete(id),
    },
    Actor: class {},
    // GNOME's calendar menu, which holds its weather (read once when main.js loads).
    panel: {statusArea: {dateMenu: {_weatherItem: {_weatherClient: null}}}},
};
globalThis.global = {stage: {}};

const M = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/frostmath.js');
const C = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/config.js');

const STATE = '/home/u/.cache/liquid-glass/weather-frost.json';

/** A stand-in for GNOME's own WeatherClient (misc/weather.js) with libgweather's GWeatherInfo. */
function client({temp = 5, feels = 2, dew = undefined, available = true, hasLocation = true, loading = false, valid = true} = {}) {
    return {
        available, hasLocation, loading, updates: 0, handlers: new Map(), n: 0,
        info: {
            is_valid: () => valid,
            // Asked in °C (GWEATHER_TEMP_UNIT_CENTIGRADE = 3) whatever unit the user shows.
            get_value_temp: unit => (unit === 3 ? [temp !== null, temp ?? 0] : [false, 0]),
            get_value_apparent: unit => (unit === 3 ? [feels !== null, feels ?? 0] : [false, 0]),
            ...(dew === undefined ? {} : {get_value_dew: unit => (unit === 3 ? [dew !== null, dew ?? 0] : [false, 0])}),
            get_location_name: () => { throw new Error('the place is never read'); },
        },
        connect(sig, fn) { this.handlers.set(++this.n, fn); return this.n; },
        disconnect(id) { this.handlers.delete(id); },
        emit() { [...this.handlers.values()].forEach(fn => fn()); },
        update() { this.updates++; },
        set(t, f) { this.info.get_value_temp = () => [true, t]; this.info.get_value_apparent = () => [true, f]; },
    };
}

function withClient(c) {
    globalThis.fake.panel.statusArea.dateMenu._weatherItem._weatherClient = c;
}

/** Runs the easing timer to its end. */
function settle() {
    for (let i = 0; i < 200; i++) {
        const ease = [...timers].find(([, t]) => t.ms === 50);
        if (!ease)
            return;
        now += 50e3;
        if (!ease[1].fn())
            timers.delete(ease[0]);
    }
}

const on = extra => ({weather: {enabled: true, ...extra}});

test('Dino\'s outdoor table is the default: just right from 18 °C up', () => {
    const d = M.cleanFrost({enabled: true});
    assert.deepEqual([d.cool, d.cold, d.freezing], [18, 10, 0]);
    for (const t of [18, 21, 23, 26, 35])
        assert.deepEqual(M.frostFor(t, d), {level: 'neutral', frost: 0, flakes: 0}, `${t} °C`);
});

test('the frost builds up step by step as it gets colder', () => {
    const d = M.cleanFrost({});
    const at = t => M.frostFor(t, d);
    assert.equal(at(17).level, 'cool');
    assert.equal(at(10).level, 'cool');
    assert.equal(at(9).level, 'cold');
    assert.equal(at(0).level, 'freezing');
    // Progressive: never less frost when it is colder.
    let last = -1, lastFlakes = -1;
    for (let t = 25; t >= -25; t -= 0.5) {
        const f = at(t);
        assert.ok(f.frost >= last && f.flakes >= lastFlakes, `${t} °C`);
        last = f.frost;
        lastFlakes = f.flakes;
    }
    assert.ok(at(17.9).frost > 0.1, 'just under cool it is a mist you can see');
    assert.equal(at(5).flakes, 0, 'no flakes above freezing');
    assert.equal(at(-0.1).frost, 1);
    assert.ok(at(0).flakes >= 0.4, 'flakes you can see at freezing');
    assert.equal(at(-10).flakes, 1);
    assert.equal(at(-40).flakes, 1);
});

test('no temperature is no frost', () => {
    for (const t of [null, undefined, NaN, Infinity, '3'])
        assert.equal(M.frostFor(t, {}).frost, 0);
});

test('the user\'s thresholds are kept in order and in range, and how much frost too', () => {
    const c = M.cleanFrost({enabled: 'yes', cool: 12, cold: 15, freezing: 40, amount: 5, feelsLike: 0});
    assert.equal(c.enabled, false, 'only a real true turns it on');
    assert.equal(c.feelsLike, true);
    assert.ok(c.cold < c.cool && c.freezing < c.cold);
    assert.equal(c.amount, 1);
    assert.deepEqual(M.cleanFrost({cool: 99, cold: -99, freezing: -99}), {...M.cleanFrost({}), cool: 26, cold: -10, freezing: -30});
    assert.equal(M.frostFor(-20, {amount: 0.5}).frost, 0.5);
    assert.equal(M.frostFor(-20, {amount: 0.5}).flakes, 0.5);
});

test('config.js passes the weather settings through, checked', () => {
    const cfg = C.parse(JSON.stringify({weather: {enabled: true, cool: 16, cold: 8, freezing: -2, amount: 0.6, feelsLike: false}}));
    assert.deepEqual(cfg.weather, {enabled: true, feelsLike: false, cool: 16, cold: 8, freezing: -2, amount: 0.6});
    assert.equal(C.parse('{}').weather.enabled, false, 'off unless turned on');
});

test('the extra blur steps at most three times', () => {
    const seen = new Set();
    for (let f = 0; f <= 1; f += 0.01)
        seen.add(M.frostBlur(f));
    assert.deepEqual([...seen].sort((a, b) => a - b), [0, 6, 12, 18]);
});

const {WeatherFrost} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/frost.js');

test('off, nothing is read and the glass is as you set it', () => {
    const c = client();
    withClient(c);
    globalThis.fake.frosts = [];
    globalThis.fake.fs.set(STATE, {text: '{}'});
    const w = new WeatherFrost(C.parse('{}'));
    assert.equal(c.handlers.size, 0);
    assert.equal(c.updates, 0);
    assert.equal(timers.size, 0, 'no timer at all');
    assert.equal(globalThis.fake.fs.has(STATE), false, 'an old state file goes');
    w.destroy();
    assert.deepEqual(globalThis.fake.frosts.at(-1), [0, 0]);
});

test('on, it reads GNOME\'s weather (feels like by default), shows the frost at once, and says it for the app', () => {
    now = 1e12;
    const c = client({temp: 5, feels: -3});
    withClient(c);
    globalThis.fake.frosts = [];
    const w = new WeatherFrost(C.parse(JSON.stringify(on())));
    assert.equal(c.updates, 1, 'asks for fresh numbers once at the start');
    assert.deepEqual(globalThis.fake.frosts.at(-1), [1, M.frostFor(-3, {}).flakes], 'at once, no easing at a start');
    const state = JSON.parse(globalThis.fake.fs.get(STATE).text);
    assert.equal(state.status, 'ok');
    assert.equal(state.level, 'freezing');
    assert.equal(state.feels, -3);
    assert.equal(state.temp, 5);
    assert.equal(globalThis.fake.fs.get(STATE).mode, 0o600);
    assert.deepEqual(Object.keys(state).sort(), ['at', 'dew', 'feels', 'feelsLike', 'flakes', 'frost', 'level',
        'status', 'temp', 'version'], 'only these: never where you are');
    w.destroy();
    assert.equal(c.handlers.size, 0, 'lets go of GNOME\'s weather');
    assert.equal(timers.size, 0);
});

test('the air temperature when the user picks it', () => {
    const c = client({temp: 15, feels: 8});
    withClient(c);
    globalThis.fake.frosts = [];
    const w = new WeatherFrost(C.parse(JSON.stringify(on({feelsLike: false}))));
    assert.deepEqual(globalThis.fake.frosts.at(-1), [M.frostFor(15, {}).frost, 0]);
    w.destroy();
});

test('a new reading eases in, and warm again goes back to your look', () => {
    now = 2e12;
    const c = client({temp: 20, feels: 20});
    withClient(c);
    globalThis.fake.frosts = [];
    const w = new WeatherFrost(C.parse(JSON.stringify(on())));
    assert.deepEqual(globalThis.fake.frosts.at(-1), [0, 0]);
    c.set(4, 4);
    c.emit();
    const target = M.frostFor(4, {}).frost;
    assert.ok(globalThis.fake.frosts.at(-1)[0] < target, 'not at once');
    settle();
    assert.deepEqual(globalThis.fake.frosts.at(-1), [target, 0]);
    const steps = globalThis.fake.frosts.length;
    assert.ok(steps < 70, `about 60 steps over 3 s, not ${steps}`);
    c.set(22, 22);
    c.emit();
    settle();
    assert.deepEqual(globalThis.fake.frosts.at(-1), [0, 0]);
    w.destroy();
});

test('refreshes every 30 minutes, keeps a reading through a failed refresh, and lets it go after 3 hours', () => {
    now = 3e12;
    const c = client({temp: -5, feels: -5});
    withClient(c);
    globalThis.fake.frosts = [];
    const w = new WeatherFrost(C.parse(JSON.stringify(on())));
    const tick = [...timers.values()].find(t => t.ms === 600e3);
    assert.ok(tick, 'one check every 10 minutes');
    now += 10 * 60e6;
    tick.fn();
    assert.equal(c.updates, 1, 'not due yet');
    now += 21 * 60e6;
    tick.fn();
    assert.equal(c.updates, 2, 'due after 30 minutes');
    // Offline: GNOME's weather has nothing valid any more.
    c.info.is_valid = () => false;
    c.emit();
    assert.equal(globalThis.fake.frosts.at(-1)[0], 1, 'the last reading still counts');
    now += 3 * 3600e6;
    tick.fn();
    settle();
    assert.deepEqual(globalThis.fake.frosts.at(-1), [0, 0], 'too old: back to your look');
    assert.equal(JSON.parse(globalThis.fake.fs.get(STATE).text).status, 'waiting');
    w.destroy();
});

test('no GNOME Weather, or no place set: no frost, and the app is told why', () => {
    for (const [c, why] of [[null, 'no-weather'], [client({available: false}), 'no-weather'], [client({hasLocation: false}), 'no-place']]) {
        withClient(c);
        globalThis.fake.frosts = [];
        const w = new WeatherFrost(C.parse(JSON.stringify(on())));
        assert.equal(JSON.parse(globalThis.fake.fs.get(STATE).text).status, why);
        assert.equal(c?.updates ?? 0, 0, 'nothing is fetched without a place');
        assert.ok(globalThis.fake.frosts.every(([f, k]) => f === 0 && k === 0));
        w.destroy();
    }
});

test('turned off with Apply: the frost eases away and the state file goes', () => {
    const c = client({temp: -8, feels: -8});
    withClient(c);
    globalThis.fake.frosts = [];
    const w = new WeatherFrost(C.parse(JSON.stringify(on())));
    w.update(C.parse('{}'));
    settle();
    assert.deepEqual(globalThis.fake.frosts.at(-1), [0, 0]);
    assert.equal(globalThis.fake.fs.has(STATE), false);
    assert.equal(c.handlers.size, 0);
    assert.equal(timers.size, 0);
    w.destroy();
});

test('new thresholds apply to the reading it has', () => {
    const c = client({temp: 12, feels: 12});
    withClient(c);
    globalThis.fake.frosts = [];
    const w = new WeatherFrost(C.parse(JSON.stringify(on())));
    assert.ok(globalThis.fake.frosts.at(-1)[0] > 0);
    w.update(C.parse(JSON.stringify(on({cool: 11, cold: 5}))));
    settle();
    assert.deepEqual(globalThis.fake.frosts.at(-1), [0, 0]);
    w.destroy();
});

test('humid air frosts a little more than dry air, and no dew point leaves the steps as they are', () => {
    const plain = M.frostFor(5, {});
    assert.deepEqual(M.frostFor(5, {}, null), plain);
    assert.deepEqual(M.frostFor(5, {}, NaN), plain, 'no dew point: a usual day');
    const humid = M.frostFor(5, {}, 4.5), dry = M.frostFor(5, {}, -15);
    assert.ok(humid.frost > plain.frost && dry.frost < plain.frost, 'mist forms from the water in the air');
    const ice = M.frostFor(-4, {}), iceDry = M.frostFor(-4, {}, -20);
    assert.ok(iceDry.flakes < ice.flakes && iceDry.flakes > 0.6 * ice.flakes, 'dry air ices over a little less, never none');
    assert.ok(M.frostFor(-40, {}, -40).flakes <= 1 && M.frostFor(-40, {}, -40).frost <= 1);
    assert.equal(M.wetness(5, 5), 1);
    assert.equal(M.wetness(5, -30), 0.15);
    assert.equal(M.wetness(5, null), M.WET_DEFAULT);
    assert.equal(M.frostFor(25, {}, 25).frost, 0, 'warm is your look, however humid');
});

test('the frost goes by the dew point GNOME\'s weather has', () => {
    now = 4e12;
    const c = client({temp: 3, feels: 1, dew: 2.5});
    withClient(c);
    globalThis.fake.frosts = [];
    const w = new WeatherFrost(C.parse(JSON.stringify(on())));
    const want = M.frostFor(1, {}, 2.5);     // feels like, with the dew point
    assert.deepEqual(globalThis.fake.frosts.at(-1), [want.frost, want.flakes]);
    const state = JSON.parse(globalThis.fake.fs.get(STATE).text);
    assert.equal(state.dew, 2.5);
    assert.equal(state.frost, want.frost);
    w.destroy();
});

test('a dew point over the temperature (a rounding in the weather) is taken as the temperature', () => {
    const c = client({temp: -5, feels: -5, dew: -3});
    withClient(c);
    const w = new WeatherFrost(C.parse(JSON.stringify(on())));
    assert.equal(JSON.parse(globalThis.fake.fs.get(STATE).text).dew, -5);
    w.destroy();
});

test('the frost shader is plain GLSL both GNOME Shell and the app take', () => {
    const g = M.ICE_GLSL;
    for (const fn of ['iceHash', 'iceNoise', 'iceFbm', 'iceSkin', 'iceField', 'iceBend', 'iceVapour', 'iceCrust', 'iceLook',
        'iceGlow', 'iceHalo'])
        assert.ok(g.includes(` ${fn}(`), fn);
    assert.ok(!/`|\$\{/.test(g), 'nothing that would break the shader\'s JS string');
    assert.ok(!/\b(texture|uniform|OFF)\b/.test(g), 'uses only its own arguments');
    assert.ok(!/\d\.\d*f\b|\bint\s+\w+\s*=\s*\d+\.\d/.test(g), 'no C-style float suffixes');
    const code = g.replace(/\/\/.*$/gm, '');
    assert.ok(!/\b(fern|needle|crystal|star|glint|flake|drop|branch)/i.test(code), 'no patterns: just frost and ice');
});

test('frozen glass is stiff: the further it has frozen over, the less liquid it is', () => {
    // Not frozen: your own "How liquid", untouched.
    for (const set of [0.25, 1, 2.5])
        assert.equal(M.frozenLiquid(set, 0), set);
    // All ice: a quarter of it, and never under the least the slider goes to.
    assert.ok(Math.abs(M.frozenLiquid(2, 1) - 2 * (1 - M.FROZEN_STIFF)) < 1e-9);
    assert.equal(M.frozenLiquid(1, 1), 0.25);
    assert.equal(M.frozenLiquid(0.25, 1), 0.25);
    // In between it eases off, step by step.
    let last = M.frozenLiquid(2.5, 0);
    for (const k of [0.2, 0.4, 0.6, 0.8, 1]) {
        const now = M.frozenLiquid(2.5, k);
        assert.ok(now < last, `less liquid at ${k}`);
        last = now;
    }
    // Liquid at 1 or under has no pull along a drag (motion.js): frozen glass is not drawn out.
    assert.ok(M.frozenLiquid(2.5, 1) <= 1);
    // Out of range counts as its nearest end.
    assert.equal(M.frozenLiquid(1, 7), M.frozenLiquid(1, 1));
    assert.equal(M.frozenLiquid(1, -3), 1);
});

test('the ice knows what lies over a menu: its veil and its own soft shadow', () => {
    // config.js passes the theme's shadow under the veil through, checked.
    const look = (shade) => C.parse(JSON.stringify({version: 1, menus: {enabled: true, look: {shade}}})).menus.look.shade;
    assert.equal(look(0.36), 0.36);
    assert.equal(look(5), 0.9);
    // None unless the theme says so (glass.js reads a missing one as 0).
    assert.equal(look('x') ?? 0, 0);
    assert.equal(C.parse('{}').menus.look.shade ?? 0, 0);
    assert.equal(look(-1), 0);
});

