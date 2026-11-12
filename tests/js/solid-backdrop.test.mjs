// Apps without glass become solid (windows.js, config.js): a window of an app on the
// user's list gets a plain opaque backdrop in the theme's window colour, with the glass's
// corners, instead of glass, since the themes paint its background see-through for the
// glass. The built-in apps without glass and Fedora Glass itself still get nothing, a
// full-screen window gets nothing in its actor, and the backdrop is as opaque as glass for
// the windows below it.
import assert from 'node:assert/strict';
import {test, beforeEach} from 'node:test';

class Emitter {
    constructor() { this._h = new Map(); this._n = 1; }
    connect(sig, fn) { const id = this._n++; this._h.set(id, [sig, fn]); return id; }
    disconnect(id) { this._h.delete(id); }
    emit(sig, ...a) { for (const [s, fn] of [...this._h.values()]) if (s === sig) fn(this, ...a); }
}

class Actor extends Emitter {
    constructor(p = {}) {
        super();
        Object.assign(this, {x: 0, y: 0, width: 0, height: 0, visible: true, opacity: 255, scale_x: 1, scale_y: 1,
            translation_x: 0, translation_y: 0, rotation_angle_x: 0, rotation_angle_y: 0, rotation_angle_z: 0}, p);
        this._children = [];
        this._parent = null;
        this._effects = new Map();
        this.styles = [];
    }
    add_child(c) { this._children.push(c); c._parent = this; }
    insert_child_at_index(c, i) { this._children.splice(i, 0, c); c._parent = this; }
    remove_child(c) { this._children = this._children.filter(x => x !== c); c._parent = null; }
    get_parent() { return this._parent; }
    get_children() { return [...this._children]; }
    set_position(x, y) { this.x = x; this.y = y; }
    set_size(w, h) { this.width = w; this.height = h; }
    set_style(s) { this.styles.push(s); }
    show() { this.visible = true; }
    hide() { this.visible = false; }
    destroy() { this._parent?.remove_child(this); this.destroyed = true; this.emit('destroy'); this._h.clear(); }
    add_effect_with_name(n, e) { this._effects.set(n, e); }
    get_effect(n) { return this._effects.get(n) ?? null; }
    remove_effect_by_name(n) { this._effects.delete(n); }
    get_effects() { return [...this._effects.values()]; }
    get_transition() { return null; }
    is_in_clone_paint() { return false; }
}

class Win extends Emitter {
    constructor(id, rect, wmClass) {
        super();
        Object.assign(this, {id, rect, wmClass, minimized: false, fullscreen: false, maximized: false, shadow: 0});
    }
    get_frame_rect() { return {...this.rect}; }
    // A CSD window's buffer holds its shadow around the frame.
    get_buffer_rect() {
        const {x, y, width, height} = this.rect, s = this.shadow;
        return {x: x - s, y: y - s, width: width + 2 * s, height: height + 2 * s};
    }
    get_monitor() { return 0; }
    located_on_workspace() { return true; }
    get_window_type() { return 0; }
    get_work_area_current_monitor() { return {x: 0, y: 0, width: 4000, height: 3000}; }
    is_maximized() { return this.maximized; }
    get_wm_class() { return this.wmClass; }
    get_wm_class_instance() { return null; }
    get_gtk_application_id() { return null; }
    get_sandboxed_app_id() { return null; }
}

const laters = new Map();
let nextLater = 1;
const runLaters = () => {
    while (laters.size) {
        const now = [...laters.entries()];
        laters.clear();
        now.forEach(([, fn]) => fn());
    }
};
const timers = new Map();
let nextTimer = 1;
const display = Object.assign(new Emitter(), {focus_window: null});
const monitors = [{inFullscreen: false}];
globalThis.fake = {Actor, Widget: Actor, ui: new Actor(), uiGroup: new Actor(), overview: new Emitter(),
    themeContext: {scale_factor: 1}, timeouts: {add: (ms, fn) => { timers.set(nextTimer, fn); return nextTimer++; },
        remove: id => timers.delete(id)},
    layoutManager: {monitors, findMonitorForActor: () => null, _backgroundGroup: new Actor()}};
