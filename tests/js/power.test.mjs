// Lighter glass on battery or in Power Saver (power.js, speed.js): UPower's OnBattery and
// the power profile, followed through D-Bus proxies made without blocking, cap the level at
// lighter; never heavier than the setting or auto; back on mains it goes back. A PC with
// neither service (a desktop) changes nothing.
import assert from 'node:assert/strict';
import {test, beforeEach} from 'node:test';

class Clock {
    constructor() { this.now = 0; this._next = 1; this._due = new Map(); }
    add(ms, fn) { const id = this._next++; this._due.set(id, {at: this.now + ms, fn}); return id; }
    remove(id) { this._due.delete(id); }
    advance(ms) {
        const end = this.now + ms;
        for (;;) {
            const next = [...this._due.entries()].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
            if (!next)
                break;
            this._due.delete(next[0]);
            this.now = next[1].at;
            if (next[1].fn())
                this._due.set(next[0], {at: this.now + 1, fn: next[1].fn});
        }
        this.now = end;
    }
}

class Emitter {
    constructor() { this._h = new Map(); this._n = 1; }
    connect(sig, fn) { const id = this._n++; this._h.set(id, [sig, fn]); return id; }
    disconnect(id) { this._h.delete(id); }
    emit(sig, ...a) { for (const [s, fn] of [...this._h.values()]) if (s === sig) fn(this, ...a); }
    get count() { return this._h.size; }
}

// A system bus with the services a test puts on it. Proxies answer when the test says so
// (answer()), as GLib's async calls answer on a later turn of the main loop.
class Bus {
    constructor() { this.services = new Map(); this.calls = []; this.waiting = []; this.proxies = new Map(); }
    run(name, props) { this.services.set(name, {props: {...props}, owner: ':1.' + this.services.size}); }
    stop(name) {
        this.services.delete(name);
        this.proxies.get(name)?.emit('notify::g-name-owner');
    }
    start(name, props) {
        this.run(name, props);
        this.proxies.get(name)?.emit('notify::g-name-owner');
    }
    set(name, prop, value) {
        this.services.get(name).props[prop] = value;
        this.proxies.get(name)?.emit('g-properties-changed');
    }
    new_for_bus(bus, flags, info, name, path, iface, cancel, cb) {
        this.calls.push({bus, flags, name, path, iface});
        this.waiting.push(() => {
            if (cancel?.is_cancelled())
                return cb(null, {error: new Error('Operation was cancelled')});
            const self = this;
            const p = new Emitter();
            p.get_name_owner = () => self.services.get(name)?.owner ?? null;
            p.get_cached_property = prop => {
                const v = self.services.get(name)?.props[prop];
                return v === undefined ? null : {unpack: () => v};
            };
            this.proxies.set(name, p);
            cb(null, {proxy: p});
        });
    }
    answer() {
        const w = this.waiting;
        this.waiting = [];
        w.forEach(f => f());
    }
}

let usNow = 0;
globalThis.fake = {Actor: class {}, ui: {}, layoutManager: new Emitter()};
globalThis.global = {stage: new Emitter(), display: new Emitter(), get_window_actors: () => []};
globalThis.logError = () => {};
const SPEED = '/home/u/.cache/liquid-glass/speed.json';
const {Speed} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/speed.js');
const {parse} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/config.js');

const UPOWER = 'org.freedesktop.UPower';
const PROFILES = 'org.freedesktop.UPower.PowerProfiles';
const HADESS = 'net.hadess.PowerProfiles';

let clock, bus;
beforeEach(() => {
    clock = new Clock();
    usNow = 0;
    bus = new Bus();
    Object.assign(globalThis.fake, {timeouts: clock, now: () => usNow, fs: new Map(), monitors: [], renders: 0,
        shown: 0, dbus: bus, quality: undefined});
    console.warn = () => {};
});
const status = () => {
    clock.advance(0);
    return JSON.parse(globalThis.fake.fs.get(SPEED).text);
};
const levels = [];
function speed(cfg) {
    levels.length = 0;
    return new Speed(cfg, l => levels.push(l));
}

test('the services are asked for without blocking, never started, and followed without polling', () => {
    const s = speed({speed: {quality: 'auto'}});
    assert.deepEqual(bus.calls.map(c => c.name), [UPOWER, PROFILES, HADESS]);
    assert.ok(bus.calls.every(c => c.bus === 1 && c.flags === 4), 'system bus, DO_NOT_AUTO_START');
    assert.deepEqual(bus.calls.map(c => c.path), ['/org/freedesktop/UPower', '/org/freedesktop/UPower/PowerProfiles',
        '/net/hadess/PowerProfiles']);
    bus.answer();
    clock.advance(0);
    assert.equal(clock._due.size, 0, 'no timer left running: changes come by signal');
    s.destroy();
    assert.ok([...bus.proxies.values()].every(p => p.count === 0), 'every signal let go');
});

test('a desktop PC without UPower or power profiles: nothing changes', () => {
    const s = speed({speed: {quality: 'auto'}});
    bus.answer();
    assert.equal(s.level, 0);
    assert.deepEqual(levels, []);
    assert.equal(status().reason, 'setting');
    assert.equal(status().power, '');
    s.destroy();
});

test('no system bus at all: the glass carries on at full', () => {
    bus.new_for_bus = (_b, _f, _i, _n, _p, _if, _c, cb) => bus.waiting.push(() => cb(null, {error: new Error('no bus')}));
    const s = speed({speed: {quality: 'full'}});
    assert.doesNotThrow(() => bus.answer());
    assert.equal(s.level, 0);
    s.destroy();
});

