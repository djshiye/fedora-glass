// The login screen add-on's look (style.js): look.json is checked again field by field,
// and only checked colours and numbers ever reach the stylesheet.
import assert from 'node:assert/strict';
import {test} from 'node:test';

const S = await import('../../fedoraglass/data/login-extension/fedora-glass-login@djshiye.github.io/style.js');

const GOOD = Object.freeze({version: 1, token: '0123456789abcdef0123456789abcdef', accent: '#3584e4', tint: '#1e1e2a',
    tint_amount: 0.2, frost: 0.35, blur: 60, dim: 0.28, card: true, clock: 'bold', picture: 'wallpaper',
    fit: 'zoom', battery: true, message: ''});
const with_ = o => ({...GOOD, ...o});
const refused = raw => S.checkLook(raw).look === null;

// Strings a hostile or broken file could carry, aimed at CSS, markup and the shell.
const HOSTILE = ['}', '{', ';', '#3584e4;}', '#3584e4 }* {color:red', 'red', 'url(x)', '#12345', '#1234567',
    '#12345g', ' #3584e4', '#3584e4 ', '#3584e4\n', '/*', '*/', '<b>', '"', "'", '\\', '\u0000', '‮',
    'expression(alert(1))', '@import "x";', '-st-accent-color', 'rgba(0,0,0,1)', '', '0x3584e4'];

test('the defaults of the contract pass, and come back clean', () => {
    const {look, problem} = S.checkLook({...GOOD});
    assert.equal(problem, '');
    assert.deepEqual(look, {...GOOD});
    assert.equal(S.checkLook(with_({accent: '#3584E4'})).look.accent, '#3584e4');
});

test('every bound of the contract holds, edges included', () => {
    for (const ok of [{tint_amount: 0}, {tint_amount: 1}, {frost: 0}, {frost: 1}, {dim: 0}, {dim: 0.65},
        {blur: 10}, {blur: 100}, {clock: 'gnome'}, {clock: 'thin'}, {picture: 'system'}, {picture: 'glow'},
        {card: false}, {battery: false}, {fit: 'spanned'}, {fit: 'scaled'}, {fit: 'stretched'}, {fit: 'centered'},
        {fit: 'wallpaper'}, {message: 'x'.repeat(120)}, {message: 'é'.repeat(120)},
        {message: 'Ünïcödé 🙂 ok'}])
        assert.ok(!refused(with_(ok)), JSON.stringify(ok));
    for (const bad of [{tint_amount: -0.01}, {tint_amount: 1.01}, {frost: 2}, {dim: 0.66}, {dim: -1},
        {blur: 9}, {blur: 101}, {blur: 60.5}, {blur: '60'}, {dim: '0.2'}, {dim: NaN}, {dim: Infinity},
        {dim: null}, {card: 'true'}, {card: 1}, {battery: null}, {clock: 'middle'}, {clock: 'Bold'},
        {picture: 'file:///etc/shadow'}, {fit: 'none'}, {fit: 'Spanned'}, {fit: ''}, {fit: null}, {fit: 1}, {message: 'x'.repeat(121)}, {message: 'a\nb'}, {message: 'tab\there'},
        {message: '\u007f'}, {message: '\u0085'}, {message: 5}, {message: null}, {version: 2}, {version: '1'},
        {token: 'ABCDEF0123456789abcdef0123456789'}, {token: '0123'}, {token: `${'0'.repeat(32)}\n`}])
        assert.ok(refused(with_(bad)), JSON.stringify(bad));
});

test('a missing key, an extra key or not an object is refused whole', () => {
    for (const k of Object.keys(GOOD).filter(k => k !== 'fit')) {
        const raw = {...GOOD};
        delete raw[k];
        assert.ok(refused(raw), k);
    }
    // fit came later: a look.json without it is GNOME's default placing, zoom.
    const raw = {...GOOD};
    delete raw.fit;
    assert.equal(S.checkLook(raw).look.fit, 'zoom');
    assert.ok(refused(with_({style: 'x'})));
    assert.ok(refused(with_({__proto__: {x: 1}, css: '}'})));
    for (const raw of [null, undefined, 1, 'x', [], [GOOD]])
        assert.ok(refused(raw));
});

