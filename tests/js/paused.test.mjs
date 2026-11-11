// The solid surfaces of a paused glass (paused.js) under a fake Shell: the sheet loads at
// once from its own private file (not popups.css), follows new rules at once (light and
// dark), and Dash to Panel's panel, which paints its colour as an inline style no sheet can
// beat, has its opacity lifted while paused and put back after.
import assert from 'node:assert/strict';
import {test} from 'node:test';

class Theme {
    constructor() { this.sheets = []; }
    get_custom_stylesheets() { return this.sheets.map(s => ({path: s.path, equal(o) { return o?.path === this.path; }})); }
    load_stylesheet(f) {
        this.sheets.push({path: f.path, text: globalThis.fake.fs.get(f.path).text});
        globalThis.fake.themeContext.emit();
    }
    unload_stylesheet(f) { this.sheets = this.sheets.filter(s => s.path !== f.path); }
}
class Context {
    constructor() { this.theme = new Theme(); this.handlers = new Map(); this.next = 1; }
    get_theme() { return this.theme; }
    connect(_s, fn) { this.handlers.set(this.next, fn); return this.next++; }
    disconnect(id) { this.handlers.delete(id); }
    emit() { for (const fn of [...this.handlers.values()]) fn(); }
}
class Timeouts {
    constructor() { this.map = new Map(); this.next = 1; }
    add(ms, fn) { this.map.set(this.next, {ms, fn}); return this.next++; }
    remove(id) { this.map.delete(id); }
    fireAll() { for (const [id, t] of [...this.map]) { this.map.delete(id); t.fn(); } }
}

// Dash to Panel's DynamicTransparency, as far as paused.js uses it: alpha from the
// trans-panel-opacity setting, then an inline background-color on the panel.
class FakeTransparency {
    constructor(opacity) { this.opacity = opacity; this.styles = []; this._updateAlphaAndSet(); }
    _updateAlpha() { this.alpha = this.opacity; }
    _updateAlphaAndSet() { this._updateAlpha(); this.styles.push(this.alpha); }
}
class FakeDtp {
    constructor(panels) { this.panels = panels; this.handlers = new Map(); this.next = 1; }
    connect(sig, fn) { this.handlers.set(this.next, {sig, fn}); return this.next++; }
    disconnect(id) { this.handlers.delete(id); }
    emit(sig) { for (const h of [...this.handlers.values()]) if (h.sig === sig) h.fn(); }
}

globalThis.global = {stage: {}};
globalThis.fake = {fs: new Map(), themeContext: new Context(), Actor: class {}, Widget: class {}, timeouts: new Timeouts()};
const DIR = '../../fedoraglass/data/extension/liquid-glass@djshiye.github.io';
const {PausedStyle, liftPanel} = await import(`${DIR}/paused.js`);
const {PopupStyle} = await import(`${DIR}/popupstyle.js`);
const {parse} = await import(`${DIR}/config.js`);
const FILE = '/run/user/1000/fedora-glass/paused.css';
const DARK = '#uiGroup #panel {\n  background-color: rgba(41,42,48,0.960) !important; }\n';
const LIGHT = '#uiGroup #panel {\n  background-color: rgba(244,245,249,0.960) !important; }\n';

test('the sheet loads at once from its own private file, follows new rules at once, and goes', () => {
    const ctx = globalThis.fake.themeContext;
    global.dashToPanel = undefined;
    const p = new PausedStyle({pausedCss: DARK, popupCss: 'not this one'});
    assert.deepEqual(ctx.theme.sheets.map(s => [s.path, s.text]), [[FILE, DARK]]);
    assert.ok(globalThis.fake.fs.get(FILE).flags & 1, 'written private to the user');
    p.update({pausedCss: LIGHT});
    assert.equal(globalThis.fake.timeouts.map.size, 0, 'no settle wait: the paused look is there at once');
    assert.deepEqual(ctx.theme.sheets.map(s => s.text), [LIGHT], 'light and dark follow the theme');
    p.destroy();
    assert.deepEqual(ctx.theme.sheets, []);
    assert.ok(!globalThis.fake.fs.has(FILE));
    assert.equal(ctx.handlers.size, 0);
});

