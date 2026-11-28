// Taskbar icons lift and hop away from the screen edge their panel sits on: up for a
// bottom panel (as always), down for a top one, sideways for a left or right one.
import assert from 'node:assert/strict';
import {test} from 'node:test';

import {Actor, makeFake, windowActor} from './anim-fake.mjs';

const {fake, shellwm, advance} = makeFake();
fake.fs = new Map();
const MON = {x: 0, y: 0, width: 2048, height: 1152};
fake.layoutManager.monitors = [MON];
const app = {id: 'files', state: 2};
fake.windowTracker.get_window_app = () => app;

const {Animations} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/animations.js');
const C = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/curves.js');

// A Dash to Panel panel along one edge of the screen, with one app icon in it.
// At the bottom or top the icon sits at the far left of the panel (a corner of the screen).
function dtp(edge, {withMonitor = true} = {}) {
    const thick = 48;
    const rect = {
        bottom: {x: 0, y: MON.height - thick, width: MON.width, height: thick},
        top: {x: 0, y: 0, width: MON.width, height: thick},
        left: {x: 0, y: 0, width: thick, height: MON.height},
        right: {x: MON.width - thick, y: 0, width: thick, height: MON.height},
    }[edge];
    const box = new Actor(rect);
    const inner = new Actor({width: 48, height: 40, x: rect.x + 4, y: rect.y + 4});
    const icon = new Actor({app, _iconContainer: inner, hover: false, _container: new Actor(), x: rect.x + 4, y: rect.y + 4});
    const panel = new Actor({taskbar: {_getAppIcons: () => [icon]}, statusArea: {}, panelBox: box,
        monitor: withMonitor ? MON : undefined});
    box.add_child(panel);
    panel.add_child(icon);
    icon.add_child(inner);
    globalThis.global.dashToPanel = Object.assign(new Actor(), {panels: [panel]});
    return {icon, inner};
}

function start(preset = 'spring') {
    return new Animations({animations: cleanMotion({hover: {preset}, launch: {preset: 'bounce'}, minimize: {preset: 'bounce'}}),
        glide: {enabled: false}});
}
const {cleanMotion} = C;

function hoverIt(el) {
    const {icon} = el;
    icon.hover = true;
    icon.emit('notify::hover');
    for (let i = 0; i < 60; i++)
        advance(16);
    return {tx: el.inner.translation_x, ty: el.inner.translation_y};
}

const goal = C.hoverTarget(cleanMotion({}).hover.intensity);

test('bottom panel: the hover lift goes up, to the value it always had', () => {
    const el = dtp('bottom');
    const an = start();
    const at = hoverIt(el);
    const {width: tw, height: th} = el.inner;
    an.destroy();
    // (these are the numbers of the old code: centred growth, lifted by goal.lift)
    assert.ok(at.ty === th * (1 - goal.scale) / 2 - goal.lift, `ty ${at.ty}`);
    assert.ok(at.tx === tw * (1 - goal.scale) / 2, `tx ${at.tx}`);
});

test('top panel: the hover lift goes down, away from the screen edge', () => {
    const el = dtp('top');
    const an = start();
    const at = hoverIt(el);
    const {width: tw, height: th} = el.inner;
    an.destroy();
    assert.equal(at.ty, th * (1 - goal.scale) / 2 + goal.lift);
    assert.equal(at.tx, tw * (1 - goal.scale) / 2);
});

test('left panel: the hover lift goes right', () => {
    const el = dtp('left');
    const an = start();
    const at = hoverIt(el);
    const {width: tw, height: th} = el.inner;
    an.destroy();
    assert.equal(at.tx, tw * (1 - goal.scale) / 2 + goal.lift);
    assert.equal(at.ty, th * (1 - goal.scale) / 2);
});

test('right panel: the hover lift goes left', () => {
    const el = dtp('right');
    const an = start();
    const at = hoverIt(el);
    const {width: tw, height: th} = el.inner;
    an.destroy();
    assert.equal(at.tx, tw * (1 - goal.scale) / 2 - goal.lift);
    assert.equal(at.ty, th * (1 - goal.scale) / 2);
});

test('a panel with no monitor to be found lifts up, as before', () => {
    const el = dtp('top', {withMonitor: false});
    const an = start();
    const at = hoverIt(el);
    const {height: th} = el.inner;
    an.destroy();
    assert.equal(at.ty, th * (1 - goal.scale) / 2 - goal.lift);
});

// The launch hop: how far the icon gets from rest, and in which direction.
function hopExtent(el) {
    const an = start();
    app.state = 1;
    fake.appSystem.emit('app-state-changed', app);
    let most = {x: 0, y: 0};
    for (let i = 0; i < 40; i++) {
        advance(16);
        const {translation_x: x, translation_y: y} = el.inner;
        if (Math.abs(x) + Math.abs(y) > Math.abs(most.x) + Math.abs(most.y))
            most = {x, y};
    }
    an.destroy();
    app.state = 2;
    return most;
}

test('launch hop: a bottom panel hops up, a top panel down, side panels sideways', () => {
    const bottom = hopExtent(dtp('bottom'));
    const top = hopExtent(dtp('top'));
    const left = hopExtent(dtp('left'));
    const right = hopExtent(dtp('right'));
    assert.ok(bottom.y < -4 && Math.abs(bottom.x) < 4, `bottom ${JSON.stringify(bottom)}`);
    assert.ok(top.y > 4 && Math.abs(top.x) < 4, `top ${JSON.stringify(top)}`);
    assert.ok(left.x > 4 && Math.abs(left.y) < 4, `left ${JSON.stringify(left)}`);
    assert.ok(right.x < -4 && Math.abs(right.y) < 4, `right ${JSON.stringify(right)}`);
});

// The icon's translation, frame by frame, while a window lands in it with the bounce.
function landing(edge) {
    const el = dtp(edge);
    const an = start();
    const a = windowActor(fake);
    shellwm.emit('kill-window-effects', a);
    shellwm.emit('minimize', a);
    const frames = [];
    for (let i = 0; i < 80; i++) {
        advance(16);
        frames.push([el.inner.translation_x, el.inner.translation_y]);
    }
    an.destroy();
    return frames;
}

test('the bounce landing dips away from the edge: down on a top panel, sideways on side panels', () => {
    const bottom = landing('bottom'), top = landing('top'), left = landing('left'), right = landing('right');
    // Only the dip changes sign with the edge: the rest of the give is the same.
    const dip = (a, b, axis) => a.map((f, i) => (f[axis] - b[i][axis]) / 2);
    const downDip = dip(top, bottom, 1), sideDip = dip(left, right, 0);
    assert.ok(downDip.every(d => d > -1e-9) && Math.max(...downDip) > 1, `top panel dip ${Math.max(...downDip)}`);
    assert.ok(sideDip.every(d => d > -1e-9) && Math.max(...sideDip) > 1, `left panel dip ${Math.max(...sideDip)}`);
    assert.ok(dip(left, right, 1).every(d => Math.abs(d) < 1e-9), 'a side panel does not dip up or down');
    // The bottom panel dips up, by the same amount (the old behaviour).
    assert.ok(bottom.some(f => f[1] < -1));
});
