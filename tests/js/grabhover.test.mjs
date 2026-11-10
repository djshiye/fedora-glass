// Panel hover while a menu holds the grab (grabhover.js) under a fake Shell: the
// pointer's item counts as hovered only while the stage is grabbed, nothing is
// followed without a grab, and nothing is left behind.
import assert from 'node:assert/strict';
import {test} from 'node:test';

class Actor {
    constructor(props = {}) {
        this._handlers = new Map();
        this._next = 1;
        this.mapped = true;
        this.rect = [0, 0, 0, 0];
        Object.assign(this, props);
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
    is_mapped() {
        return this.mapped;
    }
    get_transformed_extents() {
        const [x, y, width, height] = this.rect;
        return {origin: {x, y}, size: {width, height}};
    }
}

class Filters {
    constructor() {
        this._fns = new Map();
        this._next = 1;
    }
    add(fn) {
        const id = this._next++;
        this._fns.set(id, fn);
        return id;
    }
    remove(id) {
        if (!this._fns.delete(id))
            throw new Error(`no filter ${id}`);
    }
    get size() {
        return this._fns.size;
    }
    send(event) {
        for (const fn of [...this._fns.values()])
            assert.equal(fn(event), false, 'events always go on to GNOME');
    }
}

class Timeouts {
    constructor() {
        this._fns = new Map();
        this._next = 1;
    }
    add(ms, fn) {
        const id = this._next++;
        this._fns.set(id, fn);
        return id;
    }
    remove(id) {
        this._fns.delete(id);
    }
    get size() {
        return this._fns.size;
    }
    fireAll() {
        const all = [...this._fns.values()];
        this._fns.clear();
        all.forEach(fn => fn());
    }
}

const fake = {Actor, filters: new Filters(), timeouts: new Timeouts()};
globalThis.fake = fake;
const stage = new Actor({is_grabbed: false});
globalThis.global = {stage};

const {GrabHover, hovered} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/grabhover.js');

const motion = (x, y) => ({type: () => 3, get_coords: () => [x, y]});
const leftStage = {type: () => 5, get_related: () => null};

function grab(on) {
    stage.is_grabbed = on;
    stage.emit('notify::is-grabbed');
}

function scene() {
    // Three 40 px tray icons in a panel at the bottom.
    const items = [0, 1, 2].map(i => new Actor({rect: [1000 + i * 40, 1400, 40, 40], hover: false}));
    const changes = [];
    const gh = new GrabHover(() => items, item => changes.push([items.indexOf(item), hovered(item, gh)]));
    gh.start();
    return {items, changes, gh};
}

test('no grab: no filter and nothing followed', () => {
    const {gh, changes} = scene();
    assert.equal(fake.filters.size, 0);
    assert.equal(gh.item, null);
    assert.deepEqual(changes, []);
    gh.stop();
    assert.equal(stage.handlerCount(), 0);
});

test('while a menu holds the grab, the icon under the pointer is hovered, and moving on hands over', () => {
    const {items, gh, changes} = scene();
    grab(true);
    assert.equal(fake.filters.size, 1);
    fake.filters.send(motion(500, 500));
    assert.deepEqual(changes, [], 'off the panel: nothing');
    fake.filters.send(motion(1010, 1410));
    assert.ok(hovered(items[0], gh));
    fake.filters.send(motion(1015, 1412));      // still on it: no new change
    fake.filters.send(motion(1050, 1410));
    assert.ok(!hovered(items[0], gh));
    assert.ok(hovered(items[1], gh));
    assert.deepEqual(changes, [[0, true], [0, false], [1, true]]);
    fake.filters.send(leftStage);
    assert.equal(gh.item, null);
    gh.stop();
    assert.equal(fake.filters.size, 0);
    assert.equal(stage.handlerCount(), 0);
    stage.is_grabbed = false;
});

test('a hidden panel (full-screen game) is never hovered', () => {
    const {items, gh} = scene();
    items.forEach(i => { i.mapped = false; });
    grab(true);
    fake.filters.send(motion(1010, 1410));
    assert.equal(gh.item, null);
    gh.stop();
    stage.is_grabbed = false;
});

test('when the menu closes, the grab hover lets go after GNOME gave the real hover back', () => {
    const {items, gh, changes} = scene();
    grab(true);
    fake.filters.send(motion(1090, 1410));
    grab(false);
    assert.equal(fake.filters.size, 0, 'no filter without a grab');
    assert.ok(hovered(items[2], gh), 'kept until idle: no drop and lift again');
    items[2].hover = true;                      // GNOME's crossing after the grab
    fake.timeouts.fireAll();
    assert.equal(gh.item, null);
    assert.deepEqual(changes.at(-1), [2, true], 'still hovered by GNOME itself');
    // A new grab before that idle ran keeps following.
    grab(true);
    fake.filters.send(motion(1010, 1410));
    grab(false);
    grab(true);
    assert.equal(fake.timeouts.size, 0);
    assert.equal(gh.item, items[0]);
    gh.stop();
    assert.equal(fake.filters.size, 0);
    assert.equal(stage.handlerCount(), 0);
    stage.is_grabbed = false;
});

test('an error while following turns it off instead of breaking pointer events', () => {
    const items = [new Actor({get_transformed_extents() { throw new Error('gone'); }})];
    const gh = new GrabHover(() => items, () => {});
    gh.start();
    grab(true);
    fake.filters.send(motion(1, 1));
    assert.equal(fake.filters.size, 0);
    assert.equal(stage.handlerCount(), 0);
    stage.is_grabbed = false;
});
