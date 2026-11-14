// Weather frost, frozen over: the ice is alive only while the glass is in use (its clock,
// frostmath.js iceEase / iceStep), and a frozen menu sheds the theme's drop shadow, which
// it gets back, untouched otherwise, when it thaws (follower.js _iceStyle).
import assert from 'node:assert/strict';
import {test} from 'node:test';

globalThis.fake = {
    fs: new Map(),
    now: () => 0,
    timeouts: {add: () => 1, remove: () => {}},
    Actor: class {},
    panel: {statusArea: {}},
};
globalThis.global = {stage: {}};

const EXT = '../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/';
const M = await import(`${EXT}frostmath.js`);
const {Follower} = await import(`${EXT}follower.js`);

test('the ice clock comes up to speed in use and slows to a stop after, never jumping', () => {
    let speed = 0, t = 0;
    const step = (using, dt = 1 / 30) => {
        const before = t;
        speed = M.iceEase(speed, using, dt);
        t = M.iceStep(t, dt, speed);
        assert.ok(t >= before || before - t > M.ICE_WRAP - 1, 'only forwards (or round at the wrap)');
        assert.ok(t - before <= dt + 1e-9 || before > t, 'never more than real time');
    };
    for (let i = 0; i < 30; i++)
        step(true);
    assert.ok(speed > 0.9, `up to speed within a second (${speed})`);
    let n = 0;
    while (speed > 0 && n < 300) {
        step(false);
        n++;
    }
    assert.equal(speed, 0, 'it comes to rest');
    assert.ok(n / 30 < 2.5, `within 2.5 s of the glass going out of use (${n / 30} s)`);
    const still = t;
    step(false);
    assert.equal(t, still, 'at rest it stays put');
    // A long gap (the PC asleep, a stall) is no jump: at most a tenth of a second.
    assert.ok(M.iceStep(10, 5, 1) - 10 <= 0.1 + 1e-9);
    // It wraps after an hour of use, so the shader never sees a huge number.
    assert.ok(M.iceStep(M.ICE_WRAP - 0.01, 0.05, 1) < 1);
    // Anything odd counts as standing still.
    assert.equal(M.iceEase(NaN, false, 1), 0);
    assert.equal(M.iceStep(Number.NaN, 0.1, 1), 0.1);
});

test('the ice lies still on the lightest quality, and only big glass counts as open', () => {
    assert.equal(M.ICE_FPS.length, 3);
    assert.ok(M.ICE_FPS[0] >= M.ICE_FPS[1] && M.ICE_FPS[1] > 0);
    assert.equal(M.ICE_FPS[2], 0, 'lightest: no clock at all');
    assert.ok(M.ICE_BIG > 64, 'a panel or a dock is not a menu');
});

function surface({style = null, shadow = true} = {}) {
    return {
        style,
        get_style() {
            return this.style;
        },
        set_style(s) {
            this.style = s;
        },
        peek_theme_node: () => ({get_box_shadow: () => (shadow ? {} : null)}),
    };
}

function follower(target, shade = 0.36) {
    const pane = {shed: null, setShadeShed(v) {
        this.shed = v;
    }};
    return {target, pane, settings: {look: {shade}}};
}

test('a frozen menu sheds the theme\'s drop shadow, and thawed has its own style back', () => {
    const ice = Follower.prototype._iceStyle;
    const t = surface({style: 'min-width: 20em;'});
    const f = follower(t);
    ice.call(f, true);
    assert.equal(t.style, 'min-width: 20em; box-shadow: none;');
    assert.equal(f.pane.shed, true, 'the glass is told: no shade under the veil now');
    ice.call(f, true);
    assert.equal(t.style, 'min-width: 20em; box-shadow: none;', 'only once');
    // Someone else restyles the menu meanwhile: only our own words come out again.
    t.style += ' color: red;';
    ice.call(f, false);
    assert.equal(t.style, 'min-width: 20em; color: red;');
    assert.equal(f.pane.shed, false);
    // A menu with no style of its own gets none back.
    const bare = surface();
    const g = follower(bare);
    ice.call(g, true);
    ice.call(g, false);
    assert.equal(bare.style, null);
});

test('the panel, a surface with no shadow and a surface already gone are left alone', () => {
    const ice = Follower.prototype._iceStyle;
    const bar = surface({style: 'background: none;'});
    ice.call(follower(bar, 0), true);
    assert.equal(bar.style, 'background: none;', 'not the panel (its look has no shade)');
    const plain = surface({shadow: false});
    ice.call(follower(plain), true);
    assert.equal(plain.style, null, 'nothing to shed');
    const gone = {get_style() {
        throw new Error('disposed');
    }};
    assert.doesNotThrow(() => ice.call(follower(gone), false));
});
