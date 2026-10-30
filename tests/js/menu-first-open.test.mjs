// A menu's glass is built when it first opens. Whatever happens to that glass,
// the menu must show: right away if the glass cannot be built, and within
// HOLD_MAX_MS if the glass never comes up.
import assert from 'node:assert/strict';
import {test, beforeEach} from 'node:test';

class Actor {
    constructor() {
        this._handlers = new Map();
        this._next = 1;
        this._children = [];
        this._parent = null;
        this.mapped = false;
        this.visible = true;
        this.opacity = 255;
        this.width = 0;
        this.height = 0;
        this.name = '';
    }
    connect(signal, fn) {
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
    has_style_class_name() {
        return false;
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
    map() {
        this.mapped = true;
        this.emit('notify::mapped');
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
    run() {
        const fns = [...this._fns.values()];
        this._fns.clear();
        fns.forEach(fn => fn());
    }
}

class Timeouts {
    constructor() {
        this._fns = new Map();
        this._next = 1;
    }
    add(ms, fn) {
        const id = this._next++;
        this._fns.set(id, {ms, fn});
        return id;
    }
    remove(id) {
        this._fns.delete(id);
    }
    fireAll() {
        const all = [...this._fns.entries()];
        this._fns.clear();
        return all.map(([, {ms, fn}]) => (fn(), ms));
    }
}

const fake = {Actor, ui: new Actor(), glassFails: false, timeouts: new Timeouts()};
globalThis.fake = fake;
const laters = new Laters();
globalThis.global = {compositor: {get_laters: () => laters}, stage: Object.assign(new Actor(), {queue_redraw() {}})};

const {Popups} = await import('../../liquidglass/data/extension/liquid-glass@djshiye.github.io/popups.js');
const {HOLD_MAX_MS} = await import('../../liquidglass/data/extension/liquid-glass@djshiye.github.io/common.js');

const cfg = {menus: {enabled: true, look: {}}, calendar: {enabled: true, look: {}},
    quicksettings: {enabled: true, look: {}}, arcmenu: {enabled: true, look: {}}};

// An OSD-like pop-up: a wrapper in the UI group holding the surface that gets glass.
function popup() {
    const anchor = new Actor();
    const surface = new Actor();
    surface.has_style_class_name = c => c === 'osd-window';
    anchor.add_child(surface);
    fake.ui.add_child(anchor);
    return {anchor, surface};
}

let errors;
beforeEach(() => {
    fake.ui._children = [];
    fake.glassFails = false;
    errors = [];
    console.error = m => errors.push(String(m));
});

function start(popups) {
    // _settings() reads the config: keep the test independent of its shape.
    popups._settings = part => cfg[part];
    return popups;
}

test('no glass is built for a menu that has not opened', () => {
    const {anchor, surface} = popup();
    const p = start(new Popups(cfg));
    p._follow(surface, anchor, 'quicksettings');
    assert.equal(p._followers.size, 0);
    assert.equal(fake.ui.get_children().length, 1, 'no pane in the UI group');
    p.destroy();
    assert.equal(surface.handlerCount(), 0, 'turning off leaves no signal behind');
});

test('if the glass throws on first open, the menu shows at once without glass', () => {
    const {anchor, surface} = popup();
    const p = start(new Popups(cfg));
    p._follow(surface, anchor, 'quicksettings');
    fake.glassFails = true;
    assert.doesNotThrow(() => surface.map());
    assert.equal(surface.opacity, 255, 'the menu is not hidden');
    assert.equal(p._followers.size, 0);
    assert.equal(p._waiting.size, 0);
    assert.deepEqual(fake.ui.get_children(), [anchor], 'the half-built panes are gone');
    assert.equal(surface.handlerCount(), 0, 'no signal left on the menu');
    assert.equal(anchor.handlerCount(), 0, 'no signal left on its wrapper');
    assert.ok(errors.some(e => e.includes('menu shown without glass')), 'the failure is logged');
    p.destroy();
});

test('if the glass never comes up, the menu shows after HOLD_MAX_MS', () => {
    assert.ok(HOLD_MAX_MS <= 100);
    const {anchor, surface} = popup();
    const p = start(new Popups(cfg));
    p._follow(surface, anchor, 'quicksettings');
    surface.map();   // 0×0: the glass stays hidden, as if it never got placed
    assert.equal(p._followers.size, 1);
    assert.equal(surface.opacity, 0, 'held back while its glass is built');
    global.stage.emit('after-paint');                            // one frame went by
    assert.deepEqual(fake.timeouts.fireAll(), [HOLD_MAX_MS]);    // the time ran out
    laters.run();
    assert.equal(surface.opacity, 255, 'shown without its glass');
    p.destroy();
});
