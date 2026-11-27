// Weather asked again soon after a failed answer: a PC waking from sleep asks before its
// network is back, and the weather chip and the frost must not wait half an hour for the next try.
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
const W = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/lockwidgets.js');
const {WeatherFrost} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/frost.js');


/** A client like GNOME's: update() fetches, and offline the answer ends invalid. */
function gnomeClient(extra) {
    const c = client(extra);
    c.online = true;
    c.update = function () {
        this.updates++;
        const ok = this.online;     // what this fetch found: it stays so until the next one
        this.info.is_valid = () => ok;
        this.emit();
    };
    return c;
}

function lockTick(c) {
    W.LockWidgets.prototype._tick.call({_ended: false, _greeting: null, _weatherClient: c});
}

test('the weather is asked again soon after a wake-up ask that found no network', () => {
    M.forgetWeatherAsked();
    now = 5e12;
    const c = gnomeClient({temp: -6, feels: -6});
    withClient(c);
    globalThis.fake.frosts = [];
    // Evening on the desktop: frosted.
    let f = new WeatherFrost(C.parse(JSON.stringify(on())));
    assert.equal(c.updates, 1);
    assert.ok(globalThis.fake.frosts.at(-1)[0] > 0.9);
    // Lock, suspend for the night.
    now += 5 * 60e6;
    f.destroy();
    now += 8 * 3600e6;
    // Waking: the lock screen's clock ticks at once, and the network is not back yet.
    c.online = false;
    lockTick(c);
    assert.equal(c.updates, 2, 'the lock screen asked at wake-up');
    // A minute later the network is back, but it is too soon to ask again.
    c.online = true;
    now += 60e6;
    lockTick(c);
    assert.equal(c.updates, 2);
    // Four minutes after the failed ask the lock clock ticks again: asked, answered.
    now += 3 * 60e6;
    lockTick(c);
    assert.equal(c.updates, 3, 'asked again a few minutes after the failed one');
    assert.equal(c.info.is_valid(), true);
    // After unlocking the frost is back at once.
    f = new WeatherFrost(C.parse(JSON.stringify(on())));
    settle();
    assert.equal(c.updates, 3, 'a good answer is not asked again');
    assert.ok(globalThis.fake.frosts.at(-1)[0] > 0.9, 'frosted again');
    assert.equal(f.state.status, 'ok');
    f.destroy();
    withClient(null);
});

test('a new frost after the unlock asks again when the answer at wake-up failed', () => {
    M.forgetWeatherAsked();
    now = 6e12;
    const c = gnomeClient({temp: -6, feels: -6});
    withClient(c);
    c.online = false;
    lockTick(c);
    assert.equal(c.updates, 1);
    c.online = true;
    now += 4 * 60e6;
    const f = new WeatherFrost(C.parse(JSON.stringify(on())));
    assert.equal(c.updates, 2, 'asked again four minutes after the failed ask');
    settle();
    assert.equal(f.state.status, 'ok');
    f.destroy();
    withClient(null);
});

test('offline all day, the weather is asked at 3, 6, 12 and 24 minutes, then every 30', () => {
    M.forgetWeatherAsked();
    now = 7e12;
    const start = now;
    const c = gnomeClient();
    c.online = false;
    withClient(c);
    const asks = [];
    for (let min = 0; min <= 150; min++) {
        now = start + min * 60e6;
        const before = c.updates;
        lockTick(c);
        if (c.updates > before)
            asks.push(min);
    }
    // Each gap is double the one before (3, 6, 12, 24), then the usual 30.
    assert.deepEqual(asks, [0, 3, 9, 21, 45, 75, 105, 135]);
    withClient(null);
});

test('after a good answer the weather is asked every 30 minutes again', () => {
    M.forgetWeatherAsked();
    now = 8e12;
    const start = now;
    const c = gnomeClient();
    c.online = false;
    withClient(c);
    lockTick(c);                    // minute 0: fails
    now = start + 3 * 60e6;
    c.online = true;
    lockTick(c);                    // minute 3: answered
    assert.equal(c.updates, 2);
    for (const min of [4, 10, 20, 32]) {
        now = start + min * 60e6;
        lockTick(c);
    }
    assert.equal(c.updates, 2, 'not asked again in the half hour after a good answer');
    now = start + 33 * 60e6;
    lockTick(c);
    assert.equal(c.updates, 3);
    // The failures start from one again: a new failure waits 3 minutes, not the old 24.
    c.online = false;
    now = start + 66 * 60e6;
    lockTick(c);
    assert.equal(c.updates, 4);
    now = start + 69 * 60e6;
    lockTick(c);
    assert.equal(c.updates, 5);
    withClient(null);
});

test('the weather is not asked again while the last ask is still loading', () => {
    M.forgetWeatherAsked();
    now = 9e12;
    const c = client({valid: false});
    c.update = function () { this.updates++; this.loading = true; };    // no answer yet
    withClient(c);
    lockTick(c);
    assert.equal(c.updates, 1);
    for (let min = 1; min <= 29; min++) {
        now += 60e6;
        lockTick(c);
    }
    assert.equal(c.updates, 1);
    withClient(null);
});

test('the lock screen does not ask the weather without GNOME Weather', () => {
    M.forgetWeatherAsked();
    now = 9.5e12;
    const c = client({available: false});
    withClient(c);
    lockTick(c);
    assert.equal(c.updates, 0);
    withClient(null);
});

test('askWeatherNow: a failed ask is retried sooner, the clock going back means due', () => {
    M.forgetWeatherAsked();
    assert.equal(M.askWeatherNow(1e12), true);
    assert.equal(M.askWeatherNow(1e12 + 2 * 60e6, true), false);
    assert.equal(M.askWeatherNow(1e12 + 3 * 60e6, true), true);
    assert.equal(M.askWeatherNow(1e12 + 8 * 60e6, true), false);
    assert.equal(M.askWeatherNow(1e12 + 9 * 60e6, true), true);
    assert.equal(M.askWeatherNow(1e12 + 9 * 60e6 - 1, true), true, 'the clock was set back');
    M.forgetWeatherAsked();
    assert.equal(M.askWeatherNow(1e12, true), true);
    assert.equal(M.askWeatherNow(1e12 + 2 * 60e6, true), false);
    assert.equal(M.askWeatherNow(1e12 + 3 * 60e6, true), true);
    M.forgetWeatherAsked();
    assert.equal(M.askWeatherNow(1e12), true, 'forgetting clears the count too');
    assert.equal(M.askWeatherNow(1e12 + 3 * 60e6, true), true, 'one failure: 3 minutes');
    M.forgetWeatherAsked();
});
