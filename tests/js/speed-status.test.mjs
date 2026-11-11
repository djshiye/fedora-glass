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

let clock, writes;
beforeEach(() => {
    clock = new Clock();
    usNow = 0;
    writes = 0;
    const fs = new Map();
    const set = fs.set.bind(fs);
    fs.set = (k, v) => {
        if (k.startsWith(SPEED))
            writes++;
        return set(k, v);
    };
    Object.assign(globalThis.fake, {timeouts: clock, now: () => usNow, fs, monitors: [], renders: 0, shown: 0});
    console.warn = () => {};
});
const status = () => JSON.parse(globalThis.fake.fs.get(SPEED).text);
const view = {get_refresh_rate: () => 144};
// One frame on `v` that takes `ms` to draw, 7 ms after the last.
function frame(ms, v = view) {
    usNow += 7000;
    stage.emit('before-paint', v);
    usNow += ms * 1000;
    stage.emit('after-paint', v);
}

test('the status is written at a quiet moment, once for several changes, and not waited for on the disk', () => {
    const s = new Speed({speed: 'auto'}, () => {});
    assert.equal(writes, 0, 'not in the middle of starting up');
    s._writeStatus();
    s._writeStatus();
    s.update({speed: 'lighter'});
    clock.advance(0);
    assert.equal(writes, 2, 'one write (of the file beside it, then moved over it)');
    const f = globalThis.fake.fs.get(SPEED);
    assert.equal(f.flags, 0, 'no fsync: the app reads it again on the next change');
    assert.equal(f.moved, true, 'moved over the old one, so the app never reads half of it');
    assert.equal(f.mode, 0o600);
    assert.equal(status().quality, 'lighter', 'the latest state');
    s.destroy();
});

test('a status still waiting is written when the speed watch goes away (the screen locks)', () => {
    const s = new Speed({speed: 'auto'}, () => {});
    s.destroy();
    assert.equal(status().version, 1);
    assert.equal(stage.count, 0);
    assert.equal(display.count, 0, 'no drag handler left behind');
});

test("a window drag's frame times go to the status once, when it ends", () => {
    globalThis.global.get_window_actors = () => [1, 2, 3].map(() => ({visible: true, meta_window: {minimized: false}}))
        .concat([{visible: true, meta_window: {minimized: true}}]);
    const s = new Speed({speed: 'full'}, () => {});
    clock.advance(0);
    const before = writes;
    display.emit('grab-op-begin');
    for (let i = 0; i < 100; i++)
        frame(i < 90 ? 5 : 40);
    // The other screen drew a few small frames too: the busy one counts.
    for (let i = 0; i < 12; i++)
        frame(1, {get_refresh_rate: () => 60});
    clock.advance(0);
    assert.equal(writes, before, 'nothing written while dragging');
    display.emit('grab-op-end');
    clock.advance(0);
    assert.deepEqual(Object.keys(status().drag).sort(), ['at', 'frames', 'median_ms', 'p95_ms', 'refresh', 'windows']);
    const d = status().drag;
    assert.equal(d.frames, 100);
    // The time between frames: 7 ms before each one plus its own 5 (or 40) ms.
    assert.equal(d.median_ms, 12);
    assert.equal(d.p95_ms, 47);
    assert.equal(d.refresh, 144);
    assert.equal(d.windows, 3, 'minimized windows do not count');
    const n = writes;
    clock.advance(0);
    assert.equal(writes, n, 'once per drag');
    // A click on a title bar is a grab too: too short to say anything, the last drag stays.
    display.emit('grab-op-begin');
    frame(3);
    display.emit('grab-op-end');
    clock.advance(0);
    assert.equal(writes, n);
    s.destroy();
    // It is still there after a restart.
    const again = new Speed({speed: 'full'}, () => {});
    again._writeStatus();
    clock.advance(0);
    assert.equal(status().drag.frames, 100);
    again.destroy();
});

// One frame on `v` that the CPU asks for in `paintMs`, `gapMs` after the last one ended.
function frameAfter(gapMs, paintMs, v = view) {
    usNow += (gapMs - paintMs) * 1000;
    stage.emit('before-paint', v);
    usNow += paintMs * 1000;
    stage.emit('after-paint', v);
}

test('a drag held up by the GPU reads as few frames, though each asks the CPU for little', () => {
    const s = new Speed({speed: 'full'}, () => {});
    const v = {get_refresh_rate: () => 60};
    frameAfter(10, 1, v);
    clock.advance(0);
    usNow += 5e6;                       // idle for a while before the drag
    display.emit('grab-op-begin');
    frameAfter(5000, 1, v);             // its gap reaches back to before the drag: left out
    for (let i = 0; i < 40; i++)
        frameAfter(i % 2 ? 50 : 34, 1, v);  // 1 ms of CPU, 20-30 frames a second on the screen
    usNow += 2e6;                       // the pointer held still: no frames, no stutter
    frameAfter(50, 1, v);
    display.emit('grab-op-end');
    clock.advance(0);
    const d = status().drag;
    assert.equal(d.frames, 42);
    assert.equal(d.median_ms, 50, 'the time between frames, not the 1 ms of CPU');
    assert.equal(d.p95_ms, 50, 'neither the first gap nor the pause counts');
    assert.equal(d.refresh, 60);
    s.destroy();
});
