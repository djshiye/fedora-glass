// The login screen add-on as a whole (extension.js with login.js and health.js) on a fake
// greeter: what it draws and where, what the health note says, and that every way out
// (disable, an error, high contrast, a broken look.json, GNOME taking the dialog away)
// leaves GNOME's own login screen exactly as it was.
import assert from 'node:assert/strict';
import {test} from 'node:test';

import {BOOT, CSS_PATH, LOOK, LOOK_PATH, NOTE_PATH, PICTURE_PATH, RUN_PATH, TOKEN, makeGreeter, note, ours,
    registerStubs} from './login-fake.mjs';

makeGreeter();
registerStubs();
const {default: FedoraGlassLogin} =
    await import('../../fedoraglass/data/login-extension/fedora-glass-login@djshiye.github.io/extension.js');
// Loaded once here, so extension.js's own import('./login.js') lands within settle().
await import('../../fedoraglass/data/login-extension/fedora-glass-login@djshiye.github.io/login.js');

const logged = [];
console.error = (...a) => logged.push(a.join(' '));
console.warn = (...a) => logged.push(a.join(' '));

// Lets extension.js's import('./login.js') land (the loader answers on its own thread).
const settle = () => new Promise(r => setTimeout(r, 30));

/** A greeter with the add-on started on it. */
async function started(opts = {}) {
    const fake = makeGreeter(opts);
    logged.length = 0;
    const group = fake.screenShield._lockDialogGroup;
    const before = {kids: group.get_children(), handlers: group.handlerCount()};
    const ext = new FedoraGlassLogin({uuid: 'fedora-glass-login@djshiye.github.io'});
    ext.enable();
    await settle();
    return {fake, ext, group, before};
}

const layer = group => group.get_children().find(a => a.name === 'fedora-glass-login') ?? null;
const smallClock = fake => fake.panel.statusArea.dateMenu.container;

function assertPlain(fake, group, before) {
    assert.deepEqual(ours(), [], 'nothing of ours is left');
    assert.deepEqual(group.get_children(), before.kids.filter(k => !k.destroyed));
    assert.deepEqual(fake.themeContext.theme.sheets, [], 'no stylesheet of ours');
    assert.ok(!fake.fs.has(CSS_PATH), 'the stylesheet file is gone');
    assert.equal(smallClock(fake).visible, true, 'the panel\'s small clock shows');
}

test('it draws at the very bottom of the lock dialog group, takes no input, and says ok 2 s later', async () => {
    const {fake, ext, group} = await started();
    const L = layer(group);
    assert.ok(L);
    assert.equal(group.get_children().indexOf(L), 0, 'under GNOME\'s login dialog');
    assert.equal(group.get_children()[1].name, 'LoginDialog');
    for (const a of ours())
        assert.ok(!a.reactive && !a.can_focus, `${a.name} takes no input`);
    assert.equal(ours().filter(a => a.name === 'fedora-glass-login-sheet').length, 1, 'one sheet per screen');
    assert.equal(fake.bgManagers.size, 1, 'the picture: one background per screen');
    assert.deepEqual(fake.themeContext.theme.sheets, [CSS_PATH]);
    assert.ok(fake.fs.get(CSS_PATH).text.includes('.login-dialog'));
    assert.equal(smallClock(fake).visible, false, 'the big clock replaces the small one');
    const msg = ours().find(a => a.name === 'fedora-glass-login-message');
    assert.equal(msg.text, 'Hello');
    assert.equal(msg.clutter_text.use_markup, false, 'the message is plain text');
    assert.equal(note().phase, 'starting');
    fake.timeouts.run(1999);
    assert.equal(note().phase, 'starting');
    fake.timeouts.run(2000);
    assert.deepEqual(note(), {v: 1, token: TOKEN, boot: BOOT, phase: 'ok', verified: ''});
    assert.deepEqual(logged, []);
    ext.disable();
});

test('the card shows only with the password prompt, around it, and goes with it', async () => {
    const {fake, ext} = await started();
    const d = fake.screenShield._dialog;
    const card = () => ours().find(a => a.name === 'fedora-glass-login-card');
    fake.laters.run();
    assert.equal(card().visible, false, 'no card with the user list');
    d._userSelectionBox.hide();
    d._authPrompt.show();
    fake.laters.run();
    assert.equal(card().visible, true);
    d._authPrompt.hide();
    d._userSelectionBox.show();
    fake.laters.run();
    assert.equal(card().visible, false);
    ext.disable();
});

