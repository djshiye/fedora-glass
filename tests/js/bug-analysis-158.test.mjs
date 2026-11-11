// Bug analysis after 1.5.8, under a fake Shell:
//  - a glass start that fails halfway takes down what it built, and GNOME's
//    window handlers are never left blocked or blocked twice;
//  - a session that never drew glass (the screen was locked) is not a crash;
//  - an aborted speed check keeps the last finished one for auto quality;
//  - Dash to Panel previews: no handler left behind, opaque stays opaque;
//  - a speed check's limit says so ('check'), not 'setting'.
import assert from 'node:assert/strict';
import {test, beforeEach} from 'node:test';

class Obj {
    constructor(props = {}) {
        this._handlers = new Map();
        this._next = 1;
        Object.assign(this, props);
    }
    connect(signal, fn) {
        const id = this._next++;
        this._handlers.set(id, [signal, fn]);
        return id;
    }
    disconnect(id) {
        if (!this._handlers.delete(id))
            throw new Error(`no handler ${id}`);
    }
    emit(signal, ...args) {
        for (const [s, fn] of [...this._handlers.values()]) {
            if (s === signal)
                fn(this, ...args);
        }
    }
    handlerCount(signal) {
        return [...this._handlers.values()].filter(([s]) => !signal || s === signal).length;
    }
    firstHandler(signal) {
        for (const [id, [s]] of this._handlers) {
            if (s === signal)
                return id;
        }
        return 0;
    }
}

class Actor extends Obj {
    constructor(props = {}) {
        super();
        this._children = [];
        this._parent = null;
        this._style = null;
        this.mapped = false;
        this.visible = true;
        this.opacity = 255;
        this.width = 0;
        this.height = 0;
        this.name = '';
        Object.assign(this, props);
    }
    add_child(c) { c._parent = this; this._children.push(c); }
    insert_child_at_index(c, i) { c._parent = this; this._children.splice(i, 0, c); }
    remove_child(c) { this._children = this._children.filter(x => x !== c); c._parent = null; }
    get_parent() { return this._parent; }
    get_children() { return [...this._children]; }
    has_style_class_name() { return false; }
    get_style() { return this._style; }
    set_style(s) { this._style = s; this.emit('notify::style'); }
    set_size() {}
    add_constraint() {}
    add_effect() {}
    destroy() { this._parent?.remove_child(this); this.emit('destroy'); }
}

class Clock {
    constructor() { this.now = 0; this._next = 1; this._due = new Map(); }
    add(ms, fn) { const id = this._next++; this._due.set(id, {at: this.now + ms, fn}); return id; }
    remove(id) { this._due.delete(id); }
    get pending() { return this._due.size; }
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
}

// GObject's handler blocking, on the fake window manager.
const blocks = new Map();
const gobject = {
    find: (obj, {signalId}) => obj.firstHandler(signalId),
    block: (_obj, id) => blocks.set(id, (blocks.get(id) ?? 0) + 1),
    unblock: (_obj, id) => {
        if (!blocks.get(id))
            throw new Error(`handler ${id} is not blocked`);
        blocks.set(id, blocks.get(id) - 1);
    },
};

const wm = {_mapping: new Set(), _minimizing: new Set(), _unminimizing: new Set(), _destroying: new Set(),
    _skippedActors: new Set()};
for (const n of ['_mapWindow', '_mapWindowDone', '_minimizeWindow', '_minimizeWindowDone', '_unminimizeWindow',
    '_unminimizeWindowDone', '_destroyWindow', '_destroyWindowDone', '_shouldAnimate', '_getAnimationWindowType'])
    wm[n] = () => {};

const extensionManager = new Obj();
const appSystem = new Obj();
const failing = {apps: false, extensions: false};
for (const [o, key] of [[appSystem, 'apps'], [extensionManager, 'extensions']]) {
    const connect = o.connect.bind(o);
    o.connect = (...a) => {
        if (failing[key])
            throw new Error('forced test failure');
        return connect(...a);
    };
}

class Laters {
    constructor() { this._fns = new Map(); this._next = 1; }
    add(_when, fn) { const id = this._next++; this._fns.set(id, fn); return id; }
    remove(id) { this._fns.delete(id); }
}

const ui = new Actor();
const layoutManager = Object.assign(new Obj(), {uiGroup: ui, monitors: [{}], findMonitorForActor: () => null});
const stSettings = Object.assign(new Obj(), {enable_animations: true});
const fake = {
    Actor, ui, wm, gobject, extensionManager, appSystem, layoutManager, stSettings,
    timeouts: new Clock(), fs: new Map(), monitors: [],
    BackgroundManager: class { destroy() {} },
};
globalThis.fake = fake;

