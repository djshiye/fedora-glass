// Logic breaks in the extension's lifecycles, each found by running a sequence that broke
// it (a pause in the middle of the speed check, an unlock while the weather refreshes, the
// glass started with the overview open, a damaged safe mode file, a part that fails to go
// at a switch-off), kept as regression tests.
import assert from 'node:assert/strict';
import {register} from 'node:module';
import {test, beforeEach} from 'node:test';

register('./extension-stubs.mjs', import.meta.url);

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
            if (next[1].fn())
                this._due.set(next[0], {at: this.now + 1, fn: next[1].fn});
        }
        this.now = end;
    }
    get pending() { return this._due.size; }
}

class Emitter {
    constructor() { this._h = new Map(); this._n = 1; }
    connect(sig, fn) { const id = this._n++; this._h.set(id, [sig, fn]); return id; }
    disconnect(id) { this._h.delete(id); }
    emit(sig, ...a) { for (const [s, fn] of [...this._h.values()]) if (s === sig) fn(this, ...a); }
    get count() { return this._h.size; }
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
    constructor(rect, wmClass) {
        super();
        Object.assign(this, {rect, wmClass, minimized: false, fullscreen: false, maximized: false, here: true});
    }
    get_frame_rect() { return {...this.rect}; }
    get_buffer_rect() { return {...this.rect}; }
    get_monitor() { return 0; }
    located_on_workspace() { return this.here; }
    get_window_type() { return 0; }
    get_work_area_current_monitor() { return {x: 0, y: 0, width: 4000, height: 3000}; }
    is_maximized() { return this.maximized; }
    get_wm_class() { return this.wmClass; }
    get_wm_class_instance() { return null; }
    get_gtk_application_id() { return null; }
    get_sandboxed_app_id() { return null; }
}

// ---- one fake GNOME Shell for every part below (main.js reads it once) ----------------
const laters = new Map();
let nextLater = 1;
const runLaters = () => {
    while (laters.size) {
        const now = [...laters.entries()];
        laters.clear();
        now.forEach(([, fn]) => fn());
    }
};
let clock = new Clock();
const stage = new Emitter();
const display = Object.assign(new Emitter(), {focus_window: null});
const overview = Object.assign(new Emitter(), {visible: false});
const layoutManager = Object.assign(new Emitter(), {monitors: [{x: 0, y: 0, width: 4000, height: 3000, inFullscreen: false}],
    findMonitorForActor: () => null, _backgroundGroup: new Actor()});
const weather = {client: null};
globalThis.fake = {
    Actor, Widget: Actor, ui: new Actor(), uiGroup: new Actor(), overview, layoutManager,
    themeContext: {scale_factor: 1},
    timeouts: {add: (ms, fn) => clock.add(ms, fn), remove: id => clock.remove(id)},
    now: () => clock.now * 1000,
    realNow: () => 1e15 + clock.now * 1000,
    fs: new Map(), monitors: [],
    sessionMode: {isLocked: false, connect: () => 1, disconnect() {}},
    // GNOME's calendar menu, which holds its weather.
    panel: {statusArea: {dateMenu: {_weatherItem: {get _weatherClient() { return weather.client; }}}}},
};
let actors = [];
const shutdown = new Map();
globalThis.global = {
    stage, display,
    workspace_manager: Object.assign(new Emitter(), {get_active_workspace: () => ({})}),
    get_window_actors: () => actors,
    compositor: {get_laters: () => ({add: (_t, fn) => { const id = nextLater++; laters.set(id, fn); return id; },
        remove: id => laters.delete(id)})},
    connect: (_sig, fn) => { shutdown.set(shutdown.size + 1, fn); return shutdown.size; },
    disconnect: id => shutdown.delete(id),
};
globalThis.logError = () => {};

const EXT = '../../fedoraglass/data/extension/liquid-glass@djshiye.github.io';
const {Speed} = await import(`${EXT}/speed.js`);
const {WeatherFrost} = await import(`${EXT}/frost.js`);
const {forgetWeatherAsked} = await import(`${EXT}/frostmath.js`);
const {Windows} = await import(`${EXT}/windows.js`);
const {Safety, RESTART_LIMIT} = await import(`${EXT}/safety.js`);
const {parse} = await import(`${EXT}/config.js`);
const {windowWatch} = await import(`${EXT}/common.js`);