test('disable takes away every actor, signal, stylesheet and timer, and gives the small clock back', async () => {
    const {fake, ext, group, before} = await started();
    const dialog = fake.screenShield._dialog;
    const dialogHandlers = dialog.handlerCount();
    ext.disable();
    assertPlain(fake, group, before);
    assert.equal(group.handlerCount(), before.handlers);
    assert.ok(dialog.handlerCount() < dialogHandlers);
    assert.equal(dialog.handlerCount(), 0, 'nothing of ours listens to the dialog');
    assert.equal(fake.stSettings.handlerCount(), 0);
    assert.equal(fake.layoutManager.handlerCount(), 0);
    assert.equal(fake.themeContext.handlerCount(), 0);
    assert.equal(fake.bgManagers.size, 0);
    assert.equal(fake.timeouts.list.size, 0, 'no timer left');
    assert.equal(note().phase, 'ok', 'switched off on purpose before 2 s: no crash');
});

test('the last start with this look never finished: safe, nothing drawn, and safe again', async () => {
    const {fake, ext, group, before} = await started({note: {v: 1, token: TOKEN, boot: BOOT, phase: 'starting', verified: ''}});
    assertPlain(fake, group, before);
    assert.equal(note().phase, 'safe');
    ext.disable();
    ext.enable();
    await settle();
    assertPlain(fake, group, before);
    assert.equal(note().phase, 'safe', 'disable does not turn safe into ok');
    ext.disable();
    // A new look (another token) is tried again.
    const {fake: f2, ext: e2, group: g2} = await started({note: {v: 1, token: 'f'.repeat(32), boot: BOOT, phase: 'starting', verified: ''}});
    assert.ok(layer(g2));
    e2.disable();
    assert.ok(f2);
});

test('a broken look.json: error, nothing drawn, GNOME\'s login screen untouched', async () => {
    for (const look of [{...LOOK, blur: 500}, {...LOOK, accent: '#3584e4; } * { color: red'}, {...LOOK, extra: 1},
        'not json', {...LOOK, token: 'nope'}, {...LOOK, fit: 'tiled'}]) {
        const {fake, ext, group, before} = await started({look});
        assertPlain(fake, group, before);
        assert.equal(note().phase, 'error', JSON.stringify(look));
        assert.ok(logged.some(l => l.includes('no glass on the login screen')), 'the log says why');
        ext.disable();
        assert.equal(note().phase, 'error');
    }
});

test('GNOME makes its login dialog after the add-on starts: it waits, then draws', async () => {
    const {fake, ext, group} = await started({dialog: false});
    assert.equal(layer(group), null);
    assert.equal(note().phase, 'starting');
    fake.makeDialog();
    fake.laters.run();
    assert.ok(layer(group));
    assert.equal(group.get_children().indexOf(layer(group)), 0);
    fake.timeouts.run(2000);
    assert.equal(note().phase, 'ok');
    fake.timeouts.run(30000);
    assert.equal(note().phase, 'ok', 'the wait for the dialog ended with it');
    ext.disable();
});

test('no login dialog within 30 s, or one not built as expected: error and nothing drawn', async () => {
    const a = await started({dialog: false});
    a.fake.timeouts.run(30000);
    assertPlain(a.fake, a.group, a.before);
    assert.equal(note().phase, 'error');
    a.ext.disable();

    const fake = makeGreeter({dialog: false});
    const d = fake.makeDialog();
    d._authPrompt = null;
    const group = fake.screenShield._lockDialogGroup;
    const before = {kids: group.get_children()};
    const ext = new FedoraGlassLogin({});
    ext.enable();
    await settle();
    assertPlain(fake, group, before);
    assert.equal(note().phase, 'error');
    ext.disable();
});

