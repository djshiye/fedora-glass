// Frameless Qt apps (RGBeast, Wheelguard) draw a rounded card inside a clear shadow
// margin that Mutter counts as window: their glass goes on the card, not on the margin.
import assert from 'node:assert/strict';
import {test} from 'node:test';

class Actor {
    connect() { return 1; }
    disconnect() {}
}
globalThis.fake = {Actor, ui: new Actor(), overview: {visible: false}};
globalThis.global = {workspace_manager: {get_active_workspace: () => ({})}, get_window_actors: () => []};

const {clientCard, glassFrame} = await import(
    '../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/windows.js');

const frame = {x: 100, y: 50, width: 1148, height: 828};

test('RGBeast and Wheelguard are known by the ids the Shell sees', () => {
    for (const id of ['io.github.djshiye.RGBeast', 'rgbeast', 'RGBeast'])
        assert.deepEqual(clientCard([id]), {app: clientCard([id]).app, margin: 14, radius: 15});
    for (const id of ['io.github.djshiye.Wheelguard', 'wheelguard-settings'])
        assert.equal(clientCard([id]).radius, 18);
    for (const id of ['org.gnome.Nautilus', 'io.github.djshiye.RGBeastly', 'ptyxis', 'io.github.djshiye.LiquidGlass'])
        assert.equal(clientCard([id]), null);
});

test('the glass sits on the card, inside the shadow margin, with its corners', () => {
    const g = glassFrame(frame, clientCard(['io.github.djshiye.RGBeast']), false);
    assert.deepEqual(g.rect, {x: 114, y: 64, width: 1120, height: 800});
    assert.equal(g.radius, 15);
});

test('other windows, and a maximized card app, keep their whole frame and usual corners', () => {
    assert.deepEqual(glassFrame(frame, null, false), {rect: frame, radius: null});
    assert.deepEqual(glassFrame(frame, clientCard(['rgbeast']), true), {rect: frame, radius: null});
    // Too small to hold a card: never a negative size.
    const tiny = {x: 0, y: 0, width: 20, height: 20};
    assert.deepEqual(glassFrame(tiny, clientCard(['rgbeast']), false).rect, tiny);
});