test('hostile strings in any field are refused before any CSS is made', () => {
    for (const k of Object.keys(GOOD).filter(k => k !== 'message')) {
        for (const h of HOSTILE)
            assert.ok(refused(with_({[k]: h})), `${k} = ${JSON.stringify(h)}`);
    }
});

test('the message never reaches the stylesheet; hostile ones without control characters are plain text', () => {
    for (const h of HOSTILE) {
        const {look} = S.checkLook(with_({message: h}));
        if (!look) {
            assert.match(h, /[\u0000-\u001f]/u);
            continue;
        }
        // The same stylesheet as with no message at all.
        assert.equal(S.stylesheet(look), S.stylesheet({...GOOD}), JSON.stringify(h));
    }
    const look = S.checkLook(with_({message: 'MESSAGE-MARK'})).look;
    assert.ok(!S.stylesheet(look).includes('MESSAGE-MARK'));
    assert.ok(!JSON.stringify(S.glowStyles(look)).includes('MESSAGE-MARK'));
});

test('stylesheet() itself refuses unchecked colours and numbers (a second wall)', () => {
    for (const h of HOSTILE)
        assert.throws(() => S.stylesheet(with_({accent: h})), JSON.stringify(h));
    for (const f of [NaN, Infinity, '0.3', null, undefined, {}])
        assert.throws(() => S.stylesheet(with_({frost: f})), String(f));
    assert.throws(() => S.glowStyles(with_({tint: 'red'})));
    assert.throws(() => S.glassValues(with_({tint: '#12345'})));
    // The room above the prompt: a plain number of px or nothing, never text.
    for (const m of [NaN, Infinity, '155', '155px; } * { color: red', {}, [155], true])
        assert.throws(() => S.stylesheet({...GOOD}, {margin: m}), String(m));
    for (const [m, px] of [[155, 155], [154.6, 155], [0, 0], [-20, 0], [9999, 600]])
        assert.match(S.stylesheet({...GOOD}, {margin: m}), new RegExp(`prompt-layout {[^}]*margin-top: ${px}px;`));
    assert.ok(!S.stylesheet({...GOOD}).includes('margin-top'), 'no place given: GNOME\'s own');
    // GNOME 50 gives the box inside its prompt the prompt's class: the room is not for that one.
    assert.match(S.stylesheet({...GOOD}, {margin: 155}),
        /\.login-dialog \.login-dialog-prompt-layout \.login-dialog-prompt-layout {\s*margin-top: 0px; }/);
});