test('a failure while building or later takes everything away and says error', async () => {
    const fake = makeGreeter();
    fake.glassFails = true;
    const group = fake.screenShield._lockDialogGroup;
    const before = {kids: group.get_children()};
    const ext = new FedoraGlassLogin({});
    ext.enable();
    await settle();
    assertPlain(fake, group, before);
    assert.equal(note().phase, 'error');
    ext.disable();

    // Later: a screen added while the glass cannot be made.
    const b = await started();
    b.fake.timeouts.run(2000);
    assert.equal(note().phase, 'ok');
    b.fake.glassFails = true;
    b.fake.layoutManager.emit('monitors-changed');
    b.fake.laters.run();
    assertPlain(b.fake, b.group, b.before);
    assert.equal(note().phase, 'error');
    assert.equal(b.fake.layoutManager.handlerCount(), 0);
    b.ext.disable();
});

test('a screen added: a sheet on each', async () => {
    const {fake, ext} = await started();
    fake.layoutManager.monitors.push({x: 1920, y: 0, width: 1920, height: 1080});
    fake.layoutManager.emit('monitors-changed');
    fake.laters.run();
    assert.equal(ours().filter(a => a.name === 'fedora-glass-login-sheet').length, 2);
    assert.equal(ours().filter(a => a.name === 'fedora-glass-login').length, 1, 'still one layer');
    assert.equal(fake.bgManagers.size, 2);
    ext.disable();
});

test('a successful password check is written down; the phase stays', async () => {
    const {fake, ext} = await started();
    fake.timeouts.run(2000);
    fake.screenShield._dialog._authPrompt._userVerifier.emit('verification-complete');
    assert.deepEqual(note(), {v: 1, token: TOKEN, boot: BOOT, phase: 'ok', verified: TOKEN});
    ext.disable();
    assert.equal(note().verified, TOKEN);
});

test('high contrast: nothing of ours, followed live both ways', async () => {
    const {fake, ext, group, before} = await started();
    fake.stSettings.high_contrast = true;
    fake.stSettings.emit('notify::high-contrast');
    fake.laters.run();
    assertPlain(fake, group, before);
    fake.stSettings.high_contrast = false;
    fake.stSettings.emit('notify::high-contrast');
    fake.laters.run();
    assert.ok(layer(group));
    assert.deepEqual(fake.themeContext.theme.sheets, [CSS_PATH]);
    ext.disable();
    const hc = await started({highContrast: true});
    assertPlain(hc.fake, hc.group, hc.before);
    hc.fake.timeouts.run(2000);
    assert.equal(note().phase, 'ok', 'drawing nothing on purpose is no failure');
    hc.ext.disable();
});

test('a theme reload gets our stylesheet once, never twice', async () => {
    const {fake, ext} = await started();
    const theme = {...fake.themeContext.theme, sheets: [CSS_PATH]};
    fake.themeContext.theme = theme;
    fake.themeContext.emit('changed');
    assert.deepEqual(theme.sheets, [CSS_PATH]);
    const fresh = {...fake.themeContext.theme, sheets: []};
    fake.themeContext.theme = fresh;
    fake.themeContext.emit('changed');
    assert.deepEqual(fresh.sheets, [CSS_PATH]);
    ext.disable();
    assert.deepEqual(fresh.sheets, []);
});

test('GNOME taking its login dialog or the whole group away leaves nothing behind and no error', async () => {
    const a = await started();
    a.fake.screenShield._dialog.destroy();
    assert.deepEqual(ours(), []);
    assert.deepEqual(a.fake.themeContext.theme.sheets, []);
    assert.notEqual(note().phase, 'error');
    a.ext.disable();

    // GNOME Shell shutting down: the stage goes, our layer first (it is the bottom child).
    const b = await started();
    b.fake.timeouts.run(2000);
    globalThis.global.emitShell('shutdown');
    b.group.get_parent().destroy();
    assert.deepEqual(ours(), []);
    assert.equal(b.fake.bgManagers.size, 0);
    assert.equal(note().phase, 'ok', 'a clean stop is no crash');
    assert.deepEqual(logged, []);
    b.ext.disable();
});

test('a slow start that lands after disable draws nothing', async () => {
    const fake = makeGreeter();
    const ext = new FedoraGlassLogin({});
    ext.enable();
    ext.disable();
    await settle();
    assert.deepEqual(ours(), []);
    assert.equal(fake.themeContext.theme.sheets.length, 0);
    assert.ok(fake.fs.has(LOOK_PATH));
});

