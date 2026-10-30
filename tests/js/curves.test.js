// gjs -m tests/js/curves.test.js : checks the animation curves (no GNOME Shell needed).
import * as C from '../../liquidglass/data/extension/liquid-glass@djshiye.github.io/curves.js';

let failed = 0;
function check(ok, what) {
    if (!ok) {
        failed++;
        print(`FAIL ${what}`);
    }
}
const sample = (f, n = 400) => Array.from({length: n + 1}, (_, i) => f(i / n));
const near = (a, b, e = 1e-6) => Math.abs(a - b) <= e;

for (const i of [0, 0.25, 0.5, 0.75, 1]) {
    for (const name of ['spring', 'bounce', 'jelly', 'genie', 'scalefade']) {
        const f = C.curve(name, i);
        check(near(f(0), 0) && near(f(1), 1), `${name}@${i} starts at 0 and ends at 1`);
        const peak = Math.max(...sample(f));
        // Never more than 15% past the end, at any intensity.
        check(peak <= 1 + C.MAX_OVERSHOOT + 1e-6, `${name}@${i} overshoot ${peak}`);
    }
    // A bounce never passes its end point; it hops back from it.
    check(Math.max(...sample(C.bounce(i))) <= 1 + 1e-9, `bounce@${i} stays at or below 1`);
    const w = C.wobble('jelly', i);
    check(near(w(0), 0) && near(w(1), 0), `jelly@${i} wobble is 0 at both ends`);
    check(Math.max(...sample(u => Math.abs(w(u)))) <= C.MAX_OVERSHOOT, `jelly@${i} wobble within 15%`);
}
// Intensity 0 settles without overshoot; the default gives about 6%.
check(Math.max(...sample(C.spring(0))) <= 1 + 1e-9, 'spring@0 never overshoots');
const o = Math.max(...sample(C.spring(0.5))) - 1;
check(o > 0.04 && o < 0.08, `spring@0.5 overshoot about 6% (${o})`);
// A bounce hops at least twice.
const b = sample(C.bounce(0.5), 2000);
let hops = 0;
for (let k = 1; k < b.length - 1; k++) {
    if (b[k] < b[k - 1] && b[k] < b[k + 1] && b[k] < 0.999)
        hops++;
}
check(hops >= 2, `bounce@0.5 hops ${hops} times`);
// Everything a click starts is 600 ms or less at 1x, and speed divides it.
for (const ev of ['open', 'minimize', 'close', 'hover'])
    for (const p of C.PRESETS[ev])
        check(C.duration(ev, p, 1) <= 600, `${ev}/${p} <= 600 ms`);
check(C.duration('open', 'spring', 2) === Math.round(C.duration('open', 'spring', 1) / 2), 'speed 2x halves it');
check(C.duration('open', 'spring', 99) === C.duration('open', 'spring', C.SPEED_MAX), 'speed is clamped');
// Config cleaning: unknown names fall back, numbers clamp, junk is ignored.
const m = C.cleanMotion({open: {preset: 'explode', intensity: 9, speed: -1}, close: {preset: 'bounce'},
    hover: {preset: 'jelly', intensity: 0.2}, launch: 'nope'});
check(m.open.preset === C.DEFAULT_MOTION.open.preset && m.open.intensity === 1 && m.open.speed === C.SPEED_MIN,
    'open cleaned');
check(m.close.preset === C.DEFAULT_MOTION.close.preset, 'close never bounces');
check(m.hover.preset === 'jelly' && m.hover.intensity === 0.2, 'hover kept');
check(JSON.stringify(m.launch) === JSON.stringify(C.DEFAULT_MOTION.launch), 'launch default');
check(JSON.stringify(C.cleanMotion(null)) === JSON.stringify(C.cleanMotion({})), 'null is defaults');
// Genie: nothing moves at 0, everything is inside the icon at 1, from either side.
const win = {x: 200, y: 80, width: 890, height: 560};
for (const icon of [{x: 100, y: 850, width: 44, height: 44}, {x: 700, y: 0, width: 40, height: 30},
    {x: 0, y: 300, width: 40, height: 40}]) {
    for (const [px, py] of [[200, 80], [1090, 640], [600, 300], [1090, 80]]) {
        const [x0, y0] = C.genieWarp(px, py, 0, win, icon);
        check(near(x0, px, 1e-6) && near(y0, py, 1e-6), 'genie at 0 leaves the window as it is');
        const [x1, y1] = C.genieWarp(px, py, 1, win, icon);
        check(x1 >= icon.x - 1e-6 && x1 <= icon.x + icon.width + 1e-6 && y1 >= icon.y - 1e-6 &&
            y1 <= icon.y + icon.height + 1e-6, `genie at 1 lands in the icon (${x1}, ${y1})`);
    }
}
// Rows keep their order, so the shader's search for the source row is sound.
const icon = {x: 100, y: 850, width: 44, height: 44};
for (const p of [0.1, 0.3, 0.5, 0.7, 0.9]) {
    let last = -Infinity;
    for (let y = win.y; y <= win.y + win.height; y += 4) {
        const [, yy] = C.genieWarp(600, y, p, win, icon);
        check(yy >= last - 1e-9, `genie rows keep their order at p=${p}`);
        last = yy;
    }
}
check(C.genieWarp(0, 0, 0.5, win, icon).every(Number.isFinite), 'genie is finite');

if (failed) {
    print(`${failed} check(s) failed`);
    imports.system.exit(1);
}
print('curves: all checks passed');
