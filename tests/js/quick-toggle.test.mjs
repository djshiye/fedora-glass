// The "Glass" tile in Quick Settings (quicktoggle.js): GNOME's own QuickToggle in a
// SystemIndicator handed to Quick Settings, "Paused" under it while the glass is paused,
// and gone again without a trace.
import assert from 'node:assert/strict';
import {test, beforeEach} from 'node:test';

class Emitter {
    constructor() { this._h = new Map(); this._n = 1; }
    connect(sig, fn) { const id = this._n++; this._h.set(id, [sig, fn]); return id; }
    disconnect(id) { this._h.delete(id); }
    emit(sig, ...a) { for (const [s, fn] of [...this._h.values()]) if (s === sig) fn(this, ...a); }
    get count() { return this._h.size; }
}

const made = [];
class QuickToggle extends Emitter {
    constructor(p) {
        super();
        Object.assign(this, {checked: false, subtitle: null}, p);
        made.push(this);
    }
    // St.Button with toggle-mode: a click flips `checked`, then says clicked.
    click() {
        if (this.toggleMode)
            this.checked = !this.checked;
        this.emit('clicked');
    }
    destroy() { this.destroyed = true; }
}
class SystemIndicator {
    constructor() { this.quickSettingsItems = []; }
    destroy() { this.destroyed = true; }
}
const added = [];
const quickSettings = {addExternalIndicator: i => added.push(i)};
globalThis.fake = {QuickToggle, SystemIndicator, panel: {statusArea: {quickSettings}}, fs: new Map(), Actor: class {}};
globalThis.logError = () => {};
const {GlassSwitch, subtitleFor, ICON} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/quicktoggle.js');
const {parse} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/config.js');

beforeEach(() => {
    made.length = 0;
    added.length = 0;
    globalThis.fake.fs = new Map([[`/ext/${ICON}`, {text: '<svg/>'}]]);
});

test('a tile called Glass, with the extension\'s icon, added to Quick Settings the way GNOME asks', () => {
    const sw = new GlassSwitch('/ext', () => {});
    assert.equal(made.length, 1);
    const t = made[0];
    assert.equal(t.title, 'Glass');
    assert.equal(t.toggleMode, true);
    assert.equal(t.gicon.file.path, `/ext/${ICON}`);
    assert.equal(added.length, 1, 'one indicator handed to Quick Settings');
    assert.deepEqual(added[0].quickSettingsItems, [t]);
    assert.equal(t.checked, true, 'on: the glass shows');
    assert.equal(t.subtitle, null);
    sw.destroy();
});

test('without its icon file it takes a stock symbolic icon', () => {
    globalThis.fake.fs = new Map();
    const sw = new GlassSwitch('/ext', () => {});
    assert.equal(made[0].gicon, undefined);
    assert.match(made[0].iconName, /-symbolic$/);
    sw.destroy();
});

test('a click pauses, "Paused" shows under it, and a second click turns the glass on', () => {
    const asked = [];
    let sw;
    sw = new GlassSwitch('/ext', p => {
        asked.push(p);
        sw.setState(p, false);
    });
    const t = made[0];
    t.click();
    assert.deepEqual(asked, [true]);
    assert.equal(t.checked, false);
    assert.equal(t.subtitle, 'Paused');
    t.click();
    assert.deepEqual(asked, [true, false]);
    assert.equal(t.checked, true);
    assert.equal(t.subtitle, null);
    sw.destroy();
});

test('a pause that fails leaves the tile showing the truth', () => {
    const sw = new GlassSwitch('/ext', () => {
        throw new Error('forced test failure');
    });
    made[0].click();
    assert.equal(made[0].checked, true, 'still on: nothing was paused');
    sw.destroy();
});

test('safe mode: the tile stays on, and says why there is no glass', () => {
    assert.equal(subtitleFor(false, true), 'Safe mode');
    assert.equal(subtitleFor(true, true), 'Paused');
    assert.equal(subtitleFor(false, false), null);
});

test('removed: the tile, its signal and the indicator all go', () => {
    const sw = new GlassSwitch('/ext', () => {});
    const t = made[0];
    sw.destroy();
    assert.equal(t.destroyed, true);
    assert.equal(added[0].destroyed, true);
    assert.equal(t.count, 0, 'clicked handler let go');
    assert.doesNotThrow(() => sw.destroy(), 'twice is fine');
});

test('a Quick Settings without addExternalIndicator: added by hand', () => {
    const kids = [], items = [];
    globalThis.fake.panel.statusArea.quickSettings = {_indicators: {add_child: i => kids.push(i)}, _addItems: x => items.push(...x)};
    const sw = new GlassSwitch('/ext', () => {});
    assert.equal(kids.length, 1);
    assert.deepEqual(items, [made[0]]);
    sw.destroy();
    globalThis.fake.panel.statusArea.quickSettings = quickSettings;
});

test('shell-glass.json: the tile is there unless the setting says off', () => {
    assert.equal(parse('{}').quickToggle.enabled, true);
    assert.equal(parse('{"quickToggle": {"enabled": true}}').quickToggle.enabled, true);
    assert.equal(parse('{"quickToggle": {"enabled": false}}').quickToggle.enabled, false);
    assert.equal(parse('{"quickToggle": false}').quickToggle.enabled, true, 'only the setting\'s own shape turns it off');
});
