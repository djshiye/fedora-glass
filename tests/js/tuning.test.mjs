// Auto glass quality (tuning.js): when slow frames make the glass lighter, when it
// tries a higher level again, and how a speed check is scored.
import assert from 'node:assert/strict';
import {test} from 'node:test';

const T = await import('../../liquidglass/data/extension/liquid-glass@djshiye.github.io/tuning.js');
const HZ60 = 1e6 / 60;

function feed(tuner, start, n, late, every = HZ60) {
    let changed = null, t = start;
    for (let i = 0; i < n; i++) {
        t += every;
        const r = tuner.frame(t, late);
        if (r !== null)
            changed = r;
    }
    return [changed, t];
}

test('frames after a pause never read as slow, slow paints always do', () => {
    assert.equal(T.frameLate(HZ60, 2000, HZ60), false);
    assert.equal(T.frameLate(2 * HZ60, 2000, HZ60), false);   // an app redrawing at 30 fps: its pace, not ours
    assert.equal(T.frameLate(50e3, 3000, HZ60), false);       // glass catching up at 20 Hz with a busy app
    assert.equal(T.frameLate(2 * HZ60, 12000, HZ60), true);   // a heavy frame that also came late
    assert.equal(T.frameLate(100e3, 2000, HZ60), null);   // typing: one frame now and then
    assert.equal(T.frameLate(100e3, 40e3, HZ60), true);    // but that frame took 40 ms to draw
    assert.equal(T.frameLate(0, 1000, 0), null);
    // A 144 Hz screen: glass at 60 frames a second or better is on time.
    const HZ144 = 1e6 / 144;
    assert.equal(T.frameLate(2 * HZ144, 9000, HZ144), false);
    assert.equal(T.frameLate(HZ60 * 2, 9000, HZ144), true);
    assert.equal(T.frameLate(HZ144, 20000, HZ144), true);
});

test('smooth frames keep full glass', () => {
    const t = new T.Tuner();
    const [changed] = feed(t, 0, 600, false);
    assert.equal(changed, null);
    assert.equal(t.level, 0);
});

test('a few late frames among many do not step down', () => {
    const t = new T.Tuner();
    let at = 0;
    for (let i = 0; i < 300; i++) {
        at += HZ60;
        assert.equal(t.frame(at, i % 4 === 0), null);  // 25% late
    }
});

test('mostly late frames step down one level at a time, with a pause between', () => {
    const t = new T.Tuner();
    let [changed, at] = feed(t, 0, 30, true, 2 * HZ60);
    assert.equal(changed, 1);
    assert.equal(t.reason, 'slow');
    // Straight after, the new level gets time to settle.
    [changed, at] = feed(t, at, 30, true, 2 * HZ60);
    assert.equal(changed, null);
    [changed, at] = feed(t, at + T.SETTLE_US, 30, true, 2 * HZ60);
    assert.equal(changed, 2);
    [changed] = feed(t, at + T.SETTLE_US, 300, true, 2 * HZ60);
    assert.equal(changed, null, 'never past lightest');
});

test('it tries a higher level later, and stays down if that is slow again soon', () => {
    const t = new T.Tuner();
    let [, at] = feed(t, 0, 30, true, 2 * HZ60);
    assert.equal(t.level, 1);
    assert.ok(t.retryAt > at);
    assert.equal(t.tick(at + 1e6), null, 'not yet');
    at = t.retryAt;
    assert.equal(t.tick(at), 0);
    assert.equal(t.reason, 'retry');
    // Slow again within a minute: back to lighter, for good.
    [, at] = feed(t, at + T.SETTLE_US, 30, true, 2 * HZ60);
    assert.equal(t.level, 1);
    assert.equal(t.retryAt, null);
    assert.equal(t.tick(at + 10 * T.RETRY_US), null);
});

test('a retry that holds keeps full glass', () => {
    const t = new T.Tuner();
    feed(t, 0, 30, true, 2 * HZ60);
    const at = t.retryAt;
    assert.equal(t.tick(at), 0);
    const [changed] = feed(t, at + T.SETTLE_US, 3000, false);
    assert.equal(changed, null);
    assert.equal(t.level, 0);
});

test('unknown quality values mean auto', () => {
    assert.equal(T.cleanQuality({quality: 'lighter'}), 'lighter');
    assert.equal(T.cleanQuality({quality: 'turbo'}), 'auto');
    assert.equal(T.cleanQuality(null), 'auto');
    assert.equal(T.cleanQuality('lightest'), 'lightest');
});

test('a check is scored against the screen rate', () => {
    const smooth = T.scorePhase(0, Array(300).fill(HZ60), 60);
    assert.equal(smooth.verdict, 'smooth');
    assert.equal(Math.round(smooth.fps), 60);
    const ok = T.scorePhase(1, Array(200).fill(HZ60 * 1.6), 60);
    assert.equal(ok.verdict, 'slow');      // every frame late
    const fair = T.scorePhase(1, [...Array(160).fill(HZ60), ...Array(40).fill(2 * HZ60)], 60);
    assert.equal(fair.verdict, 'ok');
    assert.equal(T.scorePhase(2, [], 60).verdict, 'slow');
});

test('the pick is the highest level that ran smoothly, else the fastest', () => {
    const p = (level, verdict, fps) => ({level, verdict, fps});
    assert.equal(T.pickLevel([p('full', 'smooth', 60), p('lighter', 'smooth', 60), p('lightest', 'smooth', 60)]), 'full');
    assert.equal(T.pickLevel([p('full', 'slow', 20), p('lighter', 'smooth', 59), p('lightest', 'smooth', 60)]), 'lighter');
    assert.equal(T.pickLevel([p('full', 'slow', 20), p('lighter', 'ok', 40), p('lightest', 'smooth', 60)]), 'lightest');
    assert.equal(T.pickLevel([p('full', 'slow', 10), p('lighter', 'slow', 14), p('lightest', 'slow', 12)]), 'lighter');
});

test('lightest glass shows only the wallpaper; other levels change nothing', () => {
    const cfg = {panel: {behind: 'windows', enabled: true}, menus: {behind: 'windows'}, windows: {behind: 'windows'},
        parts: {arcmenu: {behind: 'windows'}}, look: {blur: 6}};
    assert.equal(T.effectiveConfig(cfg, 1), cfg);
    const out = T.effectiveConfig(cfg, 2);
    assert.equal(out.panel.behind, 'wallpaper');
    assert.equal(out.menus.behind, 'wallpaper');
    assert.equal(out.windows.behind, 'wallpaper');
    assert.equal(out.parts.arcmenu.behind, 'wallpaper');
    assert.equal(cfg.panel.behind, 'windows', 'the setting itself is untouched');
    assert.equal(out.look, cfg.look);
});

test('the running count of late frames matches a full count at 144 Hz on two screens', () => {
    // The tuner keeps a running count instead of walking its window each frame. Feed a
    // long mixed run and check, frame by frame, that it decides exactly as a recount would.
    const t = new T.Tuner();
    const every = 1e6 / 288;
    let at = 0;
    for (let i = 0; i < 6000; i++) {
        at += every;
        const late = (i * 7919) % 10 < 3;   // 30 % late, never enough to step down
        assert.equal(t.frame(at, late), null);
        if (i % 500 === 0) {
            const n = t._frames.filter(([, l]) => l).length;
            assert.equal(t._late, n);
        }
    }
});