test('only #rrggbb colours and plain numbers are put into the stylesheet', () => {
    const fuzz = [];
    for (let i = 0; i < 300; i++) {
        const hex = () => `#${Math.floor(Math.random() * 0x1000000).toString(16).padStart(6, '0')}`;
        fuzz.push(with_({accent: hex(), tint: hex(), frost: Math.random(), tint_amount: Math.random(),
            dim: Math.random() * 0.65, blur: 10 + Math.floor(Math.random() * 91)}));
    }
    for (const raw of [GOOD, with_({frost: 0}), with_({frost: 1}), with_({card: false}), ...fuzz]) {
        const {look} = S.checkLook(raw);
        assert.ok(look);
        const css = S.stylesheet(look, {margin: Math.random() < 0.5 ? null : Math.random() * 400});
        // Every value: a #rrggbb, an rgba() of numbers, a number with a unit, or a fixed word.
        for (const [, value] of css.matchAll(/:\s*([^;{}]+);/g)) {
            const v = value.replace(/!important/, '').trim();
            assert.match(v, /^(#[0-9a-f]{6}|rgba\(\d{1,3}, \d{1,3}, \d{1,3}, [01]\.\d{3}\)|transparent|none|vertical|center|[\d.]+(px|em)?|-?\d+px( -?\d+px)*( \d+px)?( #[0-9a-f]{6}| rgba\([^)]*\))?|\d+px solid (rgba\([^)]*\)|transparent)|inset 0 0 0 [12]px rgba\([^)]*\)|0 \d+px \d+px rgba\([^)]*\)|0 1px 3px rgba\([^)]*\))$/,
                `${v} in ${JSON.stringify(raw)}`);
        }
        // Braces balance: nothing closed a rule early.
        assert.equal((css.match(/{/g) ?? []).length, (css.match(/}/g) ?? []).length);
        for (const v of Object.values(S.glowStyles(look)))
            assert.ok(!/[{}]/.test(v));
    }
});

test('the stylesheet keeps to the login screen and makes every text white on the glass', () => {
    const css = S.stylesheet(S.checkLook({...GOOD}).look);
    for (const [, selectors] of css.matchAll(/(?:^|})\s*([^{}]+){/g)) {
        for (const sel of selectors.split(',').map(s => s.trim()).filter(s => s && !s.startsWith('/*')))
            assert.match(sel, /^(\.login-dialog\b|#panel\.login-screen\b)/, sel);
    }
    assert.match(css, /\.login-dialog {[^}]*color: #ffffff;/);
    assert.match(css, /\.login-dialog \.login-dialog-prompt-entry {[^}]*border-radius: 999px;[^}]*min-width: 14em;/);
    assert.match(css, /\.login-dialog \.login-dialog-prompt-entry:focus {[^}]*box-shadow: inset 0 0 0 2px rgba\(53, 132, 228, 0\.850\) !important;/);
    assert.ok(!css.includes('#lockDialogGroup'), 'the backdrop is the glass, not a painted colour');
});

test('on the card a user is a quiet row that lights up; without the card each user is a pane', () => {
    const ROW = '.login-dialog .login-dialog-user-list-view .login-dialog-user-list .login-dialog-user-list-item';
    const rule = (css, sel) => {
        const at = css.indexOf(`${sel} {`);
        assert.ok(at >= 0 && (at === 0 || css[at - 1] === '\n'), sel);
        return css.slice(at, css.indexOf('}', at));
    };
    const card = S.stylesheet({...GOOD});
    assert.match(rule(card, ROW), /background-color: transparent;[^}]*border: 1px solid transparent;[^}]*box-shadow: none;/);
    // Chosen (GNOME gives the first user the focus): a white light and a clear white
    // rim, and GNOME's accent ring is taken off. No accent colour on a row at all.
    const chosen = rule(card, `${ROW}:focus`);
    assert.match(chosen, /background-color: rgba\(255, 255, 255, 0\.120\);/);
    assert.match(chosen, /box-shadow: none !important;/);
    assert.ok(card.includes(`${ROW}:selected,\n${ROW}:focus {`));
    // The row that has the keyboard is never mistaken for one that is only pointed at:
    // that one has no rim at all and less light; this one has a rim anyone can see.
    const alpha = (text, prop) => Number(text.match(new RegExp(`${prop}: rgba\\(255, 255, 255, ([0-9.]+)\\)`))?.[1]);
    const pointed = rule(card, `${ROW}:hover`);
    assert.ok(!pointed.includes('border'), 'no rim under the pointer alone');
    assert.ok(alpha(chosen, 'border-color') >= 0.35 && alpha(chosen, 'border-top-color') >= 0.5);
    assert.ok(alpha(chosen, 'background-color') >= alpha(pointed, 'background-color') + 0.04);
    const link = rule(card, '.login-dialog .login-dialog-not-listed-button:focus:hover');
    assert.ok(card.includes('.login-dialog .login-dialog-not-listed-button:focus,\n.login-dialog .login-dialog-not-listed-button:focus:hover {'));
    assert.ok(Number(link.match(/inset 0 0 0 1px rgba\(255, 255, 255, ([0-9.]+)\) !important/)?.[1]) >= 0.4, link);
    const plain = S.stylesheet(with_({card: false}));
    for (const css of [card, plain]) {
        for (const [, selectors, body] of css.matchAll(/([^{}]+){([^}]*)}/g)) {
            if (selectors.includes('login-dialog-user-list-item') || selectors.includes('not-listed'))
                assert.ok(!body.includes('#3584e4'), selectors);
        }
    }
    assert.match(rule(plain, ROW), /background-gradient-direction: vertical;[^}]*border-radius: 18px;[^}]*box-shadow: 0 8px 24px/);
    assert.match(rule(plain, `${ROW}:focus`), /border-color: rgba\(255, 255, 255, 0\.460\);[^}]*box-shadow: 0 8px 24px rgba\(0, 0, 0, 0\.28\) !important;/);
    assert.ok(!rule(plain, `${ROW}:focus`).includes('#3584e4'));
    // "Not listed?" is a line of text as wide as the rows, in both; the list and the
    // prompt are as wide as each other, and the list stands in the middle of its box.
    for (const css of [card, plain]) {
        assert.match(rule(css, '.login-dialog .login-dialog-not-listed-button'),
            /width: 25em;[^}]*background-color: transparent;[^}]*border-width: 0;/);
        assert.match(css, /\.login-dialog \.login-dialog-not-listed-label {[^}]*text-align: center;/);
        assert.match(css, /\.login-dialog \.login-dialog-prompt-layout {[^}]*width: 25em;[^}]*min-width: 25em;/);
        assert.match(css, /\.login-dialog \.login-dialog-user-selection-box {\s*padding-top: 4em;\s*padding-bottom: 4em; }/);
    }
    // The keyboard's place stays plain to see on the field and the buttons: the accent.
    assert.match(rule(card, '.login-dialog .login-dialog-button.cancel-button:focus'), /border-color: #3584e4;/);
});

