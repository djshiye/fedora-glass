// The focused window's glass copies only the windows behind it that can be seen:
// windows hidden behind opaque windows nearer the top are left out (1.5.17 copied all
// of them, and a drag over 20 windows took five times as long a frame).
import assert from 'node:assert/strict';
import {test} from 'node:test';

class Actor {
    connect() { return 1; }
    disconnect() {}
}
globalThis.fake = {Actor, ui: new Actor(), overview: {visible: false}};
globalThis.global = {workspace_manager: {get_active_workspace: () => ({})}, get_window_actors: () => []};

const {visibleOnly} = await import(
    '../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/windows.js');

const rect = (x, y, width, height) => ({x, y, width, height});
const glass = rect(100, 100, 1000, 700);
const wall = {actor: 'wallpaper', need: glass, solid: []};

test('a window wholly behind a maximized one is left out, and so is the wallpaper', () => {
    const below = {actor: 'below', need: rect(200, 200, 600, 400), solid: [rect(200, 200, 600, 400)]};
    const max = {actor: 'max', need: rect(0, 0, 2560, 1440), solid: [rect(0, 0, 2560, 1440)]};
    assert.deepEqual(visibleOnly([wall, below, max], ...Object.values(glass)), ['max']);
});

test('a window that shows past the ones above it is kept, bottom first', () => {
    const left = {actor: 'left', need: rect(0, 0, 500, 1440), solid: [rect(0, 0, 500, 1440)]};
    const right = {actor: 'right', need: rect(500, 0, 2060, 1440), solid: [rect(500, 0, 2060, 1440)]};
    const peeks = {actor: 'peeks', need: rect(150, 150, 300, 300), solid: [rect(150, 150, 300, 300)]};
    // "peeks" lies under "left" only: hidden. Where the two meet, a grid cell lies on
    // both and wholly in neither, so the wallpaper stays (one copy too many, never one too few).
    assert.deepEqual(visibleOnly([wall, peeks, left, right], ...Object.values(glass)), ['wallpaper', 'left', 'right']);
    // Above "left" it shows.
    assert.deepEqual(visibleOnly([wall, left, peeks, right], ...Object.values(glass)), ['wallpaper', 'left', 'peeks', 'right']);
});

test('see-through windows and rounded corners hide nothing', () => {
    const under = {actor: 'under', need: rect(300, 300, 400, 300), solid: [rect(300, 300, 400, 300)]};
    const clear = {actor: 'clear', need: rect(0, 0, 2560, 1440), solid: []};
    assert.deepEqual(visibleOnly([wall, under, clear], ...Object.values(glass)), ['wallpaper', 'under', 'clear']);
    // A floating window over the whole glass, but with corners: the corners still show what is under them.
    const r = 12, f = rect(90, 90, 1020, 720);
    const round = {actor: 'round', need: f, solid: [rect(f.x + r, f.y, f.width - 2 * r, f.height), rect(f.x, f.y + r, f.width, f.height - 2 * r)]};
    const corner = {actor: 'corner', need: rect(60, 60, 60, 60), solid: [rect(60, 60, 60, 60)]};
    assert.deepEqual(visibleOnly([wall, corner, round], ...Object.values(glass)), ['wallpaper', 'corner', 'round']);
});

test('a window\'s shadow counts: one covered but for its shadow is kept', () => {
    const top = {actor: 'top', need: rect(100, 100, 1000, 700), solid: [rect(100, 100, 1000, 700)]};
    // Its frame is under "top", but its buffer (with the shadow) reaches out past the glass's left edge cell.
    const shadowed = {actor: 'shadowed', need: rect(50, 150, 400, 300), solid: [rect(150, 150, 300, 300)]};
    const out = visibleOnly([wall, shadowed, top], 40, 100, 1060, 700);
    assert.ok(out.includes('shadowed'));
});
