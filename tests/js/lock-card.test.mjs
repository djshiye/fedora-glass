// lock.js (helper in common.js): the glass card behind the lock screen's password prompt waits
// for GNOME's layout of the prompt. 1.7.1 placed it from what the prompt said before the layout.
import assert from 'node:assert/strict';
import {test} from 'node:test';

globalThis.fake = {timeouts: {add: () => 1, remove() {}}, Actor: class {}};
globalThis.global = {stage: {}};
const L = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/common.js');

const box = (over = {}) => ({visible: true, opacity: 255, ...over});

/**
 * A prompt as Clutter gives it. With a layout due it says the size it would like (none
 * at all for one just made), and has_allocation() is false; asking for its box makes
 * the layout happen, unless nothing can lay it out (`lays` false: not on screen yet).
 */
function prompt({visible = true, due = false, lays = true, got = 420, wants = 1} = {}) {
    return {
        visible, due, asked: 0,
        get width() {
            return this.due ? wants : got;
        },
        has_allocation() {
            return this.visible && !this.due;
        },
        get_allocation_box() {
            this.asked++;
            if (lays)
                this.due = false;
            return {};
        },
    };
}

test('nothing to sit behind: the card hides, and no layout is asked for', () => {
    assert.equal(L.cardStep(box(), null), 'hide');
    assert.equal(L.cardStep(null, prompt()), 'hide');
    for (const [b, p] of [[box({visible: false}), prompt()], [box({opacity: 0}), prompt()], [box(), prompt({visible: false})]]) {
        assert.equal(L.cardStep(b, p), 'hide');
        assert.equal(p.asked, 0);
    }
});

test('a prompt GNOME has laid out is read as it is', () => {
    assert.equal(L.cardStep(box(), prompt()), 'place');
});

test('with a layout due, GNOME lays the prompt out first and the card takes that place', () => {
    // 1.7.1: the prompt asked for 443 px and got 425, and the card kept the 443.
    const late = prompt({due: true, wants: 443, got: 425});
    assert.equal(L.cardStep(box(), late), 'place');
    assert.equal(late.asked, 1);
    assert.equal(late.width, 425);
});

test('a prompt GNOME has just made gets its card (1.7.1 hid the card and never looked again)', () => {
    const fresh = prompt({due: true, wants: 1});
    assert.equal(L.cardStep(box(), fresh), 'place');
});

test('a prompt nothing has laid out yet makes the card wait, not hide or guess', () => {
    assert.equal(L.cardStep(box(), prompt({due: true, lays: false, wants: 443})), 'wait');
    assert.equal(L.cardStep(box(), prompt({due: true, lays: false, wants: 1})), 'wait');
});

test('a laid out prompt with nothing in it has no card', () => {
    assert.equal(L.cardStep(box(), prompt({got: 1})), 'hide');
});

test('the wait for GNOME\'s layout ends', () => {
    assert.ok(Number.isInteger(L.CARD_LOOKS) && L.CARD_LOOKS >= 2 && L.CARD_LOOKS <= 120);
});