test('no look.json at all (switched off): nothing drawn, nothing written, nothing logged as a problem', async () => {
    const {fake, ext, group, before} = await started({look: null, note: {v: 1, token: TOKEN, boot: BOOT, phase: 'ok', verified: ''}});
    assertPlain(fake, group, before);
    assert.deepEqual(note(), {v: 1, token: TOKEN, boot: BOOT, phase: 'ok', verified: ''}, 'the old note is left as it was');
    assert.ok(!fake.fs.has(RUN_PATH));
    assert.deepEqual(fake.writes, []);
    assert.deepEqual(logged, []);
    globalThis.global.emitShell('shutdown');
    ext.disable();
    assert.deepEqual(fake.writes, []);
});

const sheets = () => ours().filter(a => a.name === 'fedora-glass-login-sheet');

test('no glass before the picture has loaded; not loaded in time: the glow instead, and still ok', async () => {
    const fake = makeGreeter();
    fake.bgNeverLoads = true;
    logged.length = 0;
    const ext = new FedoraGlassLogin({});
    ext.enable();
    await settle();
    assert.equal(sheets().length, 1);
    assert.ok(sheets().every(s => !s.visible), 'the sheet waits for the picture');
    fake.screenShield._dialog._userSelectionBox.hide();
    fake.screenShield._dialog._authPrompt.show();
    fake.laters.run();
    assert.equal(ours().find(a => a.name === 'fedora-glass-login-card').visible, false, 'no card on no glass');
    fake.timeouts.run(4000);
    fake.laters.run();
    await settle();
    assert.equal(fake.bgManagers.size, 0, 'the glow needs no picture');
    assert.ok(sheets().length === 1 && sheets().every(s => s.visible), 'the glow shows');
    assert.ok(logged.some(l => l.includes('did not load within')));
    fake.timeouts.run(2000);
    assert.equal(note().phase, 'ok', 'a picture that will not load is no failure of the add-on');
    ext.disable();
});

test('a picture that does not decode: the glow at once', async () => {
    const fake = makeGreeter();
    fake.fs.set(PICTURE_PATH, {text: '\xff\xd8\xff garbage'});
    logged.length = 0;
    const ext = new FedoraGlassLogin({});
    ext.enable();
    await settle();
    fake.laters.run();
    await settle();
    assert.equal(fake.bgManagers.size, 0);
    assert.ok(sheets().every(s => s.visible));
    assert.ok(logged.some(l => l.includes('does not decode')));
    ext.disable();
    // The greeter's own picture is not judged by us (GNOME may read formats we cannot).
    const sys = makeGreeter({look: {...LOOK, picture: 'system'}});
    sys.fs.set(PICTURE_PATH, {text: 'a format only GNOME reads'});
    const es = new FedoraGlassLogin({});
    es.enable();
    await settle();
    assert.equal(sys.bgManagers.size, 1);
    assert.ok(sheets().every(s => s.visible));
    es.disable();
    // A picture that loads shows the sheet as soon as it has.
    const ok = await started();
    assert.ok(sheets().every(s => s.visible));
    assert.equal(ok.fake.bgManagers.size, 1);
    ok.ext.disable();
});

test('two screens: each sheet sees its own picture mirrored over the seam, unless it is spanned', async () => {
    const fake = makeGreeter();
    fake.layoutManager.monitors = [{x: 0, y: 0, width: 960, height: 1080}, {x: 960, y: 0, width: 960, height: 1080}];
    const ext = new FedoraGlassLogin({});
    ext.enable();
    await settle();
    const sources = ours().filter(a => a.name === 'fedora-glass-login-source');
    assert.equal(sources.length, 2);
    const [left, right] = sources.map(s => s.get_children()).sort((a, b) => a[0].get_clip()[0] - b[0].get_clip()[0]);
    // The left screen: itself, and its right edge mirrored over x = 960.
    assert.deepEqual(left.map(c => [c.x, c.scale_x ?? 1, c.get_clip()]),
        [[0, 1, [0, 0, 960, 1080]], [1920, -1, [832, 0, 128, 1080]]]);
    assert.deepEqual(right.map(c => [c.x, c.scale_x ?? 1, c.get_clip()]),
        [[0, 1, [960, 0, 960, 1080]], [1920, -1, [960, 0, 128, 1080]]]);
    ext.disable();

    const f2 = makeGreeter();
    f2.layoutManager.monitors = [{x: 0, y: 0, width: 960, height: 1080}, {x: 960, y: 0, width: 960, height: 1080}];
    f2.gsettings['org.gnome.desktop.background']['picture-options'] = 'spanned';
    const e2 = new FedoraGlassLogin({});
    e2.enable();
    await settle();
    assert.equal(ours().filter(a => a.name === 'fedora-glass-login-source').length, 0, 'spanned: the picture as it is');
    assert.equal(sheets().length, 2);
    e2.disable();
});

