// Apps without glass: the user's list (shell-glass.json windows.skip, written by the app)
// keeps glass off those apps' windows, matched by any id the window carries; the built-in
// games and video players stay without glass whatever the list says; config.js keeps at
// most 200 ids of under 200 characters.
import assert from 'node:assert/strict';
import {test} from 'node:test';

class Actor {
    connect() { return 1; }
    disconnect() {}
}
globalThis.fake = {Actor, ui: new Actor(), overview: {visible: false}};
globalThis.global = {workspace_manager: {get_active_workspace: () => ({})}, get_window_actors: () => []};

const {appIds, withoutGlass} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/windows.js');
const {parse} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/config.js');

// What appIds() gives for a few real windows: wm_class, wm_class_instance, gtk_application_id, sandboxed_app_id.
const NAUTILUS = ['org.gnome.Nautilus', 'org.gnome.Nautilus', 'org.gnome.Nautilus'];
const CODE = ['Code', 'code'];
const FLATPAK_GIMP = ['Gimp-2.99', 'gimp', 'org.gimp.GIMP'];

test('a listed app gets no glass, by its desktop id, WM class or Flatpak id', () => {
    const skip = parse(JSON.stringify({windows: {skip: ['org.gnome.Nautilus', 'org.gimp.GIMP']}})).windows.skip;
    assert.equal(withoutGlass(NAUTILUS, skip), true);
    assert.equal(withoutGlass(FLATPAK_GIMP, skip), true, 'the sandboxed app id matches');
    assert.equal(withoutGlass(['org.gnome.Ptyxis'], skip), false, 'apps not listed keep their glass');
});

test('matching is whole ids: a listed id never takes glass off a different app', () => {
    const skip = ['org.gnome'];
    assert.equal(withoutGlass(NAUTILUS, skip), false);
    assert.equal(withoutGlass(['org.gnome.Nautilus2'], ['org.gnome.Nautilus']), false);
});

test('case does not matter: a StartupWMClass of Gimp matches a window of class gimp', () => {
    assert.equal(withoutGlass(['gimp'], ['Gimp']), true);
    assert.equal(withoutGlass(['Org.Gnome.Nautilus'], ['org.gnome.Nautilus']), true);
    const skip = ['MyApp'];
    assert.equal(withoutGlass(['myapp'], skip), true, 'again with the same list (worked out once)');
});

test('the desktop id GNOME matched the window to counts, without ".desktop"', () => {
    const win = {get_wm_class: () => 'jetbrains-idea', get_wm_class_instance: () => 'jetbrains-idea',
        get_gtk_application_id: () => null, get_sandboxed_app_id: () => null};
    globalThis.fake.windowTracker = {get_window_app: w => (w === win ? {get_id: () => 'com.jetbrains.IntelliJ-IDEA.desktop'} : null)};
    try {
        const ids = appIds(win);
        assert.deepEqual(ids, ['jetbrains-idea', 'jetbrains-idea', 'com.jetbrains.IntelliJ-IDEA']);
        assert.equal(withoutGlass(ids, ['com.jetbrains.IntelliJ-IDEA']), true);
        // No app known, or the tracker failing: the window's own ids still count.
        globalThis.fake.windowTracker = {get_window_app: () => null};
        assert.deepEqual(appIds(win), ['jetbrains-idea', 'jetbrains-idea']);
        globalThis.fake.windowTracker = {get_window_app: () => { throw new Error('forced'); }};
        assert.deepEqual(appIds(win), ['jetbrains-idea', 'jetbrains-idea']);
    } finally {
        delete globalThis.fake.windowTracker;
    }
});

test('the built-in games and video players stay without glass with an empty list', () => {
    for (const ids of [['steam_app_1145360'], ['mpv'], ['org.gnome.Showtime'], ['com.github.rafostar.Clapper'], ['vlc']])
        assert.equal(withoutGlass(ids, []), true, ids[0]);
    assert.equal(withoutGlass(CODE, []), false, 'Code is in the app\'s built-in list, which comes in skip');
    assert.equal(withoutGlass(['io.github.djshiye.LiquidGlass'], []), true, 'Fedora Glass draws its own');
});

test('config.js keeps at most 200 ids, each under 200 characters, strings only', () => {
    const many = Array.from({length: 250}, (_, i) => `app.${i}`);
    let skip = parse(JSON.stringify({windows: {skip: many}})).windows.skip;
    assert.equal(skip.length, 200);
    assert.deepEqual(skip.slice(0, 2), ['app.0', 'app.1'], 'the first ones (the built-in ones come first)');
    skip = parse(JSON.stringify({windows: {skip: ['a'.repeat(199), 'b'.repeat(200), 7, null, {x: 1}, 'ok']}})).windows.skip;
    assert.deepEqual(skip, ['a'.repeat(199), 'ok']);
    assert.deepEqual(parse(JSON.stringify({windows: {skip: 'org.gnome.Nautilus'}})).windows.skip, [], 'not a list: none');
});
