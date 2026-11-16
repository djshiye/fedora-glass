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
globalThis.global = {stage: new Sig(), backend: {get_cursor_tracker: () => cursor}, get_pointer: () => pointer,
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
