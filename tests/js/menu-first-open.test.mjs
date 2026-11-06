// A menu's glass is built when it first opens. Whatever happens to that glass,
// the menu must show: right away if the glass cannot be built, and within
// HOLD_MAX_MS if the glass never comes up.
import assert from 'node:assert/strict';
import {test, beforeEach} from 'node:test';

class Actor {
    constructor() {
        this._handlers = new Map();
        this._next = 1;
        this._children = [];
        this._parent = null;
        this.mapped = false;
        this.visible = true;
        this.opacity = 255;
        this.width = 0;
        this.height = 0;
        this.name = '';
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
    add_child(c) {
        c._parent = this;
        this._children.push(c);
    }
    insert_child_below(c, sibling) {
        c._parent = this;
        this._children.splice(Math.max(0, this._children.indexOf(sibling)), 0, c);
    }
    remove_child(c) {
        this._children = this._children.filter(x => x !== c);
        c._parent = null;
    }
    get_parent() {
        return this._parent;
    }
    get_children() {
        return [...this._children];
    }
    has_style_class_name() {
        return false;
    }
    show() {
        this.visible = true;
    }
    hide() {
        this.visible = false;
    }
    set_scale() {}
    destroy() {
        this._parent?.remove_child(this);
        this.emit('destroy');
    }
    map() {
        this.mapped = true;
        this.emit('notify::mapped');
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
    fireAll() {
        const all = [...this._fns.entries()];
        this._fns.clear();
        return all.map(([, {ms, fn}]) => (fn(), ms));
    }
}

const fake = {Actor, ui: new Actor(), glassFails: false, timeouts: new Timeouts()};
globalThis.fake = fake;
const laters = new Laters();
globalThis.global = {compositor: {get_laters: () => laters}, stage: Object.assign(new Actor(), {queue_redraw() {}})};

const {Popups, partOf, previewBox, dialogBox, seeThrough, tintOf, PreviewTint} = await import('../../liquidglass/data/extension/liquid-glass@djshiye.github.io/popups.js');
const {HOLD_MAX_MS} = await import('../../liquidglass/data/extension/liquid-glass@djshiye.github.io/common.js');

const cfg = {menus: {enabled: true, look: {}}, calendar: {enabled: true, look: {}},
    quicksettings: {enabled: true, look: {}}, arcmenu: {enabled: true, look: {}}};

// An OSD-like pop-up: a wrapper in the UI group holding the surface that gets glass.
function popup() {
    const anchor = new Actor();
    const surface = new Actor();
    surface.has_style_class_name = c => c === 'osd-window';
    anchor.add_child(surface);
    fake.ui.add_child(anchor);
    return {anchor, surface};
}

let errors;
beforeEach(() => {
    fake.ui._children = [];
    fake.glassFails = false;
    errors = [];
    console.error = m => errors.push(String(m));
});

function start(popups) {
    // _settings() reads the config: keep the test independent of its shape.
    popups._settings = part => cfg[part];
    return popups;
}

test('no glass is built for a menu that has not opened', () => {
    const {anchor, surface} = popup();
    const p = start(new Popups(cfg));
    p._follow(surface, anchor, 'quicksettings');
    assert.equal(p._followers.size, 0);
    assert.equal(fake.ui.get_children().length, 1, 'no pane in the UI group');
    p.destroy();
    assert.equal(surface.handlerCount(), 0, 'turning off leaves no signal behind');
});

test('if the glass throws on first open, the menu shows at once without glass', () => {
    const {anchor, surface} = popup();
    const p = start(new Popups(cfg));
    p._follow(surface, anchor, 'quicksettings');
    fake.glassFails = true;
    assert.doesNotThrow(() => surface.map());
    assert.equal(surface.opacity, 255, 'the menu is not hidden');
    assert.equal(p._followers.size, 0);
    assert.equal(p._waiting.size, 0);
    assert.deepEqual(fake.ui.get_children(), [anchor], 'the half-built panes are gone');
    assert.equal(surface.handlerCount(), 0, 'no signal left on the menu');
    assert.equal(anchor.handlerCount(), 0, 'no signal left on its wrapper');
    assert.ok(errors.some(e => e.includes('menu shown without glass')), 'the failure is logged');
    p.destroy();
});

test('if the glass never comes up, the menu shows after HOLD_MAX_MS', () => {
    assert.ok(HOLD_MAX_MS <= 100);
    const {anchor, surface} = popup();
    const p = start(new Popups(cfg));
    p._follow(surface, anchor, 'quicksettings');
    surface.map();   // 0×0: the glass stays hidden, as if it never got placed
    assert.equal(p._followers.size, 1);
    assert.equal(surface.opacity, 0, 'held back while its glass is built');
    global.stage.emit('after-paint');                            // one frame went by
    assert.deepEqual(fake.timeouts.fireAll(), [HOLD_MAX_MS]);    // the time ran out
    laters.run();
    assert.equal(surface.opacity, 255, 'shown without its glass');
    p.destroy();
});

// The start menus of ArcMenu and Spawn share the part called 'arcmenu'.
test('the ArcMenu and Spawn start menus are the arcmenu part, other menus are not', () => {
    const menu = (...classes) => {
        const bp = new Actor();
        bp.has_style_class_name = c => classes.includes(c);
        return bp;
    };
    assert.equal(partOf(menu('arcmenu-menu')), 'arcmenu');
    assert.equal(partOf(menu('spawn-popup', 'spawn-menu-popup')), 'arcmenu');
    assert.equal(partOf(menu('spawn-popup', 'spawn-menu-popup', 'spawn-popup-above')), 'arcmenu');
    // Spawn's runner, power and context menus are app menus, like any other pop-up.
    assert.equal(partOf(menu('spawn-popup')), 'quicksettings');
    assert.equal(partOf(menu('spawn-popup', 'spawn-power-popup')), 'quicksettings');
    assert.equal(partOf(menu('spawn-context-menu')), 'quicksettings');
    assert.equal(partOf(menu()), 'quicksettings');
});

// ---- Dash to Panel's window previews and the Shell's dialogs ---------------------------
function styled(...classes) {
    const a = new Actor();
    a.has_style_class_name = c => classes.includes(c);
    a._style = null;
    a.get_style = () => a._style;
    a.set_style = st => {
        a._style = st;
        a.emit('notify::style');
    };
    return a;
}

// Dash to Panel's PreviewMenu: a full-width, clipped strip holding the box people see.
function previewMenu() {
    const strip = new Actor();
    strip.requestPeek = () => {};
    const box = styled();
    strip.menu = box;
    strip.add_child(box);
    fake.ui.add_child(strip);
    return {strip, box};
}

// A GNOME ModalDialog: the dimmed backdrop, then a bin holding the dialog's box.
function modalDialog() {
    const dialog = new Actor();
    const lightbox = new Actor();
    const bin = new Actor();
    const layout = new Actor();
    const box = styled('modal-dialog');
    dialog.add_child(lightbox);
    dialog.add_child(bin);
    bin.add_child(layout);
    layout.add_child(box);
    layout._dialog = box;
    dialog.dialogLayout = layout;
    dialog.contains = a => {
        for (let x = a; x; x = x.get_parent())
            if (x === dialog)
                return true;
        return false;
    };
    return {dialog, lightbox, bin, box};
}

test('window previews and dialogs are recognised, other actors are not', () => {
    const {strip, box} = previewMenu();
    assert.equal(previewBox(strip), box);
    assert.equal(previewBox(new Actor()), null);
    assert.equal(previewBox(Object.assign(new Actor(), {menu: new Actor()})), null, 'a menu field alone is not enough');
    const d = modalDialog();
    assert.equal(dialogBox(d.dialog), d.box);
    assert.equal(dialogBox(new Actor()), null);
    d.dialog.dialogLayout._dialog = styled('something-else');
    assert.equal(dialogBox(d.dialog), null, 'only a .modal-dialog box');
});

test('a window preview that fades in by itself gets glass inside its clipped strip', () => {
    const {strip, box} = previewMenu();
    const p = start(new Popups(cfg));
    p._consider(strip);
    box.opacity = 0;          // Dash to Panel maps it invisible and eases it in
    box.map();
    const f = p._followers.get(box);
    assert.ok(f, 'the preview has glass');
    assert.equal(f._held, null, 'not held back: holding a 0-opacity pop-up never let go');
    assert.equal(box.opacity, 0, 'its own fade is left alone');
    assert.deepEqual(strip.get_children().slice(0, 2), [f.pane, f.top], 'the panes sit under the box, inside the strip');
    p.destroy();
    assert.deepEqual(strip.get_children(), [box], 'turning off takes the panes away');
});

test('a dialog gets glass between its dimmed backdrop and its box', () => {
    const d = modalDialog();
    const p = start(new Popups(cfg));
    p._dialog(d.dialog);
    d.box.map();
    const f = p._followers.get(d.box);
    assert.ok(f, 'the dialog has glass');
    assert.equal(f.anchor, d.bin);
    assert.deepEqual(d.dialog.get_children(), [d.lightbox, f.pane, f.top, d.bin]);
    p.destroy();
    assert.deepEqual(d.dialog.get_children(), [d.lightbox, d.bin]);
});

test('preview title strips get the pop-up tint, and their own style back when turned off', () => {
    assert.equal(seeThrough('padding: 4px;background-color: rgba(29,30,36,1); transition-duration:0.3s;', 0.28),
        'padding: 4px;background-color: rgba(29,30,36,0.280); transition-duration:0.3s;');
    assert.equal(seeThrough('background-color: rgba(29,30,36,0.6);', 0.28), 'background-color: rgba(29,30,36,0.6);',
        'colours that are already see-through stay');
    assert.equal(seeThrough(null, 0.3), null);
    assert.equal(tintOf('background: rgba(41,42,48,0.28); '), 0.28);
    assert.equal(tintOf('background: rgba(41,42,48,1); '), null);
    assert.equal(tintOf(null), null);

    const {strip, box} = previewMenu();
    box.set_style('background: rgba(41,42,48,0.28); ');
    const list = new Actor();
    box.add_child(list);
    const tint = new PreviewTint(box);
    // A preview made later, as the pointer moves to another app.
    const preview = new Actor();
    const header = styled('preview-header-box');
    const own = 'background-color: rgba(29,30,36,1); transition-duration:0.3s;';
    header.set_style(own);
    preview.add_child(header);
    list.add_child(preview);
    list.emit('child-added', preview);
    assert.equal(header.get_style(), 'background-color: rgba(29,30,36,0.280); transition-duration:0.3s;');
    header.set_style(own);    // Dash to Panel styles it again
    assert.equal(header.get_style(), 'background-color: rgba(29,30,36,0.280); transition-duration:0.3s;');
    tint.destroy();
    assert.equal(header.get_style(), own, 'Dash to Panel\'s own style is back');
    assert.equal(header.handlerCount(), 0);
    assert.equal(list.handlerCount(), 0);
    strip.destroy();
});
