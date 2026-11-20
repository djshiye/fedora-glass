// A menu shown again after its picture was dropped, while a window animates: it draws the
// windows behind it (up to 1.7.8: the wallpaper alone until the animation ended).
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {loadGlass} from './glass-harness.mjs';

class Actor {
    constructor(...a) {
        this._h = new Map(); this._n = 1; this._kids = [];
        Object.assign(this, {x: 0, y: 0, width: 0, height: 0, visible: true, mapped: true, has_clip: false, effects: []});
        this._init?.(...a);
    }
    _init(props = {}) { Object.assign(this, props); }
    connect(s, fn) { const id = this._n++; this._h.set(id, [s, fn]); return id; }
    disconnect(id) { this._h.delete(id); }
    emit(s, ...a) { for (const [n, fn] of [...this._h.values()]) if (n === s) fn(this, ...a); }
    add_effect_with_name(n, e) { e.name = n; this.effects.push(e); e.get_actor = () => this; }
    remove_effect(e) { this.effects = this.effects.filter(x => x !== e); }
    add_child(c) { this._kids.push(c); }
    set_child_above_sibling() {} set_child_below_sibling() {}
    set_position(x, y) { this.x = x; this.y = y; }
    set_size(w, h) { this.width = w; this.height = h; }
    set_clip(...c) { this.has_clip = true; this.clip = c; }
    remove_clip() { this.has_clip = false; }
    show() { this.visible = true; } hide() { this.visible = false; }
    queue_redraw() {} get_stage() { return global.stage; }
    destroy() { this.emit('destroy'); }
    get_paint_opacity() { return 255; }
    get_transformed_position() { return [this.x, this.y]; }
    get_transformed_size() { return [this.width, this.height]; }
    get_transformed_extents() { return {get_x: () => this.x, get_y: () => this.y, get_width: () => this.width, get_height: () => this.height}; }
}
const view = (x) => ({scale: 1, get_scale() { return 1; }, get_layout(r) { Object.assign(r, {x, y: 0, width: 2560, height: 1440}); }});
const stage = Object.assign(new Actor(), {get_size: () => [2560, 1440],
    get_context: () => ({get_backend: () => ({get_cogl_context: () => ({})})}), peek_stage_views: () => [view(0)]});
const timers = new Map(); let nt = 1;
globalThis.fake = {Actor, ui: new Actor(), made: {}, now: () => 0,
    timeouts: {add: (ms, fn) => { const id = nt++; timers.set(id, {ms, fn}); return id; }, remove: id => timers.delete(id)}};
globalThis.global = {stage, display: {get_n_monitors: () => 1, get_monitor_geometry: () => ({x: 0, y: 0, width: 2560, height: 1440})},
    compositor: {get_laters: () => ({add: () => 1, remove() {}})}, get_window_actors: () => []};
const {GlassPane, holdPanes, releaseAllPanes} = await loadGlass({paint: true});
const root = () => ({kids: [], add_child(c) { this.kids.push(c); }});
const ctx = {get_redraw_clip: () => null};

test('a menu re-shown after its picture was dropped, during a window animation, renders with the windows behind hidden', () => {
    const win = new Actor({width: 800, height: 600});
    win.meta_window = {get_buffer_rect: () => ({x: 0, y: 0, width: 800, height: 600})};
    const pane = new GlassPane('glass');
    pane.setSources([win]);
    pane.place(100, 100, 400, 300, [8, 8, 8, 8], 100, 100);
    pane._glass.vfunc_paint_node(root(), ctx, 1);
    const clone = [...pane._clones.values()][0];
    assert.equal(clone.visible, true);
    pane._glass.drop();      // hidden for more than 3 s: its picture is let go
    holdPanes('w');          // a window opens or closes now
    pane._syncClones();      // the menu shows again
    assert.equal(pane._kept(), false, 'nothing is kept after a drop');
    assert.equal(clone.visible, true, 'the window behind is in the new picture');
    releaseAllPanes(true);
});
