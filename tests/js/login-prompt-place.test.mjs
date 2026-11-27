// Where the glass login card stands on each GNOME's own layout of the password prompt
// (50, 51.0 and 51.1, as the fake greeter lays it out), with GNOME's theme and with a theme
// of someone else's on top: the card in the middle of the screen, and the big clock staying
// where it is when a user is picked.
import assert from 'node:assert/strict';
import {test} from 'node:test';

import {CSS_PATH, makeGreeter, ours, registerStubs} from './login-fake.mjs';

makeGreeter();
registerStubs();
const {default: FedoraGlassLogin} =
    await import('../../fedoraglass/data/login-extension/fedora-glass-login@djshiye.github.io/extension.js');
const LOGIN_JS = '../../fedoraglass/data/login-extension/fedora-glass-login@djshiye.github.io/login.js';
await import(LOGIN_JS);

// A fixed time of day, well away from the minute's end (see login-extension.test.mjs).
const RealDate = Date;
const NOW = new RealDate(2026, 0, 9, 9, 41, 10).getTime();
globalThis.Date = class extends RealDate {
    constructor(...a) { super(...(a.length ? a : [NOW])); }
    static now() { return NOW; }
};

const logged = [];
console.error = (...a) => logged.push(a.join(' '));
console.warn = (...a) => logged.push(a.join(' '));

const settle = async () => {
    await import(LOGIN_JS);
    for (let i = 0; i < 8; i++)
        await new Promise(r => setTimeout(r, 0));
};

const margin = fake => /prompt-layout {[^}]*margin-top: (\d+)px;/.exec(fake.fs.get(CSS_PATH).text)?.[1] ?? null;

/** The add-on on a greeter whose screen is `screen` px tall, laid out as GNOME `gnome` does. */
async function started({screen = 1080, textScale = 1, ...opts} = {}) {
    const fake = makeGreeter({layout: true, ...opts});
    logged.length = 0;
    fake.layoutManager.monitors = [{x: 0, y: 0, width: 2048, height: screen}];
    fake.gsettings['org.gnome.desktop.interface']['text-scaling-factor'] = textScale;
    // GNOME keeps its user list in the middle of the screen.
    const d = fake.screenShield._dialog;
    for (const a of [d._userList, ...d._userList.all().slice(1), d._notListedButton])
        a.y += screen / 2 - 540;
    const ext = new FedoraGlassLogin({uuid: 'fedora-glass-login@djshiye.github.io'});
    ext.enable();
    await settle();
    fake.laters.run();
    const card = ours().find(a => a.name === 'fedora-glass-login-card');
    const placed = [];
    card.place = (...a) => placed.push(a.slice(0, 4));
    const top = ours().find(a => a.name === 'fedora-glass-login-top');
    const settleCard = () => {
        fake.laters.run();
        fake.now = (fake.now ?? 0) + 300000;
        fake.timeouts.run(16);
    };
    // A user picked: GNOME hides its list and shows the prompt; and back again.
    const pick = () => {
        d._userSelectionBox.hide();
        d._authPrompt.show();
        settleCard();
        const [, y, , h] = placed.at(-1);
        return {cardMiddle: y + h / 2, clock: top.y};
    };
    const back = () => {
        d._authPrompt.hide();
        d._userSelectionBox.show();
        settleCard();
        return top.y;
    };
    return {fake, ext, d, top, pick, back, loads: () => fake.themeContext.theme.loads};
}

test('GNOME 51.1: the card stands in the middle of the screen, and the clock stays when a user is picked', async () => {
    for (const [screen, textScale] of [[1080, 1], [1152, 1], [1440, 1], [1152, 1.25]]) {
        const what = `${screen} px, text ${textScale}`;
        const g = await started({gnome: '51.1', screen, textScale});
        const listClock = g.top.y;
        const seen = g.pick();
        assert.ok(Math.abs(seen.cardMiddle - screen / 2) <= 4, `${what}: card middle ${seen.cardMiddle}`);
        assert.equal(seen.clock, listClock, `${what}: the clock stays`);
        assert.equal(g.back(), listClock, `${what}: and stays going back`);
        assert.equal(g.loads(), 1, `${what}: GNOME's own theme: nothing to set again`);
        assert.deepEqual(logged, []);
        g.ext.disable();
    }
});

