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

globalThis.global = {stage: {}};
globalThis.fake = {fs: new Map(), themeContext: new Context(), Actor: class {}, Widget: class {}};
const DIR = '../../liquidglass/data/extension/liquid-glass@djshiye.github.io';
const {PopupStyle} = await import(`${DIR}/popupstyle.js`);
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

test('config: only plain rules of a sane size get through', () => {
    assert.equal(cleanPopupCss(CSS), CSS);
    for (const bad of [42, null, '@import "x.css";', '.a { background-image: url(file:///etc/passwd); }',
        '.a { content: "\\41"; }', 'a'.repeat(POPUP_CSS_MAX + 1)])
        assert.equal(cleanPopupCss(bad), '');
});
