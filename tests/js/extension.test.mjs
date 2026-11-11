// extension.js _sync: each part it starts is guarded, so one that fails to start can't take
// the whole extension (and the glass) down. Desktop behaviour was the one part that wasn't.
import assert from 'node:assert/strict';
import {register} from 'node:module';
import {test} from 'node:test';

register('./extension-stubs.mjs', import.meta.url);

const made = [];
const part = name => function () {
    made.push(name);
    return {destroy() { made.push(`${name} gone`); }, update() {}, setState() {}};
};
const fail = name => () => {
    throw new Error(`${name} failed`);
};
globalThis.fakeMods = {
    'animations.js': {Animations: part('animations')},
    'arcrescue.js': {ArcMenuRescue: part('rescue')},
    'config.js': {Config: () => ({value: {desktop: {}}, destroy() {}})},
    'desktop.js': {DesktopBehaviour: part('desktop')},
    'lock.js': {LockGlass: part('lock')},
    'lockwidgets.js': {LockWidgets: part('widgets')},
    'popupstyle.js': {PopupStyle: part('popups')},
    'safety.js': {Safety: () => ({tripped: false, glassStarted() {}, glassStopped() {}, startFailed() {}, destroy() {}}),
        guarded: (_w, fn) => fn},
    'speed.js': {Speed: part('speed')},
    'surfaces.js': {GlassManager: part('glass')},
    'quicktoggle.js': {GlassSwitch: part('switch')},
    'themetidy.js': {UserThemesTidy: part('tidy')},
    'tuning.js': {effectiveConfig: cfg => cfg},
    'Extension': {Extension: function () { return {}; }},
};
globalThis.fake = {sessionMode: {isLocked: false, connect: () => 1, disconnect() {}}};
globalThis.logError = () => {};

const {default: FedoraGlassExtension} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/extension.js');

function quietly(fn) {
    const was = console.error;
    const said = [];
    console.error = m => said.push(String(m));
    try {
        fn();
    } finally {
        console.error = was;
    }
    return said;
}

test('the glass still starts when the desktop behaviour fails', () => {
    made.length = 0;
    globalThis.fakeMods['desktop.js'].DesktopBehaviour = fail('desktop');
    const ext = Object.create(FedoraGlassExtension.prototype);
    const said = quietly(() => assert.doesNotThrow(() => ext.enable()));
    assert.ok(made.includes('glass'), 'the glass did not start');
    assert.ok(made.includes('speed') && made.includes('rescue'), 'the parts after it did not start');
    assert.ok(said.some(m => m.includes('no desktop behaviour')), 'the failure was not logged');
    // Locking and switching off still work with that part missing.
    globalThis.fake.sessionMode.isLocked = true;
    assert.doesNotThrow(() => ext._sync());
    globalThis.fake.sessionMode.isLocked = false;
    assert.doesNotThrow(() => quietly(() => ext._sync()));
    assert.doesNotThrow(() => ext.disable());
    globalThis.fakeMods['desktop.js'].DesktopBehaviour = part('desktop');
});

test('with every part working, desktop behaviour starts as before', () => {
    made.length = 0;
    const ext = Object.create(FedoraGlassExtension.prototype);
    ext.enable();
    assert.ok(made.includes('desktop') && made.includes('glass'));
    ext.disable();
    assert.ok(made.includes('desktop gone'));
});
