// 1.7.4 review, X1: DesktopBehaviour.destroy() takes its handler off the dash's box even when
// the overview never showed (overview off). Dash to Panel back on while paused (X6) is in
// review-174-paused.test.mjs.
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
test('switched off while the overview never showed (overview off): the dash is no longer watched', () => {
    lm._startingUp = true;
    const d = new DesktopBehaviour({desktop: {overviewOff: true, startOnDesktop: true}});
    lm._startingUp = false;
    lm.emit('startup-complete');
    d.destroy();
    assert.equal(box.count('child-added'), 0);
});