test('on battery the glass is lighter, and back on mains it goes back', () => {
    bus.run(UPOWER, {OnBattery: true});
    const s = speed({speed: {quality: 'auto'}});
    assert.equal(s.level, 0, 'nothing until UPower answers');
    bus.answer();
    assert.equal(s.level, 1);
    assert.equal(globalThis.fake.quality, 1, 'the glass draws at the lighter level');
    let st = status();
    assert.equal(st.level, 'lighter');
    assert.equal(st.reason, 'battery');
    assert.equal(st.power, 'battery');
    bus.set(UPOWER, 'OnBattery', false);
    assert.equal(s.level, 0);
    st = status();
    assert.equal(st.level, 'full');
    assert.notEqual(st.reason, 'battery');
    assert.equal(st.power, '');
    assert.deepEqual(levels, [1, 0]);
    s.destroy();
});

test('Power Saver makes it lighter too, under the new and the old service name', () => {
    for (const name of [PROFILES, HADESS]) {
        bus = new Bus();
        globalThis.fake.dbus = bus;
        bus.run(name, {ActiveProfile: 'balanced'});
        const s = speed({speed: {quality: 'full'}});
        bus.answer();
        assert.equal(s.level, 0, name);
        bus.set(name, 'ActiveProfile', 'power-saver');
        assert.equal(s.level, 1, name);
        const st = status();
        assert.equal(st.reason, 'battery');
        assert.equal(st.power, 'saver');
        bus.set(name, 'ActiveProfile', 'performance');
        assert.equal(s.level, 0, name);
        s.destroy();
    }
});

test('never heavier than the setting: lightest stays lightest, lighter says it is the setting', () => {
    bus.run(UPOWER, {OnBattery: true});
    let s = speed({speed: {quality: 'lightest'}});
    bus.answer();
    assert.equal(s.level, 2);
    assert.equal(status().reason, 'setting');
    s.destroy();
    bus = new Bus();
    globalThis.fake.dbus = bus;
    bus.run(UPOWER, {OnBattery: true});
    s = speed({speed: {quality: 'lighter'}});
    bus.answer();
    assert.equal(s.level, 1);
    assert.equal(status().reason, 'setting', 'the user chose lighter: the battery is not why');
    assert.equal(status().power, '');
    s.destroy();
});

test('never heavier than auto: auto stepped down to lightest stays there on battery', () => {
    bus.run(UPOWER, {OnBattery: false});
    const s = speed({speed: {quality: 'auto'}});
    bus.answer();
    s._tuner.level = 2;
    s._setLevel(s._wanted());
    bus.set(UPOWER, 'OnBattery', true);
    assert.equal(s.level, 2);
    bus.set(UPOWER, 'OnBattery', false);
    assert.equal(s.level, 2, 'auto still says lightest');
    s.destroy();
});

test("auto doesn't count lighter glass's frames as full glass's while on battery", () => {
    bus.run(UPOWER, {OnBattery: true});
    const s = speed({speed: {quality: 'auto'}});
    bus.answer();
    const view = {get_refresh_rate: () => 60};
    for (let i = 0; i < 400; i++) {
        globalThis.fake.renders++;
        usNow += 50000;
        global.stage.emit('before-paint', view);
        usNow += 30000;      // slow frames
        global.stage.emit('after-paint', view);
    }
    assert.equal(s._tuner.level, 0, 'auto still at full: those frames were drawn lighter');
    bus.set(UPOWER, 'OnBattery', false);
    assert.equal(s.level, 0);
    s.destroy();
});

test('the switch off: no watch, and turned off on battery the glass goes back at once', () => {
    let s = speed({speed: {quality: 'auto', lighterOnBattery: false}});
    assert.equal(bus.calls.length, 0, 'nothing asked of D-Bus');
    s.destroy();
    bus.run(UPOWER, {OnBattery: true});
    s = speed({speed: {quality: 'auto'}});
    bus.answer();
    assert.equal(s.level, 1);
    s.update({speed: {quality: 'auto', lighterOnBattery: false}});
    assert.equal(s.level, 0);
    assert.equal(bus.proxies.get(UPOWER).count, 0, 'the watch is gone');
    s.update({speed: {quality: 'auto', lighterOnBattery: true}});
    bus.answer();
    assert.equal(s.level, 1, 'on again: lighter again');
    s.destroy();
});

test('UPower starting late, or going away, is followed', () => {
    const s = speed({speed: {quality: 'full'}});
    bus.answer();
    assert.equal(s.level, 0);
    bus.start(UPOWER, {OnBattery: true});
    assert.equal(s.level, 1);
    bus.stop(UPOWER);
    assert.equal(s.level, 0);
    s.destroy();
});

test('locked before the services answer: nothing happens after', () => {
    bus.run(UPOWER, {OnBattery: true});
    const s = speed({speed: {quality: 'auto'}});
    s.destroy();
    assert.doesNotThrow(() => bus.answer());
    assert.deepEqual(levels, []);
    assert.equal(bus.proxies.size, 0, 'no proxy kept');
});

test('a speed check runs every level, then goes back to lighter on battery', () => {
    bus.run(UPOWER, {OnBattery: true});
    globalThis.fake.shown = 1;
    const s = speed({speed: {quality: 'auto'}});
    bus.answer();
    s._startCheck('0123456789abcdef');
    assert.equal(s.level, 0, 'the check measures full glass too');
    s._endCheck('done', '');
    assert.equal(s.level, 1);
    s.destroy();
});

test('shell-glass.json: the switch is on unless it says false', () => {
    assert.equal(parse('{}').speed.lighterOnBattery, true);
    assert.equal(parse('{"speed": {"quality": "full"}}').speed.lighterOnBattery, true);
    assert.equal(parse('{"speed": {"quality": "full", "lighterOnBattery": false}}').speed.lighterOnBattery, false);
});
