// What a pane leaves behind each time it is drawn. Every native object an extension makes
// (a box, a colour, a screen's rectangle) is freed only when GNOME cleans up the whole
// Shell, every 10 s while the desktop is in use; the more is left, the longer that stop.
// On 1.7.4 a pane made five or more on every frame that only showed its glass again.
import assert from 'node:assert/strict';
import {test} from 'node:test';

import {loadGlass} from './glass-harness.mjs';

class Actor {
    constructor(...a) {
        this._h = new Map();
        this._n = 1;
        this._kids = [];
        Object.assign(this, {x: 0, y: 0, width: 0, height: 0, visible: true, mapped: true, has_clip: false, effects: []});
        this._init?.(...a);
    }
    _init(props = {}) { Object.assign(this, props); }
    connect(s, fn) { const id = this._n++; this._h.set(id, [s, fn]); return id; }
    disconnect(id) { this._h.delete(id); }
    emit(s, ...a) { for (const [n, fn] of [...this._h.values()]) if (n === s) fn(this, ...a); }
    add_effect_with_name(n, e) { e.name = n; this.effects.push(e); e.get_actor = () => this; }
    remove_effect(e) { this.effects = this.effects.filter(x => x !== e); e.get_actor = () => null; }
    add_child(c) { this._kids.push(c); }
    set_child_above_sibling() {}
    set_child_below_sibling() {}
    set_position(x, y) { this.x = x; this.y = y; }
    set_size(w, h) { this.width = w; this.height = h; }
    set_clip(...c) { this.has_clip = true; this.clip = c; }
    remove_clip() { this.has_clip = false; }
    show() { this.visible = true; }
    hide() { this.visible = false; }
    queue_redraw() {}
    get_stage() { return global.stage; }
    destroy() { this.emit('destroy'); }
    get_paint_opacity() { return this.paintOpacity ?? 255; }
    get_transformed_position() { return [this.x, this.y]; }
    get_transformed_size() { return [this.width, this.height]; }
    get_transformed_extents() {
        return {get_x: () => this.x, get_y: () => this.y, get_width: () => this.width, get_height: () => this.height};
    }
}

// Two screens side by side, as Mutter tells of them.
let asked = 0;
const view = (x, scale = 1) => ({scale, get_scale() { return this.scale; },
    get_layout(r) { asked++; Object.assign(r, {x, y: 0, width: 2560, height: 1440}); }});
let views = [view(0), view(2560)];
const timers = new Map();
let nextTimer = 1;
const stage = Object.assign(new Actor(), {get_size: () => [5120, 1440],
    get_context: () => ({get_backend: () => ({get_cogl_context: () => ({})})}), peek_stage_views: () => views});
globalThis.fake = {Actor, ui: new Actor(), made: {}, now: () => 0,
    timeouts: {add: (ms, fn) => { const id = nextTimer++; timers.set(id, {ms, fn}); return id; }, remove: id => timers.delete(id)}};
globalThis.global = {stage, display: {get_n_monitors: () => 2, get_monitor_geometry: i => ({x: 2560 * i, y: 0, width: 2560, height: 1440})},
    compositor: {get_laters: () => ({add: () => 1, remove() {}})}};

const {GlassPane, hasRedrawArea, paintCount} = await loadGlass({paint: true});

const DIRTY = 1;
const root = () => ({kids: [], add_child(c) { this.kids.push(c); }});
const ctx = {get_redraw_clip: () => null};

function shown(layer = 'glass') {
    const pane = new GlassPane(layer);
    pane.place(100, 100, 400, 300, [8, 8, 8, 8], 100, 100);
    pane._glass.vfunc_paint_node(root(), ctx, DIRTY);      // its first picture
    return pane;
}
const again = (pane, times = 10) => {
    const before = {...fake.made};
    let last = null;
    for (let i = 0; i < times; i++)
        pane._glass.vfunc_paint_node(last = root(), ctx, 0);
    const made = {};
    for (const [k, v] of Object.entries(fake.made)) {
        if (v !== (before[k] ?? 0))
            made[k] = v - (before[k] ?? 0);
    }
    return {made, last};
};

