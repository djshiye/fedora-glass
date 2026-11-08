// ArcMenu rescue (arcrescue.js): after GNOME restarts ArcMenu before Dash to Panel and
// ArcMenu fails with "this.panel is undefined", it is started again once Dash to Panel
// has its panels. Other failures and other extensions are left alone.
import assert from 'node:assert/strict';
import {test, beforeEach} from 'node:test';

class Clock {
    constructor() { this.now = 0; this._next = 1; this._due = new Map(); }
    add(ms, fn) { const id = this._next++; this._due.set(id, {at: this.now + ms, every: ms, fn}); return id; }
    remove(id) { this._due.delete(id); }
    advance(ms) {
        const end = this.now + ms;
        for (;;) {
            const next = [...this._due.entries()].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
            if (!next)
                break;
            this._due.delete(next[0]);
            this.now = next[1].at;
            if (next[1].fn())
                this._due.set(next[0], {...next[1], at: this.now + next[1].every});
        }
        this.now = end;
    }
    get pending() { return this._due.size; }
}

const RACE = 'TypeError: can\'t access property "statusArea", this.panel is undefined';

class Manager {
    constructor() {
        this.handlers = new Map();
        this.next = 1;
        this.exts = new Map();
        this._extensionOrder = [];
        this.enabled = [];
        this.log = [];
    }
    add(uuid, state, error = '') {
        const ext = {uuid, state, error, stateObj: {disable: () => this.log.push(`disable ${uuid}`)}};
        this.exts.set(uuid, ext);
        this._extensionOrder.push(uuid);
        return ext;
    }
    lookup(uuid) { return this.exts.get(uuid); }
    connect(_sig, fn) { const id = this.next++; this.handlers.set(id, fn); return id; }
    disconnect(id) { this.handlers.delete(id); }
    _unloadExtensionStylesheet(ext) {
        this.log.push(`unload stylesheet ${ext.uuid}`);
    }
    _changeExtensionState(ext, state) {
        ext.state = state;
        for (const fn of [...this.handlers.values()])
            fn(this, ext);
    }
    async _callExtensionEnable(uuid) {
        this.enabled.push(uuid);
        const ext = this.lookup(uuid);
        ext.state = 1;
        this._extensionOrder.push(uuid);
    }
    fail(uuid, error) {
        const ext = this.lookup(uuid);
        ext.error = error;
        this._changeExtensionState(ext, 3);
    }
}

const clock = new Clock();
const manager = new Manager();
globalThis.fake = {timeouts: clock, extensionManager: manager};
globalThis.console = {...console, log: () => {}};
const mod = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/arcrescue.js');
const {ArcMenuRescue, ARCMENU, DASH_TO_PANEL, MAX_RESCUES, GIVE_UP_MS, isPanelRace} = mod;

function reset() {
    manager.handlers.clear();
    manager.exts.clear();
    manager._extensionOrder = [];
    manager.enabled = [];
    manager.log = [];
    clock._due.clear();
    mod.resetForTests();
    globalThis.global = {dashToPanel: {panels: [{}]}};
}

beforeEach(reset);

test('restarts ArcMenu once Dash to Panel has its panels again', () => {
    manager.add(ARCMENU, 1);
    const dtp = manager.add(DASH_TO_PANEL, 1);
    const r = new ArcMenuRescue();
    // Mid-rebase: Dash to Panel is off for the moment, ArcMenu fails.
    globalThis.global.dashToPanel = undefined;
    manager.fail(ARCMENU, RACE);
    clock.advance(1000);
    assert.deepEqual(manager.enabled, [], 'waits while Dash to Panel has no panels');
    globalThis.global.dashToPanel = {panels: [{}]};
    dtp.state = 1;
    clock.advance(300);
    assert.deepEqual(manager.enabled, [ARCMENU]);
    assert.deepEqual(manager.log, [`disable ${ARCMENU}`, `unload stylesheet ${ARCMENU}`],
        'cleans up what the failed start left, its stylesheet too, so it is not loaded twice');
    assert.equal(manager.lookup(ARCMENU).state, 1);
    assert.equal(manager.lookup(ARCMENU).error, '');
    assert.equal(manager._extensionOrder.filter(u => u === ARCMENU).length, 1, 'listed once in the start order');
    r.destroy();
});

test('a failure from before this extension started is rescued too', () => {
    manager.add(DASH_TO_PANEL, 1);
    manager.add(ARCMENU, 3, RACE);
    const r = new ArcMenuRescue();
    clock.advance(300);
    assert.deepEqual(manager.enabled, [ARCMENU]);
    r.destroy();
});

test('other ArcMenu errors and other extensions are left alone', () => {
    manager.add(ARCMENU, 1);
    manager.add(DASH_TO_PANEL, 1);
    manager.add('other@x', 1);
    const r = new ArcMenuRescue();
    manager.fail(ARCMENU, 'TypeError: something else');
    manager.fail('other@x', RACE);
    clock.advance(GIVE_UP_MS + 1000);
    assert.deepEqual(manager.enabled, []);
    assert.equal(isPanelRace(manager.lookup(ARCMENU)), false);
    r.destroy();
});

test('gives up if Dash to Panel never comes back', () => {
    manager.add(ARCMENU, 1);
    manager.add(DASH_TO_PANEL, 2);
    const r = new ArcMenuRescue();
    globalThis.global.dashToPanel = undefined;
    manager.fail(ARCMENU, RACE);
    clock.advance(GIVE_UP_MS + 1000);
    assert.deepEqual(manager.enabled, []);
    assert.equal(clock.pending, 0, 'stops looking');
    r.destroy();
});

test('at most a few times per session, however often it fails', () => {
    manager.add(ARCMENU, 1);
    manager.add(DASH_TO_PANEL, 1);
    const r = new ArcMenuRescue();
    for (let i = 0; i < MAX_RESCUES + 3; i++) {
        manager.fail(ARCMENU, RACE);
        clock.advance(300);
    }
    assert.equal(manager.enabled.length, MAX_RESCUES);
    r.destroy();
});

test('switching Fedora Glass off stops it cleanly', () => {
    manager.add(ARCMENU, 1);
    manager.add(DASH_TO_PANEL, 1);
    const r = new ArcMenuRescue();
    manager.fail(ARCMENU, RACE);
    r.destroy();
    clock.advance(1000);
    assert.deepEqual(manager.enabled, []);
    assert.equal(manager.handlers.size, 0);
    assert.equal(clock.pending, 0);
});
