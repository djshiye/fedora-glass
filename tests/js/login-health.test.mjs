// The login screen add-on's health note (health.js): what it says at each step, and when a
// start must draw nothing because the last one with the same look never finished.
import assert from 'node:assert/strict';
import {test} from 'node:test';

import {BOOT, LOOK, LOOK_PATH, NOTE_PATH, TOKEN, makeGreeter, note, registerStubs} from './login-fake.mjs';

makeGreeter();
registerStubs();
const H = await import('../../fedoraglass/data/login-extension/fedora-glass-login@djshiye.github.io/health.js');

const OTHER = 'fedcba9876543210fedcba9876543210';
const OTHER_BOOT = '99999999-8888-7777-6666-555555555555';

test('a start says starting, then ok, atomically and small, in the greeter\'s state folder', () => {
    const fake = makeGreeter();
    const h = new H.Health({token: TOKEN});
    assert.equal(h.boot, BOOT);
    assert.equal(h.previous, null);
    assert.ok(h.write('starting'));
    assert.deepEqual(note(), {v: 1, token: TOKEN, boot: BOOT, phase: 'starting', verified: ''});
    h.write('ok');
    assert.equal(note().phase, 'ok');
    const f = fake.fs.get(NOTE_PATH);
    assert.equal(f.flags, 1, 'written with CONSISTENT (a temporary file renamed over the old one)');
    assert.equal(f.mode, 0o644);
    assert.ok(f.text.length < 1024);
    assert.throws(() => h.write('fine'));
});

test('a start that never finished with this look: safe, and safe again in the same boot', () => {
    makeGreeter();
    const at = prev => H.mustStaySafe(prev, TOKEN, BOOT);
    assert.equal(at({token: TOKEN, boot: BOOT, phase: 'starting'}), true);
    assert.equal(at({token: TOKEN, boot: OTHER_BOOT, phase: 'starting'}), true, 'a crash is a crash in any boot');
    assert.equal(at({token: TOKEN, boot: BOOT, phase: 'safe'}), true);
    assert.equal(at({token: TOKEN, boot: OTHER_BOOT, phase: 'safe'}), false, 'a new boot tries again (the guard decides)');
    assert.equal(at({token: OTHER, boot: BOOT, phase: 'starting'}), false, 'a new look is a new trial');
    for (const phase of ['ok', 'error'])
        assert.equal(at({token: TOKEN, boot: BOOT, phase}), false, phase);
    assert.equal(at(null), false);
    assert.equal(H.mustStaySafe({token: '', phase: 'starting'}, '', BOOT), false);
});

test('the previous note is read back, and a check that succeeded with this look is kept', () => {
    makeGreeter({note: {v: 1, token: TOKEN, boot: BOOT, phase: 'ok', verified: TOKEN}});
    const h = new H.Health({token: TOKEN});
    assert.equal(h.previous.phase, 'ok');
    assert.equal(h.verified, TOKEN);
    h.write('starting');
    assert.equal(note().verified, TOKEN);
    // Another look: the old success does not count for it.
    makeGreeter({note: {v: 1, token: TOKEN, boot: BOOT, phase: 'ok', verified: TOKEN}});
    assert.equal(new H.Health({token: OTHER}).verified, '');
});

test('markVerified writes the token once and it stays through later phases', () => {
    const fake = makeGreeter();
    const h = new H.Health({token: TOKEN});
    h.write('starting');
    assert.ok(h.markVerified());
    assert.equal(note().verified, TOKEN);
    const writes = fake.writes.length;
    assert.equal(h.markVerified(), false, 'once is enough');
    assert.equal(fake.writes.length, writes);
    h.write('error');
    assert.deepEqual(note(), {v: 1, token: TOKEN, boot: BOOT, phase: 'error', verified: TOKEN});
    // Without a token nothing can be verified.
    makeGreeter();
    assert.equal(new H.Health({token: 'nope'}).markVerified(), false);
});