test('a pane that shows its glass again makes one draw step and nothing else', () => {
    const pane = shown();
    const {made, last} = again(pane);
    assert.deepEqual(made, {PipelineNode: 10}, 'no box, colour, matrix or screen rectangle per frame');
    assert.equal(last.kids.length, 1);
    assert.deepEqual(last.kids[0].rect.slice(0, 1), [pane._glass._box]);
    pane.destroy();
});

test('so does one whose lens keeps its finished glass (125 %), and a sharp rim', () => {
    const kept = shown();
    kept._glass.keep = true;
    kept._glass.vfunc_paint_node(root(), ctx, 0);          // the lens runs into the kept picture once
    assert.deepEqual(again(kept).made, {PipelineNode: 10});
    const rim = shown('rim');
    rim._glass.radius = 0;                                  // a sharp copy asks for the screen's scale
    rim._glass.vfunc_paint_node(root(), ctx, DIRTY);
    assert.deepEqual(again(rim).made, {PipelineNode: 10});
    kept.destroy();
    rim.destroy();
});

test('a new size or a fade makes a new box or colour once, not once a frame', () => {
    const pane = shown();
    pane._glass.keep = true;
    pane._glass.vfunc_paint_node(root(), ctx, 0);
    pane.paintOpacity = 128;
    const fade = again(pane).made;
    assert.equal(fade.Color, 1, 'one colour for the new opacity');
    assert.equal(pane._glass._blit.color.alpha, 128);
    pane.width = 420;
    pane._glass.vfunc_paint_node(root(), ctx, 0);          // a new size renders anew, with a new box
    assert.equal(pane._glass._box.x2, 420);
    assert.deepEqual(again(pane).made, {PipelineNode: 10}, 'and then none again');
    pane.destroy();
});

