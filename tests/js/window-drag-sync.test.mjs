// Window glass during a drag (windows.js): a window moving works out again only the
// glass it can change, windows hidden under several opaque windows drop their glass,
// and on the screen each piece of glass skips what the windows above cover, while
// copies of the window (Alt+Tab, Dash to Panel's previews, the focused glass) get it all.
import assert from 'node:assert/strict';
import {test, beforeEach} from 'node:test';

class Emitter {
    constructor() { this._h = new Map(); this._n = 1; }
    connect(sig, fn) { const id = this._n++; this._h.set(id, [sig, fn]); return id; }
    disconnect(id) { this._h.delete(id); }
    emit(sig, ...a) { for (const [s, fn] of [...this._h.values()]) if (s === sig) fn(this, ...a); }
}

class Actor extends Emitter {
    constructor(p = {}) {
        super();
        Object.assign(this, {x: 0, y: 0, width: 0, height: 0, visible: true, opacity: 255, scale_x: 1, scale_y: 1,
            translation_x: 0, translation_y: 0, rotation_angle_x: 0, rotation_angle_y: 0, rotation_angle_z: 0}, p);
        this._children = [];
        this._parent = null;
        this._effects = new Map();
    }
    add_child(c) { this._children.push(c); c._parent = this; }
    insert_child_at_index(c, i) { this._children.splice(i, 0, c); c._parent = this; }
    remove_child(c) { this._children = this._children.filter(x => x !== c); c._parent = null; }
    get_parent() { return this._parent; }
    set_position(x, y) { this.x = x; this.y = y; }
    set_size(w, h) { this.width = w; this.height = h; }
    show() { this.visible = true; }
    hide() { this.visible = false; }
    destroy() { this._parent?.remove_child(this); this.emit('destroy'); this._h.clear(); }
    add_effect_with_name(n, e) { this._effects.set(n, e); }
    get_effect(n) { return this._effects.get(n) ?? null; }
    remove_effect_by_name(n) { this._effects.delete(n); }
    get_effects() { return [...this._effects.values()]; }
    get_transition() { return null; }
    is_in_clone_paint() { return !!this._parent?._inClone; }
    vfunc_paint() { this.painted = (this.painted ?? 0) + 1; }
}

// A Mutter window that counts the calls made on it.
class Win extends Emitter {
    constructor(id, rect) {
        super();
        Object.assign(this, {id, rect, minimized: false, fullscreen: false, calls: 0, idCalls: 0, wmClass: 'org.gnome.Nautilus'});
    }
    get_frame_rect() { this.calls++; return {...this.rect}; }
    get_buffer_rect() { this.calls++; return {...this.rect}; }
    get_monitor() { this.calls++; return 0; }
    located_on_workspace() { this.calls++; return true; }
    get_window_type() { return 0; }
    get_work_area_current_monitor() { return {x: 0, y: 0, width: 4000, height: 3000}; }
    is_maximized() { return false; }
    get_wm_class() { this.idCalls++; return this.wmClass; }
    get_wm_class_instance() { this.idCalls++; return null; }
    get_gtk_application_id() { this.idCalls++; return null; }
    get_sandboxed_app_id() { this.idCalls++; return null; }
}

const laters = new Map();
let nextLater = 1;
const runLaters = () => {
    while (laters.size) {
        const now = [...laters.entries()];
        laters.clear();
        now.forEach(([, fn]) => fn());
    }
};
const stage = new Emitter();
const display = Object.assign(new Emitter(), {focus_window: null});
globalThis.fake = {Actor, ui: new Actor(), uiGroup: new Actor(), overview: new Emitter(),
    timeouts: {add: () => 0, remove: () => {}},
    layoutManager: {monitors: [{inFullscreen: false}], findMonitorForActor: () => null, _backgroundGroup: new Actor()}};
let actors = [];
globalThis.global = {
    display, stage, workspace_manager: Object.assign(new Emitter(), {get_active_workspace: () => ({})}),
    get_window_actors: () => actors,
    compositor: {get_laters: () => ({add: (_t, fn) => { const id = nextLater++; laters.set(id, fn); return id; },
        remove: id => laters.delete(id)})},
};

const {Windows, uncovered, joined, fewParts} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/windows.js');
const {windowWatch} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/common.js');

