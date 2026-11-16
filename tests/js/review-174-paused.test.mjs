// 1.7.4 review, X6: while the glass is paused, Dash to Panel switched off and on by hand is a
// new object with new panels; PausedStyle lifts them again when GNOME says it is ACTIVE.
import assert from 'node:assert/strict';
import {test} from 'node:test';

class Signals {
    constructor() { this.handlers = new Map(); this.next = 1; }
    connect(sig, fn) { const id = this.next++; this.handlers.set(id, [sig, fn]); return id; }
    disconnect(id) { this.handlers.delete(id); }
    emit(sig, ...a) { for (const [s, fn] of [...this.handlers.values()]) if (s === sig) fn(this, ...a); }
}
class FakeTransparency {
    constructor(opacity) { this.opacity = opacity; this.styles = []; this._updateAlphaAndSet(); }
    _updateAlpha() { this.alpha = this.opacity; }
    _updateAlphaAndSet() { this._updateAlpha(); this.styles.push(this.alpha); }
}
class Theme {
    get_custom_stylesheets() { return []; }
    load_stylesheet() {}
    unload_stylesheet() {}
}
const manager = new Signals();
globalThis.global = {stage: {}};
globalThis.fake = {fs: new Map(), Actor: class {}, Widget: class {}, extensionManager: manager,
    themeContext: {get_theme: () => new Theme(), connect: () => 1, disconnect() {}},
    timeouts: {add: () => 1, remove() {}}};
const DIR = '../../fedoraglass/data/extension/liquid-glass@djshiye.github.io';
const {PausedStyle} = await import(`${DIR}/paused.js`);
const DTP = 'dash-to-panel@jderose9.github.com';

test('Dash to Panel switched off and on while paused: the new panels are lifted at once', () => {
    const old = new FakeTransparency(0.29);
    global.dashToPanel = Object.assign(new Signals(), {panels: [{dynamicTransparency: old}]});
    const p = new PausedStyle({pausedCss: '', pausedAlpha: 0.96});
    assert.equal(old.alpha, 0.96);
    // Off, then on: a new object with new panels, announced only through the manager.
    const fresh = new FakeTransparency(0.29);
    global.dashToPanel = Object.assign(new Signals(), {panels: [{dynamicTransparency: fresh}]});
    manager.emit('extension-state-changed', {uuid: 'other@x', state: 1});
    assert.equal(fresh.alpha, 0.29, 'another extension is none of its business');
    manager.emit('extension-state-changed', {uuid: DTP, state: 2});
    assert.equal(fresh.alpha, 0.29, 'not before it is ACTIVE');
    manager.emit('extension-state-changed', {uuid: DTP, state: 1});
    assert.equal(fresh.alpha, 0.96);
    p.destroy();
    assert.equal(manager.handlers.size, 0, 'the listener goes with it');
    assert.equal(fresh.alpha, 0.29);
});