beforeEach(() => {
    clock = new Clock();
    laters.clear();
    actors = [];
    overview.visible = false;
    display.focus_window = null;
    weather.client = null;
    Object.assign(globalThis.fake, {fs: new Map(), monitors: [], renders: 0, shown: 0, frosts: []});
    windowWatch.current = {listeners: new Set()};
    console.warn = () => {};
    console.error = () => {};
});

// ---- 1. the speed check, the glass paused in the middle of it -------------------------
const SPEED = '/home/u/.cache/liquid-glass/speed.json';
const SMOOTH = {id: '00000000000000aa', state: 'done', error: '', refresh: 60, pick: 'full',
    phases: [{level: 'full', fps: 60, late: 0, verdict: 'smooth'}, {level: 'lighter', fps: 60, late: 0, verdict: 'smooth'},
        {level: 'lightest', fps: 60, late: 0, verdict: 'smooth'}]};
const view = {get_refresh_rate: () => 60};
// One frame on a 60 Hz screen, its timers run on the way; for `ms`, frames one after another.
function frame() {
    clock.advance(15);
    stage.emit('before-paint', view);
    clock.advance(1);
    stage.emit('after-paint', view);
}
function frames(ms) {
    for (let t = 0; t < ms; t += 16)
        frame();
}

test('the glass paused in the middle of a speed check: the check fails, the last real one stays', () => {
    // The last check found this PC smooth: auto never goes down to the lightest glass.
    globalThis.fake.fs.set(SPEED, {text: JSON.stringify({version: 1, check: SMOOTH, lastDone: SMOOTH})});
    globalThis.fake.shown = 3;
    const s = new Speed({speed: {quality: 'auto'}}, () => {});
    assert.equal(s._tuner.deepest, 1);
    s._startCheck('0123456789abcdef');
    frames(800 + 6000 + 2000);      // full glass measured, and part of lighter
    // The Glass tile in Quick Settings: every pane goes, the speed watch stays.
    globalThis.fake.shown = 0;
    frames(1000);
    clock.advance(17000);
    assert.equal(s._check, null, 'over');
    assert.equal(s._result.state, 'failed', 'no glass was drawn for the rest of it: nothing to score');
    assert.equal(s._result.error, 'noglass');
    assert.equal(s._done.id, SMOOTH.id, 'the last finished check is still the real one');
    assert.equal(s._tuner.deepest, 1, 'auto keeps the floor that check gave it');
    s.destroy();
    const status = JSON.parse(globalThis.fake.fs.get(SPEED).text);
    assert.equal(status.lastDone.id, SMOOTH.id, 'and the app is told the same');
});

test('the glass gone between two levels, with no frame since: the check fails too', () => {
    globalThis.fake.shown = 3;
    const s = new Speed({speed: {quality: 'full'}}, () => {});
    s._startCheck('0123456789abcdef');
    frames(800 + 3000);
    globalThis.fake.shown = 0;      // safe mode: nothing paints any more
    clock.advance(17000);
    assert.equal(s._result.state, 'failed');
    assert.equal(s._result.error, 'noglass');
    assert.equal(s.level, 0, 'back to the setting');
    s.destroy();
});

test('a check with glass all the way through still finishes as before', () => {
    globalThis.fake.shown = 3;
    const s = new Speed({speed: {quality: 'full'}}, () => {});
    s._startCheck('0123456789abcdef');
    frames(800 + 6000 + 5000 + 5000 + 100);
    assert.equal(s._result.state, 'done');
    assert.deepEqual(s._result.phases.map(p => p.verdict), ['smooth', 'smooth', 'smooth']);
    s.destroy();
});

// ---- 2. weather frost across a lock ---------------------------------------------------
function client({temp = -5, loading = false, valid = true} = {}) {
    return {
        available: true, hasLocation: true, loading, updates: 0, handlers: new Map(), n: 0,
        info: {is_valid: () => valid, get_value_temp: () => [true, temp], get_value_apparent: () => [true, temp]},
        connect(_sig, fn) { this.handlers.set(++this.n, fn); return this.n; },
        disconnect(id) { this.handlers.delete(id); },
        update() { this.updates++; },
    };
}
const frostOn = {weather: {enabled: true}};