const CFG = {windows: {enabled: true, behind: 'windows', skip: [], radius: 12, look: {}, terminalLook: null}};
const group = new Actor();
function windowAt(id, x, y, width, height) {
    const win = new Win(id, {x, y, width, height});
    const a = new Actor({x, y, width, height, meta_window: win});
    win.get_compositor_private = () => a;
    group.add_child(a);
    return a;
}
const glassOf = (ws, a) => ws.glassOf(a);
const calls = () => actors.reduce((n, a) => n + a.meta_window.calls, 0);
const zero = () => actors.forEach(a => (a.meta_window.calls = 0));
// Moves window actor a to (x, y), as Mutter does, and tells the glass.
function move(a, x, y) {
    Object.assign(a.meta_window.rect, {x, y});
    Object.assign(a, {x, y});
    a.meta_window.emit('position-changed');
    for (const fn of windowWatch.current.listeners)
        fn(a.meta_window);
}

let ws;
beforeEach(() => {
    actors = [];
    laters.clear();
    group._children = [];
    windowWatch.current = {listeners: new Set()};
});

test('what is left of a rect once others are taken out of it', () => {
    const r = {x: 0, y: 0, width: 100, height: 100};
    assert.deepEqual(uncovered(r, []), [r]);
    // Two halves together cover it, neither alone.
    assert.equal(uncovered(r, [{x: 0, y: 0, width: 60, height: 100}]).length, 1);
    assert.deepEqual(uncovered(r, [{x: 0, y: 0, width: 60, height: 100}, {x: 50, y: 0, width: 50, height: 100}]), []);
    // A hole in the middle leaves four pieces around it, with the area outside it.
    const left = uncovered(r, [{x: 40, y: 40, width: 20, height: 20}]);
    assert.equal(left.reduce((n, q) => n + q.width * q.height, 0), 100 * 100 - 20 * 20);
    // Pieces that make one rect together are joined.
    assert.deepEqual(joined(uncovered(r, [{x: 0, y: 40, width: 60, height: 20}])),
        [{x: 0, y: 0, width: 100, height: 40}, {x: 0, y: 60, width: 100, height: 40}, {x: 60, y: 40, width: 40, height: 20}]);
    assert.deepEqual(joined([{x: 0, y: 0, width: 10, height: 5}, {x: 0, y: 5, width: 10, height: 5}, {x: 10, y: 0, width: 5, height: 10}]),
        [{x: 0, y: 0, width: 15, height: 10}]);
    // Many pieces (a cascade of windows above): drawn as strips across, around what shows.
    const steps = Array.from({length: 12}, (_, i) => ({x: i * 8, y: i * 8, width: 4, height: 8}));
    const strips = fewParts(steps, r);
    assert.ok(strips.length <= 8);
    for (const q of steps)
        assert.ok(strips.some(s => s.x <= q.x && s.y <= q.y && s.x + s.width >= q.x + q.width), 'nothing that shows is left out');
    for (let i = 1; i < strips.length; i++)
        assert.ok(strips[i].y >= strips[i - 1].y + strips[i - 1].height, 'strips never overlap');
    assert.ok(strips.reduce((n, q) => n + q.width * q.height, 0) < 0.5 * 100 * 100);
    // Too many pieces: not worth it.
    const comb = Array.from({length: 40}, (_, i) => ({x: i * 2.5, y: i * 2.5, width: 1, height: 1}));
    assert.equal(uncovered(r, comb, 8), null);
});

function cascade(n) {
    // n windows stacked, each 40 px right of the one below, and one big window on top.
    actors = Array.from({length: n}, (_, i) => windowAt(i, 40 + i * 40, 80, 1600, 1000));
    const top = windowAt(99, 300, 200, 1400, 900);
    actors.push(top);
    display.focus_window = top.meta_window;
    ws = new Windows(CFG);
    runLaters();
    return top;
}

test('a drag step works out again only the dragged window, not all 20 behind it', () => {
    const top = cascade(20);
    zero();
    move(top, 320, 210);
    runLaters();
    const perStep = calls();
    // Every window's glass asking about every window (1.5.22): over 20 x 21 calls.
    assert.ok(perStep < 8 * actors.length, `${perStep} calls into Mutter for one drag step`);
    // The app's ids are asked once, not on every step.
    const ids = actors.reduce((n, a) => n + a.meta_window.idCalls, 0);
    move(top, 340, 220);
    runLaters();
    assert.equal(actors.reduce((n, a) => n + a.meta_window.idCalls, 0), ids);
    ws.destroy();
});

