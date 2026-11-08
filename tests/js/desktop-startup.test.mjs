// Overview off (desktop.js): while GNOME is still starting, the overview on screen is
// GNOME's startup animation. Closing it then left GNOME waiting for good, so the second
// screen kept no wallpaper. It must be closed only once start-up has finished.
import assert from 'node:assert/strict';
import {test, beforeEach} from 'node:test';

class Signals {
    constructor() { this.handlers = new Map(); this.next = 1; }
    connect(sig, fn) { const id = this.next++; this.handlers.set(id, [sig, fn]); return id; }
    disconnect(id) { this.handlers.delete(id); }
    emit(sig) { for (const [s, fn] of [...this.handlers.values()]) if (s === sig) fn(); }
    count(sig) { return [...this.handlers.values()].filter(([s]) => s === sig).length; }
}

const overview = {
    visible: false, hides: 0,
    show() { this.visible = true; },
    hide() { this.hides++; this.visible = false; },
};
const sessionMode = {hasOverview: true};
const extensionManager = {lookup: () => ({state: 1})};
globalThis.fake = {ui: {}, overview, sessionMode, extensionManager};
globalThis.global = {settings: {get_strv: () => ['dash-to-panel@jderose9.github.com', 'arcmenu@arcmenu.com']}};

const Main = await import('resource:///org/gnome/shell/ui/main.js');
const lm = Main.layoutManager;
Object.assign(lm, new Signals());
for (const k of ['connect', 'disconnect', 'emit', 'count'])
    lm[k] = Signals.prototype[k].bind(lm);
const {DesktopBehaviour} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/desktop.js');

const CFG = {desktop: {overviewOff: true, startOnDesktop: true}};

beforeEach(() => {
    lm.handlers.clear();
    lm._startingUp = false;
    overview.visible = false;
    overview.hides = 0;
    delete overview.show;     // drop any patch left by a previous test
});

test('during start-up the startup overview is left alone until start-up finishes', () => {
    lm._startingUp = true;
    overview.visible = true;          // GNOME's startup animation is running
    const d = new DesktopBehaviour(CFG);
    assert.equal(overview.hides, 0, 'closed the overview while GNOME was still starting');
    lm._startingUp = false;
    lm.emit('startup-complete');
    assert.equal(overview.visible, false, 'the overview stayed open after start-up');
    assert.equal(lm.count('startup-complete'), 0, 'left a start-up handler connected');
    d.destroy();
});

test('after start-up an open overview is closed at once', () => {
    overview.visible = true;
    const d = new DesktopBehaviour({desktop: {overviewOff: true, startOnDesktop: false}});
    assert.equal(overview.hides, 1);
    d.destroy();
});

test('turning Fedora Glass off during start-up leaves no handler behind', () => {
    lm._startingUp = true;
    overview.visible = true;
    const d = new DesktopBehaviour({desktop: {overviewOff: true, startOnDesktop: false}});
    d.destroy();
    assert.equal(lm.count('startup-complete'), 0);
    lm.emit('startup-complete');
    assert.equal(overview.hides, 0, 'closed the overview after Fedora Glass was turned off');
});

// With the overview off, the app grid stays reachable only while no start menu (ArcMenu, Spawn) is running.
for (const [name, uuid] of [['ArcMenu', 'arcmenu@arcmenu.com'], ['Spawn', 'spawn@djshiye.github.io']]) {
    test(`${name} running counts as a way to start apps: the app grid stays closed`, () => {
        const was = extensionManager.lookup;
        let shown = 0;
        overview.show = () => { shown++; };
        extensionManager.lookup = id => ({state: id === uuid ? 1 : 2});
        const d = new DesktopBehaviour(CFG);
        overview.show(2);                       // ControlsState.APP_GRID
        assert.equal(shown, 0, `the app grid opened with ${name} running`);
        extensionManager.lookup = () => ({state: 2});
        overview.show(2);
        assert.equal(shown, 1, 'no start menu running: the app grid must open');
        d.destroy();
        extensionManager.lookup = was;
    });
}

test('locking the screen never brings Activities back onto the lock screen', () => {
    const activities = {visible: true, show() { this.visible = true; }, hide() { this.visible = false; }};
    Main.panel.statusArea.activities = {container: activities};
    try {
        const d = new DesktopBehaviour(CFG);
        assert.equal(activities.visible, false, 'Activities shows with the overview off');
        // Locking: GNOME's panel hides every button the lock screen has no use for, then
        // Fedora Glass stops its desktop part.
        sessionMode.isLocked = true;
        activities.hide();
        d.destroy();
        assert.equal(activities.visible, false, 'Activities came back on the lock screen');
        // Unlocking: GNOME's panel shows it again, Fedora Glass hides it again, and when
        // Fedora Glass is turned off normally it comes back.
        sessionMode.isLocked = false;
        activities.show();
        const d2 = new DesktopBehaviour(CFG);
        d2.destroy();
        assert.equal(activities.visible, true);
    } finally {
        delete Main.panel.statusArea.activities;
        delete sessionMode.isLocked;
    }
});