test('a note that cannot be written is no failure of the login screen', () => {
    const fake = makeGreeter();
    fake.readOnly = true;
    const h = new H.Health({token: TOKEN});
    assert.equal(h.write('starting'), false);
    assert.equal(h.phase, 'starting');
});

test('look.json and the note are only read when small, whole JSON objects', () => {
    const fake = makeGreeter();
    assert.equal(H.tokenOf(H.readLook()), TOKEN);
    assert.deepEqual(H.readLook(LOOK_PATH), {...LOOK});
    for (const text of ['', 'not json', '[1]', '"x"', 'null', JSON.stringify({...LOOK, pad: 'x'.repeat(5000)})]) {
        fake.fs.set(LOOK_PATH, {text});
        assert.equal(H.readLook(), null, text.slice(0, 20));
    }
    fake.fs.delete(LOOK_PATH);
    assert.equal(H.readLook(), null);
    for (const t of [undefined, 5, 'ABCDEF0123456789abcdef0123456789', `${TOKEN}\n`, TOKEN.slice(1)])
        assert.equal(H.tokenOf({token: t}), '');
    fake.fs.set(NOTE_PATH, {text: JSON.stringify({phase: 'starting', token: TOKEN, junk: 'x'.repeat(2000)})});
    assert.equal(new H.Health({token: TOKEN}).previous, null, 'an oversized note is not believed');
    fake.fs.set('/proc/sys/kernel/random/boot_id', {text: 'garbage\n'});
    assert.equal(H.bootId(), '');
});

test('the run note counts runs in a row that ended without a clean stop or a login', () => {
    const at = prev => H.uncleanBefore(prev, TOKEN, BOOT);
    const p = o => ({v: 1, boot: BOOT, token: TOKEN, clean: false, verified: false, unclean: 0, ...o});
    assert.equal(at(null), 0);
    assert.equal(at(p({})), 1, 'the last run was killed');
    assert.equal(at(p({unclean: 1})), 2);
    assert.equal(at(p({clean: true, unclean: 5})), 0, 'a clean end starts again');
    assert.equal(at(p({verified: true, unclean: 5})), 0, 'a login that worked starts again');
    assert.equal(at(p({boot: OTHER_BOOT, unclean: 5})), 0, 'a new boot starts again');
    assert.equal(at(p({token: OTHER, unclean: 5})), 0, 'a new look starts again');
    assert.equal(at(p({unclean: -3})), 1, 'nonsense counts as none');
    assert.equal(at(p({unclean: '9'})), 1);
    assert.equal(at(p({v: 2, unclean: 9})), 0);
    assert.equal(H.UNCLEAN_LIMIT, 2);
});

test('the run note is written privately, and what a run did is kept', () => {
    const fake = makeGreeter();
    const path = '/var/lib/gdm/seat0/state/fedora-glass-login/run.json';
    const r = new H.RunNote({token: TOKEN});
    assert.equal(r.unclean, 0);
    assert.equal(r.tooMany, false);
    r.start();
    assert.equal(fake.fs.get(path).mode, 0o600);
    assert.deepEqual(JSON.parse(fake.fs.get(path).text), {v: 1, boot: BOOT, token: TOKEN, clean: false, verified: false, unclean: 0});
    // Killed: the next run counts 1, then 2 (too many).
    const r2 = new H.RunNote({token: TOKEN});
    assert.equal(r2.unclean, 1);
    r2.start();
    const r3 = new H.RunNote({token: TOKEN});
    assert.equal(r3.unclean, 2);
    assert.equal(r3.tooMany, true);
    r3.start();
    r3.endClean();
    assert.equal(new H.RunNote({token: TOKEN}).unclean, 0);
    const r4 = new H.RunNote({token: TOKEN});
    r4.start();
    r4.markVerified();
    assert.equal(new H.RunNote({token: TOKEN}).unclean, 0);
    fake.fs.set(path, {text: 'x'.repeat(600)});
    assert.equal(new H.RunNote({token: TOKEN}).previous, null, 'an oversized note is not believed');
});
