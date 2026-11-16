// A menu that opens while its glass is still hidden (it fades in from clear, and
// the glass waits for it) must still finish opening. 1.7.1 stopped the open spring
// while the glass was hidden and could leave the menu at its grow-start size.
import assert from 'node:assert/strict';
import {test} from 'node:test';

class Obj {
    constructor() { this._h = new Map(); this._n = 1; }
    connect(s, fn) { const id = this._n++; this._h.set(id, [s, fn]); return id; }
    disconnect(id) { this._h.delete(id); }
}

let clock = 0;
const laters = new Map();
let nextLater = 1;
globalThis.fake = {Actor: Obj, now: () => clock, stSettings: Object.assign(new Obj(), {enable_animations: true})};
globalThis.global = {
    compositor: {get_laters: () => ({
        add: (_w, fn) => { const id = nextLater++; laters.set(id, fn); return id; },
        remove: id => laters.delete(id),
    })},
    stage: Object.assign(new Obj(), {get_event_actor: () => null}),
    backend: {get_cursor_tracker: () => new Obj()},
    get_pointer: () => [0, 0, 0],
};

const EXT = '../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/';
const {Motion} = await import(`${EXT}motion.js`);
const {followers} = await import(`${EXT}common.js`);

// Run redraw laters like frames, 16 ms apart, until nothing asks for one.
function frames(limit = 200) {
    let n = 0;
    while (laters.size && n++ < limit) {
        clock += 16000;
        const [id, fn] = laters.entries().next().value;
        laters.delete(id);
        fn();
    }
    return n;
}

function menu() {
    const seen = [];
    return {rect: null, anchor: {contains: () => false}, settings: {look: {motion: 1}},
        seen, setMotion: m => seen.push(m)};
}

test('a menu opened while its glass is hidden still finishes opening', () => {
    const m = new Motion();
    const f = menu();
    followers.add(f);
    try {
        m.opened(f);                 // grows from 0
        const n = frames();
        assert.ok(n > 3, 'the open spring kept going');
        const opens = f.seen.filter(s => s.open !== undefined).map(s => s.open);
        assert.equal(opens.at(-1), 1, 'landed at full size');
        assert.equal(laters.size, 0, 'and then stops asking for frames');
    } finally {
        followers.delete(f);
        m.destroy();
    }
});

test('with animations off the hidden menu is full size at once', () => {
    const m = new Motion();
    const f = menu();
    followers.add(f);
    try {
        m.opened(f);
        globalThis.fake.stSettings.enable_animations = false;
        frames();
        assert.equal(f.seen.filter(s => s.open !== undefined).at(-1).open, 1);
    } finally {
        globalThis.fake.stSettings.enable_animations = true;
        followers.delete(f);
        m.destroy();
    }
});
