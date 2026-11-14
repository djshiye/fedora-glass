// While the glass is paused from Quick Settings, or in safe mode, the theme's see-through
// panel, menus and pop-ups have no glass under them: extension.js loads the solid sheet
// (paused.js) then, and only then. It goes when the glass comes back (before the glass's own
// sheet loads), at a lock and at disable, and the two sheets are never loaded together.
import assert from 'node:assert/strict';
import {register} from 'node:module';
import {test, beforeEach, afterEach} from 'node:test';

register('./extension-stubs.mjs', import.meta.url);

let live = new Set();
let log = [];
let later = [];
let overlaps = [];
const part = name => function (cfg) {
    log.push(name);
    live.add(name);
    // Recorded, not thrown: extension.js catches a part that throws.
    if (live.has('popups') && live.has('paused'))
        overlaps.push(name);
    return {cfg, updates: [],
        update(c) { this.updates.push(c); },
        destroy() { log.push(`${name} gone`); live.delete(name); },
        destroyLater(done) { later.push(() => { this.destroy(); done(); }); }};
};
let switches = [];
let safety;
let config;
const made = {};
const track = name => function (cfg) {
    const p = part(name)(cfg);
    made[name] = p;
    return p;
};
globalThis.fakeMods = {
    'animations.js': {Animations: part('animations')},
    'arcrescue.js': {ArcMenuRescue: part('rescue')},
    'config.js': {Config: onChange => {
        config = {value: {desktop: {}, quickToggle: {enabled: true}, pausedCss: '#uiGroup #panel {}'}, destroy() {}, onChange};
        return config;
    }},
    'frost.js': {WeatherFrost: () => ({update() {}, destroy() {}})},
    'desktop.js': {DesktopBehaviour: part('desktop')},
    'lock.js': {LockGlass: part('lock')},
    'lockwidgets.js': {LockWidgets: part('widgets')},
    'popupstyle.js': {PopupStyle: track('popups')},
    'paused.js': {PausedStyle: track('paused')},
    'pausestate.js': {PauseState: () => ({set() {}, destroy() {}})},
    'safety.js': {Safety: onChange => {
        safety = {tripped: false, onChange, glassStarted() {}, glassStopped() {}, startFailed() {}, destroy() {}};
        return safety;
    }, guarded: (_w, fn) => fn},
    'speed.js': {Speed: part('speed')},
    'surfaces.js': {GlassManager: part('glass')},
    'themetidy.js': {UserThemesTidy: part('tidy')},
    'tuning.js': {effectiveConfig: cfg => cfg},
    'quicktoggle.js': {GlassSwitch: (dir, onPause) => {
        const sw = {onPause, gone: false, setState() {}, destroy() { this.gone = true; }};
        switches.push(sw);
        return sw;
    }},
    'Extension': {Extension: function () { return {}; }},
};
globalThis.fake = {sessionMode: {isLocked: false, connect: () => 1, disconnect() {}}};
globalThis.logError = () => {};

const {default: FedoraGlassExtension} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/extension.js');

beforeEach(() => {
    live = new Set();
    log = [];
    later = [];
    switches = [];
    globalThis.fake.sessionMode.isLocked = false;
    overlaps = [];
});
afterEach(() => assert.deepEqual(overlaps, [], 'the glass sheet and the solid one were loaded together'));

function start() {
    const ext = Object.create(FedoraGlassExtension.prototype);
    ext.path = '/ext';
    ext.enable();
    return ext;
}
const tile = () => switches.filter(s => !s.gone)[0];
const lock = (ext, locked) => {
    globalThis.fake.sessionMode.isLocked = locked;
    ext._sync();
};

test('with the glass on there is no solid sheet', () => {
    const ext = start();
    assert.ok(live.has('popups') && !live.has('paused'));
    ext.disable();
    assert.equal(live.size, 0);
});