test('the screens are looked up once, and again when Mutter makes new ones', () => {
    const pane = shown('rim');
    pane._glass.radius = 0;
    pane._glass.vfunc_paint_node(root(), ctx, DIRTY);
    asked = 0;
    again(pane, 50);
    assert.equal(asked, 0, 'not for every frame');
    // The screens changed (a new scale): told by the stage's size...
    views = [view(0, 2), view(2560, 2)];
    stage.emit('notify::width');
    again(pane, 5);
    assert.equal(asked, 2, 'each screen once');
    assert.match(pane._glass._targetFor, /@2\//, 'and the picture follows the new scale');
    // ...or seen as a screen the list does not hold being painted.
    views = [view(0, 1), view(2560, 1)];
    asked = 0;
    stage.emit('before-paint', views[0]);
    again(pane, 5);
    stage.emit('after-paint', views[0]);
    assert.equal(asked, 2);
    assert.match(pane._glass._targetFor, /@1\//);
    pane.destroy();
});

test('Clutter keeps the finished glass, unless that costs too much at a fractional scale', () => {
    views = [view(0), view(2560)];
    stage.emit('notify::width');
    const pane = shown();              // 400 x 300: a window-sized pane would be larger still
    const names = () => pane.effects.map(e => e.name);
    const kept = () => names().includes('fedora-glass-keep');
    assert.deepEqual(names(), ['fedora-glass-lens'], 'a menu or the panel keeps nothing');
    pane.setKeep(true);
    assert.deepEqual(names(), ['fedora-glass-keep', 'fedora-glass-lens'],
        'the keeper comes first: Clutter then never calls the lens for a pane at rest');
    assert.equal(pane._glass.get_actor(), pane, 'the lens is still the pane\'s');
    assert.equal(pane._glass.keep, false, 'not kept twice');
    // At 125 % Clutter keeps twice the px each way: fine for a strip of rim or a title band...
    views = [view(0, 1.25), view(2560)];
    stage.emit('notify::width');
    assert.equal(kept(), true);
    assert.equal(pane._glass.keep, false);
    // ...but a pane the size of a window is kept by the lens, at the screen's own px.
    pane.place(100, 100, 1600, 900, [8, 8, 8, 8], 100, 100);
    assert.equal(kept(), false);
    assert.equal(pane._glass.keep, true);
    // At a whole scale Clutter's picture has the screen's own px: any size.
    views = [view(0, 2), view(2560)];
    stage.emit('notify::width');
    assert.equal(kept(), true);
    assert.equal(pane._glass.keep, false);
    // New screens the stage did not tell of in time are seen when one of them is painted.
    views = [view(0, 1.5), view(2560)];
    stage.emit('before-paint', views[0]);
    stage.emit('after-paint', views[0]);
    assert.equal(kept(), false);
    assert.equal(pane._glass.keep, true);
    views = [view(0), view(2560)];
    stage.emit('before-paint', views[1]);
    stage.emit('after-paint', views[1]);
    assert.equal(kept(), true);
    // The window moves: nothing is kept until it settles (see WindowGlass._moved).
    pane.setKeep(false);
    assert.equal(kept(), false);
    assert.equal(pane._glass.keep, false);
    pane.setKeep(true);
    // Hidden for a while: the kept glass is let go of with the picture, and comes back when shown.
    pane.mapped = false;
    pane.emit('notify::mapped');
    const drop = [...timers.values()].at(-1);
    drop.fn();
    assert.equal(kept(), false);
    assert.equal(pane._glass._target, null);
    pane.mapped = true;
    pane.emit('notify::mapped');
    assert.deepEqual(names(), ['fedora-glass-keep', 'fedora-glass-lens']);
    pane.destroy();
});

test('whether a paint has a redraw area is asked once per screen paint', () => {
    const pane = shown();      // the stage is followed while there is glass
    let asks = 0;
    const screen = [{}, {}], other = {};
    const onScreen = i => ({get_framebuffer: () => screen[i], get_redraw_clip: () => { asks++; return {}; }});
    const picture = {get_framebuffer: () => other, get_redraw_clip: () => { asks++; return null; }};
    stage.emit('before-paint', views[0]);
    for (let i = 0; i < 20; i++)
        assert.equal(hasRedrawArea(onScreen(0)), true);
    assert.equal(asks, 1);
    // A picture of one window taken while the screen paints (a window shared in a call)
    // draws into something else: it gets its own answer, and the screen keeps its own.
    assert.equal(hasRedrawArea(picture), false);
    assert.equal(hasRedrawArea(onScreen(0)), true);
    assert.equal(asks, 2);
    const n = paintCount();
    stage.emit('after-paint', views[0]);
    assert.equal(paintCount(), n + 1, 'and what is worked out once a paint is worked out again after it');
    // Between screen paints: asked each time, it may be either.
    assert.equal(hasRedrawArea(picture), false);
    assert.equal(hasRedrawArea(onScreen(0)), true);
    assert.equal(asks, 4);
    stage.emit('before-paint', views[1]);
    assert.equal(hasRedrawArea(onScreen(1)), true);
    assert.equal(hasRedrawArea(onScreen(1)), true);
    assert.equal(asks, 5, 'the next screen asks again, once');
    stage.emit('after-paint', views[1]);
    // The picture asked first: the screen's pieces are then asked each time, never told "no".
    stage.emit('before-paint', views[0]);
    assert.equal(hasRedrawArea(picture), false);
    assert.equal(hasRedrawArea(onScreen(0)), true);
    stage.emit('after-paint', views[0]);
    // With the last glass gone the stage is no longer followed: nothing kept from the
    // last paint seen may be taken for the next one.
    const last = paintCount();
    pane.destroy();
    assert.ok(paintCount() > last);
});
