// While a window animates, the glass is held (glass.js holdPanes) and let go when it
// lands. hold.js decides when: the real module runs here against a fake window manager.
import assert from 'node:assert/strict';
import {test, beforeEach} from 'node:test';

class Emitter {
    constructor() {
        this._handlers = new Map();
        this._next = 1;
        this.disposed = false;
    }
    connect(signal, fn) {
        if (this.disposed)
            throw new Error('connect on a disposed actor');
        const id = this._next++;
        this._handlers.set(id, [signal, fn]);
        return id;
    }
    disconnect(id) {
        if (this.disposed)
            throw new Error('disconnect on a disposed actor');
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

const wm = {_mapping: new Set(), _minimizing: new Set(), _unminimizing: new Set(), _destroying: new Set(),
    _resizing: new Set()};
const fake = {Actor: Emitter, wm, holds: []};
globalThis.fake = fake;
const laters = new Laters();
const shellwm = new Emitter();
globalThis.global = {compositor: {get_laters: () => laters}, window_manager: shellwm};

const {WindowAnimationHold} = await import('../../liquidglass/data/extension/liquid-glass@djshiye.github.io/hold.js');

let hold;
beforeEach(() => {
    hold?.destroy();
    Object.values(wm).forEach(s => s.clear());
    fake.holds = [];
    hold = new WindowAnimationHold();
});

// GNOME starts an effect: its handler (connected first) adds the actor to its set.
function gnomeStarts(signal, set, actor) {
    wm[set].add(actor);
    shellwm.emit(signal, actor);
    laters.run();
}

test('GNOME minimize holds the glass until the window lands', () => {
    const actor = new Emitter();
    gnomeStarts('minimize', '_minimizing', actor);
    assert.deepEqual(fake.holds, [['hold', actor]]);
    assert.equal(hold.count, 1);
    wm._minimizing.delete(actor);
    actor.emit('effects-completed');
    assert.deepEqual(fake.holds.at(-1), ['release', actor]);
    assert.equal(hold.count, 0);
    assert.equal(actor.handlerCount(), 0, 'no handlers left on the window');
});

test('an event GNOME does not animate never holds', () => {
    const actor = new Emitter();
    shellwm.emit('map', actor);   // animations off: GNOME finished it at once
    laters.run();
    assert.deepEqual(fake.holds, []);
    assert.equal(actor.handlerCount(), 0);
});

test('every effect GNOME animates is covered, the maximize too', () => {
    const sets = {map: '_mapping', minimize: '_minimizing', unminimize: '_unminimizing', destroy: '_destroying',
        'size-changed': '_resizing'};
    for (const [signal, set] of Object.entries(sets)) {
        const actor = new Emitter();
        gnomeStarts(signal, set, actor);
        assert.deepEqual(fake.holds.at(-1), ['hold', actor], signal);
        actor.emit('effects-completed');
        assert.deepEqual(fake.holds.at(-1), ['release', actor], signal);
    }
});

test('a window destroyed mid-animation lets go without touching the dead actor', () => {
    const actor = new Emitter();
    gnomeStarts('destroy', '_destroying', actor);
    actor.emit('destroy');
    actor.disposed = true;
    assert.deepEqual(fake.holds.at(-1), ['release', actor]);
    assert.equal(hold.count, 0);
});

test('a new effect on a window still watched holds again, and one landing lets go', () => {
    const actor = new Emitter();
    gnomeStarts('minimize', '_minimizing', actor);
    wm._minimizing.delete(actor);
    gnomeStarts('unminimize', '_unminimizing', actor);
    assert.deepEqual(fake.holds.map(h => h[0]), ['hold', 'hold']);
    assert.equal(actor.handlerCount(), 2, 'watched once, not twice');
    actor.emit('effects-completed');
    assert.equal(hold.count, 0);
    assert.equal(actor.handlerCount(), 0);
});

test('turned off mid-animation: every hold is let go and every handler removed', () => {
    const a = new Emitter(), b = new Emitter();
    gnomeStarts('minimize', '_minimizing', a);
    gnomeStarts('map', '_mapping', b);
    shellwm.emit('destroy', new Emitter());   // pending, not looked at yet
    hold.destroy();
    hold = null;
    assert.deepEqual(fake.holds.filter(h => h[0] === 'release').map(h => h[1]), [a, b]);
    assert.equal(a.handlerCount() + b.handlerCount(), 0);
    assert.equal(shellwm.handlerCount(), 0, 'no window manager handlers left');
    laters.run();   // the pending look was cancelled
    assert.equal(fake.holds.filter(h => h[0] === 'hold').length, 2);
});
