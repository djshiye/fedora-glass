// Start on the desktop (desktop.js): with Dash to Panel or Just Perfection on, they skip
// the startup overview themselves and we leave GNOME's overview switch alone. GNOME keeps
// the name of a removed extension on its list, so a name alone must not count: the
// extension has to be installed (GNOME knows it), and not on the switched-off list.
import assert from 'node:assert/strict';
import {test} from 'node:test';

const DTP = 'dash-to-panel@jderose9.github.com';
const sessionMode = {hasOverview: true};
const known = new Map();
const lists = {'enabled-extensions': [], 'disabled-extensions': []};
const extensionManager = {lookup: uuid => known.get(uuid)};
globalThis.fake = {ui: {}, overview: {visible: false, connect: () => 1, disconnect() {}, hide() {}},
    sessionMode, extensionManager};
globalThis.global = {settings: {get_strv: k => lists[k] ?? []}};

const Main = await import('resource:///org/gnome/shell/ui/main.js');
const lm = Main.layoutManager;
lm.connect = () => 1;
lm.disconnect = () => {};

let n = 0;
// desktop.js only skips the overview at the first start after login: a fresh copy each time.
async function startAtLogin() {
    sessionMode.hasOverview = true;
    lm._startingUp = true;
    const {DesktopBehaviour} = await import(`../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/desktop.js?login=${n++}`);
    const d = new DesktopBehaviour({desktop: {overviewOff: false, startOnDesktop: true}});
    const touched = sessionMode.hasOverview === false;
    d.destroy();
    return touched;
}

test('Dash to Panel installed and on (even if it starts after us): its own option skips the overview', async () => {
    lists['enabled-extensions'] = [DTP];
    known.set(DTP, {state: 6});          // known to GNOME, not started yet
    assert.equal(await startAtLogin(), false, 'changed the overview switch under Dash to Panel');
});

test('a removed Dash to Panel still named on the list does not count', async () => {
    lists['enabled-extensions'] = [DTP];
    known.clear();
    assert.equal(await startAtLogin(), true, 'trusted the name of an extension that is not installed');
});

test('Dash to Panel on the switched-off list does not count', async () => {
    lists['enabled-extensions'] = [DTP];
    lists['disabled-extensions'] = [DTP];
    known.set(DTP, {state: 2});
    assert.equal(await startAtLogin(), true);
    lists['disabled-extensions'] = [];
});