test('an app that changes its id is asked again', () => {
    const top = cascade(1);
    const w = top.meta_window;
    const before = w.idCalls;
    w.wmClass = 'mpv';
    w.emit('notify::wm-class');
    runLaters();
    assert.ok(w.idCalls > before);
    assert.equal(glassOf(ws, top).shown, false, 'a video player shows no glass');
    ws.destroy();
});

test('a window under two others that cover it together hides its glass; under the focused one it keeps it', () => {
    const below = windowAt(0, 100, 100, 400, 300);
    const left = windowAt(1, 80, 80, 260, 340);
    const right = windowAt(2, 320, 80, 200, 340);
    actors = [below, left, right];
    display.focus_window = null;
    ws = new Windows(CFG);
    runLaters();
    runLaters();
    assert.equal(glassOf(ws, left).shown, true);
    assert.equal(glassOf(ws, below)._whyNot(), 'hidden', 'nobody can see any of it');
    // The focused window's glass shows the windows behind it through its blur.
    display.focus_window = right.meta_window;
    assert.equal(glassOf(ws, below)._whyNot(), null);
    display.focus_window = null;
    // One of them moves away: the window below looks again in the same step.
    move(right, 900, 80);
    assert.ok([...laters.values()].length > 0);
    runLaters();
    assert.equal(glassOf(ws, below)._whyNot(), null);
    ws.destroy();
});

test('on the screen and in our own copies, glass skips what opaque glass above covers; other copies get all of it', async () => {
    const below = windowAt(0, 100, 100, 400, 300);
    const over = windowAt(1, 50, 50, 300, 400);
    actors = [below, over];
    display.focus_window = over.meta_window;
    ws = new Windows(CFG);
    runLaters();
    const g = glassOf(ws, below);
    const h = g._holder;
    const onScreen = {get_redraw_clip: () => ({}), get_framebuffer: () => null};
    // Its left part lies under the window above (corners aside): only the right part is drawn.
    const box = g._paintBox(h, onScreen);
    assert.ok(Array.isArray(box), 'clipped');
    // The window above leaves the right side and the band below it, less its round corner.
    const area = box.reduce((n, [x1, y1, x2, y2]) => n + (x2 - x1) * (y2 - y1), 0);
    assert.ok(area < 0.6 * h.width * h.height, `drawn ${area} of ${h.width * h.height}`);
    assert.ok(box.every(([x1]) => x1 >= 0) && box.some(([, , x2]) => x2 === h.width), `box ${box}`);
    // A copy (Alt+Tab, Dash to Panel, the focused window's glass) and a window screenshot
    // (no redraw area) draw it whole.
    below._inClone = true;
    assert.equal(g._paintBox(h, onScreen), null);
    // Our own glass that copies both windows draws the one above over it there too:
    // left out there as well. A pane that doesn't copy the window above leaves out nothing.
    const {copying} = await import('./glass.js');
    const copyOf = a => ({x: a.x, y: a.y, visible: true});
    const pane = {_clones: new Map([[below, copyOf(below)], [over, copyOf(over)]])};
    Object.assign(copying, {pane});
    stage.emit('after-paint');
    assert.deepEqual(g._paintBox(h, onScreen), box);
    // A rim strip's copy shows a thin strip of the window: the rest of its glass is not drawn.
    pane._clones.get(below)._clipBox = [0, 0, 40, 300];
    assert.equal(g._paintBox(h, onScreen), false, 'the strip lies under the window above');
    pane._clones.get(below)._clipBox = [380, 0, 20, 300];
    assert.deepEqual(g._paintBox(h, onScreen), [[380, 0, 400, 300]]);
    delete pane._clones.get(below)._clipBox;
    pane._clones.delete(over);
    stage.emit('after-paint');
    assert.equal(g._paintBox(h, onScreen), null);
    Object.assign(copying, {pane: null});
    below._inClone = false;
    assert.equal(g._paintBox(h, {get_redraw_clip: () => null}), null);
    // Under it entirely: nothing to draw.
    stage.emit('after-paint');
    Object.assign(over, {x: 0, y: 0, width: 800, height: 800});
    Object.assign(over.meta_window.rect, {x: 0, y: 0, width: 800, height: 800});
    glassOf(ws, over).sync();
    assert.equal(g._paintBox(h, onScreen), false);
    // ...unless the window above is see-through or animates.
    stage.emit('after-paint');
    over.opacity = 200;
    assert.notEqual(g._paintBox(h, onScreen), false);
    stage.emit('after-paint');
    over.opacity = 255;
    over.scale_x = 0.9;
    assert.notEqual(g._paintBox(h, onScreen), false);
    ws.destroy();
});
