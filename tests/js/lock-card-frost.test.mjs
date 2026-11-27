// Weather frost never reaches the lock screen's glass: the password card keeps its look
// while it slides away on unlock, though the desktop's frost starts in that same moment.
import assert from 'node:assert/strict';
import {test} from 'node:test';

import {loadGlass} from './glass-harness.mjs';

class Actor {
    constructor(...a) {
        this._h = new Map(); this._n = 1; this._kids = [];
        Object.assign(this, {x: 0, y: 0, width: 0, height: 0, visible: true, mapped: true, has_clip: false});
        this._init?.(...a);
    }
    _init(props = {}) { Object.assign(this, props); }
    connect(s, fn) { const id = this._n++; this._h.set(id, [s, fn]); return id; }
    disconnect(id) { this._h.delete(id); }
    emit(s, ...a) { for (const [n, fn] of [...this._h.values()]) if (n === s) fn(this, ...a); }
    add_effect_with_name(n, e) { this.effect = e; e.get_actor = () => this; }
    add_child(c) { this._kids.push(c); }
    set_child_above_sibling() {} set_child_below_sibling() {}
    set_position(x, y) { this.x = x; this.y = y; }
    set_size(w, h) { this.width = w; this.height = h; }
    set_clip(...c) { this.has_clip = true; this.clip = c; }
    remove_clip() { this.has_clip = false; }
    show() { this.visible = true; } hide() { this.visible = false; }
    queue_repaint() {} queue_redraw() {}
    get_stage() { return global.stage; }
    destroy() { this.emit('destroy'); }
    get_transformed_position() { return [this.x, this.y]; }
}

let now = 1e9;
const timers = new Map();
let nextId = 1;
globalThis.fake = {Actor, now: () => now, stSettings: {enable_animations: true},
    timeouts: {add: (ms, fn) => { const id = nextId++; timers.set(id, {ms, fn}); return id; },
        remove: id => timers.delete(id)}};
const stage = Object.assign(new Actor(), {get_size: () => [2560, 1440],
    get_context: () => ({get_backend: () => ({get_cogl_context: () => ({})})}), peek_stage_views: () => []});
globalThis.global = {stage, display: {get_n_monitors: () => 1, get_monitor_geometry: () => ({x: 0, y: 0, width: 2560, height: 1440})},
    compositor: {get_laters: () => ({add: () => 1, remove() {}})}};

const G = await loadGlass();

const LL = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/locklook.js');
const C = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/config.js');


function lockPanes() {
    const lock = C.parse('{}').lock;
    const sheet = new G.GlassPane('full');
    sheet.setLook(LL.sheetLook(lock));
    sheet.place(0, 0, 2560, 1440, [0, 0, 0, 0], 0, 0);
    sheet.show();
    const card = new G.GlassPane('full');
    card.setLook(LL.cardLook(lock));
    card.place(1000, 500, 480, 300, [32, 32, 32, 32], 1000, 500);
    card.show();
    return {sheet, card};
}

const frostOf = p => p._glass._sent.get('frost') ?? 0;

test('the lock screen card and sheet keep their look when the weather frost starts during the unlock slide', () => {
    const {sheet, card} = lockPanes();
    const menu = new G.GlassPane('full');
    menu.setLook({...G.DEFAULT_LOOK, blur: 20});
    menu.place(100, 100, 300, 400, [32, 32, 32, 32], 100, 100);
    menu.show();
    const before = {card: card._glass.radius, sheet: sheet._glass.radius, menu: menu._glass.radius};
    try {
        G.setFrost(1, 1);
        assert.equal(card._glass.radius, before.card, 'the card is not blurred more');
        assert.equal(sheet._glass.radius, before.sheet);
        assert.ok(menu._glass.radius > before.menu, 'an ordinary menu pane still frosts');
        assert.equal(frostOf(card), 0, 'no ice skin on the card');
        assert.equal(frostOf(sheet), 0);
        assert.ok(frostOf(menu) > 0);
        assert.equal(card._frosts(), false);
        assert.equal(card._iceLive(), false);
        const glass = new G.GlassPane('glass');
        glass.setLook({...G.DEFAULT_LOOK});
        assert.equal(glass._iceLive(), true);
        glass.setLook({...G.DEFAULT_LOOK, frostless: 1});
        assert.equal(glass._iceLive(), false);
    } finally {
        G.setFrost(0, 0);
    }
});
