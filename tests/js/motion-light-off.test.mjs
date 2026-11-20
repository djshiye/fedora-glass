// A menu closes with the pointer on it (you clicked an item). Up to 1.7.4 its pointer light
// then stayed "on" for the rest of the session: every pointer move woke the motion
// controller (a stage update) even with no glass on screen, and the menu reopened lit
// where the pointer had been.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {register} from 'node:module';

register('data:text/javascript,' + encodeURIComponent(`
export async function resolve(s, c, next) {
    if (s === './glass.js' && c.parentURL?.endsWith('motion.js'))
        return {url: 'stub:mglass', shortCircuit: true};
    return next(s, c);
}
export async function load(u, c, next) {
    if (u === 'stub:mglass')
        return {format: 'module', shortCircuit: true, source: 'export const getFrost = () => ({flakes: 0}); export const liquidNow = l => l; export function moving() {}'};
    return next(u, c);
}`));

class Sig {
    constructor() { this.h = new Map(); this.n = 1; }
    connect(s, f) { const i = this.n++; this.h.set(i, [s, f]); return i; }
    disconnect(i) { this.h.delete(i); }
    emit(s, ...a) { for (const [n, f] of [...this.h.values()]) if (n === s) f(this, ...a); }
}
const laters = [];
let now = 0;
let pointer = [500, 500, 0];
globalThis.fake = {Actor: class {}, now: () => now, stSettings: Object.assign(new Sig(), {enable_animations: true}),
    timeouts: {add: () => 1, remove() {}}};
const cursor = new Sig();
let asked = 0;
globalThis.global = {stage: new Sig(), backend: {get_cursor_tracker: () => cursor}, get_pointer: () => { asked++; return pointer; },
    compositor: {get_laters: () => ({add: (_t, fn) => laters.push(fn), remove() {}})}};

const EXT = '../../fedoraglass/data/extension/liquid-glass@djshiye.github.io';
const {followers} = await import(`${EXT}/common.js`);
const {Motion} = await import(`${EXT}/motion.js`);

const run = () => { for (let i = 0; i < 200 && laters.length; i++) { now += 16000; laters.shift()(); } };

test('a menu closed under the pointer: its light goes out and the pointer stops waking the glass', () => {
    const sent = [];
    const menu = {rect: [400, 400, 300, 300], settings: {look: {pointerLight: 0.5, motion: 1}}, setMotion: m => sent.push(m)};
    followers.add(menu);
    const m = new Motion();
    cursor.emit('position-invalidated');
    run();
    assert.ok(m._state.get(menu).k > 0.5, 'lit while the pointer is on the open menu');

    menu.rect = null;           // the menu closed
    sent.length = 0;
    pointer = [2000, 1300, 0];  // and the pointer went on its way
    cursor.emit('position-invalidated');
    run();
    const st = m._state.get(menu);
    assert.equal(st.k, 0, 'its light is out');
    assert.equal(st.x, null, 'and forgets where it was: reopened, it lights up at the pointer');
    assert.deepEqual(sent, [{k: 0}], 'the glass is told once, and nothing about its size or opening');
    assert.equal(m._lightable(), false, 'nothing left to light');

    const before = laters.length;
    cursor.emit('position-invalidated');
    assert.equal(laters.length, before, 'a pointer move with no glass on screen wakes nothing');

    // Reopened from the keyboard: not lit (the pointer is far away).
    menu.rect = [400, 400, 300, 300];
    sent.length = 0;
    cursor.emit('position-invalidated');
    run();
    assert.ok(m._state.get(menu).k < 0.01, 'reopened away from the pointer it stays dark');
    followers.delete(menu);
    m.destroy();
});

// A gaming mouse reports a thousand moves a second. Up to 1.7.7 each of them asked GNOME
// where the pointer was and went through all the glass, and the step before each frame
// worked out every pane's springs even with the pointer far from any glass.
test('the pointer moving far from the glass: one look per frame, and nothing worked out or sent', () => {
    const sent = [];
    const panel = {rect: [0, 1400, 2560, 40], settings: {look: {pointerLight: 0.5, motion: 1}}, setMotion: m => sent.push(m)};
    followers.add(panel);
    pointer = [1200, 300, 0];       // more than the light's reach above the panel
    const m = new Motion();
    cursor.emit('position-invalidated');
    run();
    sent.length = 0;
    asked = 0;
    for (let i = 0; i < 16; i++)
        cursor.emit('position-invalidated');
    assert.equal(asked, 0, 'a move only notes that the pointer moved');
    assert.equal(laters.length, 1, 'one step for the frame');
    run();
    assert.equal(asked, 1, 'which asks for the pointer once');
    assert.deepEqual(sent, [], 'and tells the glass nothing');
    assert.equal(laters.length, 0, 'nor asks for another frame');
    assert.equal(m._state.get(panel)?.k ?? 0, 0);

    // Coming near, the light comes on as before, from where the pointer is.
    pointer = [1200, 1300, 0];
    cursor.emit('position-invalidated');
    run();
    const st = m._state.get(panel);
    assert.ok(st.k > 0.1, 'lit near the panel');
    assert.equal(st.x, 1200);
    assert.ok(sent.length > 0);
    // And going away again it fades out fully before the steps stop.
    pointer = [1200, 300, 0];
    sent.length = 0;
    cursor.emit('position-invalidated');
    run();
    assert.equal(m._state.get(panel).k, 0);
    assert.equal(sent.at(-1).k, 0, 'the glass is told the light is out');
    assert.equal(laters.length, 0);

    // A press far from the pointer light's reach still gives: it is not "at rest".
    m._state.get(panel).pressT = 1;
    m._kick();
    run();
    assert.ok(sent.some(x => x.press > 0.5), 'pressed');
    m._released();
    run();
    assert.equal(m._state.get(panel).press, 0);

    // Reduce animation switched on while all is at rest: nothing to do, as before.
    sent.length = 0;
    fake.stSettings.enable_animations = false;
    fake.stSettings.emit('notify::enable-animations');
    run();
    assert.equal(m._lightable(), false);
    assert.deepEqual(sent, []);
    fake.stSettings.enable_animations = true;
    fake.stSettings.emit('notify::enable-animations');
    run();
    // GNOME 51's Reduce Motion counts the same (up to 1.7.8 it was not looked at).
    fake.ReducedMotion = {NO_PREFERENCE: 0, REDUCE: 1};
    const m51 = new Motion();
    assert.equal(m51._animate, true);
    fake.stSettings.reduced_motion = 1;
    fake.stSettings.emit('notify::reduced-motion');
    assert.equal(m51._animate, false, 'Reduce Motion: the glass stops moving with the pointer');
    fake.stSettings.reduced_motion = 0;
    fake.stSettings.emit('notify::reduced-motion');
    assert.equal(m51._animate, true);
    const before = fake.stSettings.h.size;
    m51.destroy();
    assert.equal(fake.stSettings.h.size, before - 2, 'both settings are let go of');
    delete fake.ReducedMotion;
    followers.delete(panel);
    m.destroy();
});
