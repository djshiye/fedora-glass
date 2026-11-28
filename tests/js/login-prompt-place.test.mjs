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
// What the add-on says once it has looked at the prompt's place (one line for each build).
const said = [];
console.log = (...a) => said.push(a.join(' '));
const SAID = /^Fedora Glass login: the prompt stands (-?\d+) px down the screen, wanted (-?\d+)(, and does not follow the margin)? \((\d+) px tall, margin (\d+), set again: (\d+), way: (\w+), screen: (\d+) px, scale: ([\d.]+), text: ([\d.]+)\)$/;
/** The one line said about the prompt's place, as numbers. */
const place = () => {
    assert.equal(said.length, 1, `one line about the prompt's place: ${JSON.stringify(said)}`);
    const m = SAID.exec(said[0]);
    assert.ok(m, said[0]);
    return {top: +m[1], wanted: +m[2], follows: !m[3], tall: +m[4], margin: +m[5], again: +m[6], way: m[7],
        screen: +m[8], scale: +m[9], text: +m[10]};
};

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
    said.length = 0;
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
    const seen = () => {
        const [, y, , h] = placed.at(-1);
        return {cardMiddle: y + h / 2, clock: top.y};
    };
    // A user picked: GNOME hides its list and shows the prompt; and back again. ask: false =
    // as on a real login screen, where the prompt shows first, with the back button alone in
    // the field's row, and the field comes when GDM asks its question (ask()).
    const field = d._authPrompt._entryArea ?? d._authPrompt._entry;
    const pick = ({ask = true} = {}) => {
        field.visible = ask;
        d._userSelectionBox.hide();
        d._authPrompt.show();
        settleCard();
        return seen();
    };
    // GNOME 51's row keeps its height, so nothing but the field's own box tells of it.
    // GNOME 50 has its field there from the start in a password login; there this stands
    // for the field coming back after a list of ways to log in, and its prompt is laid out again.
    const ask = () => {
        field.show();
        if (opts.gnome === '50')
            fake.relayout();
        settleCard();
        return seen();
    };
    const back = () => {
        d._authPrompt.hide();
        d._userSelectionBox.show();
        settleCard();
        return top.y;
    };
    return {fake, ext, d, top, pick, ask, back, loads: () => fake.themeContext.theme.loads};
}

test('GNOME 51.1: the card stands in the middle of the screen, and the clock stays when a user is picked', async () => {
    for (const [screen, textScale] of [[1080, 1], [1152, 1], [1440, 1], [1152, 1.25]]) {
        const what = `${screen} px, text ${textScale}`;
        const g = await started({gnome: '51.1', screen, textScale});
        const listClock = g.top.y;
        const seen = g.pick();
        assert.ok(Math.abs(seen.cardMiddle - screen / 2) <= 1, `${what}: card middle ${seen.cardMiddle}`);
        assert.equal(seen.clock, listClock, `${what}: the clock stays`);
        assert.equal(g.back(), listClock, `${what}: and stays going back`);
        assert.equal(g.loads(), 1, `${what}: GNOME's own theme: nothing to set again`);
        assert.deepEqual(logged, []);
        // Said once, for the journal: where it stands, and that nothing had to be set again.
        const p = place();
        assert.deepEqual([p.top - p.wanted, p.follows, p.again, p.way, p.screen, p.scale, p.text],
            [0, true, 0, 'offset', screen, 1, textScale], `${what}: ${said[0]}`);
        assert.equal(String(p.margin), margin(g.fake), `${what}: the margin said is the one in the stylesheet`);
        assert.ok(Math.abs(p.top + p.tall / 2 - screen / 2) <= 1, `${what}: what it shows is in the middle (${said[0]})`);
        g.ext.disable();
    }
    // The line itself, as the real-boot check reads it (tests/test_login_boot_lane.py has the same one).
    const g = await started({gnome: '51.1'});
    g.pick();
    assert.equal(said[0], 'Fedora Glass login: the prompt stands 415 px down the screen, wanted 415 ' +
        '(249 px tall, margin 201, set again: 0, way: offset, screen: 1080 px, scale: 1, text: 1)');
    g.ext.disable();
});

