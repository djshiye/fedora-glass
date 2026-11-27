// The weather frost's last reading, kept over a lock, also survives the way GNOME locks the
// first time in a session: it switches the extension off and straight on again (extension.js).
import assert from 'node:assert/strict';
import {register} from 'node:module';
import {test} from 'node:test';

register('./extension-frost-stubs.mjs', import.meta.url);

let clockMs = 0;
const timers = new Map();
let nextId = 1;
const weather = {client: null};
class Actor { constructor(p = {}) { Object.assign(this, p); } connect() { return 1; } disconnect() {} destroy() {} }
globalThis.fake = {
    Actor, Widget: Actor, ui: new Actor(), uiGroup: new Actor(),
    now: () => clockMs * 1000,
    realNow: () => 1e15 + clockMs * 1000,
    timeouts: {add: (ms, fn) => { const id = nextId++; timers.set(id, fn); return id; }, remove: id => timers.delete(id)},
    fs: new Map(), monitors: [], frosts: [], flakes: [],
    sessionMode: {isLocked: false, connect: () => 1, disconnect() {}},
    panel: {statusArea: {dateMenu: {_weatherItem: {get _weatherClient() { return weather.client; }}}}},
};
globalThis.logError = () => {};
console.warn = () => {};

const part = () => function () { return {destroy() {}, update() {}}; };
globalThis.fakeMods = {
    'animations.js': {Animations: part()},
    'arcrescue.js': {ArcMenuRescue: part()},
    'config.js': {Config: () => ({value: {desktop: {}, quickToggle: {enabled: false}, weather: {enabled: true}}, destroy() {}})},
    'desktop.js': {DesktopBehaviour: part()},
    'lock.js': {LockGlass: part()},
    'lockwidgets.js': {LockWidgets: part()},
    'popupstyle.js': {PopupStyle: part()},
    'paused.js': {PausedStyle: part()},
    'pausestate.js': {PauseState: () => ({set() {}, destroy() {}})},
    'safety.js': {Safety: () => ({tripped: false, glassStarted() {}, glassStopped() {}, startFailed() {}, destroy() {}}),
        guarded: (_w, fn) => fn},
    'speed.js': {Speed: function () { return {level: 0, destroy() {}, update() {}}; }},
    'surfaces.js': {GlassManager: part()},
    'themetidy.js': {UserThemesTidy: part()},
    'gcsweep.js': {SettingsSweep: part()},
    'windows.js': {Windows: part(), allSolid: c => c},
    'tuning.js': {effectiveConfig: c => c},
    'quicktoggle.js': {GlassSwitch: part()},
    'Extension': {},
};

const {default: Ext} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/extension.js');

function client(temp) {
    return {available: true, hasLocation: true, loading: false, handlers: new Map(), n: 0,
        info: {is_valid: () => true, get_value_temp: () => [true, temp], get_value_apparent: () => [true, temp]},
        connect(_s, fn) { this.handlers.set(++this.n, fn); return this.n; }, disconnect(id) { this.handlers.delete(id); },
        update() {}};
}

function run(rebase) {
    weather.client = client(-5);
    const ext = Object.create(Ext.prototype);
    ext.path = '/ext';
    ext.enable();                                   // logged in, on the desktop, frost on
    const frosted = globalThis.fake.frosts.at(-1);
    assert.ok(frosted && frosted[0] > 0, 'frosted over');
    globalThis.fake.sessionMode.isLocked = true;
    let cur = ext;
    if (rebase) {
        // First lock of the session: GNOME switches the extension off and straight on (rebase).
        clockMs += 200;
        ext.disable();
        cur = Object.create(Ext.prototype);
        cur.path = '/ext';
        cur.enable();
    } else {
        ext._sync();
    }
    // The PC wakes on the lock screen; GNOME's weather refreshes (offline): still loading at unlock.
    weather.client.loading = true;
    clockMs += 60e3;
    globalThis.fake.sessionMode.isLocked = false;
    cur._sync();
    const after = globalThis.fake.frosts.at(-1);
    cur.disable();
    globalThis.fake.sessionMode.isLocked = false;
    return {frosted, after};
}

test('the frost showing before a lock is there at once after unlocking while the weather refreshes', () => {
    const {frosted, after} = run(false);
    assert.deepEqual(after, frosted);
});

test('the same at the first lock of a session, when GNOME switches the extension off and on again', () => {
    const {frosted, after} = run(true);
    assert.deepEqual(after, frosted, `frost after unlock ${JSON.stringify(after)} vs before ${JSON.stringify(frosted)}`);
});

test('switched off and on by hand, the weather is read afresh: no old reading is carried over', () => {
    weather.client = client(-5);
    const ext = Object.create(Ext.prototype);
    ext.path = '/ext';
    ext.enable();
    assert.ok(globalThis.fake.frosts.at(-1)[0] > 0, 'frosted over');
    ext.disable();
    weather.client.loading = true;
    clockMs += 60e3;
    const again = Object.create(Ext.prototype);
    again.path = '/ext';
    again.enable();
    assert.deepEqual(globalThis.fake.frosts.at(-1), [0, 0]);
    again.disable();
});
