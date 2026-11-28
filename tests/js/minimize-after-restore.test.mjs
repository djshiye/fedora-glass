// A window restored and minimized again a moment later (a double click on its taskbar
// icon) carries on from where the restore was, not from full size.
import assert from 'node:assert/strict';
import {test} from 'node:test';

import {makeFake, windowActor} from './anim-fake.mjs';

const {fake, shellwm, log, advance} = makeFake();
fake.fs = new Map();
const {Animations} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/animations.js');
const {cleanMotion} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/curves.js');

const anims = preset => new Animations({
    animations: cleanMotion({open: {preset: 'spring'}, minimize: {preset}, close: {preset: 'spring'}}),
    glide: {enabled: false}});

// Mutter ends the window's effects, then starts the new one.
function mutter(signal, actor) {
    shellwm.emit('kill-window-effects', actor);
    shellwm.emit(signal, actor);
}

const snap = a => ({sx: a.scale_x, tx: a.translation_x, ty: a.translation_y, op: a.opacity});

for (const kill of [false, true]) {
    for (const preset of ['spring', 'scalefade', 'bounce', 'jelly']) {
        test(`${preset}: minimized again while it grows back, it shrinks from where it was (Mutter ends restores: ${kill})`, () => {
            fake.killUnminimize = kill;
            const an = anims(preset);
            const a = windowActor(fake);
            a.visible = false;
            mutter('unminimize', a);
            for (let i = 0; i < 4; i++)
                advance(16);
            const before = snap(a);
            assert.ok(before.sx < 0.95, `the restore should still be growing (scale ${before.sx})`);
            mutter('minimize', a);
            const first = snap(a);
            an.destroy();
            assert.ok(Math.abs(first.sx - before.sx) < 0.15, `the window jumps from scale ${before.sx} to ${first.sx}`);
            assert.ok(Math.abs(first.tx - before.tx) < 2 && Math.abs(first.ty - before.ty) < 2,
                `the window jumps from ${before.tx}, ${before.ty} to ${first.tx}, ${first.ty}`);
        });
    }

    test(`after the double click the window ends minimized and clean (Mutter ends restores: ${kill})`, () => {
        fake.killUnminimize = kill;
        const an = anims('spring');
        const a = windowActor(fake);
        a.visible = false;
        log.length = 0;
        mutter('unminimize', a);
        advance(16);
        advance(16);
        mutter('minimize', a);
        for (let i = 0; i < 80; i++)
            advance(16);
        assert.deepEqual(snap(a), {sx: 1, tx: 0, ty: 0, op: 255});
        assert.equal(a.z_position, 0);
        assert.equal(log.filter(l => l[0] === 'completed_minimize').length, 1);
        assert.equal(log.filter(l => l[0] === 'completed_unminimize').length, 1);
        an.destroy();
    });
}

test('a minimize after a restore that finished long ago starts from the full window', () => {
    fake.killUnminimize = false;
    const an = anims('spring');
    const a = windowActor(fake);
    a.visible = false;
    mutter('unminimize', a);
    for (let i = 0; i < 4; i++)
        advance(16);
    mutter('minimize', a);   // cut: leaves a note of the restore
    for (let i = 0; i < 80; i++)
        advance(16);
    // The note is old now; a plain restore then minimize must not use it.
    mutter('unminimize', a);
    for (let i = 0; i < 80; i++)
        advance(16);
    mutter('minimize', a);
    assert.equal(a.scale_x, 1);
    an.destroy();
});