test('pause loads the solid sheet at once, after the glass sheet is gone; resume swaps back', () => {
    const ext = start();
    tile().onPause(true);
    assert.ok(live.has('paused') && !live.has('popups'));
    assert.ok(log.indexOf('popups gone') < log.lastIndexOf('paused'), 'the glass sheet goes first');
    assert.equal(made.paused.cfg, config.value, 'from the current settings');
    // A settings change (light or dark) reaches it.
    const next = {...config.value, pausedCss: '#uiGroup #panel { background-color: white; }'};
    config.value = next;
    config.onChange(next);
    assert.deepEqual(made.paused.updates, [next]);
    tile().onPause(false);
    assert.ok(!live.has('paused') && live.has('popups') && live.has('glass'));
    assert.ok(log.indexOf('paused gone') < log.lastIndexOf('popups'), 'unloaded before the glass sheet loads');
    // Pausing again twice is still one sheet.
    tile().onPause(true);
    tile().onPause(true);
    assert.equal(log.filter(n => n === 'paused').length, 2);
    ext.disable();
    assert.ok(!live.has('paused'), 'disable takes it away');
});

test('safe mode loads it too, and the glass coming back takes it away', () => {
    const ext = start();
    safety.tripped = true;
    safety.onChange(true);
    assert.ok(live.has('paused') && !live.has('popups') && !live.has('glass'));
    safety.tripped = false;
    safety.onChange(false);
    assert.ok(!live.has('paused') && live.has('popups'));
    ext.disable();
});

test('safe mode at login: the solid sheet from the start', () => {
    const was = globalThis.fakeMods['safety.js'].Safety;
    globalThis.fakeMods['safety.js'].Safety = onChange => {
        const s = was(onChange);
        s.tripped = true;
        return s;
    };
    const warn = console.warn;
    console.warn = () => {};
    try {
        const ext = start();
        assert.ok(live.has('paused') && !live.has('glass'));
        ext.disable();
        assert.equal(live.size, 0);
    } finally {
        globalThis.fakeMods['safety.js'].Safety = was;
        console.warn = warn;
    }
});

test('safe mode ending while paused keeps the solid sheet', () => {
    const ext = start();
    tile().onPause(true);
    safety.tripped = true;
    safety.onChange(true);
    safety.tripped = false;
    safety.onChange(false);
    assert.ok(live.has('paused') && !live.has('glass'));
    assert.equal(log.filter(n => n === 'paused').length, 1, 'never loaded twice');
    ext.disable();
});

test('not on the lock screen: it goes once the lock is up, and is back after the unlock', () => {
    const ext = start();
    tile().onPause(true);
    lock(ext, true);
    assert.equal(later.length, 1, 'removed a moment after the lock, as the glass sheet is');
    later.shift()();
    assert.ok(!live.has('paused'));
    lock(ext, false);
    assert.ok(live.has('paused') && !live.has('glass'), 'still paused after the unlock');
    ext.disable();
    assert.equal(live.size, 0);
});

test('an unlock before the lock\'s removal ran: the old sheet goes at once, one sheet stays', () => {
    const ext = start();
    tile().onPause(true);
    lock(ext, true);
    lock(ext, false);
    assert.equal(log.filter(n => n === 'paused gone').length, 1, 'the old one went first');
    assert.equal([...live].filter(n => n === 'paused').length, 1);
    ext.disable();
    assert.ok(!live.has('paused'));
});

test('disable while locked and paused leaves nothing loaded', () => {
    const ext = start();
    tile().onPause(true);
    lock(ext, true);
    ext.disable();
    assert.ok(!live.has('paused') && !live.has('popups'));
});

test('resumed while locked: no solid sheet on the lock screen, the glass after the unlock', () => {
    const ext = start();
    tile().onPause(true);
    lock(ext, true);
    later.splice(0).forEach(f => f());
    ext._setPaused(false);
    assert.ok(!live.has('paused'));
    lock(ext, false);
    assert.ok(live.has('glass') && live.has('popups') && !live.has('paused'));
    ext.disable();
});
