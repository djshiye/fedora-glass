// The gliding taskbar highlight (glide.js) under a fake Shell: one tile per panel,
// it fades in where the pointer is, glides between icons, fades out on leaving,
// lands at once with Reduce animation, and leaves nothing behind.
import assert from 'node:assert/strict';
import {test} from 'node:test';

class Actor {
    constructor(props = {}) {
        this._handlers = new Map();
        this._next = 1;
        this._children = [];
        this._parent = null;
        this.mapped = true;
        this.visible = true;
        this.opacity = 255;
        this.width = 0;
        this.height = 0;
        this.translation_x = 0;
        this.translation_y = 0;
        this.destroyed = false;
        this.pos = [0, 0];
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
    handlerCount() {
        return this._handlers.size;
    }
    insert_child_at_index(c, i) {
        c._parent = this;
        this._children.splice(i, 0, c);
    }
    remove_child(c) {
        this._children = this._children.filter(x => x !== c);
        c._parent = null;
    }
    get_children() {
        return [...this._children];
    }
    get_parent() {
        return this._parent;
    }
    // On the stage when its parent is; a panel (no parent) is on it unless taken off.
    get_stage() {
        if (this._parent)
            return this._parent.get_stage();
        return this.offStage ? null : {};
    }
    get_transformed_position() {
        return this.pos;
    }
    get_transformed_size() {
        return [this.width, this.height];
    }
    transform_stage_point(x, y) {
        return [true, x - this.pos[0], y - this.pos[1]];
    }
    set_size(w, h) {
        this.width = w;
        this.height = h;
    }
    allocate(box) {
        if (!this.get_stage())
            fake.warnings.push(`Spurious clutter_actor_allocate called for actor ${this.name}`);
        this.width = box.x2 - box.x1;
        this.height = box.y2 - box.y1;
        this.allocated = true;
    }
    set_style(s) {
        this.style = s;
    }
    show() {
        this.visible = true;
    }
    hide() {
        this.visible = false;
    }
    destroy() {
        if (this.destroyed)
            throw new Error('destroyed twice');
        this.destroyed = true;
        for (const c of [...this._children])
            c.destroy();
        this._parent?.remove_child(this);
        this.emit('destroy');
    }
}

class Laters {
    constructor() {
        this._fns = new Map();
        this._next = 1;
    }
    add(_when, fn) {
        const id = this._next++;
        this._fns.set(id, fn);
        return id;
    }
    remove(id) {
        this._fns.delete(id);
    }
    get size() {
        return this._fns.size;
    }
    run() {
        const fns = [...this._fns.values()];
        this._fns.clear();
        fns.forEach(fn => fn());
    }
}

class Timeouts {
    constructor() {
        this._fns = new Map();
        this._next = 1;
    }
    add(ms, fn) {
        const id = this._next++;
        this._fns.set(id, {ms, fn});
        return id;
    }
    remove(id) {
        this._fns.delete(id);
    }
    get size() {
        return this._fns.size;
    }
    fireAll() {
        const all = [...this._fns.values()];
        this._fns.clear();
        all.forEach(({fn}) => fn());
    }
}

let clock = 0;
const stSettings = Object.assign(new Actor(), {enable_animations: true});
const fake = {
    Actor, Widget: Actor, warnings: [], timeouts: new Timeouts(), now: () => clock, stSettings,
    appSystem: new Actor(), windowTracker: new Actor(), extensionManager: new Actor(),
};
globalThis.fake = fake;
const laters = new Laters();
let dtp = new Actor({panels: []});
globalThis.global = {compositor: {get_laters: () => laters}, dashToPanel: dtp};

const {HoverGlide} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/glide.js');

const LOOK = {enabled: true, color: 'rgba(255,255,255,0.08)', radius: 8};

// A panel at (100, 850) with three 48 px icons in a row.
function scene() {
    const panel = new Actor({pos: [100, 850], width: 1400, height: 44});
    const icons = [0, 1, 2].map(i => {
        const container = new Actor({pos: [100 + 4 + i * 52, 852], width: 48, height: 40});
        return new Actor({_container: container, hover: false});
    });
    panel.taskbar = {_getAppIcons: () => icons};
    dtp.panels = [panel];
    return {panel, icons};
}

function frames(n, ms = 16) {
    for (let i = 0; i < n && laters.size; i++) {
        clock += ms * 1000;
        laters.run();
    }
}

function hover(icon, on) {
    icon.hover = on;
    icon.emit('notify::hover');
}

function tileOf(panel) {
    return panel.get_children().find(c => c.name === 'fedora-glass-hover-glide');
}

test('one tile per panel, under the icons, styled from the config', () => {
    const {panel} = scene();
    const g = new HoverGlide();
    g.update(LOOK);
    const tile = tileOf(panel);
    assert.ok(tile);
    // A theme change asks for a new layout: the tile allocates itself again before the frame.
    tile.allocated = false;
    tile.emit('queue-relayout');
    laters.run();
    assert.ok(tile.allocated);
    assert.equal(panel.get_children()[0], tile);
    assert.match(tile.style, /background-color: rgba\(255,255,255,0.08\); border-radius: 8px;/);
    assert.equal(tile.opacity, 0, 'idle: shown at opacity 0, so it never asks for a layout');
    assert.ok(tile.allocated, 'it gives itself an allocation');
    g.destroy();
    assert.equal(tileOf(panel), undefined);
});

test('fades in on the first icon, glides to the next, fades out after leaving', () => {
    const {panel, icons} = scene();
    const g = new HoverGlide();
    g.update(LOOK);
    hover(icons[0], true);
    frames(1);
    const tile = tileOf(panel);
    // Appears where the pointer is, not gliding in from elsewhere, at the icon's size.
    assert.equal(tile.translation_x, 4);
    assert.deepEqual([tile.width, tile.height], [48, 40]);
    assert.ok(tile.opacity > 0 && tile.opacity < 255, 'fading in');
    frames(20);
    assert.equal(tile.opacity, 255);
    assert.equal(laters.size, 0, 'nothing runs once it has arrived');

    // To the next icon: leave one, enter the other in the same moment.
    hover(icons[0], false);
    hover(icons[1], true);
    frames(4);
    assert.ok(tile.translation_x > 4 && tile.translation_x < 56, `mid glide at ${tile.translation_x}`);
    assert.equal(tile.opacity, 255, 'stays lit while gliding');
    frames(60);
    assert.equal(tile.translation_x, 56);
    assert.equal(laters.size, 0);

    // Leaving the taskbar: a short grace, then a fade.
    hover(icons[1], false);
    assert.equal(fake.timeouts.size, 1);
    fake.timeouts.fireAll();
    frames(4);
    assert.ok(tile.opacity < 255);
    frames(40);
    assert.equal(tile.opacity, 0);
    assert.equal(laters.size, 0);
    g.destroy();
});

test('crossing the gap between icons does not fade the tile', () => {
    const {panel, icons} = scene();
    const g = new HoverGlide();
    g.update(LOOK);
    hover(icons[0], true);
    frames(30);
    hover(icons[0], false);       // in the gap
    hover(icons[1], true);        // before the grace runs out
    assert.equal(fake.timeouts.size, 0, 'the grace timer is dropped');
    frames(3);
    assert.equal(tileOf(panel).opacity, 255);
    g.destroy();
});

test('Reduce animation: the tile jumps and lands at once', () => {
    const {panel, icons} = scene();
    const g = new HoverGlide();
    g.update(LOOK);
    stSettings.enable_animations = false;
    hover(icons[2], true);
    frames(1);
    const tile = tileOf(panel);
    assert.equal(tile.translation_x, 108);
    assert.equal(tile.opacity, 255);
    assert.equal(laters.size, 0);
    stSettings.enable_animations = true;
    g.destroy();
});

test('turning it off or a panel rebuild leaves no tile, timer or handler behind', () => {
    const {panel, icons} = scene();
    const g = new HoverGlide();
    g.update(LOOK);
    hover(icons[0], true);
    hover(icons[0], false);       // grace timer pending
    g.update({...LOOK, enabled: false});
    assert.equal(tileOf(panel), undefined);
    assert.equal(fake.timeouts.size, 0);
    assert.equal(laters.size, 0);
    assert.ok(icons.every(i => i.handlerCount() === 0));
    assert.equal(panel.handlerCount(), 0);
    assert.equal(dtp.handlerCount(), 0);

    // Back on, then Dash to Panel destroys the panel: the tile goes with it, once.
    g.update(LOOK);
    assert.ok(tileOf(panel));
    panel.destroy();
    g.destroy();
    assert.equal(fake.appSystem.handlerCount(), 0);
    assert.equal(stSettings.handlerCount(), 0);
});

test('config: only plain colours reach the style string', async () => {
    const {cleanGlide} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/config.js');
    assert.equal(cleanGlide({enabled: true, color: 'rgba(0,0,0,0.05)', radius: 8}).color, 'rgba(0,0,0,0.05)');
    assert.equal(cleanGlide({enabled: true, color: '#11223344'}).color, '#11223344');
    assert.equal(cleanGlide({color: 'red; background-image: url(x)'}).color, 'rgba(255,255,255,0.08)');
    assert.equal(cleanGlide({radius: 500}).radius, 48);
    assert.equal(cleanGlide(null).enabled, false);
});

test('the shared spring settles on its target with a small overshoot, also over long frames', async () => {
    const {springStep} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/curves.js');
    let [x, v, peak] = [0, 0, 0];
    for (let i = 0; i < 60; i++) {
        [x, v] = springStep(x, v, 1, 700, 46, 0.016);
        peak = Math.max(peak, x);
    }
    assert.ok(Math.abs(x - 1) < 1e-3 && Math.abs(v) < 0.05);
    assert.ok(peak < 1.03, `overshoot ${peak}`);
    // One 150 ms stall is sub-stepped, not one huge Euler step.
    [x, v] = springStep(0, 0, 1, 1370, 44, 0.15);
    assert.ok(Number.isFinite(x) && x > 0 && x < 1.3);
});

test('Dash to Panel turned off and on again: the new panels get the glide too', () => {
    const {panel} = scene();
    const g = new HoverGlide();
    g.update(LOOK);
    assert.ok(tileOf(panel));
    // Dash to Panel makes a new object (and new panels) each time it is turned on.
    const old = dtp;
    dtp = new Actor({panels: []});
    global.dashToPanel = dtp;
    fake.extensionManager.emit('extension-state-changed');
    assert.equal(old.handlerCount(), 0, 'nothing left on the old object');
    const {panel: fresh} = scene();
    dtp.emit('panels-created');
    laters.run();
    fake.timeouts.fireAll();
    assert.ok(tileOf(fresh), 'the new panel has its tile');
    g.destroy();
    assert.equal(dtp.handlerCount(), 0);
    assert.equal(fake.extensionManager.handlerCount(), 0);
});

// A GObject that GJS has already disposed: it still passes instanceof, and every
// method call on it is what fills GNOME Shell's log with "has been already disposed".
function dispose(actor) {
    return new Proxy(actor, {
        get(target, prop) {
            if (prop === Symbol.for('fake-disposed'))
                return true;
            const v = Reflect.get(target, prop);
            if (typeof v !== 'function')
                return v;
            return (...args) => {
                fake.warnings.push(`${String(prop)} on a disposed panel`);
                return v.apply(target, args);
            };
        },
    });
}

// The 1.7.5 bug from a Dash to Panel user's log: after Dash to Panel rebuilt its panels,
// its list still held the destroyed ones, and the glide put a new tile on each (touching
// a disposed panel), which left "fedora-glass-hover-glide" actors outside the stage.
test('Dash to Panel rebuilding its panels many times: no dead panel touched, no tile left loose', () => {
    fake.warnings.length = 0;
    const {panel: first} = scene();
    const g = new HoverGlide();
    g.update(LOOK);
    let current = [first];
    const made = [tileOf(first)];
    for (let round = 0; round < 5; round++) {
        // Dash to Panel takes its panels down; its list keeps them, now disposed.
        for (const p of current)
            p.destroy();
        dtp.panels = current.map(dispose);
        // Anything that refreshes the glide in between (a window opened, an extension
        // changed state) must not touch them.
        fake.windowTracker.emit('tracked-windows-changed');
        fake.timeouts.fireAll();
        laters.run();
        assert.deepEqual(g.qaState(), [], `round ${round}: no tile for a dead panel`);
        // Then the new panels (two screens on odd rounds), and its signal.
        current = round % 2 ? [scene().panel, scene().panel] : [scene().panel];
        dtp.panels = current;
        dtp.emit('panels-created');
        fake.timeouts.fireAll();
        laters.run();
        const tiles = current.map(tileOf);
        assert.ok(tiles.every(Boolean), `round ${round}: every new panel has its tile`);
        assert.equal(g.qaState().length, current.length, 'tile count = panel count');
        made.push(...tiles);
    }
    assert.deepEqual(fake.warnings, [], 'nothing touched a disposed panel or allocated off the stage');
    g.destroy();
    assert.ok(made.every(t => t.destroyed), 'no tile is left behind');
    assert.ok(current.every(p => p.handlerCount() === 0));
});

test('a panel destroyed without telling the glide, and a panel off the stage, get no tile', () => {
    fake.warnings.length = 0;
    const {panel} = scene();
    const g = new HoverGlide();
    g.update(LOOK);
    const tile = tileOf(panel);
    // Gone behind our back (no destroy signal reached us): the list holds it, disposed.
    dtp.panels = [dispose(panel)];
    fake.windowTracker.emit('tracked-windows-changed');
    fake.timeouts.fireAll();
    assert.deepEqual(g.qaState(), []);
    assert.ok(tile.destroyed, 'its tile went');
    // A live panel that is not on the stage yet waits for the next refresh.
    const {panel: later} = scene();
    later.offStage = true;
    fake.windowTracker.emit('tracked-windows-changed');
    fake.timeouts.fireAll();
    assert.equal(tileOf(later), undefined);
    later.offStage = false;
    dtp.emit('panels-created');
    fake.timeouts.fireAll();
    laters.run();
    assert.ok(tileOf(later));
    // A theme change asking for a layout while the panel is off the stage allocates nothing.
    later.offStage = true;
    tileOf(later).emit('queue-relayout');
    laters.run();
    assert.deepEqual(fake.warnings, []);
    g.destroy();
});

test('the shared Dash to Panel list leaves out disposed panels, and plain objects are never disposed', async () => {
    const {dtpPanels, disposed} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/common.js');
    const live = new Actor({panelBox: new Actor()});
    const deadBox = new Actor({panelBox: dispose(new Actor())});
    dtp.panels = [live, dispose(new Actor()), deadBox, null];
    assert.deepEqual(dtpPanels(), [live]);
    // A main panel Dash to Panel took down but did not destroy is off the stage: left out too.
    const takenDown = new Actor({panelBox: new Actor(), offStage: true});
    dtp.panels = [live, takenDown];
    assert.deepEqual(dtpPanels(), [live]);
    assert.equal(disposed({}), false);
    assert.equal(disposed(null), true);
    const was = global.dashToPanel;
    global.dashToPanel = undefined;
    assert.deepEqual(dtpPanels(), []);
    global.dashToPanel = was;
});

// Dash to Panel fills a taskbar after its panel is there (the icons come as deferred work):
// a panel whose taskbar is still empty, as the glide finds it right after login.
function lateScene() {
    const panel = new Actor({pos: [100, 850], width: 1400, height: 44});
    const icons = [];
    const box = new Actor();
    panel.taskbar = {_getAppIcons: () => icons, _box: box};
    dtp.panels = [panel];
    return {panel, icons, box};
}

// Dash to Panel adds the taskbar's i-th icon; the idle that looks again runs.
function arrive({icons, box}, i = icons.length) {
    const container = new Actor({pos: [100 + 4 + i * 52, 852], width: 48, height: 40});
    const icon = new Actor({_container: container, hover: false});
    icons.push(icon);
    box.emit('child-added', icon);
    fake.timeouts.fireAll();
    return icon;
}

test('an icon Dash to Panel adds after the start gets the highlight', () => {
    const s = lateScene();
    const g = new HoverGlide();
    g.update(LOOK);
    assert.equal(s.box.handlerCount(), 1, 'the taskbar is followed');
    // Until 1.7.10 nothing told the glide: a pinned icon had no highlight until a window
    // opened or closed, and Dash to Panel's own highlight is clear while the glide is on.
    const icon = arrive(s);
    hover(icon, true);
    frames(20);
    const tile = tileOf(s.panel);
    assert.equal(tile.opacity, 255, 'lit under the icon that came later');
    assert.equal(tile.translation_x, 4);
    // a second one: glides there
    const next = arrive(s);
    hover(icon, false);
    hover(next, true);
    frames(60);
    assert.equal(tile.translation_x, 56);
    g.destroy();
    assert.equal(s.box.handlerCount(), 0, 'nothing stays connected to the taskbar');
    assert.ok([icon, next].every(i => i.handlerCount() === 0));
});

test('after Dash to Panel builds a new panel its taskbar is followed and the old one let go', () => {
    const old = lateScene();
    const g = new HoverGlide();
    g.update(LOOK);
    const fresh = lateScene();          // dtp.panels is now the new panel alone
    dtp.emit('panels-created');
    fake.timeouts.fireAll();
    assert.equal(old.box.handlerCount(), 0, 'the old taskbar is let go');
    assert.equal(fresh.box.handlerCount(), 1);
    const icon = arrive(fresh);
    hover(icon, true);
    frames(20);
    assert.equal(tileOf(fresh.panel).opacity, 255);
    g.destroy();
    assert.equal(fresh.box.handlerCount(), 0);
});

test('a taskbar that was destroyed is never touched, and the glide switched off follows none', () => {
    fake.warnings.length = 0;
    const s = lateScene();
    const g = new HoverGlide();
    g.update(LOOK);
    // Dash to Panel took the taskbar down behind our back: from now on every call on its
    // box would only fill the log.
    s.box[Symbol.for('fake-disposed')] = true;
    s.box.connect = s.box.disconnect = () => fake.warnings.push('touched a disposed taskbar');
    fake.windowTracker.emit('tracked-windows-changed');
    fake.timeouts.fireAll();
    g.update({...LOOK, enabled: false});
    assert.deepEqual(fake.warnings, []);
    const off = lateScene();
    g.update({...LOOK, enabled: false});
    assert.equal(off.box.handlerCount(), 0, 'off: no taskbar is followed');
    arrive(off);
    assert.equal(tileOf(off.panel), undefined, 'and an icon arriving makes no tile');
    g.update(LOOK);
    assert.equal(off.box.handlerCount(), 1);
    g.destroy();
    assert.equal(off.box.handlerCount(), 0);
});

// ---- while the glass is paused or in safe mode (paused.js) ------------------------------
// The glide goes down with the animations when the glass stops, but Dash to Panel's own
// hover colour stays clear (the app set it so): up to 1.7.10 a taskbar icon under the pointer
// showed nothing at all while the glass was paused. The paused look carries a glide of its own.
fake.fs = new Map();
fake.themeContext = {get_theme: () => ({get_custom_stylesheets: () => [], load_stylesheet() {}, unload_stylesheet() {}}),
    connect: () => 1, disconnect() {}};
const {PausedStyle} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/paused.js');
const PAUSED = {pausedCss: '', pausedAlpha: 0.96};

function nothingLeft(panel, icons) {
    assert.equal(tileOf(panel), undefined, 'no tile is left');
    assert.ok(icons.every(i => i.handlerCount() === 0));
    for (const o of [panel, dtp, fake.appSystem, fake.windowTracker, fake.extensionManager, stSettings])
        assert.equal(o.handlerCount(), 0);
    assert.equal(laters.size, 0);
}

test('paused: the gliding highlight carries on, follows its switch, and goes with the paused look', () => {
    const {panel, icons} = scene();
    const p = new PausedStyle({...PAUSED, glide: LOOK});
    hover(icons[1], true);
    frames(20);
    const tile = tileOf(panel);
    assert.equal(tile.opacity, 255, 'lit under the icon while the glass is paused');
    assert.equal(tile.translation_x, 56);
    assert.match(tile.style, /background-color: rgba\(255,255,255,0.08\); border-radius: 8px;/);
    // A new look from the app while paused (another colour) reaches the same tile.
    p.update({...PAUSED, glide: {...LOOK, color: 'rgba(0,0,0,0.06)'}});
    assert.equal(tileOf(panel), tile);
    assert.match(tile.style, /rgba\(0,0,0,0.06\)/);
    // Switched off in the app while paused: gone; switched on again: back.
    p.update({...PAUSED, glide: {...LOOK, enabled: false}});
    assert.equal(tileOf(panel), undefined);
    p.update({...PAUSED, glide: LOOK});
    assert.ok(tileOf(panel));
    hover(icons[1], false);
    fake.timeouts.fireAll();
    p.destroy();
    nothingLeft(panel, icons);
});

test('paused: locking takes the highlight down at once, not with the sheet a moment later', () => {
    const {panel, icons} = scene();
    const p = new PausedStyle({...PAUSED, glide: LOOK});
    assert.ok(tileOf(panel));
    p.destroyLater(() => {});
    nothingLeft(panel, icons);
    p.destroy();     // the sheet's own end: nothing to do twice
    nothingLeft(panel, icons);
});

test('paused: no highlight when the glide is switched off, or the config says nothing of it', () => {
    const {panel, icons} = scene();
    for (const cfg of [{...PAUSED, glide: {...LOOK, enabled: false}}, PAUSED, undefined]) {
        const p = new PausedStyle(cfg);
        assert.equal(tileOf(panel), undefined);
        p.destroy();
        nothingLeft(panel, icons);
    }
});

test('paused: a highlight that cannot start leaves the rest of the paused look standing', () => {
    const {panel, icons} = scene();
    const lifted = {alpha: 0.29, _updateAlpha() { this.alpha = 0.29; }, _updateAlphaAndSet() { this._updateAlpha(); }};
    panel.dynamicTransparency = lifted;
    // GNOME's settings object refuses the glide's listener: the glide cannot be made.
    const connect = stSettings.connect;
    stSettings.connect = () => { throw new Error('no settings today'); };
    const errors = [];
    const error = console.error;
    console.error = m => errors.push(String(m));
    let p;
    try {
        p = new PausedStyle({...PAUSED, glide: LOOK});
    } finally {
        console.error = error;
        stSettings.connect = connect;
    }
    assert.equal(lifted.alpha, 0.96, 'Dash to Panel\'s panel is solid all the same');
    assert.equal(tileOf(panel), undefined);
    assert.equal(errors.length, 1);
    assert.match(errors[0], /Fedora Glass: no gliding highlight while paused: Error: no settings today/);
    // The next word from the app tries again, and now it can.
    p.update({...PAUSED, glide: LOOK});
    assert.ok(tileOf(panel));
    p.destroy();
    assert.equal(lifted.alpha, 0.29);
    delete panel.dynamicTransparency;
    nothingLeft(panel, icons);
});
