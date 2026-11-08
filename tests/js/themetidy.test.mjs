// User Themes leak (themetidy.js): GNOME's User Themes leaves its theme-name listener
// on an old settings object at every lock. The stale ones go; its current one stays.
import assert from 'node:assert/strict';
import {test} from 'node:test';

class Settings {
    constructor(schema) { this.schema_id = schema; this.handlers = new Map(); this.next = 1; }
    connect(_s, fn) { const id = this.next++; this.handlers.set(id, fn); return id; }
    disconnect(id) { this.handlers.delete(id); }
    emit() { [...this.handlers.values()].forEach(fn => fn()); }
}

// The shape of GNOME 50's misc/signalTracker.js: one tracker per emitter, keyed by
// the object that connected.
const trackers = new Map();
class Tracker {
    constructor(owner) { this._owner = owner; this._map = new Map(); }
    track(obj, id) { (this._map.get(obj) ?? this._map.set(obj, []).get(obj)).push(id); }
    untrack(obj) {
        (this._map.get(obj) ?? []).forEach(id => this._owner.disconnect(id));
        this._map.delete(obj);
        if (!this._map.size)
            trackers.delete(this._owner);
    }
}
function connectObject(emitter, fn, owner) {
    const t = trackers.get(emitter) ?? trackers.set(emitter, new Tracker(emitter)).get(emitter);
    t.track(owner, emitter.connect('changed::name', fn));
}

// GNOME's User Themes, as shipped in gnome-shell-extensions 50.
class ThemeManager {
    constructor() { this.reloads = 0; }
    enable() {
        this._settings = new Settings('org.gnome.shell.extensions.user-theme');
        connectObject(this._settings, () => this.reloads++, this);
    }
    disable() {
        this._settings?.disconnectObject?.();    // disconnects nothing: no object given
        this._settings = null;
    }
}

const UT = 'user-theme@gnome-shell-extensions.gcampax.github.com';
const ext = {uuid: UT, state: 1, stateObj: new ThemeManager()};
const timeouts = {fns: [], add(_ms, fn) { this.fns.push(fn); return this.fns.length; }, remove() {},
    run() { const f = this.fns; this.fns = []; f.forEach(fn => fn()); }};
const manager = {handlers: [], connect(_s, fn) { this.handlers.push(fn); return 1; }, disconnect() {},
    lookup: uuid => (uuid === UT ? ext : null)};
const themeContext = {handlers: [], connect(_s, fn) { this.handlers.push(fn); return this.handlers.length; },
    disconnect(id) { this.handlers[id - 1] = null; }, emit() { this.handlers.forEach(fn => fn?.()); }};
globalThis.global = {stage: {}};
globalThis.fake = {Settings, signalTrackers: trackers, timeouts, extensionManager: manager, themeContext};
globalThis.console = {...console, log: () => {}};
const {UserThemesTidy, tidyTrackers} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/themetidy.js');

test('each lock leaves one more listener in User Themes as GNOME ships it', () => {
    const tm = new ThemeManager();
    tm.enable();
    for (let i = 0; i < 5; i++) { tm.disable(); tm.enable(); }
    let all = 0;
    trackers.forEach((t, emitter) => { if (t._map.has(tm)) all += emitter.handlers.size; });
    assert.equal(all, 6);
    trackers.clear();
});

test('the tidy-up lets go of the stale listeners and keeps the current one', () => {
    const tm = ext.stateObj;
    tm.enable();
    const tidy = new UserThemesTidy();
    for (let i = 0; i < 5; i++) {
        tm.disable(); tm.enable();
        manager.handlers.forEach(fn => fn(manager, ext));    // User Themes is back on
        timeouts.run();
    }
    assert.equal(trackers.size, 1);
    assert.ok(trackers.has(tm._settings));
    assert.equal(tm._settings.handlers.size, 1);
    tm._settings.emit();
    assert.equal(tm.reloads, 1);
    assert.equal(tidy.tidied, 5);
    tidy.destroy();
});

test('a User Themes restart with no state change is tidied when the theme reloads', () => {
    trackers.clear();
    const tm = ext.stateObj;
    tm.enable();
    const tidy = new UserThemesTidy();
    const before = tidy.tidied;
    tm.disable(); tm.enable();                 // GNOME rebases extensions: no state change
    themeContext.emit();                       // its enable() loaded the theme
    assert.equal(tidy.tidied - before, 1);
    assert.equal(trackers.size, 1);
    tidy.destroy();
    assert.ok(themeContext.handlers.every(h => h === null));
});

test('other settings and other listeners are never touched', () => {
    trackers.clear();
    const tm = new ThemeManager();
    const other = new Settings('org.gnome.shell.extensions.dash-to-panel');
    const someone = {};
    connectObject(other, () => {}, tm);
    const oldUt = new Settings('org.gnome.shell.extensions.user-theme');
    connectObject(oldUt, () => {}, someone);       // not User Themes' own listener
    tm.enable();
    const n = tidyTrackers(trackers, tm, tm._settings, e => e.schema_id === 'org.gnome.shell.extensions.user-theme');
    assert.equal(n, 0);
    assert.equal(other.handlers.size, 1);
    assert.equal(oldUt.handlers.size, 1);
});

test('nothing happens when GNOME looks different', () => {
    assert.equal(tidyTrackers(undefined, {}, null, () => true), 0);
    assert.equal(tidyTrackers(new Map([[{}, {}]]), {}, null, () => true), 0);
});