test('a theme of someone else\'s: what is seen sets the place, the card is in the middle and the clock stays from then on', async () => {
    for (const gnome of ['51.1', '51.0', '50']) {
        for (const [screen, textScale] of [[1080, 1], [1152, 1], [1152, 1.25]]) {
            const what = `GNOME ${gnome}, ${screen} px, text ${textScale}`;
            const g = await started({gnome, screen, textScale, foreign: true});
            const seen = g.pick();
            assert.ok(Math.abs(seen.cardMiddle - screen / 2) <= 4, `${what}: card middle ${seen.cardMiddle}`);
            assert.ok(g.loads() > 1 && g.loads() <= 1 + 4, `${what}: set again a few times (${g.loads() - 1})`);
            const loads = g.loads();
            assert.equal(g.back(), seen.clock, `${what}: the clock stays going back to the list`);
            assert.equal(g.pick().clock, seen.clock, `${what}: and picking a user again`);
            assert.equal(g.loads(), loads, `${what}: looked at once`);
            assert.deepEqual(logged, []);
            g.ext.disable();
        }
    }
});

test('GNOME 50 and 51.0 with their own theme: today\'s margins, and nothing set again', async () => {
    for (const [gnome, screen, textScale, want] of [['51.0', 1080, 1, '155'], ['51.0', 1440, 1, '155'],
        ['51.0', 1080, 1.25, '143'], ['50', 1080, 1, '67'], ['50', 1152, 1.25, '84']]) {
        const what = `GNOME ${gnome}, ${screen} px, text ${textScale}`;
        const g = await started({gnome, screen, textScale});
        const listClock = g.top.y;
        assert.equal(margin(g.fake), want, what);
        const seen = g.pick();
        assert.equal(margin(g.fake), want, `${what}: the same once laid out`);
        assert.equal(g.loads(), 1, `${what}: the stylesheet loaded once`);
        assert.ok(Math.abs(seen.cardMiddle - screen / 2) <= 4, `${what}: card middle ${seen.cardMiddle}`);
        // As before: where GNOME 50 rounds down and promptPlace rounds, 1 px.
        assert.ok(Math.abs(seen.clock - listClock) <= 1, `${what}: the clock stays`);
        g.ext.disable();
    }
});

test('a layout that takes no notice of the margin: a few tries, the first place again, and then nothing', async () => {
    const g = await started({gnome: '51.1', ignoreMargin: true});
    const first = margin(g.fake);
    g.pick();
    const loads = g.loads();
    assert.ok(loads <= 1 + 4 + 1, `set again ${loads - 1} times`);
    assert.equal(margin(g.fake), first, 'the place that came closest');
    for (let i = 0; i < 10; i++) {
        g.fake.relayout();
        g.fake.laters.run();
    }
    g.back();
    g.pick();
    assert.equal(g.loads(), loads, 'no more tries, however often GNOME lays it out');
    assert.deepEqual(logged, []);
    g.ext.disable();
});

test('GNOME 51.1 on a short screen: the prompt still gets GNOME\'s own place back, once', async () => {
    const g = await started({gnome: '51.1', screen: 600});
    assert.notEqual(margin(g.fake), null);
    g.pick();
    assert.equal(margin(g.fake), null, 'no room of ours above the prompt');
    assert.equal(g.loads(), 2);
    g.back();
    g.pick();
    assert.equal(g.loads(), 2, 'given back once');
    assert.deepEqual(logged, []);
    g.ext.disable();
});
