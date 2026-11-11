// Pausing the glass from Quick Settings (extension.js): the glass and the animations come
// down as in safe mode, nothing is written, the pause lasts through a lock, and the next
// login (a fresh enable) starts with the glass on. The tile is there only while the
// setting says so.
import assert from 'node:assert/strict';
import {register} from 'node:module';
import {test, beforeEach} from 'node:test';

register('./extension-stubs.mjs', import.meta.url);

const made = [];
let live = new Set();
const part = name => function () {
    made.push(name);
    live.add(name);
    return {destroy() { made.push(`${name} gone`); live.delete(name); }, update() {}};
};
let switches = [];
let safety;
let config;
globalThis.fakeMods = {
    'animations.js': {Animations: part('animations')},
    'arcrescue.js': {ArcMenuRescue: part('rescue')},
    'config.js': {Config: onChange => {
        config = {value: {desktop: {}, quickToggle: {enabled: true}}, destroy() {}, onChange};
        return config;
    }},
    'desktop.js': {DesktopBehaviour: part('desktop')},
    'lock.js': {LockGlass: part('lock')},
    'lockwidgets.js': {LockWidgets: part('widgets')},
    'popupstyle.js': {PopupStyle: part('popups')},
    'safety.js': {Safety: onChange => {
        safety = {tripped: false, onChange, calls: [], glassStarted() { this.calls.push('started'); },
            glassStopped() { this.calls.push('stopped'); }, startFailed() {}, destroy() {}};
        return safety;
    }, guarded: (_w, fn) => fn},
    'speed.js': {Speed: part('speed')},
    'surfaces.js': {GlassManager: part('glass')},
    'themetidy.js': {UserThemesTidy: part('tidy')},
    'tuning.js': {effectiveConfig: cfg => cfg},
    'quicktoggle.js': {GlassSwitch: (dir, onPause) => {
        const sw = {dir, onPause, state: null, gone: false,
            setState(p, safe) { this.state = {paused: p, safe}; }, destroy() { this.gone = true; }};
        switches.push(sw);
        return sw;
    }},
    'Extension': {Extension: function () { return {}; }},
};
globalThis.fake = {sessionMode: {isLocked: false, connect: () => 1, disconnect() {}}};
globalThis.logError = () => {};

const {default: FedoraGlassExtension} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/extension.js');

beforeEach(() => {
    made.length = 0;
    live = new Set();
    switches = [];
    globalThis.fake.sessionMode.isLocked = false;
});

function start() {
    const ext = Object.create(FedoraGlassExtension.prototype);
    ext.path = '/ext';
    ext.enable();
    return ext;
}
const shown = () => switches.filter(s => !s.gone);

test('the tile is there with the glass on', () => {
    const ext = start();
    assert.equal(shown().length, 1);
    assert.equal(shown()[0].dir, '/ext', 'it finds its icon in the extension folder');
    assert.deepEqual(shown()[0].state, {paused: false, safe: false});
    assert.ok(live.has('glass') && live.has('animations'));
    ext.disable();
    assert.equal(shown().length, 0);
});

test('pause: glass, animations and pop-up styles come down; the rest stays; back on, they return', () => {
    const ext = start();
    shown()[0].onPause(true);
    assert.ok(!live.has('glass') && !live.has('animations') && !live.has('popups'), 'the safe mode path');
    assert.ok(live.has('desktop') && live.has('speed'), 'desktop behaviour carries on');
    assert.equal(safety.calls.at(-1), 'stopped', 'a Shell stop while paused is no glass crash');
    assert.deepEqual(shown()[0].state, {paused: true, safe: false});
    // A settings change while paused does not bring the glass back.
    config.onChange({desktop: {}, quickToggle: {enabled: true}});
    assert.ok(!live.has('glass'));
    shown()[0].onPause(false);
    assert.ok(live.has('glass') && live.has('animations') && live.has('popups'));
    assert.deepEqual(shown()[0].state, {paused: false, safe: false});
    ext.disable();
});

test('safe mode turning off while paused keeps the glass paused', () => {
    const ext = start();
    shown()[0].onPause(true);
    safety.onChange(false);
    assert.ok(!live.has('glass'));
    ext.disable();
});

test('the pause lasts through a lock; the next login starts with the glass on', () => {
    const ext = start();
    shown()[0].onPause(true);
    globalThis.fake.sessionMode.isLocked = true;
    ext._sync();
    assert.equal(shown().length, 0, 'no tile on the lock screen');
    globalThis.fake.sessionMode.isLocked = false;
    ext._sync();
    assert.ok(!live.has('glass'), 'still paused after unlocking');
    assert.deepEqual(shown()[0].state, {paused: true, safe: false});
    ext.disable();
    // The next login: a new session enables the extension afresh.
    live = new Set();
    const next = start();
    assert.ok(live.has('glass'));
    assert.deepEqual(shown()[0].state, {paused: false, safe: false});
    next.disable();
});

test('the setting off: no tile, and a pause ends with it', () => {
    const ext = start();
    shown()[0].onPause(true);
    config.onChange({desktop: {}, quickToggle: {enabled: false}});
    assert.equal(shown().length, 0);
    assert.ok(live.has('glass'), 'no way to turn it back on, so the glass is back');
    config.onChange({desktop: {}, quickToggle: {enabled: true}});
    assert.equal(shown().length, 1);
    ext.disable();
});

test('a tile that fails to show leaves the glass running', () => {
    const was = globalThis.fakeMods['quicktoggle.js'].GlassSwitch;
    const err = console.error;
    console.error = () => {};
    globalThis.fakeMods['quicktoggle.js'].GlassSwitch = () => {
        throw new Error('forced test failure');
    };
    try {
        const ext = start();
        assert.ok(live.has('glass'));
        ext.disable();
    } finally {
        globalThis.fakeMods['quicktoggle.js'].GlassSwitch = was;
        console.error = err;
    }
});
