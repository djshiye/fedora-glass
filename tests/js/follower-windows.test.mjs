// A Follower (follower.js) on a Shell surface: a window moving elsewhere leaves it alone,
// hidden it keeps no copies of the windows behind, and a menu that condensed gets its
// pivot point back.
import assert from 'node:assert/strict';
import {test, beforeEach} from 'node:test';

class Actor {
    constructor() {
        this._h = new Map();
        this._n = 1;
        this._children = [];
        this._parent = null;
        Object.assign(this, {mapped: true, visible: true, opacity: 255, width: 100, height: 40});
    }
    connect(s, fn) { const id = this._n++; this._h.set(id, [s, fn]); return id; }
    disconnect(id) { this._h.delete(id); }
    emit(s, ...a) { for (const [n, fn] of [...this._h.values()]) if (n === s) fn(this, ...a); }
    add_child(c) { c._parent = this; this._children.push(c); }
    insert_child_below(c, sib) { c._parent = this; this._children.splice(Math.max(0, this._children.indexOf(sib)), 0, c); }
    set_child_below_sibling() {}
    remove_child(c) { this._children = this._children.filter(x => x !== c); c._parent = null; }
    get_parent() { return this._parent; }
    get_next_sibling() { const l = this._parent?._children ?? []; return l[l.indexOf(this) + 1] ?? null; }
    contains(o) { return o === this; }
    show() { this.visible = true; }
    hide() { this.visible = false; }
    destroy() { this._parent?.remove_child(this); this.emit('destroy'); }
    set_scale(x, y) { this.scale = [x, y]; }
    get_scale() { return this.scale ?? [1, 1]; }
    set_pivot_point(x, y) { this.pivot = [x, y]; }
    get_pivot_point() { return this.pivot ?? [0, 0]; }
    get_transformed_position() { return [0, 0]; }
}

// A surface at (500, 500), 100 x 40, in a parent that maps the stage one to one.
class Surface extends Actor {
    get_transformed_position() { return [500, 500]; }
    get_allocation_box() { return {get_width: () => this.width, get_height: () => this.height, x1: 500, y1: 500}; }
    apply_transform_to_point() { return {x: 500 + this.width, y: 500 + this.height}; }
    get_theme_node() { throw new Error('not styled'); }
    get_style() { return null; }
}

class Laters {
    constructor() { this.fns = new Map(); this.n = 1; }
    add(_w, fn) { const id = this.n++; this.fns.set(id, fn); return id; }
    remove(id) { this.fns.delete(id); }
    run() { const f = [...this.fns.values()]; this.fns.clear(); f.forEach(fn => fn()); }
}

const laters = new Laters();
let windows = [];
const monitor = {x: 0, y: 0, width: 1920, height: 1080};
globalThis.fake = {Actor, ui: new Actor(), overview: {visible: false}, timeouts: {add: () => 1, remove() {}},
    layoutManager: {monitors: [monitor], _backgroundGroup: new Actor(), findMonitorForActor: () => null}};
globalThis.global = {
    compositor: {get_laters: () => laters},
    stage: Object.assign(new Actor(), {queue_redraw() {}}),
    workspace_manager: {get_active_workspace: () => ({})},
    get_window_actors: () => windows,
};

const {Follower, rectsMeet} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/follower.js');
const {windowWatch} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/common.js');

function windowAt(x, y, w = 300, h = 200) {
    const actor = new Actor();
    actor.meta_window = {rect: {x, y, width: w, height: h}, minimized: false,
        get_monitor: () => 0, located_on_workspace: () => true, get_buffer_rect() { return {...this.rect}; }};
    return actor;
}

let uiGroup, anchor, target, f;
function follow() {
    uiGroup = new Actor();
    uiGroup.transform_stage_point = (x, y) => [true, x, y];
    anchor = new Actor();
    uiGroup.add_child(anchor);
    target = new Surface();
    anchor.add_child(target);
    f = new Follower(target, anchor, {enabled: true, behind: 'windows', look: {}}, () => {});
    f.pane.pad = 8;
    laters.run();
    return f;
}

beforeEach(() => {
    windows = [];
    laters.fns.clear();
    windowWatch.current = {listeners: new Set()};
});

test('rectsMeet is about shared area, not touching edges', () => {
    assert.ok(rectsMeet([0, 0, 10, 10], {x: 5, y: 5, width: 10, height: 10}));
    assert.ok(!rectsMeet([0, 0, 10, 10], {x: 10, y: 0, width: 10, height: 10}));
});

test('a window moving far from the surface does not make it look again', () => {
    const near = windowAt(450, 450), far = windowAt(1200, 700);
    windows = [near, far];
    follow();
    assert.equal(laters.fns.size, 0);
    const hear = win => windowWatch.current.listeners.forEach(fn => fn(win));
    far.meta_window.rect.x = 1250;
    hear(far.meta_window);
    assert.equal(laters.fns.size, 0, 'a drag far away costs this surface nothing');
    hear(null);
    assert.equal(laters.fns.size, 1, 'a restack may change anything');
    laters.run();
    // A window the surface shows moves a little: look again.
    near.meta_window.rect.x = 440;
    hear(near.meta_window);
    assert.equal(laters.fns.size, 1);
    laters.run();
    // It leaves for good: that frame still looks once (where it was), the next ones do not.
    near.meta_window.rect.x = 1500;
    hear(near.meta_window);
    assert.equal(laters.fns.size, 1, 'once, for where it was');
    laters.run();
    near.meta_window.rect.x = 1550;
    hear(near.meta_window);
    assert.equal(laters.fns.size, 0);
    // And back over it.
    near.meta_window.rect.x = 480;
    hear(near.meta_window);
    assert.equal(laters.fns.size, 1);
    f.destroy();
});

test('hidden, a surface\'s panes keep no copies of the windows; shown again they copy them anew', () => {
    windows = [windowAt(450, 450)];
    follow();
    const log = [];
    for (const p of [f.pane, f.top])
        p.setSources = list => log.push([p === f.pane ? 'pane' : 'top', list.length]);
    target.mapped = false;
    f.sync();
    assert.deepEqual(log, [['pane', 0], ['top', 0]]);
    f.sync();
    assert.equal(log.length, 2, 'dropped once, not on every look while hidden');
    target.mapped = true;
    f.sync();
    assert.ok(log.some(([n, c]) => n === 'pane' && c === 2), 'the wallpaper and the window again');
    f.destroy();
});

test('a menu that condensed gets its own pivot point back', () => {
    follow();
    target.pivot = [0.2, 0.9];
    f.condense = true;
    f.setMotion({open: 0.5});
    assert.deepEqual(target.pivot, [0.5, 0.5]);
    f.destroy();
    assert.deepEqual(target.pivot, [0.2, 0.9]);
    assert.deepEqual(target.scale, [1, 1]);
});
