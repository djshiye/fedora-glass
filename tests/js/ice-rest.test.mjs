// Weather frost: a frozen bar's ice comes to rest when the pointer does. Up to 1.7.4 a
// pointer left lying within reach of a frozen taskbar kept the ice's clock running for as
// long as it stayed there: 30 redraws a second of the whole panel, with nothing in use.
// Also: a picture the glass let go of is let go of by the pipeline that drew it.
import assert from 'node:assert/strict';
import {test} from 'node:test';

import {loadGlass} from './glass-harness.mjs';

class Actor {
    constructor(...a) {
        this._h = new Map(); this._n = 1; this._kids = [];
        Object.assign(this, {x: 0, y: 0, width: 0, height: 0, visible: true, mapped: true, has_clip: false});
        this._init?.(...a);
    }
    _init(props = {}) { Object.assign(this, props); }
    connect(s, fn) { const id = this._n++; this._h.set(id, [s, fn]); return id; }
    disconnect(id) { this._h.delete(id); }
    emit(s, ...a) { for (const [n, fn] of [...this._h.values()]) if (n === s) fn(this, ...a); }
    add_effect_with_name(n, e) { this.effect = e; e.get_actor = () => this; }
    add_child(c) { this._kids.push(c); }
    set_child_above_sibling() {} set_child_below_sibling() {}
    set_position(x, y) { this.x = x; this.y = y; }
    set_size(w, h) { this.width = w; this.height = h; }
    set_clip(...c) { this.has_clip = true; this.clip = c; }
    remove_clip() { this.has_clip = false; }
    show() { this.visible = true; } hide() { this.visible = false; }
    queue_repaint() {} queue_redraw() {}
    get_stage() { return global.stage; }
    destroy() { this.emit('destroy'); }
    get_transformed_position() { return [this.x, this.y]; }
}

let now = 1e9;
const timers = new Map();
let nextId = 1;
globalThis.fake = {Actor, now: () => now, stSettings: {enable_animations: true},
    timeouts: {add: (ms, fn) => { const id = nextId++; timers.set(id, {ms, fn}); return id; },
        remove: id => timers.delete(id)}};
const stage = Object.assign(new Actor(), {get_size: () => [2560, 1440],
    get_context: () => ({get_backend: () => ({get_cogl_context: () => ({})})}), peek_stage_views: () => []});
globalThis.global = {stage, display: {get_n_monitors: () => 1, get_monitor_geometry: () => ({x: 0, y: 0, width: 2560, height: 1440})},
    compositor: {get_laters: () => ({add: () => 1, remove() {}})}};

const G = await loadGlass();
const {ICE_LINGER_US} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/frostmath.js');

/** Let the ice's clock tick for `seconds`; returns how many times it ticked. */
function run(seconds) {
    let ticks = 0;
    for (let i = 0; i < 30 * seconds; i++) {
        const t = [...timers.entries()].find(([, v]) => v.ms === 33);
        if (!t)
            break;
        now += 33333;
        ticks++;
        if (!t[1].fn())
            timers.delete(t[0]);
    }
    return ticks;
}

function frozenBar() {
    const pane = new G.GlassPane('glass');
    const top = new G.GlassPane('reflections');
    top.shareIce(pane);
    pane.place(0, 1396, 2560, 44, [0, 0, 0, 0], 0, 1396);
    top.place(0, 1396, 2560, 44, [0, 0, 0, 0], 0, 1396);
    pane.show(); top.show();
    G.setFrost(1, 1);
    return [pane, top];
}

// motion.js: the pointer 150 px above the bar, pointer light 0.5.
const NEAR = Math.min(1, 0.5 * 1.6) * (1 - 150 / 220);

test('the pointer left resting by a frozen taskbar: the ice comes to rest', () => {
    const [pane, top] = frozenBar();
    pane.setMotion({sx: 1200, sy: 1246, k: NEAR});
    top.setMotion({sx: 1200, sy: 1246, iceK: NEAR});
    assert.ok(G.iceRunning(), 'the pointer came near: the ice is alive');
    const ticks = run(600);     // ten minutes of the pointer lying still
    assert.equal(G.iceRunning(), false, 'the clock stopped');
    // The linger, plus the clock slowing to a stop: seconds, not the 18,000 ticks of 1.7.4.
    assert.ok(ticks < 30 * (ICE_LINGER_US / 1e6 + 5), `the ice ticked ${ticks} times in ten minutes at rest`);
    const t = pane._ice.t;
    run(60);
    assert.equal(pane._ice.t, t, 'and it lies still after');
    pane.destroy(); top.destroy();
});

test('the pointer moving by the bar keeps the ice alive, and wakes it again after a rest', () => {
    const [pane, top] = frozenBar();
    let x = 1200;
    const move = () => {
        x += 3;
        pane.setMotion({sx: x, sy: 1246, k: NEAR});
        top.setMotion({sx: x, sy: 1246, iceK: NEAR});
    };
    move();
    // Twenty seconds of slow gliding along the bar: longer than the linger.
    for (let i = 0; i < 40; i++) {
        assert.equal(run(0.5), 15, 'the clock runs while the pointer moves');
        move();
    }
    assert.ok(G.iceRunning());
    run(600);
    assert.equal(G.iceRunning(), false, 'at rest');
    const t = pane._ice.t;
    move();
    assert.ok(G.iceRunning(), 'one move wakes it');
    run(1);
    assert.ok(pane._ice.t > t, 'and the ice moves again');
    pane.destroy(); top.destroy();
});

test('a press holds the ice alive however long, and an open menu is in use while it shows', () => {
    const [pane, top] = frozenBar();
    pane.setMotion({sx: 1200, sy: 1410, k: 0.8, press: 1});
    run(60);
    assert.ok(G.iceRunning(), 'held down for a minute: still alive');
    pane.setMotion({press: 0});
    run(60);
    assert.equal(G.iceRunning(), false);
    pane.destroy(); top.destroy();

    G.setFrost(0, 0);
    const menu = new G.GlassPane('glass');
    menu.place(800, 60, 420, 520, [16, 16, 16, 16], 800, 60);
    menu.show();
    G.setFrost(1, 1);
    run(60);
    assert.ok(G.iceRunning(), 'a menu left open keeps its ice alive with the pointer away');
    menu.destroy();
});

test('a kept picture that is dropped is let go of by the pipeline that drew it', () => {
    const pane = new G.GlassPane('glass');
    const e = pane._glass;
    const calls = [];
    const blit = {set_layer_null_texture: i => calls.push(i)};
    e._blit = blit;
    e._blitTex = {};
    e.drop();
    assert.deepEqual(calls, [0], 'drop() clears the kept picture\'s texture from its pipeline');
    assert.equal(e._blitTex, null, 'so the next kept draw sets it again');
    e.drop();
    assert.deepEqual(calls, [0], 'nothing to let go of twice');

    e.keep = true;
    e._blitTex = {};
    e.keep = false;
    assert.deepEqual(calls, [0, 0], 'turning keep off (a window being dragged) lets go of it too');
    assert.equal(e._blitTex, null);
    pane.destroy();
});