let actors = [];
globalThis.global = {
    display, stage: new Emitter(), workspace_manager: Object.assign(new Emitter(), {get_active_workspace: () => ({})}),
    get_window_actors: () => actors,
    compositor: {get_laters: () => ({add: (_t, fn) => { const id = nextLater++; laters.set(id, fn); return id; },
        remove: id => laters.delete(id)})},
};

const EXT = '../../fedoraglass/data/extension/liquid-glass@djshiye.github.io';
const {Windows, windowKind} = await import(`${EXT}/windows.js`);
const {parse, cleanSkip} = await import(`${EXT}/config.js`);
const {windowWatch} = await import(`${EXT}/common.js`);

// As the app writes it: the built-in ones first, then the user's own from solidFrom on.
const BUILT_IN = ['steam', 'Code', 'code', 'firefox', 'Slack'];
function config(own, color = '#1d1e23') {
    return parse(JSON.stringify({windows: {skip: [...BUILT_IN, ...own], solidFrom: BUILT_IN.length,
        solidColor: color, radius: 12}}));
}

const solidOf = a => a.get_children().find(c => c.name === 'fedora-glass-solid') ?? null;

function windowAt(id, x, y, width, height, wmClass = 'org.gnome.gedit') {
    const win = new Win(id, {x, y, width, height}, wmClass);
    const a = new Actor({x, y, width, height, meta_window: win});
    win.get_compositor_private = () => a;
    a.add_child(new Actor({name: 'surface'}));     // the window's own surface
    return a;
}

beforeEach(() => {
    actors = [];
    laters.clear();
    timers.clear();
    display.focus_window = null;
    monitors[0].inFullscreen = false;
    windowWatch.current = {listeners: new Set()};
});

test('who gets what: the user\'s own apps solid, the built-in ones glass behind their title bar, Fedora Glass nothing', () => {
    const c = config(['org.gnome.gedit', 'CODE', 'mpv', 'io.github.djshiye.LiquidGlass']).windows;
    assert.deepEqual(c.solid, ['org.gnome.gedit', 'CODE', 'mpv', 'io.github.djshiye.LiquidGlass']);
    assert.equal(windowKind(['org.gnome.gedit'], c.skip, c.solid), 'solid');
    assert.equal(windowKind(['Org.Gnome.Gedit'], c.skip, c.solid), 'solid', 'whatever the case');
    assert.equal(windowKind(['org.gnome.Ptyxis'], c.skip, c.solid), 'glass');
    // The built-in list has it too (in another case): it goes by the built-in list. Those
    // apps paint their own body, but their title bar may come from the GTK theme: glass
    // behind the title bar only (Slack's showed the desktop sharp, 1.5.23 to 1.5.27).
    assert.equal(windowKind(['Code', 'code'], c.skip, c.solid), 'title');
    assert.equal(windowKind(['slack'], c.skip, c.solid), 'title', 'Slack, whatever the case');
    assert.equal(windowKind(['firefox', 'org.mozilla.firefox'], [...c.skip, 'org.mozilla.firefox'],
        [...c.solid, 'org.mozilla.firefox']), 'title', 'one of its ids is built in');
    assert.equal(windowKind(['steam'], c.skip, c.solid), 'none', 'Steam: no title bar of ours');
    assert.equal(windowKind(['mpv'], c.skip, c.solid), 'none', 'a video player');
    assert.equal(windowKind(['io.github.djshiye.LiquidGlass'], c.skip, c.solid), 'none', 'draws its own glass');
    // A file from before (no solidFrom): the whole list counts as built in.
    const old = parse(JSON.stringify({windows: {skip: ['steam', 'org.gnome.gedit']}})).windows;
    assert.deepEqual(old.solid, []);
    assert.equal(windowKind(['org.gnome.gedit'], old.skip, old.solid), 'title');
    assert.equal(windowKind(['steam'], old.skip, old.solid), 'none');
});

