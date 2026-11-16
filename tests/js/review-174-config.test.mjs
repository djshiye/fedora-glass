// 1.7.4 review, X4 and X5 (extension.js): a settings change that changes the glass level
// updates the glass once with the new level (not from the speed callback too), and a part
// whose update throws does not stop the others (each failure is one reported error).
import assert from 'node:assert/strict';
import {register} from 'node:module';
import {test} from 'node:test';

register('./extension-stubs.mjs', import.meta.url);

const calls = [];
const errors = [];
let handler = null;
let speedCb = null;
let level = 0;
const part = name => function () {
    return {destroy() {}, setState() {}, update(cfg) { calls.push([name, cfg, level]); if (part.fail === name) throw new Error('boom'); }};
};
globalThis.fakeMods = {
    'animations.js': {Animations: part('animations')},
    'arcrescue.js': {ArcMenuRescue: part('rescue')},
    'config.js': {Config: function (fn) { handler = fn; return {value: {desktop: {}, level: 0}, destroy() {}}; }},
    'frost.js': {WeatherFrost: part('frost')},
    'desktop.js': {DesktopBehaviour: part('desktop')},
    'lock.js': {LockGlass: part('lock')},
    'lockwidgets.js': {LockWidgets: part('widgets')},
    'popupstyle.js': {PopupStyle: part('popups')},
    'paused.js': {PausedStyle: part('paused')},
    'pausestate.js': {PauseState: () => ({set() {}, destroy() {}})},
    'safety.js': {Safety: () => ({tripped: false, glassStarted() {}, glassStopped() {}, startFailed() {}, destroy() {}}),
        guarded: (where, fn) => (...a) => { try { return fn(...a); } catch (e) { errors.push(where); } }},
    'speed.js': {Speed: function (_cfg, cb) {
        speedCb = cb;
        return {destroy() {}, get level() { return level; },
            update(cfg) { level = cfg.level; speedCb(); }};
    }},
    'surfaces.js': {GlassManager: part('glass')},
    'quicktoggle.js': {GlassSwitch: part('switch')},
    'themetidy.js': {UserThemesTidy: part('tidy')},
    'gcsweep.js': {SettingsSweep: part('sweep')},
    'tuning.js': {effectiveConfig: (cfg, l) => ({...cfg, effectiveLevel: l})},
    'Extension': {Extension: function () { return {}; }},
};
globalThis.fake = {sessionMode: {isLocked: false, connect: () => 1, disconnect() {}}};
globalThis.logError = () => {};

const {default: FedoraGlassExtension} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/extension.js');

function start() {
    const ext = Object.create(FedoraGlassExtension.prototype);
    ext.enable();
    calls.length = 0;
    errors.length = 0;
    return ext;
}
const glass = () => calls.filter(c => c[0] === 'glass');

test('a settings change that changes the level updates the glass once, with the new level', () => {
    const ext = start();
    handler({level: 2});
    assert.equal(glass().length, 1);
    assert.equal(glass()[0][1].effectiveLevel, 2);
    // Outside the handler (auto quality, a power change) the callback still updates.
    calls.length = 0;
    level = 1;
    speedCb();
    assert.equal(glass().length, 1);
    ext.disable();
});

test('one part that throws does not stop the others, and counts once', () => {
    const ext = start();
    part.fail = 'frost';
    handler({level: 0});
    part.fail = null;
    const got = calls.map(c => c[0]);
    for (const n of ['glass', 'frost', 'desktop', 'animations', 'popups'])
        assert.ok(got.includes(n), `${n} missed the change`);
    assert.equal(errors.length, 1);
    ext.disable();
});
