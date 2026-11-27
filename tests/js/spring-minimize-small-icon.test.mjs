// A spring minimize into a small taskbar icon overshoots a little past the icon's size.
// That is normal: it must not count as a runaway value or write to the log.
import assert from 'node:assert/strict';
import {test} from 'node:test';

import {makeFake, windowActor} from './anim-fake.mjs';

const {fake, shellwm, log, advance} = makeFake();
fake.fs = new Map();
fake.logs = [];
const {Animations, qaGenie} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/animations.js');
const {cleanMotion, SCALE_MIN} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/curves.js');

for (const [preset, intensity] of [['spring', 0.5], ['spring', 1], ['jelly', 0.5], ['jelly', 1], ['bounce', 1]]) {
    test(`${preset} (${intensity}): minimizing into a small icon is not held back as a bad value`, () => {
        const an = new Animations({animations: cleanMotion({minimize: {preset, intensity}}), glide: {enabled: false}});
        const a = windowActor(fake);
        // A 20 px wide icon under a 1000 px wide window: scale 0.02.
        a.meta_window.get_icon_geometry = () => [true, {x: 1000, y: 1110, width: 20, height: 20}];
        const clamps = qaGenie().clamps;
        log.length = 0;
        fake.logs.length = 0;
        shellwm.emit('kill-window-effects', a);
        shellwm.emit('minimize', a);
        let least = 1;
        for (let i = 0; i < 80; i++) {
            advance(16);
            least = Math.min(least, a.scale_x);
        }
        an.destroy();
        assert.equal(qaGenie().clamps, clamps, `a clamp was counted (smallest scale seen ${least})`);
        assert.deepEqual(fake.logs.filter(l => l.includes('held it in range')), []);
        assert.ok(least >= SCALE_MIN);
        assert.equal(log.filter(l => l[0] === 'completed_minimize').length, 1);
        assert.deepEqual([a.scale_x, a.translation_x, a.translation_y, a.opacity, a.z_position], [1, 0, 0, 255, 0]);
    });
}
