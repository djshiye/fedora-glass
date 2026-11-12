// Glass behind GNOME's snap preview (tile.js): built the first time a window is dragged to
// a screen edge, below the preview in the window group; the preview is marked so the theme
// makes it nearly clear only while glass is behind it; the glass never shows the dragged
// window (stacked above the preview); another tiling extension's preview, or none at all,
// is left alone; turning the glass off leaves nothing behind.
import assert from 'node:assert/strict';
import {test, beforeEach} from 'node:test';

class Actor {
    constructor(name = '') {
        this._handlers = new Map();
        this._next = 1;
        this._children = [];
        this._parent = null;
        this._classes = new Set();
        this.mapped = false;
        this.visible = true;
        this.opacity = 255;
        this.width = 0;
        this.height = 0;
        this.name = name;
    }
    connect(signal, fn) {
        if (globalThis.fake.connectFails && signal === 'show-tile-preview')
            throw new Error('forced');
        const id = this._next++;
        this._handlers.set(id, [signal, fn]);
        return id;
    }
    disconnect(id) {
        if (!this._handlers.delete(id))
            throw new Error(`no handler ${id}`);
    }
    emit(signal, ...args) {
        for (const [s, fn] of [...this._handlers.values()]) {
            if (s === signal)
                fn(this, ...args);
        }
    }
    handlerCount() {
        return this._handlers.size;
    }
    add_child(c) {
        c._parent = this;
        this._children.push(c);
    }
    insert_child_below(c, sibling) {
        c._parent = this;
        this._children.splice(Math.max(0, this._children.indexOf(sibling)), 0, c);
    }
    remove_child(c) {
        this._children = this._children.filter(x => x !== c);
        c._parent = null;
    }
    get_parent() {
        return this._parent;
    }
    get_children() {
        return [...this._children];
    }
    get_next_sibling() {
        const k = this._parent?._children ?? [];
        return k[k.indexOf(this) + 1] ?? null;
    }
    set_child_below_sibling(c, sibling) {
        this._children = this._children.filter(x => x !== c);
        this._children.splice(this._children.indexOf(sibling), 0, c);
    }
    add_style_class_name(c) {
        this._classes.add(c);
    }
    remove_style_class_name(c) {
        this._classes.delete(c);
    }
    has_style_class_name(c) {
        return this._classes.has(c);
    }
    get_transformed_position() {
        return [10, 20];
    }
    get_transformed_size() {
        return [400, 300];
    }
    show() {
        this.visible = true;
    }
    hide() {
        this.visible = false;
    }
    set_scale() {}
    destroy() {
        this._parent?.remove_child(this);
        this.emit('destroy');
    }
}

class Laters {
    constructor() {
        this._fns = new Map();
        this._next = 1;
    }
    add(_when, fn) {
        const id = this._next++;
        this._fns.set(id, fn);
        return id;
    }
    remove(id) {
        this._fns.delete(id);
    }
}

const fake = {Actor, ui: new Actor(), overview: {visible: false}, wm: {}, connectFails: false};
globalThis.fake = fake;
const windowManager = new Actor('wm');
const windowGroup = new Actor('window-group');
globalThis.global = {
    compositor: {get_laters: () => new Laters()}, stage: new Actor(), window_manager: windowManager,
    window_group: windowGroup, workspace_manager: {get_active_workspace: () => ({})}, get_window_actors: () => [],
};

const {TileGlass, GLASS_CLASS, tilePreviewOf, behindPreview} =
    await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/tile.js');

const cfg = (enabled = true, behind = 'windows') => ({menus: {enabled, behind, look: {}},
    parts: {quicksettings: {enabled, behind, look: {}}}});

let errors;
beforeEach(() => {
    windowGroup._children = [];
    windowManager._handlers.clear();
    delete fake.wm._tilePreview;      // Main.wm is this same object
    fake.connectFails = false;
    errors = [];
    console.error = m => errors.push(String(m));
});

// GNOME's TilePreview.open: made on first use, put right below the dragged window, shown.
function showPreview(dragged) {
    let p = fake.wm._tilePreview;
    if (!p) {
        p = new Actor('');
        p.add_style_class_name('tile-preview');
        windowGroup.add_child(p);
        fake.wm._tilePreview = p;
    }
    windowGroup.set_child_below_sibling(p, dragged);
    windowManager.emit('show-tile-preview');
    return p;
}

function windows(...names) {
    return names.map(n => {
        const w = new Actor(n);
        windowGroup.add_child(w);
        return w;
    });
}

test('no glass, no pane, until a window is first dragged to an edge', () => {
    windows('a', 'b');
    const t = new TileGlass(cfg());
    assert.equal(t._follower, null);
    assert.equal(windowGroup.get_children().length, 2);
    assert.equal(windowManager.handlerCount(), 1, 'listens for the preview');
    t.destroy();
    assert.equal(windowManager.handlerCount(), 0);
});

