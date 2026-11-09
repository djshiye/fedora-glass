// Stock GNOME, start on the desktop (desktop.js): the overview's dash fills itself in
// while hidden, finds its first app icon without a picture (GNOME's dash.js
// _adjustIconSize: "firstIcon.icon is null"), stops, and its app icons stay invisible.
// Each icon it adds must get its style at once, and icons it left hidden are shown.
import assert from 'node:assert/strict';
import {test} from 'node:test';

class Signals {
    constructor() { this.handlers = new Map(); this.next = 1; }
    connect(sig, fn) { const id = this.next++; this.handlers.set(id, [sig, fn]); return id; }
    disconnect(id) { this.handlers.delete(id); }
    emit(sig, ...a) { for (const [s, fn] of [...this.handlers.values()]) if (s === sig) fn(this, ...a); }
    count(sig) { return [...this.handlers.values()].filter(([s]) => s === sig).length; }
}

// GNOME's BaseIcon makes its picture only once its style is worked out.
class BaseIcon { constructor() { this.icon = null; } ensure_style() { this.icon ??= {}; } }
class DashItemContainer {
    constructor() {
        this.scale_x = 0; this.animatingOut = false;
        this.child = {ensure_style() {}, _delegate: {icon: new BaseIcon()}};
    }
    show() { this.scale_x = 1; }
}
class Box extends Signals {
    constructor() { super(); this.kids = []; }
    get_children() { return this.kids; }
    add(item) { this.kids.push(item); this.emit('child-added', item); }
}

const box = new Box();
const dash = {
    _box: box, sized: 0,
    // GNOME's own: throws on an icon without its picture, before showing any.
    _adjustIconSize() {
        if (!box.kids[0].child._delegate.icon.icon)
            throw new TypeError('firstIcon.icon is null');
        this.sized++;
    },
};
const overview = Object.assign(new Signals(), {visible: false, dash, hide() { this.visible = false; }});
globalThis.fake = {ui: {}, overview, sessionMode: {hasOverview: true}, extensionManager: {lookup: () => null}};
globalThis.global = {settings: {get_strv: () => []}};

const Main = await import('resource:///org/gnome/shell/ui/main.js');
const lm = Main.layoutManager;
Object.assign(lm, new Signals());
for (const k of ['connect', 'disconnect', 'emit', 'count'])
    lm[k] = Signals.prototype[k].bind(lm);
const {DesktopBehaviour, repairDash} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/desktop.js');

test('icons the hidden dash adds at login get their picture before it sizes them', () => {
    lm._startingUp = true;
    const d = new DesktopBehaviour({desktop: {overviewOff: false, startOnDesktop: true}});
    assert.equal(Main.sessionMode.hasOverview, false, 'the startup overview was not skipped');
    box.add(new DashItemContainer());
    box.add(new DashItemContainer());
    assert.doesNotThrow(() => dash._adjustIconSize(), 'the dash would still stop on an icon without its picture');
    lm._startingUp = false;
    lm.emit('startup-complete');
    assert.equal(Main.sessionMode.hasOverview, true);
    overview.emit('showing');
    assert.equal(box.count('child-added'), 0, 'kept watching the dash after the overview showed');
    assert.equal(overview.count('showing'), 0, 'left an overview handler connected');
    assert.ok(box.kids.every(k => k.scale_x === 1), 'app icons left invisible in the dash');
    d.destroy();
});

test('a dash that already stopped is shown again', () => {
    box.kids = [new DashItemContainer(), new DashItemContainer()];
    assert.throws(() => dash._adjustIconSize());     // as GNOME left it
    const before = dash.sized;
    assert.equal(repairDash(), true);
    assert.ok(box.kids.every(k => k.scale_x === 1));
    assert.equal(dash.sized, before + 1, 'the dash did not size its icons again');
    assert.equal(repairDash(), false, 'a healthy dash is left alone');
});

test('icons on their way out are not brought back', () => {
    const going = new DashItemContainer();
    going.animatingOut = true;
    box.kids = [going];
    repairDash();
    assert.equal(going.scale_x, 0);
});