test('the room above GNOME\'s prompt brings what it shows to the middle of the screen', () => {
    // GNOME 51+: the prompt's top is 275 px above the middle; 240 px of content go 120 above it.
    assert.deepEqual(S.promptPlace({fixedTop: true}), {margin: 155, content: 240, top: 420});
    assert.deepEqual(S.promptPlace(), {margin: 155, content: 240, top: 420});
    assert.deepEqual(S.promptPlace({screen: 1440}), {margin: 155, content: 240, top: 600});
    // A scale factor of 2: GNOME's 275 are stage px, a stylesheet's px are doubled.
    assert.deepEqual(S.promptPlace({fixedTop: true, scale: 2, screen: 2160}), {margin: 18, content: 240, top: 841});
    // Large text: the name and the field grow, the avatar does not.
    assert.deepEqual(S.promptPlace({fixedTop: true, textScale: 1.25}), {margin: 143, content: 264, top: 408});
    // GNOME 50 centres the prompt with the room under its field: as much above it.
    assert.deepEqual(S.promptPlace({fixedTop: false}), {margin: 67, content: 236, top: 422});
    assert.equal(S.promptPlace({fixedTop: false, scale: 2, screen: 2160}).margin, 67);
    // Never a value that is not a sane number of px.
    for (const bad of [{scale: NaN}, {textScale: '1'}, {scale: null}, {screen: '1080'}, {above: NaN}])
        assert.throws(() => S.promptPlace(bad), JSON.stringify(bad));
    assert.equal(S.promptPlace({fixedTop: true, scale: 0.01}).margin, 155, 'a scale under 1 counts as 1');
    assert.equal(S.promptPlace({fixedTop: true, textScale: 3, scale: 4}).margin, 0, 'never under 0');
});