test('config.js: the user\'s part survives bad entries, and only a plain colour gets through', () => {
    const w = cleanSkip({skip: ['steam', 7, 'Code', 'org.gnome.gedit', null, '', 'x'.repeat(200), 'org.gimp.GIMP'],
        solidFrom: 3, solidColor: '#ABCDEF'});
    assert.deepEqual(w.skip, ['steam', 'Code', 'org.gnome.gedit', 'org.gimp.GIMP']);
    assert.deepEqual(w.solid, ['org.gnome.gedit', 'org.gimp.GIMP']);
    assert.equal(w.solidColor, '#abcdef');
    for (const bad of ['red', 'rgb(1,2,3)', '#12345', '#1234567', 'url(x)', 5])
        assert.equal(cleanSkip({skip: [], solidColor: bad}).solidColor, '#242424', String(bad));
    // Out of range: clamped.
    assert.deepEqual(cleanSkip({skip: ['a', 'b'], solidFrom: -4}).solid, ['a', 'b']);
    assert.deepEqual(cleanSkip({skip: ['a', 'b'], solidFrom: 99}).solid, []);
    assert.deepEqual(cleanSkip({skip: ['a', 'b'], solidFrom: 1.5}).solid, [], 'not a whole number: none');
    // Never more than 200, the built-in ones first.
    const many = cleanSkip({skip: [...Array.from({length: 150}, (_, i) => `b${i}`), ...Array.from({length: 150}, (_, i) => `u${i}`)],
        solidFrom: 150});
    assert.equal(many.skip.length, 200);
    assert.deepEqual([many.solid.length, many.solid[0]], [50, 'u0']);
});

test('a listed window gets one solid box under its surface, on its frame, with the glass\'s corners', () => {
    const a = windowAt(0, 100, 100, 800, 600);
    a.meta_window.shadow = 20;
    actors = [a];
    const ws = new Windows(config(['org.gnome.gedit']));
    runLaters();
    const g = ws.glassOf(a);
    const box = solidOf(a);
    assert.ok(box, 'a backdrop');
    assert.equal(a.get_children()[0], box, 'under the window\'s own surface');
    assert.deepEqual([box.x, box.y, box.width, box.height], [20, 20, 800, 600], 'on the frame, not the shadow');
    assert.equal(box.styles.at(-1), 'background-color: #1d1e23; border-radius: 12px;');
    assert.equal(box.reactive, false);
    assert.equal(g.pane, null, 'no glass, so nothing blurred or copied');
    assert.equal(g.shown, false);
    assert.equal(a.get_effect('fedora-glass-no-cull'), null);
    // Maximized: square corners, like the glass and the app.
    a.meta_window.maximized = true;
    a.meta_window.emit('notify::maximized-horizontally');
    runLaters();
    assert.match(solidOf(a).styles.at(-1), /border-radius: 0px;/);
    ws.destroy();
    assert.equal(solidOf(a), null, 'gone with the glass');
});

