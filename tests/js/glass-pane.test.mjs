// The real GlassPane (glass.js) over a fake Clutter and Cogl: how often it looks at
// the windows behind it, which uniforms it really sends, and what a new screen size does.
import assert from 'node:assert/strict';
import {test} from 'node:test';

import {loadGlass} from './glass-harness.mjs';

class Actor {
    constructor(...a) {
        this._h = new Map();
        this._n = 1;
        this._kids = [];
        this._parent = null;
        Object.assign(this, {x: 0, y: 0, width: 0, height: 0, visible: true, mapped: true, has_clip: false});
        this._init?.(...a);
    }
    _init(props = {}) { Object.assign(this, props); }
    connect(s, fn) { const id = this._n++; this._h.set(id, [s, fn]); return id; }
    disconnect(id) { this._h.delete(id); }
    emit(s, ...a) { for (const [n, fn] of [...this._h.values()]) if (n === s) fn(this, ...a); }
    add_effect_with_name(n, e) { this.effect = e; e.get_actor = () => this; }
    add_child(c) { c._parent = this; this._kids.push(c); }
    set_child_above_sibling() {}
    set_child_below_sibling() {}
    set_position(x, y) { this.x = x; this.y = y; }
    set_size(w, h) { this.width = w; this.height = h; }
    set_clip(...c) { this.has_clip = true; this.clip = c; }
    remove_clip() { this.has_clip = false; }
    show() { this.visible = true; }
    hide() { this.visible = false; }
    queue_repaint() { this.repaints = (this.repaints ?? 0) + 1; }
    queue_redraw() {}
    get_stage() { return global.stage; }
    destroy() { this.emit('destroy'); }
    get_transformed_position() { return [this.x, this.y]; }
}

class Win extends Actor {
    constructor(rect) {
        super();
        this.meta_window = {rects: 0, get_buffer_rect: () => { this.meta_window.rects++; return {...this.rect}; }};
        this.rect = rect;
    }
}

const laters = new Map();
let nextLater = 1;
const stage = Object.assign(new Actor(), {size: [1920, 1080], get_size() { return this.size; },
    get_context: () => ({get_backend: () => ({get_cogl_context: () => ({})})}), peek_stage_views: () => []});
const display = {monitors: [{x: 0, y: 0, width: 1920, height: 1080}],
    get_n_monitors() { return this.monitors.length; }, get_monitor_geometry(i) { return this.monitors[i]; }};
globalThis.fake = {Actor, ui: new Actor(), timeouts: {add: () => 1, remove() {}}};
globalThis.global = {stage, display, compositor: {get_laters: () => ({
    add: (_t, fn) => { const id = nextLater++; laters.set(id, fn); return id; }, remove: id => laters.delete(id)})}};

const {GlassPane, setFrost} = await loadGlass();

const sent = pane => pane._glass._pipeline.log ?? [];
const quiet = pane => {
    pane._glass._pipeline.log = [];
    pane._glass.repaints = 0;
    pane.repaints = 0;
};

function placed(layer = 'glass') {
    const pane = new GlassPane(layer);
    pane.place(100, 100, 200, 100, [8, 8, 8, 8], 100, 100);
    quiet(pane);
    return pane;
}

test('place() right after setSources() does not look at the windows a second time', () => {
    const pane = placed('full');
    const win = new Win({x: 150, y: 150, width: 100, height: 100});
    pane.setSources([win]);
    const looked = win.meta_window.rects;
    assert.ok(looked > 0);
    // The owner says it has just called setSources() (a window's glass and the panel's do).
    pane.place(100, 100, 200, 100, [8, 8, 8, 8], 100, 100, null, true);
    assert.equal(win.meta_window.rects, looked, 'setSources just looked');
    // A place() alone looks again, as windows behind may have moved.
    win.rect = {x: 160, y: 150, width: 100, height: 100};
    pane.place(100, 100, 200, 100, [8, 8, 8, 8], 100, 100);
    assert.ok(win.meta_window.rects > looked);
    const clone = pane._clones.get(win);
    assert.equal(clone.x, 160 - pane._stage[0], 'and the copy follows it');
});

