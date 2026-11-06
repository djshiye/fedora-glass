// What a menu's glass shows through. GNOME's own wallpaper actor skips whatever an
// opaque window covers, so glass copying it had a hole over each window and showed
// that window sharp (the see-through calendar at the lightest glass level). Menus and
// the panel must copy our own whole wallpaper copy instead.
import assert from 'node:assert/strict';
import {test} from 'node:test';

class Actor {
    connect() { return 1; }
    disconnect() {}
}
globalThis.fake = {Actor, ui: new Actor(), overview: {visible: false}};
const shellWallpaper = {name: 'GNOME wallpaper'};
const ourCopy = {name: 'liquid-glass-wallpaper'};
const sheet = {
    visible: true,
    meta_window: {
        get_monitor: () => 0, minimized: false, located_on_workspace: () => true,
        get_buffer_rect: () => ({x: 0, y: 0, width: 800, height: 600}),
    },
};
globalThis.global = {
    workspace_manager: {get_active_workspace: () => ({})},
    get_window_actors: () => [sheet],
};

const Main = await import('resource:///org/gnome/shell/ui/main.js');
Main.layoutManager._backgroundGroup = shellWallpaper;
Main.layoutManager.monitors = [{x: 0, y: 0, width: 1600, height: 900}];
const C = await import('../../liquidglass/data/extension/liquid-glass@djshiye.github.io/common.js');

test('lightest glass (wallpaper only) copies the whole wallpaper, never the one with holes', () => {
    C.wallpaper.current = {actor: ourCopy};
    assert.deepEqual(C.sourcesFor('wallpaper', 100, 100, 400, 300), [ourCopy]);
});

test('glass that shows windows lays them over the whole wallpaper copy', () => {
    C.wallpaper.current = {actor: ourCopy};
    assert.deepEqual(C.sourcesFor('windows', 100, 100, 400, 300), [ourCopy, sheet]);
});

test('before the copy exists, the glass still has a wallpaper', () => {
    C.wallpaper.current = null;
    assert.deepEqual(C.sourcesFor('wallpaper', 100, 100, 400, 300), [shellWallpaper]);
});