const shutdown = new Obj();
globalThis.global = {
    compositor: {get_laters: () => new Laters()},
    stage: Object.assign(new Actor(), {get_size: () => [100, 100], queue_redraw() {}}),
    display: new Obj(),
    workspace_manager: new Obj(),
    window_manager: new Obj(),
    get_window_actors: () => [],
    get_pointer: () => [0, 0],
    backend: {get_cursor_tracker: () => cursor},
    connect: (s, fn) => shutdown.connect(s, fn),
    disconnect: id => shutdown.disconnect(id),
};
const cursor = new Obj();

const EXT = '../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/';
const {Animations} = await import(`${EXT}animations.js`);
const {GlassManager} = await import(`${EXT}surfaces.js`);
const common = await import(`${EXT}common.js`);
const {Safety, RESTART_LIMIT} = await import(`${EXT}safety.js`);
const {Speed} = await import(`${EXT}speed.js`);
const {Tuner} = await import(`${EXT}tuning.js`);
const {Popups, PreviewTint} = await import(`${EXT}popups.js`);

// GNOME's own window manager handlers, connected first at startup.
const WM_SIGNALS = ['map', 'minimize', 'unminimize', 'destroy'];
const gnomeIds = WM_SIGNALS.map(s => global.window_manager.connect(s, () => {}));

beforeEach(() => {
    failing.apps = false;
    failing.extensions = false;
    console.error = () => {};
    console.warn = () => {};
    globalThis.log = () => {};
    globalThis.logError = () => {};
});

const animCfg = {
    animations: {open: {preset: 'genie'}, minimize: {preset: 'genie'}, close: {preset: 'genie'},
        unminimize: {preset: 'genie'}, hover: {preset: 'off'}, launch: {preset: 'bounce'}},
    glide: {enabled: false},
};
const blocked = () => gnomeIds.map(id => blocks.get(id) ?? 0);

// ---- S2: a glass start that fails halfway ----------------------------------------------
test('animations that fail to start give GNOME its window handlers back', () => {
    failing.apps = true;     // panel.sync() throws, after windows.sync() blocked GNOME's handlers
    assert.throws(() => new Animations(animCfg));
    assert.deepEqual(blocked(), [0, 0, 0, 0], "GNOME's map/minimize/unminimize/destroy run again");
    assert.equal(global.window_manager.handlerCount(), WM_SIGNALS.length, 'none of ours left connected');
    assert.equal(stSettings.handlerCount(), 0, 'no Reduce animation watch left');
});

test("a second set of window animations never handles GNOME's window events twice", () => {
    const a = new Animations(animCfg);
    assert.deepEqual(blocked(), [1, 1, 1, 1]);
    const b = new Animations(animCfg);      // a leftover from before, still there
    assert.deepEqual(blocked(), [1, 1, 1, 1], 'blocked once, not twice');
    assert.equal(global.window_manager.handlerCount('destroy'), 2, "GNOME's and one of ours");
    b.destroy();
    a.destroy();
    assert.deepEqual(blocked(), [0, 0, 0, 0]);
    assert.equal(global.window_manager.handlerCount(), WM_SIGNALS.length);
});

test('glass that fails to start takes down the parts it already built', () => {
    failing.extensions = true;     // new Panels() throws, after the watchers came up
    assert.throws(() => new GlassManager({}));
    assert.equal(common.windowWatch.current, null);
    assert.equal(common.motion.current, null);
    assert.equal(common.wallpaper.current, null);
    assert.equal(global.stage.handlerCount('captured-event'), 0, 'no pointer handler left on the stage');
    assert.equal(global.display.handlerCount(), 0);
    assert.equal(global.workspace_manager.handlerCount(), 0);
    assert.equal(layoutManager.handlerCount(), 0);
    assert.equal(cursor.handlerCount(), 0);
    assert.equal(stSettings.handlerCount(), 0);
});

// ---- S3: a session that never drew glass is not a crash --------------------------------
const SAFE = '/home/u/.cache/liquid-glass/safe-mode.json';
test('starting while locked, then crashing, is not a crash loop', () => {
    fake.fs.delete(SAFE);
    for (let i = 0; i < RESTART_LIMIT + 1; i++) {
        // GNOME turned the extension off and on while locked; the PC slept; the Shell crashed on resume.
        new Safety(() => {});
        fake.timeouts.advance(0);     // written on the next main-loop turn (safety.js)
        assert.equal(JSON.parse(fake.fs.get(SAFE).text).running, false, 'no glass on the lock screen');
        shutdown._handlers.clear();
    }
    const s = new Safety(() => {});
    assert.equal(s.tripped, false);
    s.destroy();
});

