// Settings sweep (gcsweep.js): the Gio.Settings that switched-off extensions leave behind are
// collected at once, at a moment the Fedora Glass app is waiting for GNOME, never left for
// GJS's own collection that can land while the app writes settings (GJS + GLib deadlock:
// the Shell froze for good). The rule: another extension switched off or failed -> one
// collection at high priority (before GNOME answers the app's next state question); this
// extension starting -> one collection; this extension switched off -> one collection right
// then, as its very last step.
import assert from 'node:assert/strict';
import {test, beforeEach} from 'node:test';

class Idles {
    constructor() { this.next = 1; this.due = new Map(); }
    add(_ms, fn, priority) { const id = this.next++; this.due.set(id, {fn, priority}); return id; }
    remove(id) { this.due.delete(id); }
    run() {
        for (const [id, {fn}] of [...this.due]) {
            this.due.delete(id);
            if (fn())
                this.due.set(id, {fn});
        }
    }
    get priorities() { return [...this.due.values()].map(d => d.priority); }
}

class Manager {
    constructor() { this.handlers = new Map(); this.n = 1; }
    connect(sig, fn) { assert.equal(sig, 'extension-state-changed'); const id = this.n++; this.handlers.set(id, fn); return id; }
    disconnect(id) { this.handlers.delete(id); }
    change(uuid, state) { for (const fn of [...this.handlers.values()]) fn(this, {uuid, state}); }
}

const OWN = 'liquid-glass@djshiye.github.io';
const idles = new Idles();
const manager = new Manager();
let gcs = 0;
globalThis.fake = {timeouts: idles, extensionManager: manager, gc: () => gcs++};
const realWarn = console.warn;
const {SettingsSweep, collect} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/gcsweep.js');

beforeEach(() => {
    idles.due.clear();
    manager.handlers.clear();
    gcs = 0;
    console.warn = realWarn;
});

test('starting collects once, soon, at high priority', () => {
    const s = new SettingsSweep(OWN);
    assert.equal(gcs, 0, 'not inside enable()');
    assert.deepEqual(idles.priorities, [-100]);
    idles.run();
    assert.equal(gcs, 1);
    s.destroy({collect: false});
});

test('another extension switched off or failed: one collection, before the next answer to the app', () => {
    const s = new SettingsSweep(OWN);
    idles.run();
    gcs = 0;
    manager.change('dash-to-panel@jderose9.github.com', 2);
    assert.deepEqual(idles.priorities, [-100], 'high priority: ahead of D-Bus calls waiting at default priority');
    idles.run();
    assert.equal(gcs, 1);
    manager.change('arcmenu@arcmenu.com', 3);
    idles.run();
    assert.equal(gcs, 2);
    s.destroy({collect: false});
});

test('GNOME switching several off in one go gives one collection', () => {
    const s = new SettingsSweep(OWN);
    idles.run();
    gcs = 0;
    for (const u of ['a@x', 'b@x', 'c@x'])
        manager.change(u, 2);
    assert.equal(idles.due.size, 1);
    idles.run();
    assert.equal(gcs, 1);
    s.destroy({collect: false});
});

test('starting extensions and this extension\'s own changes ask for nothing', () => {
    const s = new SettingsSweep(OWN);
    idles.run();
    gcs = 0;
    manager.change('arcmenu@arcmenu.com', 1);
    manager.change('arcmenu@arcmenu.com', 6);
    manager.change(OWN, 2);
    assert.equal(idles.due.size, 0);
    assert.equal(gcs, 0);
    s.destroy({collect: false});
});

test('switched off: disconnects, drops a waiting collection and collects right then', () => {
    const s = new SettingsSweep(OWN);
    manager.change('arcmenu@arcmenu.com', 2);
    assert.equal(idles.due.size, 1);
    s.destroy();
    assert.equal(gcs, 1, 'collected inside disable(), no idle left behind');
    assert.equal(idles.due.size, 0);
    assert.equal(manager.handlers.size, 0);
    manager.change('dash-to-panel@jderose9.github.com', 2);
    assert.equal(idles.due.size, 0, 'nothing scheduled after disable');
});

test('a failing collection never throws out', () => {
    const warned = [];
    console.warn = m => warned.push(m);
    assert.equal(collect(() => { throw new Error('boom'); }), false);
    assert.match(warned[0], /could not collect garbage/);
    const s = new SettingsSweep(OWN, {manager, gc: () => { throw new Error('boom'); }});
    idles.run();
    assert.equal(s.collections, 0);
    s.destroy();
});
