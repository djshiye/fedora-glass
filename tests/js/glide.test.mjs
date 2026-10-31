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
    get_stage() {
        return {};
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
    allocate(box) {
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
    Actor, Widget: Actor, timeouts: new Timeouts(), now: () => clock, stSettings,
    appSystem: new Actor(), windowTracker: new Actor(),
};
globalThis.fake = fake;
const laters = new Laters();
const dtp = new Actor({panels: []});
globalThis.global = {compositor: {get_laters: () => laters}, dashToPanel: dtp};

const {HoverGlide} = await import('../../liquidglass/data/extension/liquid-glass@djshiye.github.io/glide.js');

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
    return panel.get_children().find(c => c.name === 'liquid-glass-hover-glide');
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
    const {cleanGlide} = await import('../../liquidglass/data/extension/liquid-glass@djshiye.github.io/config.js');
    assert.equal(cleanGlide({enabled: true, color: 'rgba(0,0,0,0.05)', radius: 8}).color, 'rgba(0,0,0,0.05)');
    assert.equal(cleanGlide({enabled: true, color: '#11223344'}).color, '#11223344');
    assert.equal(cleanGlide({color: 'red; background-image: url(x)'}).color, 'rgba(255,255,255,0.08)');
    assert.equal(cleanGlide({radius: 500}).radius, 48);
    assert.equal(cleanGlide(null).enabled, false);
});