test('the card hugs what the prompt shows, and grows smoothly with a message', async () => {
    const {fake, ext} = await started();
    const d = fake.screenShield._dialog, prompt = d._authPrompt;
    const card = ours().find(a => a.name === 'fedora-glass-login-card');
    const placed = [];
    card.place = (...a) => placed.push(a.slice(0, 4));
    d._userSelectionBox.hide();
    prompt.show();
    fake.laters.run();
    // Content: avatar 400..528, entry row 540..580, from x 800 to 1120; 28 px all round.
    assert.deepEqual(placed.at(-1), [772, 372, 376, 236]);
    fake.now = 0;
    prompt._message.text = 'Sorry, that didn’t work. Please try again.';
    fake.laters.run();
    assert.ok(fake.timeouts.list.size > 0, 'it eases');
    fake.now = 80000;
    fake.timeouts.run(16);
    const mid = placed.at(-1)[3];
    assert.ok(mid > 236 && mid < 296, `half way: ${mid}`);
    fake.now = 200000;
    fake.timeouts.run(16);
    assert.deepEqual(placed.at(-1), [772, 372, 376, 296], 'to the message’s foot (640) + 28');
    prompt._message.text = '';
    fake.laters.run();
    fake.now = 400000;
    fake.timeouts.run(16);
    assert.deepEqual(placed.at(-1), [772, 372, 376, 236]);
    ext.disable();
});

test('crash loops later than 2 s: two unclean ends in a row in one boot give safe; a clean end resets', async () => {
    let fs = null;
    // One run of the login screen: killed (no shutdown, no disable) or ended cleanly.
    const run = async (end, opts = {}) => {
        const fake = makeGreeter(opts);
        if (fs) {
            fake.fs.clear();
            for (const [k, v] of fs) fake.fs.set(k, v);
        }
        const ext = new FedoraGlassLogin({});
        ext.enable();
        await settle();
        fake.timeouts.run(2000);
        const drawn = ours().length > 0;
        const phase = note().phase;
        if (end === 'verified')
            fake.screenShield._dialog._authPrompt._userVerifier.emit('verification-complete');
        if (end === 'clean' || end === 'verified')
            globalThis.global.emitShell('shutdown');
        fs = new Map(fake.fs);
        if (end === 'clean')
            ext.disable();   // what a clean stop also does
        return {drawn, phase};
    };
    assert.deepEqual(await run('kill'), {drawn: true, phase: 'ok'});
    assert.deepEqual(await run('kill'), {drawn: true, phase: 'ok'}, 'one bad end is not a loop');
    assert.deepEqual(await run('clean'), {drawn: false, phase: 'safe'}, 'two in a row: safe');
    assert.deepEqual(await run('clean'), {drawn: false, phase: 'safe'}, 'safe sticks for this boot');
    const run_ = JSON.parse(fs.get(RUN_PATH).text);
    assert.equal(fs.get(RUN_PATH).mode, 0o600, 'private to the greeter');
    assert.deepEqual(Object.keys(run_).sort(), ['boot', 'clean', 'token', 'unclean', 'v', 'verified']);
    assert.deepEqual(Object.keys(JSON.parse(fs.get(NOTE_PATH).text)).sort(), ['boot', 'phase', 'token', 'v', 'verified'],
        'health.json keeps its five keys');

    // A clean end between two kills: never a loop. A login that worked: never counts.
    fs = null;
    for (const end of ['kill', 'clean', 'kill', 'verified', 'kill', 'clean'])
        assert.equal((await run(end)).drawn, true, end);
    // A new boot starts the count again.
    fs = null;
    await run('kill');
    await run('kill');
    fs.set('/proc/sys/kernel/random/boot_id', {text: '99999999-8888-7777-6666-555555555555\n'});
    const next = await run('clean');
    assert.equal(next.drawn, true);
});
