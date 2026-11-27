// A taskbar icon under the pointer keeps its hover lift when the window it minimizes
// lands in it (the icon gives a little around the lift, then goes back to it).
import assert from 'node:assert/strict';
import {test} from 'node:test';

import {Actor, makeFake, windowActor} from './anim-fake.mjs';

const {fake, shellwm, advance} = makeFake();
fake.fs = new Map();
const app = {id: 'files'};
fake.windowTracker.get_window_app = () => app;
const inner = new Actor({width: 48, height: 40});
const icon = new Actor({app, _iconContainer: inner, hover: false, _container: new Actor()});
const panel = new Actor({taskbar: {_getAppIcons: () => [icon]}, statusArea: {}});
globalThis.global.dashToPanel = Object.assign(new Actor(), {panels: [panel]});

const {Animations} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/animations.js');
const {cleanMotion} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/curves.js');

const snap = a => ({sx: +a.scale_x.toFixed(3), ty: +a.translation_y.toFixed(2)});

function lift(preset) {
    const an = new Animations({animations: cleanMotion({minimize: {preset}, hover: {preset: 'spring'}}),
        glide: {enabled: false}});
    icon.hover = true;
    icon.emit('notify::hover');
    for (let i = 0; i < 40; i++)
        advance(16);
    return an;
}

for (const preset of ['spring', 'bounce', 'jelly']) {
    test(`${preset}: the icon under the pointer stays lifted after its window lands in it`, () => {
        const an = lift(preset);
        const lifted = snap(inner);
        assert.ok(lifted.sx > 1.03 && lifted.ty < -1, 'the icon should be lifted before the click');
        const a = windowActor(fake);
        shellwm.emit('kill-window-effects', a);
        shellwm.emit('minimize', a);   // the click on the icon minimized it; the pointer stays on the icon
        const trace = [];
        for (let i = 0; i < 80; i++) {
            advance(16);
            trace.push(snap(inner));
        }
        an.destroy();
        assert.deepEqual(trace.at(-1), lifted, 'the icon under the pointer should end lifted');
        // The give is around the lift: the icon never drops to its resting size.
        assert.ok(trace.every(s => s.sx > 1.0), `the icon dropped out of its lift: ${JSON.stringify(trace.find(s => s.sx <= 1.0))}`);
        assert.equal(icon.hover, true);
    });
}

test('the pointer left the icon during the landing: it settles back to rest', () => {
    const an = lift('spring');
    const a = windowActor(fake);
    shellwm.emit('kill-window-effects', a);
    shellwm.emit('minimize', a);
    for (let i = 0; i < 40; i++)
        advance(16);
    icon.hover = false;
    icon.emit('notify::hover');
    for (let i = 0; i < 80; i++)
        advance(16);
    an.destroy();
    assert.deepEqual(snap(inner), {sx: 1, ty: 0});
});

test('hover animation off: the icon gives a little and ends at rest', () => {
    const an = new Animations({animations: cleanMotion({minimize: {preset: 'bounce'}, hover: {preset: 'off'}}),
        glide: {enabled: false}});
    const a = windowActor(fake);
    shellwm.emit('kill-window-effects', a);
    shellwm.emit('minimize', a);
    let moved = false;
    for (let i = 0; i < 80; i++) {
        advance(16);
        moved ||= inner.scale_x !== 1;
    }
    an.destroy();
    assert.ok(moved, 'the icon should give a little');
    assert.deepEqual(snap(inner), {sx: 1, ty: 0});
});
