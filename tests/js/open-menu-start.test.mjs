// The glass starts while a menu is already open (the Glass tile switched back on inside Quick
// Settings): the glass comes in under the menu and the menu stays still. A menu that appears
// later (Alt+Tab, the OSD, banners) is followed while already shown and still condenses.
import assert from 'node:assert/strict';
import {test} from 'node:test';

class Actor {
    constructor() {
        this._h = new Map(); this._n = 1; this._children = []; this._parent = null;
        Object.assign(this, {mapped: true, visible: this.constructor.name !== 'GlassPane', opacity: 255, width: 100, height: 40, name: ''});   // glass.js: panes start hidden
    }
    connect(s, fn) { const id = this._n++; this._h.set(id, [s, fn]); return id; }
    disconnect(id) { this._h.delete(id); }
    emit(s, ...a) { for (const [n, fn] of [...this._h.values()]) if (n === s) fn(this, ...a); }
    add_child(c) { c._parent = this; this._children.push(c); }
    insert_child_below(c, sib) { c._parent = this; this._children.splice(Math.max(0, this._children.indexOf(sib)), 0, c); }
    set_child_below_sibling() {}
    remove_child(c) { this._children = this._children.filter(x => x !== c); c._parent = null; }
    get_parent() { return this._parent; }
    get_children() { return [...this._children]; }
    get_next_sibling() { const l = this._parent?._children ?? []; return l[l.indexOf(this) + 1] ?? null; }
    contains(o) { return o === this; }
    has_style_class_name() { return false; }
    show() { this.visible = true; }
    hide() { this.visible = false; }
    destroy() { this._parent?.remove_child(this); this.emit('destroy'); }
    set_scale(x, y) { this.scale = [x, y]; (this.scales ??= []).push([x, y]); }
    get_scale() { return this.scale ?? [1, 1]; }
    set_pivot_point(x, y) { this.pivot = [x, y]; }
    get_pivot_point() { return this.pivot ?? [0, 0]; }
    get_transformed_position() { return [0, 0]; }
    get_transformed_size() { return [this.width, this.height]; }
}
class Surface extends Actor {
    constructor() { super(); this.width = 400; this.height = 500; }
    get_transformed_position() { return [1500, 40]; }
    get_allocation_box() { return {get_width: () => this.width, get_height: () => this.height, x1: 1500, y1: 40}; }
    apply_transform_to_point() { return {x: 1500 + this.width, y: 40 + this.height}; }
    get_theme_node() { throw new Error('not styled'); }
    get_style() { return null; }
}
class Laters {
    constructor() { this.fns = new Map(); this.n = 1; }
    add(_w, fn) { const id = this.n++; this.fns.set(id, fn); return id; }
    remove(id) { this.fns.delete(id); }
    run() { const f = [...this.fns.values()]; this.fns.clear(); f.forEach(fn => fn()); }
}
const laters = new Laters();
const ui = new Actor();
ui.transform_stage_point = (x, y) => [true, x, y];
const panelButton = new Actor();
panelButton.get_transformed_position = () => [1850, 0];
panelButton.width = 60; panelButton.height = 32;
let now = 0;
const sig = () => ({connect: () => 1, disconnect() {}});
globalThis.fake = {Actor, ui, overview: {visible: false}, timeouts: {add: () => 1, remove() {}}, now: () => now,
    stSettings: Object.assign(sig(), {enable_animations: true}),
    layoutManager: {uiGroup: ui, monitors: [{x: 0, y: 0, width: 1920, height: 1080}], _backgroundGroup: new Actor(), findMonitorForActor: () => null}};
globalThis.global = {compositor: {get_laters: () => laters}, stage: Object.assign(new Actor(), {queue_redraw() {}}),
    backend: {get_cursor_tracker: () => sig()}, get_pointer: () => [100, 900, 0],
    workspace_manager: {get_active_workspace: () => ({})}, get_window_actors: () => []};

const {BoxPointer} = await import('resource:///org/gnome/shell/ui/boxpointer.js');
const {Popups} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/popups.js');
const {motion} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/common.js');
const {Motion} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/motion.js');

test('glass back on with the Quick Settings menu already open: the menu keeps its size', () => {
    // The Quick Settings menu, open on screen: a wrapper in the UI group with a BoxPointer whose bin holds the box.
    const wrapper = new Actor();
    const bp = new BoxPointer();
    const box = new Surface();
    bp.bin = {get_child: () => box};
    bp.add_child(box);
    bp._sourceActor = panelButton;
    wrapper.add_child(bp);
    ui.add_child(wrapper);
    motion.current ??= new Motion();   // the real controller, as GlassManager makes it before Popups
    const cfg = {menus: {enabled: true, behind: 'wallpaper', look: {motion: 1}}, parts: {}, grow: {enabled: true}};
    const p = new Popups(cfg);     // what _startGlass builds when the tile switches the glass back on
    assert.equal(p._followers.size, 1, 'the open menu gets its glass');
    for (let i = 0; i < 40; i++) {   // frames: Motion steps before each redraw
        now += 16000;
        laters.run();
    }
    assert.ok(!(box.scales ?? []).some(([x, y]) => x !== 1 || y !== 1), `the open menu was rescaled: ${JSON.stringify(box.scales)}`);
    p.destroy();
    ui.remove_child(wrapper);
});

test('a menu that appears later (added mapped, like Alt+Tab) still condenses into place', () => {
    const cfg = {menus: {enabled: true, behind: 'wallpaper', look: {motion: 1}}, parts: {}, grow: {enabled: true}};
    const p = new Popups(cfg);
    const wrapper = new Actor();
    const bp = new BoxPointer();
    const box = new Surface();
    bp.bin = {get_child: () => box};
    bp.add_child(box);
    wrapper.add_child(bp);
    ui.add_child(wrapper);
    ui.emit('child-added', wrapper);
    laters.run();            // Popups._soon -> _consider
    for (let i = 0; i < 40; i++) { now += 16000; laters.run(); }
    assert.ok((box.scales ?? []).some(([x]) => x < 0.99), `no condense: ${JSON.stringify(box.scales)}`);
    p.destroy();
    ui.remove_child(wrapper);
});
