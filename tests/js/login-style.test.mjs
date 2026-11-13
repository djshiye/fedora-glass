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
});

test('only #rrggbb colours and plain numbers are put into the stylesheet', () => {
    const fuzz = [];
    for (let i = 0; i < 300; i++) {
        const hex = () => `#${Math.floor(Math.random() * 0x1000000).toString(16).padStart(6, '0')}`;
        fuzz.push(with_({accent: hex(), tint: hex(), frost: Math.random(), tint_amount: Math.random(),
            dim: Math.random() * 0.65, blur: 10 + Math.floor(Math.random() * 91)}));
    }
    for (const raw of [GOOD, with_({frost: 0}), with_({frost: 1}), ...fuzz]) {
        const {look} = S.checkLook(raw);
        assert.ok(look);
        const css = S.stylesheet(look);
        // Every value: a #rrggbb, an rgba() of numbers, or a number with a unit.
        for (const [, value] of css.matchAll(/:\s*([^;{}]+);/g)) {
            const v = value.replace(/!important/, '').trim();
            assert.match(v, /^(#[0-9a-f]{6}|rgba\(\d{1,3}, \d{1,3}, \d{1,3}, [01]\.\d{3}\)|transparent|none|vertical|[\d.]+(px|em)?|-?\d+px( -?\d+px)*( \d+px)?( #[0-9a-f]{6}| rgba\([^)]*\))?|\d+px solid rgba\([^)]*\)|inset 0 0 0 2px rgba\([^)]*\)|0 \d+px \d+px rgba\([^)]*\)|0 1px 3px rgba\([^)]*\))$/,
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
