// lock.js (helpers in common.js): the clock in the middle keeps clear of GNOME's notifications under it.
import assert from 'node:assert/strict';
import {test} from 'node:test';

globalThis.fake = {timeouts: {add: () => 1, remove() {}}, Actor: class {}};
globalThis.global = {stage: {}};
const L = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/common.js');

test('the middle clock is centred when nothing shows under it', () => {
    assert.equal(L.clockMiddle(900, 500, null), 200);
});

test('with notifications showing, the middle clock moves up just enough to clear them', () => {
    // 1.5.7: clock 191..710 with notifications from 696, the unlock hint ran into them.
    assert.equal(L.clockMiddle(900, 519, 696), 696 - 24 - 519);
    assert.equal(L.clockMiddle(900, 400, 800), 250);          // far enough away: still centred
    assert.equal(L.clockMiddle(900, 700, 300), 0);            // never above the screen
});
