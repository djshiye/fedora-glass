// The pause said for the Fedora Glass app (pausestate.js): written as the user pauses and
// resumes, put right at every start (a pause lasts one session) and at turning off, and
// the app's Resume request brings the glass back only when it is new.
import assert from 'node:assert/strict';
import {test, beforeEach} from 'node:test';

globalThis.fake = {};
const STATE = '/home/u/.cache/liquid-glass/paused.json';
const RESUME = '/home/u/.config/liquid-glass/resume-glass.json';
const {PauseState} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/pausestate.js');

let resumed;
beforeEach(() => {
    globalThis.fake.fs = new Map();
    globalThis.fake.monitors = [];
    resumed = 0;
});
const said = () => JSON.parse(globalThis.fake.fs.get(STATE).text);
const make = () => new PauseState(() => resumed++);
const askResume = id => {
    globalThis.fake.fs.set(RESUME, {text: JSON.stringify({id})});
    for (const [, m] of globalThis.fake.monitors)
        m.handlers.forEach(h => h(m, {get_basename: () => 'resume-glass.json'}, null));
};

test('a start with no pause writes nothing', () => {
    const p = make();
    assert.equal(globalThis.fake.fs.has(STATE), false);
    p.destroy();
    assert.equal(globalThis.fake.fs.has(STATE), false, 'turning off with no pause writes nothing either');
});

test('a pause is written, private, and resuming says so', () => {
    const p = make();
    p.set(true);
    assert.deepEqual(said(), {version: 1, paused: true});
    assert.equal(globalThis.fake.fs.get(STATE).mode, 0o600);
    p.set(false);
    assert.deepEqual(said(), {version: 1, paused: false});
    p.destroy();
});

test('turning off (disable) clears a pause', () => {
    const p = make();
    p.set(true);
    p.destroy();
    assert.equal(said().paused, false);
    assert.equal(globalThis.fake.monitors[0][1].cancelled, true, 'the folder is no longer watched');
});

test('a pause left by a Shell that stopped is cleared at the next start: a pause lasts one session', () => {
    globalThis.fake.fs.set(STATE, {text: JSON.stringify({version: 1, paused: true})});
    const p = make();
    assert.equal(said().paused, false);
    assert.equal(p.paused, false);
    p.destroy();
});

test("the app's Resume brings the glass back while paused; old or bad requests do nothing", () => {
    globalThis.fake.fs.set(RESUME, {text: JSON.stringify({id: '0123456789abcdef'})});
    const p = make();
    p.set(true);
    askResume('0123456789abcdef');
    assert.equal(resumed, 0, 'a request from before this start is no request now');
    askResume('not hex');
    assert.equal(resumed, 0);
    askResume('fedcba9876543210');
    assert.equal(resumed, 1);
    askResume('fedcba9876543210');
    assert.equal(resumed, 1, 'the same request counts once');
    p.set(false);
    askResume('aaaaaaaaaaaaaaaa');
    assert.equal(resumed, 0 + 1, 'not paused: nothing to resume');
    p.destroy();
    askResume('bbbbbbbbbbbbbbbb');
    assert.equal(resumed, 1, 'turned off: no more requests');
});