test('a theme of someone else\'s: what is seen sets the place, the card is in the middle and the clock stays from then on', async () => {
    for (const gnome of ['51.1', '51.0', '50']) {
        for (const [screen, textScale] of [[1080, 1], [1152, 1], [1152, 1.25]]) {
            const what = `GNOME ${gnome}, ${screen} px, text ${textScale}`;
            const g = await started({gnome, screen, textScale, foreign: true});
            const seen = g.pick();
            assert.ok(Math.abs(seen.cardMiddle - screen / 2) <= 1, `${what}: card middle ${seen.cardMiddle}`);
            assert.equal(g.loads(), 2, `${what}: set again once`);
            const loads = g.loads();
            assert.equal(g.back(), seen.clock, `${what}: the clock stays going back to the list`);
            assert.equal(g.pick().clock, seen.clock, `${what}: and picking a user again`);
            assert.equal(g.loads(), loads, `${what}: looked at once`);
            assert.deepEqual(logged, []);
            // Said once, after it was set again: where it stands now is where it is wanted.
            const p = place();
            assert.deepEqual([p.follows, p.again, p.way], [true, 1, {'51.1': 'offset', '51.0': 'fixedTop', '50': 'centred'}[gnome]],
                `${what}: ${said[0]}`);
            assert.ok(Math.abs(p.top - p.wanted) <= 1, `${what}: ${said[0]}`);
            assert.equal(String(p.margin), margin(g.fake), `${what}: the margin said is the one in the stylesheet`);
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
        assert.ok(Math.abs(seen.cardMiddle - screen / 2) <= 1, `${what}: card middle ${seen.cardMiddle}`);
        // As before: where GNOME 50 rounds down and promptPlace rounds, 1 px.
        assert.ok(Math.abs(seen.clock - listClock) <= 1, `${what}: the clock stays`);
        g.ext.disable();
    }
});

test('the field comes a moment after the prompt, when GDM asks its question: looked at only then, and nothing set again', async () => {
    // On a real login screen the back button stands alone in the field's row at first, and it
    // is shorter than the field; GNOME 51's row is taller than both. Neither sets the place.
    for (const gnome of ['51.1', '51.0', '50']) {
        for (const textScale of [1, 1.25]) {
            const what = `GNOME ${gnome}, text ${textScale}`;
            const g = await started({gnome, textScale});
            const first = margin(g.fake), listClock = g.top.y;
            g.pick({ask: false});
            assert.equal(g.loads(), 1, `${what}: nothing set while the back button stands alone`);
            assert.deepEqual(said, [], `${what}: and nothing said yet`);
            const seen = g.ask();
            assert.equal(margin(g.fake), first, `${what}: the same margin with the field there`);
            assert.equal(g.loads(), 1, `${what}: the stylesheet loaded once`);
            assert.ok(Math.abs(seen.cardMiddle - 540) <= 1, `${what}: card middle ${seen.cardMiddle}`);
            // 1 px: where GNOME 50 rounds down and promptPlace rounds, as before.
            assert.ok(Math.abs(seen.clock - listClock) <= 1, `${what}: the clock stays`);
            assert.ok(Math.abs(g.back() - listClock) <= 1, `${what}: and stays going back`);
            assert.deepEqual(logged, []);
            assert.equal(place().again, 0, `${what}: ${said[0]}`);
            g.ext.disable();
        }
    }
});

test('a theme of someone else\'s with the field coming later: the place is set once the field is there', async () => {
    for (const gnome of ['51.1', '51.0', '50']) {
        const what = `GNOME ${gnome}`;
        const g = await started({gnome, foreign: true});
        g.pick({ask: false});
        assert.equal(g.loads(), 1, `${what}: nothing set before the field shows`);
        const seen = g.ask();
        assert.equal(g.loads(), 2, `${what}: set again once`);
        assert.ok(Math.abs(seen.cardMiddle - 540) <= 1, `${what}: card middle ${seen.cardMiddle}`);
        const loads = g.loads();
        assert.equal(g.back(), seen.clock, `${what}: the clock stays going back to the list`);
        assert.equal(g.pick().clock, seen.clock, `${what}: and picking a user again`);
        assert.equal(g.loads(), loads, `${what}: looked at once`);
        assert.deepEqual(logged, []);
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
    // Said once, and plainly: it stands elsewhere than wanted and takes no notice of the margin.
    const p = place();
    assert.equal(p.follows, false, said[0]);
    assert.ok(Math.abs(p.top - p.wanted) >= 2, said[0]);
    assert.equal(String(p.margin), first, said[0]);
    g.ext.disable();
});

test('GNOME 51.1 on a screen shorter than its theme\'s box and our margin: GNOME cuts the box, the card still where it belongs', async () => {
    // 600 px: under the big clock, with room for GNOME's messages under the field.
    for (const [screen, textScale, middle] of [[600, 1, 340], [720, 1, 360], [720, 1.25, 360]]) {
        const what = `${screen} px, text ${textScale}`;
        const g = await started({gnome: '51.1', screen, textScale});
        const listClock = g.top.y;
        const seen = g.pick();
        assert.notEqual(margin(g.fake), null, `${what}: our place is kept`);
        assert.ok(g.d._authPrompt.height < 550, `${what}: cut`);
        assert.ok(Math.abs(seen.cardMiddle - middle) <= 1, `${what}: card middle ${seen.cardMiddle}`);
        if (screen === 600)
            assert.ok(g.top.y + g.top.height <= g.d._authPrompt._userWell.y, `${what}: the clock above the prompt`);
        assert.equal(seen.clock, listClock, `${what}: the clock stays`);
        assert.equal(g.loads(), 1, `${what}: nothing to set again`);
        assert.deepEqual(logged, []);
        g.ext.disable();
    }
});

test('GNOME 51.1 on a screen too short for what it shows: the prompt still gets GNOME\'s own place back, once', async () => {
    const g = await started({gnome: '51.1', screen: 400});
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

test('GNOME 51.1 on a screen 768 to 864 px tall: the prompt keeps our place, the card in the middle and the clock staying', async () => {
    // Its theme's 550 px box reaches near the screen's bottom there, but under the field it
    // is empty: what GNOME shows ends far higher.
    for (const [screen, textScale] of [[768, 1], [800, 1], [864, 1], [800, 1.25], [864, 1.5]]) {
        const what = `${screen} px, text ${textScale}`;
        const g = await started({gnome: '51.1', screen, textScale});
        const listClock = g.top.y;
        const seen = g.pick();
        assert.notEqual(margin(g.fake), null, `${what}: our place is kept`);
        assert.ok(Math.abs(seen.cardMiddle - screen / 2) <= 1, `${what}: card middle ${seen.cardMiddle}`);
        assert.equal(seen.clock, listClock, `${what}: the clock stays`);
        assert.equal(g.loads(), 1, `${what}: nothing to set again`);
        assert.deepEqual(logged, []);
        g.ext.disable();
    }
});

test('GNOME 51.1 at 864 px: a long message under the field still gives the prompt GNOME\'s own place back, once', async () => {
    const g = await started({gnome: '51.1', screen: 864});
    g.pick();
    assert.notEqual(margin(g.fake), null);
    const well = g.d._authPrompt._inputWell;
    well.height = 864 - 4 - well.y;
    well.emit('notify::allocation');
    g.fake.laters.run();
    assert.equal(margin(g.fake), null, 'no room of ours above the prompt');
    assert.equal(g.loads(), 2);
    g.back();
    g.pick();
    assert.equal(g.loads(), 2, 'given back once');
    assert.deepEqual(logged, []);
    g.ext.disable();
});
