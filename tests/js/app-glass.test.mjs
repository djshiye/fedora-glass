// Per-app glass strength: shell-glass.json windows.appGlass (id -> 'solid' or 'clearer')
// and windows.appLooks (those two looks, as overrides on the windows' look). config.js
// keeps only clean entries; windows.js picks the look by any of a window's ids, whatever
// their case, with the no-glass list first, then the app's own strength, then the
// terminals' look, then the windows' look.
import assert from 'node:assert/strict';
import {test} from 'node:test';

class Actor {
    connect() { return 1; }
    disconnect() {}
}
globalThis.fake = {Actor, ui: new Actor(), overview: {visible: false}};
globalThis.global = {workspace_manager: {get_active_workspace: () => ({})}, get_window_actors: () => []};

const {lookFor, windowKind} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/windows.js');
const {parse, cleanAppGlass, cleanAppLooks} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/config.js');

const FILE = {windows: {
    look: {blur: 24, refraction: 14},
    terminalLook: {blur: 20},
    skip: ['Steam', 'org.gimp.GIMP'], solidFrom: 1,
    appGlass: {'org.gnome.Nautilus': 'solid', 'org.gnome.Ptyxis': 'clearer', 'org.gimp.GIMP': 'solid'},
    appLooks: {solid: {blur: 40, ceiling: 0.18, haze: 0.35}, clearer: {blur: 16, refraction: 18}},
}};

test('config.js reads the per-app strengths in lower case and both looks over the windows look', () => {
    const w = parse(JSON.stringify(FILE)).windows;
    assert.ok(w.appGlass instanceof Map);
    assert.equal(w.appGlass.get('org.gnome.nautilus'), 'solid');
    assert.equal(w.appGlass.get('org.gnome.ptyxis'), 'clearer');
    assert.equal(w.appLooks.solid.blur, 40);
    assert.equal(w.appLooks.solid.haze, 0.35);
    assert.equal(w.appLooks.solid.refraction, 14, 'what a look leaves out is the windows look');
    assert.equal(w.appLooks.clearer.refraction, 18);
});

test('a file without them: no app has its own strength, and both looks are the windows look', () => {
    const w = parse(JSON.stringify({windows: {look: {blur: 30}}})).windows;
    assert.equal(w.appGlass.size, 0);
    assert.equal(w.appLooks.solid, w.look);
    assert.equal(w.appLooks.clearer, w.look);
    assert.equal(parse('not json').windows.appGlass.size, 0);
});

test('config.js drops anything that is not a short id with a known strength', () => {
    const m = cleanAppGlass({'': 'solid', ['x'.repeat(200)]: 'solid', ok: 'normal', bad: 7, also: null,
        Good: 'clearer', good: 'solid', __proto__x: 'solid', constructor: 'solid'});
    assert.deepEqual([...m], [['good', 'clearer'], ['__proto__x', 'solid'], ['constructor', 'solid']],
        'the first of two ids that differ only in case wins; odd names are just ids');
    assert.equal(cleanAppGlass(['solid']).size, 0);
    assert.equal(cleanAppGlass('solid').size, 0);
    assert.equal(cleanAppGlass(null).size, 0);
    // At most 200, like the no-glass list.
    const many = Object.fromEntries(Array.from({length: 500}, (_, i) => [`app${i}`, 'solid']));
    assert.equal(cleanAppGlass(many).size, 200);
});

test('config.js checks each value of the two looks like any look', () => {
    const b = {...parse('{}').windows.look, haze: 0.1};
    const looks = cleanAppLooks({solid: {blur: 900, ceiling: -3, haze: 'lots', lift: 0.8}, clearer: [1, 2]}, b);
    assert.equal(looks.solid.blur, 100, 'clamped');
    assert.equal(looks.solid.ceiling, 0);
    assert.equal(looks.solid.haze, 0.1, 'not a number: the windows look');
    assert.equal(looks.solid.lift, 0.8);
    assert.equal(looks.clearer, b, 'not a look: the windows look');
});

test('the look picked: the app own strength, by any id and any case, before the terminal look', () => {
    const w = parse(JSON.stringify(FILE)).windows;
    assert.equal(lookFor(['org.gnome.Nautilus'], w), w.appLooks.solid);
    assert.equal(lookFor(['nautilus', 'ORG.GNOME.NAUTILUS'], w), w.appLooks.solid, 'any id, any case');
    // Ptyxis is a terminal with its own look, but the user picked Clearer for it.
    assert.equal(lookFor(['org.gnome.Ptyxis'], w), w.appLooks.clearer);
    // Another terminal keeps the terminal look; any other app the windows look.
    assert.equal(lookFor(['org.gnome.Console'], w), w.terminalLook);
    assert.equal(lookFor(['org.gnome.TextEditor'], w), w.look);
    assert.equal(lookFor([], w), w.look);
});

test('the no-glass list goes first: a listed app has no glass whatever strength it has', () => {
    const w = parse(JSON.stringify(FILE)).windows;
    assert.equal(windowKind(['org.gimp.GIMP'], w.skip, w.solid), 'solid', 'a plain solid backdrop, no glass');
    assert.equal(windowKind(['org.gnome.Nautilus'], w.skip, w.solid), 'glass');
});

test('old settings objects without the new keys still pick a look', () => {
    const look = {blur: 1}, terminalLook = {blur: 2};
    assert.equal(lookFor(['org.gnome.Ptyxis'], {look, terminalLook}), terminalLook);
    assert.equal(lookFor(['a'], {look, appGlass: new Map([['a', 'solid']])}), look, 'no looks: the windows look');
    assert.equal(lookFor(['a'], {look, appGlass: {a: 'solid'}, appLooks: {solid: {}}}), look, 'not a Map: ignored');
});
