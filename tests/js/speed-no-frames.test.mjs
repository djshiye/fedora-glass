// The speed status file (speed.js): written at a quiet moment, without waiting for the
// disk, one write for several changes; and the last window drag's frame times in it.
import assert from 'node:assert/strict';
import {test, beforeEach} from 'node:test';

class Clock {
    constructor() { this.now = 0; this._next = 1; this._due = new Map(); }
    add(ms, fn) { const id = this._next++; this._due.set(id, {at: this.now + ms, fn}); return id; }
    remove(id) { this._due.delete(id); }
    advance(ms) {
        const end = this.now + ms;
        for (;;) {
            const next = [...this._due.entries()].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
            if (!next)
                break;
            this._due.delete(next[0]);
            this.now = next[1].at;
            if (next[1].fn())
                this._due.set(next[0], {at: this.now + 1, fn: next[1].fn});
        }
        this.now = end;
    }
}

class Emitter {
    constructor() { this._h = new Map(); this._n = 1; }
    connect(sig, fn) { const id = this._n++; this._h.set(id, [sig, fn]); return id; }
    disconnect(id) { this._h.delete(id); }
    emit(sig, ...a) { for (const [s, fn] of [...this._h.values()]) if (s === sig) fn(this, ...a); }
    get count() { return this._h.size; }
}

let usNow = 0;
globalThis.fake = {Actor: class {}, ui: {}, layoutManager: new Emitter()};
const stage = new Emitter();
const display = new Emitter();
globalThis.global = {stage, display, get_window_actors: () => []};
const SPEED = '/home/u/.cache/liquid-glass/speed.json';
const {Speed} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/speed.js');

// The glass went away during the check (paused, safe mode) or the screen went off: no frames.
// Up to 1.7.8 that ended as a finished check with every level "slow" and replaced the last real one.
test('a check that got no frames fails and leaves the last finished check alone', () => {
    const clock = new Clock();
    Object.assign(globalThis.fake, {timeouts: clock, now: () => usNow, fs: new Map(), monitors: [], renders: 0, shown: 3});
    const warn = console.warn;
    console.warn = () => {};
    const s = new Speed({speed: {quality: 'auto'}}, () => {});
    const deepest = s._tuner.deepest;
    s._startCheck('0123456789abcdef');
    clock.advance(20000);
    clock.advance(100);
    assert.equal(s._result.state, 'failed');
    assert.equal(s._result.error, 'noframes');
    assert.equal(s._tuner.deepest, deepest);
    const st = JSON.parse(globalThis.fake.fs.get(SPEED).text);
    assert.ok(!st.lastDone, 'no finished check is written');
    s.destroy();
    console.warn = warn;
});