test('on a short screen the prompt stands under the big clock, while GNOME\'s messages still fit', () => {
    // 330 px for the clock: more than the middle leaves on 864 and 768 px.
    for (const fixedTop of [true, false]) {
        const tall = S.promptPlace({fixedTop, screen: 1080, above: 330});
        assert.equal(tall.top, fixedTop ? 420 : 422, 'room enough: in the middle');
        for (const screen of [864, 768]) {
            const p = S.promptPlace({fixedTop, screen, above: 330});
            assert.equal(p.top, 330, `${screen}, fixedTop ${fixedTop}`);
            // As GNOME then places it: 51 from its fixed top, 50 centred with its room.
            const got = fixedTop ? screen / 2 - 275 + p.margin
                : screen / 2 - (p.margin + p.content + 67) / 2 + p.margin;
            assert.equal(got, 330);
        }
        // Too short for the clock, the prompt and the room for messages: the middle (the clock gives way).
        const short = S.promptPlace({fixedTop, screen: 600, above: 330});
        assert.equal(short.top, fixedTop ? 180 : 182);
    }
    assert.deepEqual(S.promptPlace({screen: 864, above: 330}), {margin: 173, content: 240, top: 330});
    assert.deepEqual(S.promptPlace({fixedTop: false, screen: 864, above: 330}), {margin: 99, content: 236, top: 330});
});

test('GNOME\'s own place for the prompt: no margin of ours, and a guess of where it then begins', () => {
    // GNOME 51: its fixed top (275 px above the middle) and its theme's 80 px.
    assert.deepEqual(S.promptPlace({own: true}), {margin: null, content: 240, top: 345});
    assert.deepEqual(S.promptPlace({own: true, screen: 720, above: 330}), {margin: null, content: 240, top: 165});
    assert.deepEqual(S.promptPlace({own: true, scale: 2, screen: 2160}), {margin: null, content: 240, top: 965});
    // GNOME 50: what it shows and the room under it, centred.
    assert.deepEqual(S.promptPlace({own: true, fixedTop: false}), {margin: null, content: 236, top: 389});
    // It is always higher than ours, so more of what GNOME shows under the field fits.
    for (const fixedTop of [true, false]) {
        for (const screen of [600, 720, 768, 864, 1080, 1440])
            assert.ok(S.promptPlace({own: true, fixedTop, screen}).top < S.promptPlace({fixedTop, screen, above: 330}).top, `${fixedTop} ${screen}`);
    }
    // And the stylesheet then says nothing about the prompt's place.
    assert.ok(!S.stylesheet({...GOOD}, {margin: S.promptPlace({own: true}).margin}).includes('margin-top'));
});

test('frost makes the panes more solid, with the painted login screen\'s numbers', () => {
    const at = f => S.stylesheet(S.checkLook(with_({frost: f})).look);
    assert.ok(at(0).includes('background-color: rgba(255, 255, 255, 0.070);'));
    assert.ok(at(1).includes('background-color: rgba(255, 255, 255, 0.140);'));
    assert.ok(at(1).includes('border-top-color: rgba(255, 255, 255, 0.300);'));
});

test('the glass values follow the lock screen\'s maths', () => {
    const v = S.glassValues(S.checkLook(with_({dim: 0.28, tint_amount: 0.2, tint: '#ff8000', blur: 60})).look);
    assert.deepEqual(v, {blur: 60, dim: 0.72, tint: [1, 0.502, 0, 0.08000000000000002]});
    // Never darker than the lock screen allows, never more tint than 0.6 (1 * 0.4 here).
    const edge = S.glassValues(S.checkLook(with_({dim: 0.65, tint_amount: 1})).look);
    assert.equal(edge.dim, 0.35);
    assert.equal(edge.tint[3], 0.4);
});

test('the glow picture is made from the tint and the accent only', () => {
    const g = S.glowStyles(S.checkLook(with_({tint: '#000000', accent: '#ffffff'})).look);
    assert.match(g.base, /background-gradient-direction: vertical;/);
    assert.match(g.glow, /background-gradient-direction: radial;/);
    assert.match(g.glow, /rgba\(255, 255, 255, 0\.550\)/);
    assert.equal(S.mix('#000000', '#ffffff', 0.5), '#808080');
});