test('unlocking while GNOME\'s weather refreshes keeps the frost that was showing', () => {
    forgetWeatherAsked();
    WeatherFrost.forget();
    weather.client = client({temp: -5});
    let f = new WeatherFrost(frostOn);
    const frosted = globalThis.fake.frosts.at(-1);
    assert.ok(frosted[0] > 0, 'frosted over');
    f.destroy();                        // the screen locks
    assert.deepEqual(globalThis.fake.frosts.at(-1), [0, 0]);
    // The PC wakes on the lock screen, which asks the weather to refresh; offline, it fails.
    weather.client.loading = true;
    f = new WeatherFrost(frostOn);      // unlocked while that is still going
    assert.deepEqual(globalThis.fake.frosts.at(-1), frosted, 'the same frost at once, as before the lock');
    assert.equal(f.state.status, 'ok');
    weather.client.loading = false;
    weather.client.info.is_valid = () => false;    // the refresh failed: still offline
    [...weather.client.handlers.values()].forEach(fn => fn());
    assert.deepEqual(globalThis.fake.frosts.at(-1), frosted, 'kept through a failed refresh, as without a lock');
    f.destroy();
    WeatherFrost.forget();
});

test('a reading kept over a lock still goes stale, and none is kept with the frost off or after a switch-off', () => {
    forgetWeatherAsked();
    WeatherFrost.forget();
    weather.client = client({temp: -5});
    let f = new WeatherFrost(frostOn);
    f.destroy();
    weather.client.info.is_valid = () => false;
    clock.now += 4 * 3600e3;            // locked for four hours, offline
    f = new WeatherFrost(frostOn);
    assert.deepEqual(globalThis.fake.frosts.at(-1), [0, 0], 'too old: your own look');
    f.destroy();
    // Fresh weather again, then Fedora Glass switched off and on: read afresh.
    weather.client.info.is_valid = () => true;
    f = new WeatherFrost(frostOn);
    f.destroy();
    WeatherFrost.forget();
    weather.client.loading = true;
    f = new WeatherFrost(frostOn);
    assert.deepEqual(globalThis.fake.frosts.at(-1), [0, 0], 'nothing carried past a switch-off');
    f.destroy();
    // Frost turned off: nothing kept either.
    weather.client.loading = false;
    f = new WeatherFrost(frostOn);
    f.update({weather: {enabled: false}});
    f.destroy();
    weather.client.loading = true;
    f = new WeatherFrost(frostOn);
    assert.deepEqual(globalThis.fake.frosts.at(-1), [0, 0]);
    f.destroy();
    WeatherFrost.forget();
});

// ---- 3. the glass started with the overview open ---------------------------------------
function windowAt(x, y, width, height) {
    const win = new Win({x, y, width, height}, 'org.gnome.gedit');
    const a = new Actor({x, y, width, height, meta_window: win});
    win.get_compositor_private = () => a;
    a.add_child(new Actor({name: 'surface'}));
    return a;
}

test('the glass turned on with the overview open: windows on other workspaces have glass there too', () => {
    const away = windowAt(100, 100, 800, 600);
    away.meta_window.here = false;      // on another workspace, seen in the overview
    actors = [away];
    overview.visible = true;            // the Glass tile, from Quick Settings in the overview
    const ws = new Windows(parse('{}'));
    runLaters();
    assert.equal(ws.previewing, true, 'the overview shows copies of every workspace\'s windows');
    assert.ok(ws.glassOf(away).pane, 'so this window keeps glass in it');
    overview.visible = false;
    overview.emit('hidden');
    assert.equal(ws.previewing, false, 'closed: as before');
    ws.destroy();
    assert.equal(overview.count, 0);
});

test('with the overview closed, nothing changes: a window on another workspace gets no glass', () => {
    const away = windowAt(100, 100, 800, 600);
    away.meta_window.here = false;
    actors = [away];
    const ws = new Windows(parse('{}'));
    runLaters();
    assert.equal(ws.previewing, false);
    assert.equal(ws.glassOf(away).pane, null);
    ws.destroy();
});

// ---- 4. a damaged safe mode file -----------------------------------------------------------
const SAFE = '/home/u/.cache/liquid-glass/safe-mode.json';

