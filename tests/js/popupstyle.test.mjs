// The pop-up stylesheet (popupstyle.js) under a fake Shell: it is written to the
// private runtime folder and loaded into the theme, follows theme reloads and new
// rules, and on the way out is unloaded before its file goes, so a theme reload
// never looks for a missing file. Unsafe CSS never gets in.
import assert from 'node:assert/strict';
import {test} from 'node:test';

class Theme {
    constructor() { this.sheets = []; this.loads = 0; }
    get_custom_stylesheets() { return this.sheets.map(s => ({path: s.path, equal(o) { return o?.path === this.path; }})); }
    load_stylesheet(f) {
        if (!globalThis.fake.fs.has(f.path)) throw new Error(`Error opening file ${f.path}`);
        this.loads++;
        this.sheets.push({path: f.path, text: globalThis.fake.fs.get(f.path).text});
        globalThis.fake.themeContext.emit();
        return true;
    }
    unload_stylesheet(f) {
        const n = this.sheets.length;
        this.sheets = this.sheets.filter(s => s.path !== f.path);
        if (n !== this.sheets.length) globalThis.fake.themeContext.emit();
    }
}

class Context {
    constructor() { this.theme = new Theme(); this.handlers = new Map(); this.next = 1; }
    get_theme() { return this.theme; }
    connect(_s, fn) { this.handlers.set(this.next, fn); return this.next++; }
    disconnect(id) { this.handlers.delete(id); }
    emit() { for (const fn of [...this.handlers.values()]) fn(); }
    // Main.loadTheme: a new theme gets the old one's custom sheets, read again from file.
    reload() {
        const next = new Theme();
        for (const s of this.theme.sheets) next.load_stylesheet({path: s.path});
        this.theme = next;
        this.emit();
    }
}

class Timeouts {
    constructor() { this.map = new Map(); this.next = 1; }
    add(ms, fn) { this.map.set(this.next, {ms, fn}); return this.next++; }
    remove(id) { this.map.delete(id); }
    fireAll() {
        const fired = [];
        for (const [id, t] of [...this.map]) {
            this.map.delete(id);
            fired.push(t.ms);
            t.fn();
        }
        return fired;
    }
}

globalThis.global = {stage: {}};
globalThis.fake = {fs: new Map(), themeContext: new Context(), Actor: class {}, Widget: class {}, timeouts: new Timeouts()};
const DIR = '../../liquidglass/data/extension/liquid-glass@djshiye.github.io';
const {PopupStyle, SETTLE_MS} = await import(`${DIR}/popupstyle.js`);
const {cleanPopupCss, POPUP_CSS_MAX} = await import(`${DIR}/config.js`);
const FILE = '/run/user/1000/fedora-glass/popups.css';
const CSS = '#uiGroup .switcher-list { background-color: rgba(0,0,0,0.3); }\n';

test('loads the rules from a private runtime file and follows changes and theme reloads', () => {
    const ctx = globalThis.fake.themeContext;
    const p = new PopupStyle({popupCss: CSS});
    assert.equal(globalThis.fake.fs.get(FILE).text, CSS);
    assert.ok(globalThis.fake.fs.get(FILE).flags & 1, 'written private to the user');
    assert.deepEqual(ctx.theme.sheets.map(s => s.text), [CSS]);

    ctx.reload();
    assert.deepEqual(ctx.theme.sheets.map(s => s.text), [CSS], 'once in the new theme, not twice');
    assert.equal(ctx.theme.loads, 1, 'GNOME copied it; loading again would restyle the screen for nothing');

    const css2 = CSS.replace('0.3', '0.4');
    p.update({popupCss: css2});
    assert.deepEqual(ctx.theme.sheets.map(s => s.text), [CSS], 'new rules wait until they settle');
    assert.deepEqual(globalThis.fake.timeouts.fireAll(), [SETTLE_MS]);
    assert.deepEqual(ctx.theme.sheets.map(s => s.text), [css2], 'new rules read again');

    p.update({popupCss: ''});
    assert.deepEqual(ctx.theme.sheets, []);
    assert.ok(!globalThis.fake.fs.has(FILE));

    p.update({popupCss: CSS});
    p.destroy();
    assert.deepEqual(ctx.theme.sheets, [], 'unloaded on the way out');
    assert.ok(!globalThis.fake.fs.has(FILE), 'and its file removed');
    assert.equal(ctx.handlers.size, 0);
    ctx.reload();   // a theme reload afterwards (Restore original) finds nothing missing
    assert.deepEqual(ctx.theme.sheets, []);
});

test('rules that change while a slider moves restyle the screen once, after they settle', () => {
    const ctx = globalThis.fake.themeContext;
    const fake = globalThis.fake;
    const p = new PopupStyle({popupCss: CSS});
    const loads0 = ctx.theme.loads;
    let restyles = 0;
    const id = ctx.connect('changed', () => restyles++);
    // A frost drag: the app sends new rules every few hundred ms.
    for (let i = 1; i <= 20; i++)
        p.update({popupCss: CSS.replace('0.3', `0.3${i}`)});
    assert.equal(restyles, 0, 'nothing restyled while the rules keep changing');
    assert.equal(fake.timeouts.map.size, 1, 'one wait, started again by each change');
    assert.deepEqual(fake.timeouts.fireAll(), [SETTLE_MS]);
    assert.deepEqual(ctx.theme.sheets.map(s => s.text), [CSS.replace('0.3', '0.320')], 'the last rules win');
    assert.equal(ctx.theme.loads, loads0 + 1);
    assert.equal(restyles, 2, 'old sheet out, new sheet in: once');

    // Back to the rules already loaded before the wait ran out: nothing to do.
    p.update({popupCss: CSS});
    p.update({popupCss: CSS.replace('0.3', '0.320')});
    assert.equal(fake.timeouts.map.size, 0);
    assert.equal(restyles, 2);

    // Turning them off is at once, and drops a wait.
    p.update({popupCss: CSS});
    p.update({popupCss: ''});
    assert.equal(fake.timeouts.map.size, 0);
    assert.deepEqual(ctx.theme.sheets, []);

    // Taken down during a wait: the wait goes too.
    p.update({popupCss: CSS});
    p.update({popupCss: CSS.replace('0.3', '0.5')});
    p.destroy();
    assert.equal(fake.timeouts.map.size, 0);
    assert.deepEqual(ctx.theme.sheets, []);
    ctx.disconnect(id);
});

test('config: only plain rules of a sane size get through', () => {
    assert.equal(cleanPopupCss(CSS), CSS);
    for (const bad of [42, null, '@import "x.css";', '.a { background-image: url(file:///etc/passwd); }',
        '.a { content: "\\41"; }', 'a'.repeat(POPUP_CSS_MAX + 1)])
        assert.equal(cleanPopupCss(bad), '');
});
