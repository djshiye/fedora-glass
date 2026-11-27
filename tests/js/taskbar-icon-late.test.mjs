// Dash to Panel fills a taskbar after we first look at it (its icons come as deferred work):
// an icon that arrives later still lifts under the pointer, and nothing is left connected after destroy().
import assert from 'node:assert/strict';
import {test} from 'node:test';

import {Actor, makeFake} from './anim-fake.mjs';

const {fake, advance} = makeFake();
fake.fs = new Map();
const app = {id: 'files'};
fake.windowTracker.get_window_app = () => app;

const {Animations} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/animations.js');
const {cleanMotion} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/curves.js');

function makeIcon() {
    const inner = new Actor({width: 48, height: 40});
    return {inner, icon: new Actor({app, _iconContainer: inner, hover: false, _container: new Actor()})};
}

// A panel whose taskbar is still empty.
function makePanel() {
    const icons = [];
    const box = new Actor();
    const panel = new Actor({taskbar: {_getAppIcons: () => icons, _box: box}, statusArea: {}});
    return {panel, icons, box};
}

function start(panels, hover = 'spring') {
    globalThis.global.dashToPanel = Object.assign(new Actor(), {panels});
    return new Animations({animations: cleanMotion({hover: {preset: hover}, launch: {preset: 'off'}}),
        glide: {enabled: false}});
}

function arrive({icon, inner}, {icons, box}) {
    icons.push(icon);
    box.emit('child-added', icon);
    fake.timeouts.fire();   // the idle that looks again
    icon.hover = true;
    icon.emit('notify::hover');
    for (let i = 0; i < 40; i++)
        advance(16);
    return inner.translation_y;
}

test('an icon Dash to Panel adds after the start lifts under the pointer', () => {
    const p = makePanel();
    const an = start([p.panel]);
    assert.ok(arrive(makeIcon(), p) < -1, 'the icon should lift');
    an.destroy();
});

test('an icon added after Dash to Panel built a new panel lifts under the pointer', () => {
    const old = makePanel();
    const an = start([old.panel]);
    const fresh = makePanel();
    globalThis.global.dashToPanel.panels = [fresh.panel];
    globalThis.global.dashToPanel.emit('panels-created');
    fake.timeouts.fire();
    assert.equal(old.box.count(), 0, 'the old panel should be let go');
    assert.ok(arrive(makeIcon(), fresh) < -1, 'the icon should lift');
    an.destroy();
});

test('nothing stays connected to a taskbar after destroy', () => {
    const a = makePanel();
    const b = makePanel();
    const an = start([a.panel, b.panel]);
    assert.equal(a.box.count(), 1);
    assert.equal(b.box.count(), 1);
    an.destroy();
    assert.equal(a.box.count(), 0);
    assert.equal(b.box.count(), 0);
});

test('hover animation off: no taskbar is followed', () => {
    const p = makePanel();
    const an = start([p.panel], 'off');
    assert.equal(p.box.count(), 0);
    an.destroy();
});

test('a panel without an icon box is fine', () => {
    const panel = new Actor({taskbar: {_getAppIcons: () => []}, statusArea: {}});
    const an = start([panel]);
    an.destroy();
});
