// The glass hold (holdstate.js): a hard time limit however the holds come, and a
// catch-up that reaches every pane, the panel included, even under a stream of holds.
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
        this._due.set(id, {at: this.now + ms, every: ms, fn});
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
                this._due.set(next[0], {...next[1], at: this.now + next[1].every});
        }
        this.now = end;
    }
    get pending() {
        return this._due.size;
    }
}

const clock = new Clock();
globalThis.fake = {timeouts: clock};
const {GlassHold, HOLD_LIMIT_MS, CATCH_UP_STEP_MS} =
    await import('../../liquidglass/data/extension/liquid-glass@djshiye.github.io/holdstate.js');

const FRAME_MS = 60;   // software GL: a frame that renders glass is slow

// Fake panes: a held pane only goes stale; a pane that isn't held renders on the
// next frame whenever something behind it changes.
function setup(names = ['files', 'terminal', 'panel']) {
    const panes = names.map((name, rank) => ({name, rank, stale: false, free: false, dirty: false, renders: 0,
        renderedAt: [0]}));
    const frames = new Map();
    let nextFrame = 1;
    const log = [];
    const hold = new GlassHold({
        panes: () => panes,
        alive: p => panes.includes(p),
        isStale: p => p.stale,
        rank: p => p.rank,
        keep: p => {
            p.free = false;
            log.push(['keep', p.name, clock.now]);
        },
        free: p => {
            p.free = true;
            p.stale = false;
            p.dirty = true;
            log.push(['free', p.name, clock.now]);
        },
        renders: p => p.renders,
        afterFrame: fn => {
            const id = nextFrame++;
            frames.set(id, fn);
            return id;
        },
        cancelFrame: id => frames.delete(id),
        endAll: () => {
            for (const p of panes) {
                p.free = false;
                if (p.stale) {
                    p.stale = false;
                    p.dirty = true;
                }
            }
            log.push(['end', clock.now]);
        },
    });
    const isHeld = p => hold.held && !p.free;
    // Something behind every pane changes now and then.
    const change = () => panes.forEach(p => (isHeld(p) ? (p.stale = true) : (p.dirty = true)));
    // A frame: dirty panes that aren't held render.
    clock.add(FRAME_MS, () => {
        for (const p of panes) {
            if (p.dirty && !isHeld(p)) {
                p.dirty = false;
                p.renders++;
                p.renderedAt.push(clock.now);
            }
        }
        [...frames.values()].forEach(fn => fn());
        return true;
    });
    return {panes, hold, log, change};
}

beforeEach(() => {
    clock._due.clear();
    clock.now = 0;
});

test('a key that is never released is let go at the limit and the panes catch up', () => {
    const {panes, hold, change} = setup();
    hold.hold('stuck');
    change();
    clock.advance(HOLD_LIMIT_MS - 1);
    assert.equal(hold.holding, true);
    assert.ok(panes.every(p => p.renders === 0), 'nothing renders while held');
    clock.advance(1 + panes.length * CATCH_UP_STEP_MS);
    assert.equal(hold.held, false);
    assert.ok(panes.every(p => p.renders === 1), 'each pane renders once');
});

test('catch-up goes bottom window first, one pane per frame, panel last', () => {
    const {panes, hold, log, change} = setup();
    hold.hold('w');
    change();
    hold.release('w');
    clock.advance(500);
    assert.deepEqual(log.filter(e => e[0] === 'free').map(e => e[1]), ['files', 'terminal', 'panel']);
    const at = panes.map(p => p.renderedAt[1]);
    assert.ok(at[0] < at[1] && at[1] < at[2], `renders at ${at}`);
    assert.equal(hold.held, false);
});

test('a hold every 200 ms for 5 s: every pane, panel included, keeps rendering', () => {
    const {panes, hold, change} = setup(['files', 'terminal', 'editor', 'menu', 'panel']);
    let n = 0;
    const end = 5000;
    clock.add(200, () => {
        hold.hold(`effect ${n++}`);    // short effects that never report landing
        return clock.now < end;
    });
    clock.add(50, () => {
        change();
        return clock.now < end + 3000;
    });
    clock.advance(end + 3000);
    const bound = HOLD_LIMIT_MS + panes.length * CATCH_UP_STEP_MS + 2 * FRAME_MS;
    for (const p of panes) {
        const times = [...p.renderedAt, end + 3000];
        for (let i = 1; i < times.length; i++)
            assert.ok(times[i] - times[i - 1] <= bound, `${p.name} went ${times[i] - times[i - 1]} ms without rendering`);
        assert.ok(p.renders >= 3, `${p.name} rendered ${p.renders} times`);
    }
});

test('the last key released starts the catch-up; turning off lets go at once', () => {
    const {panes, hold, log, change} = setup();
    hold.hold('a');
    hold.hold('b');
    change();
    hold.release('a');
    assert.equal(hold.holding, true);
    hold.release('b');
    assert.equal(hold.holding, false);
    assert.equal(hold.held, true, 'catching up');
    hold.releaseAll(true);
    assert.equal(hold.held, false);
    assert.equal(log.at(-1)[0], 'end');
    clock.advance(FRAME_MS);
    assert.ok(panes.every(p => p.renders === 1));
});

test('disabled (QA), nothing is held', () => {
    const {hold} = setup();
    hold.enabled = false;
    hold.hold('a');
    assert.equal(hold.held, false);
});

test('manual steps (QA) let one pane go per step', () => {
    const {hold, change} = setup();
    hold.manual = true;
    hold.hold('a');
    change();
    hold.release('a');
    assert.equal(hold.step().name, 'files');
    assert.equal(hold.step().name, 'terminal');
    assert.equal(hold.step().name, 'panel');
    assert.equal(hold.step(), null);
    assert.equal(hold.held, false);
});
