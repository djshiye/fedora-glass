// Safe mode (safety.js): repeated errors or a crash loop turn the glass off, the state
// file says why, and the app's reset request turns it back on.
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
            next[1].fn();
        }
        this.now = end;
    }
    get pending() { return this._due.size; }
}

globalThis.fake = {};
const STATE = '/home/u/.cache/liquid-glass/safe-mode.json';
const RESET = '/home/u/.config/liquid-glass/safe-mode-reset.json';
const {Safety, report, guarded, ERROR_LIMIT, STABLE_S, RESTART_LIMIT} = await import(
    '../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/safety.js');

let calls, shutdown;
beforeEach(() => {
    const clock = new Clock();
    // GNOME Shell's 'shutdown' signal: it says the Shell is stopping on purpose.
    shutdown = new Map();
    let next = 1;
    globalThis.global = {
        connect: (sig, fn) => { assert.equal(sig, 'shutdown'); shutdown.set(next, fn); return next++; },
        disconnect: id => shutdown.delete(id),
    };
    Object.assign(globalThis.fake, {timeouts: clock, now: () => clock.now * 1000, fs: new Map(), monitors: []});
    calls = [];
    console.error = () => {};
    console.warn = () => {};
});
const state = () => JSON.parse(globalThis.fake.fs.get(STATE).text);
// A start outside the lock screen: the glass starts drawing.
const make = () => {
    const s = new Safety(t => calls.push(t));
    s.glassStarted();
    return s;
};
const askReset = id => {
    globalThis.fake.fs.set(RESET, {text: JSON.stringify({id})});
    for (const [, m] of globalThis.fake.monitors)
        m.handlers.forEach(h => h(m, {get_basename: () => 'safe-mode-reset.json'}, null));
};

test('a fresh start runs the glass and writes a private state file', () => {
    const s = make();
    assert.equal(s.tripped, false);
    assert.equal(globalThis.fake.fs.get(STATE).mode, 0o600);
    assert.equal(state().running, true);
    s.destroy();
    assert.equal(state().running, false, 'turning off on purpose is not a crash');
    assert.equal(globalThis.fake.timeouts.pending, 0, 'nothing left running');
});

test(`${ERROR_LIMIT} errors in a short time turn the glass off, once`, () => {
    const s = make();
    const fn = guarded('repaint', () => { throw new Error('boom'); });
    for (let i = 0; i < ERROR_LIMIT - 1; i++)
        assert.doesNotThrow(() => fn());
    assert.equal(s.tripped, false);
    fn();
    fn();
    assert.equal(s.tripped, true);
    assert.equal(state().reason, 'errors');
    assert.equal(state().where, 'repaint');
    globalThis.fake.timeouts.advance(0);
    assert.deepEqual(calls, [true], 'told once, on the next main-loop turn');
    s.destroy();
});

test('errors far apart do not count together', () => {
    const s = make();
    for (let i = 0; i < ERROR_LIMIT * 2; i++) {
        report('menu', new Error('x'));
        globalThis.fake.timeouts.advance(70_000);
    }
    assert.equal(s.tripped, false);
    s.destroy();
});

test('safe mode stays on after a restart until the app asks to turn it back on', () => {
    let s = make();
    for (let i = 0; i < ERROR_LIMIT; i++)
        report('x', new Error('x'));
    s.destroy();
    s = make();
    assert.equal(s.tripped, true, 'still off after GNOME restarts');
    askReset('0123456789abcdef');
    assert.equal(s.tripped, false);
    assert.deepEqual(calls, [false]);
    assert.equal(state().tripped, false);
    askReset('0123456789abcdef');
    assert.deepEqual(calls, [false], 'the same request is not taken twice');
    s.destroy();
});

test('a malformed reset request is ignored', () => {
    const s = make();
    s.startFailed();
    for (const id of ['short', '../../etc/passwd', 'ZZZZZZZZZZZZZZZZ', 42])
        askReset(id);
    globalThis.fake.fs.set(RESET, {text: '{not json'});
    askReset.call(null, undefined);
    assert.equal(s.tripped, true);
    s.destroy();
});

test(`GNOME Shell stopping within ${STABLE_S} s, ${RESTART_LIMIT} times in a row, starts in safe mode`, () => {
    for (let i = 0; i < RESTART_LIMIT; i++)
        make();          // never destroyed and never stable: a crash
    const s = make();
    assert.equal(s.tripped, true);
    assert.equal(state().reason, 'restarts');
    s.destroy();
});

test('a session that ran long enough resets the crash count', () => {
    make();
    const s2 = make();
    globalThis.fake.timeouts.advance(STABLE_S * 1000);
    assert.equal(state().stable, true);
    // s2 "crashes" now, after being stable: the next start is a normal one.
    const s3 = make();
    assert.equal(s3.tripped, false);
    s2.destroy();
    s3.destroy();
});

test('a reset written while GNOME Shell was down counts at the next start', () => {
    let s = make();
    s.startFailed();
    s.destroy();
    globalThis.fake.fs.set(RESET, {text: JSON.stringify({id: 'aaaaaaaaaaaaaaaa'})});
    s = make();
    assert.equal(s.tripped, false);
    s.destroy();
});

const stopCleanly = () => [...shutdown.values()].forEach(fn => fn());

test('restarting the PC twice right after logging in is not a crash loop', () => {
    // Shell stopped by a restart or log out within a minute of starting: GNOME emits
    // 'shutdown' and never calls disable(). 1.5.2 counted that as a crash.
    for (let i = 0; i < RESTART_LIMIT + 1; i++) {
        make();
        assert.equal(state().running, true);
        stopCleanly();
        assert.equal(state().running, false, 'a clean stop is written down');
        shutdown.clear();   // that Shell is gone
    }
    const s = make();
    assert.equal(s.tripped, false);
    assert.equal(state().restarts, 0);
    s.destroy();
});

test('a crash after clean restarts still counts', () => {
    make();
    stopCleanly();
    shutdown.clear();
    for (let i = 0; i < RESTART_LIMIT; i++) {
        make();          // crashes: no 'shutdown', no disable()
        shutdown.clear();
    }
    const s = make();
    assert.equal(s.tripped, true, 'two real crashes in a row still turn the glass off');
    s.destroy();
});

test('safe mode stays on across a clean restart', () => {
    let s = make();
    s.startFailed();
    stopCleanly();
    shutdown.clear();
    s = make();
    assert.equal(s.tripped, true);
    s.destroy();
    assert.equal(shutdown.size, 0, 'the shutdown handler is let go on disable');
});

test('the state is written once as the glass starts, waited for on the disk, and not again unchanged', () => {
    let writes = 0;
    const fs = globalThis.fake.fs;
    const set = fs.set.bind(fs);
    fs.set = (k, v) => {
        if (k === STATE)
            writes++;
        return set(k, v);
    };
    const s = make();
    globalThis.fake.timeouts.advance(0);
    assert.equal(writes, 1, 'starting up and the glass starting: one write');
    assert.equal(state().running, true);
    assert.equal(fs.get(STATE).flags, 1, 'CONSISTENT: there after a crash or a power cut');
    s.glassStopped();      // the screen locks
    assert.equal(writes, 2);
    s.destroy();           // then the extension is turned off: nothing new to say
    assert.equal(writes, 2);
    assert.equal(state().running, false);
    // A session spent on the lock screen still says it is not running.
    const t = new Safety(() => {});
    globalThis.fake.timeouts.advance(0);
    assert.equal(state().running, false);
    t.destroy();
});