test('the glass goes right below the preview, which is marked nearly clear', () => {
    const [a, b] = windows('a', 'b');
    const t = new TileGlass(cfg());
    const p = showPreview(b);
    assert.ok(t._follower, 'glass built on the first showing');
    assert.ok(p.has_style_class_name(GLASS_CLASS));
    const kids = windowGroup.get_children();
    const at = kids.indexOf(p);
    assert.equal(kids[at + 1], b, 'the dragged window stays above the preview');
    assert.deepEqual(kids.slice(at - 2, at).map(k => k.name), ['glass', 'reflections'],
        'the glass and its light sit just below the preview');
    // Dragged again, now with window a: GNOME moves the preview below it, the glass follows.
    windowGroup.set_child_below_sibling(a, b);
    const f = t._follower;
    showPreview(a);
    assert.equal(t._follower, f, 'one glass for the preview, made once');
    const k2 = windowGroup.get_children();
    const at2 = k2.indexOf(p);
    assert.equal(k2[at2 + 1], a);
    assert.deepEqual(k2.slice(at2 - 2, at2).map(k => k.name), ['glass', 'reflections']);
    t.destroy();
    assert.ok(!p.has_style_class_name(GLASS_CLASS), 'turned off: GNOME-like tinted box again');
    assert.deepEqual(windowGroup.get_children().map(k => k.name).filter(n => n === 'glass' || n === 'reflections'), [],
        'no pane left');
    assert.equal(p.handlerCount(), 0, 'no signal left on the preview');
    assert.equal(windowManager.handlerCount(), 0);
});

test('the glass never shows the dragged window or anything above the preview', () => {
    const wall = new Actor('wallpaper');
    const [a, b, c] = windows('a', 'b', 'c');
    const p = new Actor('preview');
    windowGroup.insert_child_below(p, c);    // a b preview c
    const kids = windowGroup.get_children();
    assert.deepEqual(behindPreview([wall, a, b, c], p, kids), [wall, a, b]);
    assert.deepEqual(behindPreview([wall, c], p, kids), [wall]);
    assert.deepEqual(behindPreview([wall, a], new Actor('elsewhere'), kids), [wall], 'not in the group: wallpaper only');
    // Through TileGlass: the preview below window c, which is the one dragged.
    const t = new TileGlass(cfg());
    fake.wm._tilePreview = p;
    p.add_style_class_name('tile-preview');
    windowManager.emit('show-tile-preview');
    const src = t._sources(p);
    assert.ok(!src.includes(c));
    t.destroy();
});

test('with the menus glass off the preview keeps its tinted look, and turns clear when it is on', () => {
    const [w] = windows('w');
    const t = new TileGlass(cfg(false));
    const p = showPreview(w);
    assert.ok(!p.has_style_class_name(GLASS_CLASS));
    t.update(cfg(true));
    assert.ok(p.has_style_class_name(GLASS_CLASS));
    t.update(cfg(false));
    assert.ok(!p.has_style_class_name(GLASS_CLASS));
    t.destroy();
});

test('a preview made before the glass started gets glass at once', () => {
    const [w] = windows('w');
    const p = new Actor('');
    windowGroup.insert_child_below(p, w);
    fake.wm._tilePreview = p;
    const t = new TileGlass(cfg());
    assert.ok(t._follower && p.has_style_class_name(GLASS_CLASS));
    t.destroy();
    assert.ok(!p.has_style_class_name(GLASS_CLASS));
});

test('tiling extensions: no preview, an odd one or none in the Shell are left alone', () => {
    windows('w');
    assert.equal(tilePreviewOf(null), null);
    assert.equal(tilePreviewOf({}), null);
    assert.equal(tilePreviewOf({_tilePreview: {}}), null, 'not a widget');
    assert.equal(tilePreviewOf({_tilePreview: new Actor()}), null, 'not on the stage');
    const t = new TileGlass(cfg());
    fake.wm._tilePreview = {get_parent: () => windowGroup};
    assert.doesNotThrow(() => windowManager.emit('show-tile-preview'));
    assert.equal(t._follower, null);
    assert.equal(tilePreviewOf(undefined), null);
    t.destroy();
    // A Shell where the signal can't be connected: no glass, no error thrown into GNOME.
    delete fake.wm._tilePreview;
    fake.connectFails = true;
    let t2;
    assert.doesNotThrow(() => (t2 = new TileGlass(cfg())));
    assert.ok(errors.some(e => e.includes('snap preview')));
    assert.doesNotThrow(() => t2.destroy());
});

test('the preview destroyed by the Shell takes its glass along', () => {
    const [w] = windows('w');
    const t = new TileGlass(cfg());
    const p = showPreview(w);
    p.destroy();
    assert.equal(t._follower, null);
    assert.equal(windowGroup.get_children().filter(k => k.name === 'glass').length, 0);
    t.destroy();
});
