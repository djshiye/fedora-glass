// A terminal's own strength (Clearer / Solid) is made from the terminals' look, not the windows'.
import assert from 'node:assert/strict';
import {test} from 'node:test';

class Actor {
    connect() { return 1; }
    disconnect() {}
}
globalThis.fake = {Actor, ui: new Actor(), overview: {visible: false}};
globalThis.global = {workspace_manager: {get_active_workspace: () => ({})}, get_window_actors: () => []};

const {lookFor} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/windows.js');
const {parse} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/config.js');

const FILE = {windows: {
    look: {blur: 90, refraction: 14},
    terminalLook: {blur: 30, refraction: 14},
    appGlass: {'org.gnome.Ptyxis': 'clearer', 'org.gnome.Nautilus': 'clearer'},
    appLooks: {solid: {blur: 100}, clearer: {blur: 58}},
    terminalAppLooks: {solid: {blur: 40}, clearer: {blur: 20}},
}};

test('a terminal picks the variants made from the terminals look, other apps the windows ones', () => {
    const w = parse(JSON.stringify(FILE)).windows;
    assert.equal(lookFor(['org.gnome.Ptyxis'], w).blur, 20);
    assert.ok(lookFor(['org.gnome.Ptyxis'], w).blur <= w.terminalLook.blur, 'clearer than its own look');
    assert.equal(lookFor(['org.gnome.Nautilus'], w).blur, 58);
});

test('without terminalAppLooks (an older file) a terminal keeps the windows variants', () => {
    const f = {windows: {...FILE.windows, terminalAppLooks: undefined}};
    const w = parse(JSON.stringify(f)).windows;
    assert.equal(w.terminalAppLooks, null);
    assert.equal(lookFor(['org.gnome.Ptyxis'], w).blur, 58);
    assert.equal(parse(JSON.stringify({windows: {...FILE.windows, terminalLook: null}})).windows.terminalAppLooks, null);
});