// Looking at the windows behind (every pane, on every frame of a drag) put each copy where
// it already was: ten calls into GNOME per window behind, for nothing (1.7.7).
test('a copy that is where its window is is left alone; one that moved, or was hidden, is put again', () => {
    const pane = placed('full');
    const win = new Win({x: 150, y: 150, width: 100, height: 100});
    pane.setSources([win]);
    const clone = pane._clones.get(win);
    let puts = 0;
    for (const fn of ['set_position', 'set_size', 'show']) {
        const real = clone[fn].bind(clone);
        clone[fn] = (...a) => { puts++; return real(...a); };
    }
    pane._syncClones();
    pane._syncClones();
    assert.equal(puts, 0, 'nothing moved');
    assert.deepEqual(clone._at.slice(0, 4), [clone.x, clone.y, 100, 100]);
    win.rect = {x: 170, y: 150, width: 100, height: 100};
    pane._syncClones();
    assert.equal(puts, 3, 'moved: put, sized and shown');
    assert.equal(clone.x, 170 - pane._stage[0]);
    assert.equal(clone._at[0], clone.x, 'and what is read while it draws follows');
    // A window off the stage has its copy hidden; back on, it is put and shown again
    // even though it is where it was.
    const on = win.get_stage;
    win.get_stage = () => null;
    pane._syncClones();
    assert.equal(clone.visible, false);
    assert.equal(clone._at, null);
    win.get_stage = on;
    puts = 0;
    pane._syncClones();
    assert.equal(clone.visible, true);
    assert.equal(puts, 3);
    // The pane itself changed size: the part of the copy inside it is worked out again.
    puts = 0;
    pane.place(100, 100, 260, 100, [8, 8, 8, 8], 100, 100);
    assert.ok(puts > 0);
    assert.deepEqual(clone._at.slice(4), pane._size);
    pane.destroy();
});

test('a frost step that changes nothing for a pane sets nothing and repaints nothing', () => {
    const glass = placed('glass');
    const rim = placed('rim');
    const sheet = new GlassPane('full');
    sheet.setLook({solid: 1});
    sheet.place(0, 0, 1920, 1080, [0, 0, 0, 0], 0, 0);
    quiet(sheet);
    setFrost(0.5, 0);
    assert.ok(sent(glass).some(([k]) => k === 'frost'), 'the glass frosts');
    assert.equal(sent(rim).length, 0, 'a window\'s rim is not frosted');
    assert.equal(sent(sheet).length, 0, 'nor a full-screen sheet');
    assert.equal(rim._glass.repaints ?? 0, 0);
    // Applying the same look again sends nothing.
    quiet(glass);
    glass._applyFrost();
    glass._applyMotion();
    assert.equal(sent(glass).length, 0);
    assert.equal(glass._glass.repaints ?? 0, 0);
    // A step that only moves the flakes sends the flakes and the liquid they take, no more.
    setFrost(0.5, 0.4);
    const names = new Set(sent(glass).map(([k]) => k));
    assert.ok(names.has('flakes') && names.has('liquid'));
    assert.ok(!names.has('frost'), 'the frost itself did not change');
    setFrost(0, 0);
});

test('a uniform that goes to 0 is sent as 0, and sent again only when it changes', () => {
    const pane = placed('glass');
    pane._glass.setFloats({press: 0.3});
    pane._glass.setFloats({press: 0});
    pane._glass.setFloats({press: 0});
    assert.deepEqual(sent(pane).filter(([k]) => k === 'press'), [['press', 0.3], ['press', 0]]);
});

test('a new screen size gives a pane that stayed where it is its new valid part and cut', () => {
    const pane = new GlassPane('glass');
    pane.place(1700, 100, 200, 100, [8, 8, 8, 8], 1700, 100);
    const last = k => sent(pane).filter(([n]) => n === k).at(-1)?.[1];
    assert.equal(last('valid_x1'), 1920 - pane._stage[0], 'the pane ends at the stage\'s edge');
    assert.equal(pane.clip[0] + pane.clip[2], 1920 - pane._stage[0], 'and cut at the screen\'s edge');
    quiet(pane);
    stage.size = [1900, 1080];
    display.monitors = [{x: 0, y: 0, width: 1900, height: 1080}];
    stage.emit('notify::width');
    assert.equal(last('valid_x1'), 1900 - pane._stage[0], 'the stage is narrower: so is the part that is on it');
    assert.equal(pane.clip[0] + pane.clip[2], 1900 - pane._stage[0], 'the cut moved in as well');
    stage.size = [1920, 1080];
    display.monitors = [{x: 0, y: 0, width: 1920, height: 1080}];
});
