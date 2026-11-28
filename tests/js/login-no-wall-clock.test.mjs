// A greeter where GNOME's wall clock (GnomeDesktop) cannot be had: the glass login screen
// still comes up, and its big clock still ticks on the minute by its own timer.
import assert from 'node:assert/strict';
import {test} from 'node:test';

import {makeGreeter, note, ours, registerStubs} from './login-fake.mjs';

globalThis.fakeNoGnomeDesktop = true;
makeGreeter();
registerStubs();
const {default: FedoraGlassLogin} =
    await import('../../fedoraglass/data/login-extension/fedora-glass-login@djshiye.github.io/extension.js');
const LOGIN_JS = '../../fedoraglass/data/login-extension/fedora-glass-login@djshiye.github.io/login.js';
await import(LOGIN_JS);

const RealDate = Date;
let now = new RealDate(2026, 0, 9, 9, 41, 10).getTime();
globalThis.Date = class extends RealDate {
    constructor(...a) { super(...(a.length ? a : [now])); }
    static now() { return now; }
};

const logged = [];
console.error = (...a) => logged.push(a.join(' '));
console.warn = (...a) => logged.push(a.join(' '));

test('no GNOME wall clock: the glass still comes up, and the clock ticks by its own timer', async () => {
    const fake = makeGreeter();
    const ext = new FedoraGlassLogin({uuid: 'fedora-glass-login@djshiye.github.io'});
    ext.enable();
    await import(LOGIN_JS);
    for (let i = 0; i < 8; i++)
        await new Promise(r => setTimeout(r, 0));
    assert.ok(ours().some(a => a.name === 'fedora-glass-login-card'), 'the glass is drawn');
    assert.equal(fake.wallClocks, undefined, 'no wall clock was made');
    const time = ext._glass._time;
    assert.equal(time.text, '09:41');
    // 51 s on: the minute is over, and the label says so.
    now += 51 * 1000;
    fake.timeouts.advance(51 * 1000);
    assert.equal(time.text, '09:42');
    assert.equal(note().phase, 'ok');
    assert.deepEqual(logged, []);
    ext.disable();
    assert.equal(fake.timeouts.list.size, 0);
});