test('a damaged crash count in the safe mode file never puts the crash-loop check off', () => {
    for (const restarts of [-1000, -1, 0.5, '5', null]) {
        globalThis.fake.fs.set(SAFE, {text: JSON.stringify({version: 1, tripped: false, restarts, running: true, stable: false})});
        // The glass then crashes the Shell within a minute, RESTART_LIMIT times in a row.
        for (let i = 0; i < RESTART_LIMIT; i++) {
            new Safety(() => {}).glassStarted();
            shutdown.clear();
        }
        const s = new Safety(() => {});
        assert.equal(s.tripped, true, `restarts: ${JSON.stringify(restarts)}`);
        s.destroy();
    }
});

test('a "running" that is no true does not count as a crash', () => {
    globalThis.fake.fs.set(SAFE, {text: JSON.stringify({version: 1, tripped: false, restarts: 1, running: 'false', stable: false})});
    const s = new Safety(() => {});
    assert.equal(s.tripped, false);
    assert.equal(s._restarts, 0);
    s.destroy();
});

// ---- 5. a part that fails to go at a switch-off or a lock -----------------------------
const live = new Set();
let throwing = new Set();
const part = name => function () {
    live.add(name);
    return {update() {}, unlocking() {}, destroyLater(done) { this.destroy(); done(); },
        destroy() {
            live.delete(name);
            if (throwing.has(name))
                throw new Error(`${name} failed to go`);
        }};
};
globalThis.fakeMods = {
    'animations.js': {Animations: part('animations')},
    'arcrescue.js': {ArcMenuRescue: part('rescue')},
    'config.js': {Config: () => {
        live.add('config');
        return {value: {desktop: {}, quickToggle: {enabled: true}}, destroy() { live.delete('config'); }};
    }},
    'frost.js': {WeatherFrost: part('frost')},
    'desktop.js': {DesktopBehaviour: part('desktop')},
    'lock.js': {LockGlass: part('lock')},
    'lockwidgets.js': {LockWidgets: part('widgets')},
    'popupstyle.js': {PopupStyle: part('popups')},
    'paused.js': {PausedStyle: part('paused')},
    'pausestate.js': {PauseState: () => {
        live.add('pausestate');
        return {set() {}, destroy() { live.delete('pausestate'); }};
    }},
    'safety.js': {Safety: () => {
        live.add('safety');
        return {tripped: false, glassStarted() {}, glassStopped() {}, startFailed() {}, destroy() { live.delete('safety'); }};
    }, guarded: (_w, fn) => fn},
    'speed.js': {Speed: part('speed')},
    'surfaces.js': {GlassManager: part('glass')},
    'themetidy.js': {UserThemesTidy: part('tidy')},
    'gcsweep.js': {SettingsSweep: part('sweep')},
    'windows.js': {Windows: part('solid'), allSolid: cfg => cfg},
    'tuning.js': {effectiveConfig: cfg => cfg},
    'quicktoggle.js': {GlassSwitch: part('switch')},
    'Extension': {Extension: function () { return {}; }},
};
const {default: FedoraGlassExtension} = await import(`${EXT}/extension.js`);

function start() {
    const ext = Object.create(FedoraGlassExtension.prototype);
    ext.path = '/ext';
    ext.enable();
    return ext;
}
const lockTo = (ext, locked) => {
    globalThis.fake.sessionMode.isLocked = locked;
    ext._sync();
};

test('switched off on the lock screen with a lock screen part that fails to go: everything else still goes', () => {
    for (const name of ['lock', 'widgets', 'tidy']) {
        live.clear();
        throwing = new Set([name]);
        const ext = start();
        lockTo(ext, true);
        assert.ok(live.has('lock') && live.has('widgets'));
        ext.disable();
        assert.deepEqual([...live], [], `${name} threw: nothing else may stay on`);
    }
    throwing = new Set();
    globalThis.fake.sessionMode.isLocked = false;
});

test('locking with a desktop part that fails to go still brings up the lock screen and stops the rest', () => {
    for (const name of ['desktop', 'rescue']) {
        live.clear();
        throwing = new Set([name]);
        const ext = start();
        assert.ok(live.has('speed') && live.has('glass'));
        lockTo(ext, true);
        assert.ok(!live.has('speed'), `${name} threw: the speed watch still stops at the lock`);
        assert.ok(live.has('lock') && live.has('widgets'), 'and the lock screen glass and widgets are up');
        throwing = new Set();
        lockTo(ext, false);
        ext.disable();
        assert.deepEqual([...live], []);
    }
    globalThis.fake.sessionMode.isLocked = false;
});