test('the glass sheet and the paused one are separate files', () => {
    const ctx = globalThis.fake.themeContext;
    const glass = new PopupStyle({popupCss: '#uiGroup .osd-window {}\n'});
    glass.destroy();
    const p = new PausedStyle({pausedCss: DARK});
    assert.deepEqual(ctx.theme.sheets.map(s => s.path), [FILE]);
    // A late removal of the glass sheet (a lock) never takes the paused one with it.
    new PopupStyle({popupCss: '#uiGroup .osd-window {}\n'}).destroy();
    assert.deepEqual(ctx.theme.sheets.map(s => s.path), [FILE]);
    p.destroy();
});

test('at a lock it goes a moment later, with Dash to Panel\'s colour put back at once', () => {
    const ctx = globalThis.fake.themeContext;
    const dt = new FakeTransparency(0.29);
    global.dashToPanel = new FakeDtp([{dynamicTransparency: dt}]);
    const p = new PausedStyle({pausedCss: DARK, pausedAlpha: 0.96});
    let gone = 0;
    p.destroyLater(() => gone++);
    assert.equal(dt.styles.at(-1), 0.29);
    assert.deepEqual(ctx.theme.sheets.map(s => s.text), [DARK]);
    globalThis.fake.timeouts.fireAll();
    assert.deepEqual(ctx.theme.sheets, []);
    assert.equal(gone, 1);
});

test('Dash to Panel: the panel is lifted to pausedAlpha, new panels too, and put back after', () => {
    const a = new FakeTransparency(0.29);
    const solid = new FakeTransparency(1.0);
    const dtp = new FakeDtp([{dynamicTransparency: a}, {dynamicTransparency: solid}, {}]);
    global.dashToPanel = dtp;
    const p = new PausedStyle({pausedCss: DARK, pausedAlpha: 0.96});
    assert.equal(a.alpha, 0.96, 'set at once');
    assert.equal(solid.alpha, 1.0, 'a panel more solid already stays so');
    a._updateAlphaAndSet();   // Dash to Panel works it out again (overview, settings, theme)
    assert.equal(a.alpha, 0.96, 'and stays lifted');
    // A second monitor: Dash to Panel builds its panels again.
    const b = new FakeTransparency(0.29);
    dtp.panels = [{dynamicTransparency: a}, {dynamicTransparency: b}];
    dtp.emit('panels-created');
    assert.equal(b.alpha, 0.96);
    p.destroy();
    assert.equal(a.alpha, 0.29, 'its own opacity again');
    assert.equal(b.alpha, 0.29);
    assert.ok(!Object.hasOwn(a, '_updateAlpha'), 'the wrap is gone');
    assert.equal(dtp.handlers.size, 0);
    a._updateAlphaAndSet();
    assert.equal(a.alpha, 0.29);
});

test('Dash to Panel: unknown shapes are left alone, a wrap on top of ours is kept', () => {
    assert.equal(liftPanel({}, 0.96), null);
    assert.equal(liftPanel(null, 0.96), null);
    const dt = new FakeTransparency(0.3);
    const warned = [];
    const undo = liftPanel(dt, 0.96, m => warned.push(m));
    const ours = dt._updateAlpha;
    dt._updateAlpha = function () { ours.call(this); this.alpha -= 0.01; };   // someone else's
    undo();
    assert.equal(warned.length, 1);
    assert.equal(dt.alpha, 0.29, 'ours under theirs is inert');
});

test('config: pausedCss goes through the pop-up checks; pausedAlpha is clamped', () => {
    const cfg = parse(JSON.stringify({pausedCss: DARK, pausedAlpha: 0.9}));
    assert.equal(cfg.pausedCss, DARK);
    assert.equal(cfg.pausedAlpha, 0.9);
    assert.equal(parse(JSON.stringify({pausedCss: '@import "x.css";'})).pausedCss, '');
    assert.equal(parse(JSON.stringify({pausedAlpha: 7})).pausedAlpha, 1);
    assert.equal(parse('{}').pausedAlpha, 0.96);
    assert.equal(parse('{}').pausedCss, '');
});