test('moving the window touches nothing of the box; a new size or colour does', () => {
    const a = windowAt(0, 100, 100, 800, 600);
    actors = [a];
    const ws = new Windows(config(['org.gnome.gedit']));
    runLaters();
    const box = solidOf(a);
    const styled = box.styles.length;
    for (let i = 1; i <= 5; i++) {
        Object.assign(a.meta_window.rect, {x: 100 + 10 * i});
        a.meta_window.emit('position-changed');
        runLaters();
    }
    assert.equal(box.styles.length, styled, 'no new style while it moves');
    assert.deepEqual([box.x, box.y], [0, 0]);
    Object.assign(a.meta_window.rect, {width: 900});
    a.meta_window.emit('size-changed');
    runLaters();
    assert.equal(box.width, 900);
    // Dark/light, or a new tint: the app writes a new colour, and the box follows.
    ws.update(config(['org.gnome.gedit'], '#f2f3f7'));
    runLaters();
    assert.equal(solidOf(a), box, 'the same box');
    assert.match(box.styles.at(-1), /^background-color: #f2f3f7;/);
    ws.destroy();
});

test('taking the app off the list gives it glass again, and putting it back makes it solid, live', () => {
    const a = windowAt(0, 100, 100, 800, 600);
    actors = [a];
    const ws = new Windows(config(['org.gnome.gedit']));
    runLaters();
    assert.ok(solidOf(a));
    ws.update(config([]));
    runLaters();
    assert.equal(solidOf(a), null);
    assert.equal(ws.glassOf(a).shown, true, 'glass again');
    ws.update(config(['org.gnome.gedit']));
    runLaters();
    assert.ok(solidOf(a));
    assert.equal(ws.glassOf(a).pane.visible, false, 'its glass hidden (and let go of a little later)');
    assert.equal(ws.glassOf(a)._holder.get_parent(), null, 'and out of the actor');
    ws.destroy();
});

test('Steam and full screen get nothing in their actor; other built-in apps glass behind their title bar only', () => {
    const code = windowAt(0, 100, 100, 800, 600, 'Code');
    const gedit = windowAt(1, 200, 200, 800, 600);
    const steam = windowAt(2, 300, 300, 800, 600, 'steam');
    actors = [code, gedit, steam];
    const ws = new Windows(config(['org.gnome.gedit', 'code']));
    runLaters();
    assert.equal(solidOf(steam), null);
    assert.equal(steam.get_children().length, 1, 'only its own surface');
    // Code paints its own body: glass behind its top band only, no solid backdrop.
    assert.equal(solidOf(code), null);
    const glass = ws._glass.get(code);
    assert.ok(glass?.shown, 'glass behind its title bar');
    assert.equal(glass._shape.height, 88, 'the top band, not the whole window');
    assert.equal(glass._shape.width, 800);
    assert.deepEqual(glass.solidRects().map(r => r.height).sort((x, y) => y - x)[0], 600,
        'the app\'s own body is opaque: the windows below count as hidden behind all of it');
    assert.ok(solidOf(gedit));
    // Full screen: direct scanout and VRR want nothing but the window in its actor.
    gedit.meta_window.fullscreen = true;
    gedit.meta_window.emit('notify::fullscreen');
    runLaters();
    assert.equal(solidOf(gedit), null);
    assert.equal(gedit.get_children().length, 1);
    gedit.meta_window.fullscreen = false;
    gedit.meta_window.emit('notify::fullscreen');
    runLaters();
    assert.ok(solidOf(gedit), 'back when it leaves full screen');
    ws.destroy();
});

test('a solid window hides the windows below it like opaque glass, focused or not, but not while it moves', () => {
    const below = windowAt(0, 100, 100, 400, 300, 'org.gnome.Nautilus');
    const over = windowAt(1, 50, 50, 600, 500);
    actors = [below, over];
    display.focus_window = over.meta_window;
    const ws = new Windows(config(['org.gnome.gedit']));
    runLaters();
    runLaters();
    const g = ws.glassOf(over);
    assert.equal(g.covers().length, 2, 'all but its rounded corners');
    assert.equal(ws.glassOf(below)._whyNot(), 'hidden', 'nobody sees the window below');
    // What it covers on the screen, from its actor's top left.
    assert.deepEqual(g.paintCover(), [{x: 12, y: 0, width: 576, height: 500}, {x: 0, y: 12, width: 600, height: 476}]);
    // See-through (fading in or out): it covers nothing.
    over.opacity = 128;
    assert.deepEqual(g.solidRects(), []);
    assert.deepEqual(g.paintCover(), []);
    over.opacity = 255;
    // Moving: nothing either, until it settles.
    Object.assign(over.meta_window.rect, {x: 60});
    over.meta_window.emit('position-changed');
    runLaters();
    assert.ok(g._settle);
    assert.deepEqual(g.covers(), []);
    timers.get(g._settle)();
    assert.equal(g.covers().length, 2, 'settled: it covers them again');
    ws.destroy();
});

test('a closing window keeps its backdrop for the close animation, and asks the window nothing more', () => {
    const a = windowAt(0, 100, 100, 800, 600);
    actors = [a];
    const ws = new Windows(config(['org.gnome.gedit']));
    runLaters();
    const box = solidOf(a);
    a.meta_window.emit('unmanaging');
    assert.equal(solidOf(a), box, 'still there while it animates');
    assert.equal(ws.glassOf(a), null);
    a.meta_window.get_frame_rect = () => { throw new Error('asked an unmanaged window'); };
    runLaters();
    ws.destroy();
    a.destroy();
});
