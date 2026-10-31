// The glass hold (holdstate.js) has a hard time limit: however the holds come,
// the glass is let go within HOLD_LIMIT_MS of first being held.
import assert from 'node:assert/strict';
import {test, beforeEach} from 'node:test';

// GLib timeouts on a fake clock.
class Clock {
    constructor() {
        this.now = 0;
        this._next = 1;
        this._due = new Map();
    }
    add(ms, fn) {
        const id = this._next++;
        this._due.set(id, {at: this.now + ms, fn});
        return id;
    }
    remove(id) {
        this._due.delete(id);
    }
    advance(ms) {
        const end = this.now + ms;
        for (;;) {
            const next = [...this._due.entries()].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
            if (!next)
                break;
            this._due.delete(next[0]);
            this.now = next[1].at;
            if (next[1].fn())
                this._due.set(next[0], {at: this.now + ms, fn: next[1].fn});
        }
        this.now = end;
    }
    get pending() {
        return this._due.size;
    }
}

const clock = new Clock();
globalThis.fake = {timeouts: clock};
const {HoldState, HOLD_LIMIT_MS} = await import('../../liquidglass/data/extension/liquid-glass@djshiye.github.io/holdstate.js');

let events, state;
beforeEach(() => {
    events = [];
    state = new HoldState(() => events.push(['hold', clock.now]), now => events.push(['release', clock.now, now]));
});

test('a key that is never released is let go at the limit', () => {
    state.hold('stuck');
    clock.advance(HOLD_LIMIT_MS - 1);
    assert.equal(state.held, true);
    clock.advance(1);
    assert.equal(state.held, false);
    assert.deepEqual(events, [['hold', 0], ['release', HOLD_LIMIT_MS, false]]);
    assert.equal(clock.pending, 0);
});

test('a hold every 200 ms for 5 s never keeps the glass longer than the limit', () => {
    const start = clock.now;
    let n = 0;
    for (let t = 0; t <= 5000; t += 200) {
        state.hold(`effect ${n++}`);    // each short effect starts and never lands
        clock.advance(200);
    }
    clock.advance(HOLD_LIMIT_MS);
    // Held, let go, held again...: each stretch of hold is at most the limit long.
    let since = null;
    for (const [kind, at] of events) {
        if (kind === 'hold') {
            assert.equal(since, null, 'held twice without a release');
            since = at;
        } else {
            assert.ok(at - since <= HOLD_LIMIT_MS, `held ${at - since} ms`);
            since = null;
        }
    }
    assert.equal(since, null, 'still held at the end');
    assert.ok(events.filter(e => e[0] === 'release').length >= 3, 'let go several times over 5 s');
    assert.ok(events[1][1] - start <= HOLD_LIMIT_MS);
});

test('the last key released lets go at once and stops the limit', () => {
    state.hold('a');
    state.hold('b');
    state.release('a');
    assert.equal(state.held, true);
    state.release('b');
    assert.equal(state.held, false);
    assert.equal(clock.pending, 0);
    assert.deepEqual(events.map(e => e[0]), ['hold', 'release']);
});

test('turning off lets go now and forgets every key', () => {
    state.hold('a');
    state.releaseAll(true);
    assert.deepEqual(events.at(-1), ['release', clock.now, true]);
    state.release('a');    // a late release does nothing
    assert.equal(events.length, 2);
    assert.equal(clock.pending, 0);
});

test('disabled (QA), nothing is held', () => {
    state.enabled = false;
    state.hold('a');
    assert.equal(state.held, false);
    assert.deepEqual(events, []);
});
