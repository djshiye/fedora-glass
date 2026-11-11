// A held window is not a moving one (grabmove.js) under a fake Mutter: a press on the
// taskbar above a maximized window starts a grab that never moves it, and the glass must
// not switch to its "something moves" look for that; a real drag still does.
import assert from 'node:assert/strict';
import {test} from 'node:test';

import {GrabMove} from '../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/grabmove.js';

class Emitter {
    constructor() {
        this._handlers = new Map();
        this._next = 1;
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
    get handlers() {
        return this._handlers.size;
    }
}

function setup() {
    const display = new Emitter();
    const calls = [];
    const g = new GrabMove(display, on => calls.push(on));
    return {display, calls, g};
}

test('a held window that never moves: no moving look at all', () => {
    const {display, calls} = setup();
    const win = new Emitter();
    display.emit('grab-op-begin', win, 1);
    assert.deepEqual(calls, []);
    display.emit('grab-op-end', win, 1);
    assert.deepEqual(calls, []);
    assert.equal(win.handlers, 0, 'nothing left connected to the window');
});

test('a real drag: moving from its first move until the grab ends', () => {
    const {display, calls, g} = setup();
    const win = new Emitter();
    display.emit('grab-op-begin', win, 1);
    win.emit('position-changed');
    win.emit('position-changed');
    assert.deepEqual(calls, [true]);
    assert.equal(g.on, true);
    display.emit('grab-op-end', win, 1);
    assert.deepEqual(calls, [true, false]);
    assert.equal(win.handlers, 0);
});

test('a resize counts as a move', () => {
    const {display, calls} = setup();
    const win = new Emitter();
    display.emit('grab-op-begin', win, 2);
    win.emit('size-changed');
    display.emit('grab-op-end', win, 2);
    assert.deepEqual(calls, [true, false]);
});

test('a window closed while held leaves nothing behind', () => {
    const {display, calls} = setup();
    const win = new Emitter();
    display.emit('grab-op-begin', win, 1);
    win.emit('unmanaged');
    assert.equal(win.handlers, 0);
    display.emit('grab-op-end', null, 1);
    assert.deepEqual(calls, []);
});

test('a grab without a window still counts as a move, as before', () => {
    const {display, calls} = setup();
    display.emit('grab-op-begin', null, 1);
    display.emit('grab-op-end', null, 1);
    assert.deepEqual(calls, [true, false]);
});

test('destroy lets go of the display and the window without calling back', () => {
    const {display, calls, g} = setup();
    const win = new Emitter();
    display.emit('grab-op-begin', win, 1);
    win.emit('position-changed');
    g.destroy();
    assert.equal(display.handlers, 0);
    assert.equal(win.handlers, 0);
    assert.deepEqual(calls, [true]);
});