test('the glass crashing right after it starts still counts', () => {
    fake.fs.delete(SAFE);
    for (let i = 0; i < RESTART_LIMIT; i++) {
        new Safety(() => {}).glassStarted();
        shutdown._handlers.clear();
    }
    const s = new Safety(() => {});
    assert.equal(s.tripped, true);
    s.destroy();
});

test('locking within a minute of starting, then crashing, is not a crash loop', () => {
    fake.fs.delete(SAFE);
    for (let i = 0; i < RESTART_LIMIT + 1; i++) {
        const s = new Safety(() => {});
        s.glassStarted();
        s.glassStopped();     // the screen locks
        assert.equal(JSON.parse(fake.fs.get(SAFE).text).running, false);
        shutdown._handlers.clear();
    }
    const s = new Safety(() => {});
    assert.equal(s.tripped, false);
    s.destroy();
});

// ---- S4: an aborted speed check keeps the last finished one -----------------------------
const SPEED = '/home/u/.cache/liquid-glass/speed.json';
const REQ = '/home/u/.config/liquid-glass/speed-check.json';
const askCheck = id => {
    fake.fs.set(REQ, {text: JSON.stringify({id})});
    for (const [path, m] of fake.monitors) {
        if (path === '/home/u/.config/liquid-glass')
            m.handlers.forEach(h => h(m, {get_basename: () => 'speed-check.json'}, null));
    }
};
const DONE = {id: '00000000000000aa', state: 'done', error: '', refresh: 60, pick: 'full',
    phases: [{level: 'full', fps: 60, late: 0, verdict: 'smooth'}, {level: 'lighter', fps: 60, late: 0, verdict: 'smooth'},
        {level: 'lightest', fps: 60, late: 0, verdict: 'smooth'}]};

for (const [why, shown, id] of [['noglass', 0, '00000000000000bb'], ['locked', 3, '00000000000000cc']]) {
    test(`a speed check aborted (${why}) keeps the auto quality floor of the last finished one`, () => {
        fake.fs.set(SPEED, {text: JSON.stringify({version: 1, check: DONE})});
        fake.monitors = [];
        fake.shown = shown;
        let s = new Speed({speed: 'auto'}, () => {});
        assert.equal(s._tuner.deepest, 1, 'full glass was smooth: never the lightest');
        askCheck(id);
        s.destroy();
        const status = JSON.parse(fake.fs.get(SPEED).text);
        assert.equal(status.check.state, 'failed', 'the app still sees this check failed');
        assert.equal(status.check.error, why);
        assert.equal(status.lastDone?.id, DONE.id);
        fake.monitors = [];
        s = new Speed({speed: 'auto'}, () => {});
        assert.equal(s._tuner.deepest, 1, 'after the next unlock, still never the lightest');
        s.destroy();
    });
}

// ---- S5, S6: Dash to Panel's window previews -------------------------------------------
function previewMenu(boxStyle) {
    const strip = new Actor();
    strip.requestPeek = () => {};
    const box = new Actor();
    box._style = boxStyle;
    strip.menu = box;
    strip.add_child(box);
    return {strip, box};
}

test('turning the pop-ups off leaves no handler on the preview box', () => {
    const {strip, box} = previewMenu('background: rgba(41,42,48,0.28); ');
    const p = new Popups({});
    p._follow = () => {};
    p._consider(strip);
    p.destroy();
    assert.equal(box.handlerCount(), 0, 'Dash to Panel keeps this box: nothing of ours stays on it');
});

test('a preview pop-up at 100% opacity keeps opaque title strips', () => {
    const {box} = previewMenu('background: rgba(41,42,48,1); ');
    const header = new Actor({has_style_class_name: c => c === 'preview-header-box'});
    const own = 'background-color: rgba(29,30,36,1);';
    header._style = own;
    box.add_child(header);
    const tint = new PreviewTint(box);
    assert.equal(header.get_style(), own);
    tint.destroy();
});

// ---- S7: tuning ---------------------------------------------------------------------------
test("auto stepping up to a speed check's limit says why", () => {
    const t = new Tuner();
    t.level = 2;
    assert.equal(t.limit(1, 0), 1);
    assert.equal(t.reason, 'check');
});
