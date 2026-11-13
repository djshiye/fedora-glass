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

test('one card: around the user list, then around the prompt, and it waits while GNOME brings the prompt', async () => {
    const {fake, ext} = await started();
    const d = fake.screenShield._dialog, prompt = d._authPrompt;
    const card = ours().find(a => a.name === 'fedora-glass-login-card');
    const placed = [];
    card.place = (...a) => placed.push(a.slice(0, 4));
    const settleCard = () => {
        fake.laters.run();
        fake.now = (fake.now ?? 0) + 300000;
        fake.timeouts.run(16);
    };
    // The picture has loaded: the layer came up softly, with the card around the user list.
    const L = ours().find(a => a.name === 'fedora-glass-login');
    assert.deepEqual([L.opacity, L.eased.duration], [255, 400]);
    d._userList.emit('notify::allocation');
    fake.laters.run();
    assert.equal(card.visible, true, 'a card with the user list');
    // The row 780..1140 x 500..580 and "Not listed?" down to 616; 28 px all round.
    assert.deepEqual(placed.at(-1), [752, 472, 416, 172]);
    assert.equal(card.opacity, 255);

    // A user is chosen: GNOME hides the list, asks GDM, and only then shows the prompt.
    d._userSelectionBox.hide();
    fake.laters.run();
    assert.equal(card.visible, true, 'the card waits where it is');
    assert.deepEqual(placed.at(-1), [752, 472, 416, 172]);
    prompt.opacity = 0;     // GNOME fades it in from nothing
    prompt.show();
    fake.laters.run();
    assert.deepEqual([card.visible, placed.at(-1)], [true, [752, 472, 416, 172]], 'nothing of the prompt is seen yet: still waiting');
    prompt.opacity = 40;
    prompt.emit('notify::opacity');
    fake.laters.run();
    assert.deepEqual([card.visible, card.opacity], [true, 255], 'it stood already: it only changes its shape');
    assert.ok([...fake.timeouts.list.values()].every(t => t.ms !== 1000), 'the wait is over');
    fake.now = (fake.now ?? 0) + 125000;
    fake.timeouts.run(16);
    const half = placed.at(-1)[3];
    assert.ok(half > 172 && half < 260, `on its way: ${half}`);
    settleCard();
    // The avatar 400..528 and the entry row 540..580, x 800..1120: 40 px above and below, 28 beside.
    assert.deepEqual(placed.at(-1), [772, 360, 376, 260]);

    // Back to the list: to its shape again.
    prompt.hide();
    d._userSelectionBox.show();
    settleCard();
    assert.deepEqual([card.visible, placed.at(-1)], [true, [752, 472, 416, 172]]);

    // Nothing comes after the list went (a login by other means): the card goes after a second.
    d._userSelectionBox.hide();
    fake.laters.run();
    assert.equal(card.visible, true);
    fake.timeouts.run(999);
    fake.laters.run();
    assert.equal(card.visible, true);
    fake.timeouts.run(1000);
    fake.laters.run();
    assert.equal(card.visible, false);

    // A prompt coming from nothing: no card while nothing of it is seen, then the card
    // comes up with it.
    prompt.opacity = 0;
    prompt.show();
    fake.laters.run();
    assert.equal(card.visible, false);
    prompt.opacity = 128;
    prompt.emit('notify::opacity');
    fake.laters.run();
    assert.deepEqual([card.visible, card.opacity, placed.at(-1)], [true, 128, [772, 360, 376, 260]]);
    prompt.opacity = 255;
    prompt.emit('notify::opacity');
    fake.laters.run();
    assert.equal(card.opacity, 255);

    // A prompt that stays in its place but is not seen any more: no empty card is left
    // standing, it goes after the same second.
    prompt.opacity = 0;
    prompt.emit('notify::opacity');
    fake.laters.run();
    assert.equal(card.visible, true);
    fake.timeouts.run(1000);
    fake.laters.run();
    assert.equal(card.visible, false, 'no card around nothing');
    ext.disable();
    assert.equal(fake.timeouts.list.size, 0, 'no timer left');
});

test('a card that waits is let go of with everything else', async () => {
    const {fake, ext} = await started();
    fake.laters.run();
    fake.screenShield._dialog._userSelectionBox.hide();
    fake.laters.run();
    assert.ok([...fake.timeouts.list.values()].some(t => t.ms === 1000), 'it waits');
    ext.disable();
    assert.equal(fake.timeouts.list.size, 0);
    assert.deepEqual(ours(), []);
});

test('without the card: no card anywhere, and GNOME\'s prompt still stands in the middle', async () => {
    const {fake, ext} = await started({look: {...LOOK, card: false}});
    fake.laters.run();
    assert.equal(ours().find(a => a.name === 'fedora-glass-login-card'), undefined);
    assert.match(fake.fs.get(CSS_PATH).text, /prompt-layout {[^}]*margin-top: 155px;/);
    ext.disable();
});

test('the room above the prompt is GNOME 51\'s or GNOME 50\'s, and follows scale and large text', async () => {
    const margin = fake => Number(/prompt-layout {[^}]*margin-top: (\d+)px;/.exec(fake.fs.get(CSS_PATH).text)[1]);
    const a = await started();
    assert.equal(margin(a.fake), 155, 'GNOME 51: a fixed top');
    // The screen is scaled by 2 from now on: everything is built again with it.
    a.fake.themeContext.scale_factor = 2;
    a.fake.layoutManager.emit('monitors-changed');
    a.fake.laters.run();
    assert.equal(margin(a.fake), 18);
    a.ext.disable();
    const b = await started({gnome50: true});
    assert.equal(margin(b.fake), 67, 'GNOME 50: centred');
    b.ext.disable();
    const fake = makeGreeter();
    fake.gsettings['org.gnome.desktop.interface']['text-scaling-factor'] = 1.25;
    const ext = new FedoraGlassLogin({});
    ext.enable();
    await settle();
    assert.equal(margin(fake), 143);
    ext.disable();
    // Large Text switched on at the login screen itself: everything is built again with
    // it. A change that changes nothing builds nothing.
    const live = makeGreeter();
    const e5 = new FedoraGlassLogin({});
    e5.enable();
    await settle();
    const said = () => [...live.settingsLive].forEach(g => g.emit('changed::text-scaling-factor'));
    const first = layer(live.screenShield._lockDialogGroup);
    said();
    live.laters.run();
    assert.equal(layer(live.screenShield._lockDialogGroup), first, 'the same size: nothing is built again');
    live.gsettings['org.gnome.desktop.interface']['text-scaling-factor'] = 1.25;
    said();
    live.laters.run();
    await settle();
    assert.notEqual(layer(live.screenShield._lockDialogGroup), first);
    assert.equal(margin(live), 143);
    e5.disable();
    assert.ok([...live.settingsLive].every(g => g.listeners === 0), 'nobody listens to the settings any more');
    // A short screen (600 px): the middle would leave the big clock no room, so the prompt
    // stands right under it: 48 px to clear the panel, the clock (100 px in this fake), 24 px
    // of air, 40 px of card and 4 px to spare = 216 px from the top, 191 under GNOME's fixed top.
    const low = makeGreeter();
    low.layoutManager.monitors = [{x: 0, y: 0, width: 1920, height: 600}];
    const e3 = new FedoraGlassLogin({});
    e3.enable();
    await settle();
    assert.equal(margin(low), 191);
    low.laters.run();
    const top = ours().find(a => a.name === 'fedora-glass-login-top');
    const [clock, , message] = top.get_children();
    assert.deepEqual([top.y, clock.visible, message.visible], [48, true, false], 'the clock stays, the message gives way');
    e3.disable();
    // Without a big clock there is nothing to make room for.
    const plainClock = makeGreeter({look: {...LOOK, clock: 'gnome'}});
    plainClock.layoutManager.monitors = [{x: 0, y: 0, width: 1920, height: 600}];
    const e4 = new FedoraGlassLogin({});
    e4.enable();
    await settle();
    assert.equal(margin(plainClock), 155);
    e4.disable();
    // A greeter without that setting: the usual text size.
    const bare = makeGreeter();
    delete bare.gsettings['org.gnome.desktop.interface']['text-scaling-factor'];
    const e2 = new FedoraGlassLogin({});
    e2.enable();
    await settle();
    assert.equal(margin(bare), 155);
    e2.disable();
});

test('the clock stands in the middle of the room above the card, and gives way to a long user list', async () => {
    const {fake, ext} = await started();
    const d = fake.screenShield._dialog;
    const top = ours().find(a => a.name === 'fedora-glass-login-top');
    const [clock, , message] = top.get_children();   // the clock, the battery row (no battery here), the message
    fake.laters.run();
    // The prompt's card begins at 540 - 120 - 40 = 380. The clock and the message (100 px
    // each in this fake) stand in the middle of the 380 px above it.
    assert.deepEqual([top.x, top.y], [760, 90]);
    assert.deepEqual([clock.visible, message.visible], [true, true]);
    assert.equal(top.eased, undefined, 'placed at once, not moved');
    // With the prompt up it stays exactly there (the room above the prompt puts its
    // content at 540 - 120 = 420; this fake's prompt is made at 400).
    for (const a of d._authPrompt.all())
        a.y += 20;
    d._userSelectionBox.hide();
    d._authPrompt.show();
    fake.laters.run();
    assert.deepEqual([top.x, top.y], [760, 90]);
    d._authPrompt.hide();
    d._userSelectionBox.show();
    // A longer list begins higher (its card at 300 - 28): the clock moves up softly...
    const row = d._userList._box.get_children()[0];
    for (const a of [row, d._userList])
        a.y = 300;
    d._userList.emit('notify::allocation');
    fake.laters.run();
    assert.deepEqual([top.y, top.eased], [48, {duration: 200, y: 48}], 'right under the panel');
    assert.deepEqual([clock.visible, message.visible], [true, true]);
    // ...a longer one still takes the message's place (the clock alone, in the middle)...
    for (const a of [row, d._userList])
        a.y = 280;
    d._userList.emit('notify::allocation');
    fake.laters.run();
    assert.deepEqual([clock.visible, message.visible, top.y], [true, false, 76]);
    assert.equal(smallClock(fake).visible, false);
    // ...and then the clock's: the panel's small clock shows again.
    for (const a of [row, d._userList])
        a.y = 190;
    d._userList.emit('notify::allocation');
    fake.laters.run();
    assert.deepEqual([clock.visible, message.visible], [false, false]);
    assert.equal(smallClock(fake).visible, true);
    // It stays away: looked at again and again, it does not come back by itself (the
    // empty block is 0 px wide, and a text asked for its height at no width says 0).
    for (let i = 0; i < 3; i++) {
        top.emit('notify::allocation');
        fake.laters.run();
        assert.deepEqual([clock.visible, message.visible, smallClock(fake).visible], [false, false, true]);
    }
    // Back to one user: everything again, where it was.
    for (const a of [row, d._userList])
        a.y = 500;
    d._userList.emit('notify::allocation');
    fake.laters.run();
    assert.deepEqual([clock.visible, message.visible, top.y], [true, true, 90]);
    assert.equal(smallClock(fake).visible, false);
    ext.disable();
});

test('what GNOME shows under the field never ends below the screen: the prompt gets GNOME\'s own place back', async () => {
    const {fake, ext} = await started();
    const d = fake.screenShield._dialog, prompt = d._authPrompt;
    const css = () => fake.fs.get(CSS_PATH).text;
    const loads = () => fake.themeContext.theme.loads;
    d._userSelectionBox.hide();
    prompt.show();
    fake.laters.run();
    assert.match(css(), /prompt-layout {[^}]*margin-top: 155px;/, 'it fits: in the middle, where we put it');
    const before = loads();
    // Before GNOME has laid the prompt out again it says how tall it would like to be,
    // the room above it included: that does not count.
    prompt.needsLayout = true;
    prompt.height = 1500;
    prompt.emit('notify::allocation');
    fake.laters.run();
    assert.match(css(), /margin-top: 155px;/, 'not laid out yet: nothing is decided');
    prompt.needsLayout = false;
    prompt.height = 300;
    prompt.emit('notify::allocation');
    fake.laters.run();
    assert.equal(loads(), before);
    // A long list of ways to log in: the prompt would now end 8 px or less above the
    // screen's bottom (1080 px), or below it.
    prompt.height = 1073 - prompt.y;
    prompt.emit('notify::allocation');
    fake.laters.run();
    assert.ok(!css().includes('margin-top'), 'no room of ours above the prompt any more: GNOME\'s own place');
    assert.deepEqual(fake.themeContext.theme.sheets, [CSS_PATH], 'the stylesheet is loaded once');
    assert.equal(loads(), before + 1);
    // It stays so, however the prompt changes afterwards: no going back and forth.
    prompt.height = 300;
    prompt.emit('notify::allocation');
    fake.laters.run();
    prompt.height = 2000;
    prompt.emit('notify::allocation');
    fake.laters.run();
    assert.ok(!css().includes('margin-top'));
    assert.equal(loads(), before + 1, 'given back once');
    assert.equal(note().phase, 'starting', 'and no failure');
    // A new screen: everything again, in the middle again.
    prompt.height = 180;
    fake.layoutManager.emit('monitors-changed');
    fake.laters.run();
    await settle();
    assert.match(css(), /prompt-layout {[^}]*margin-top: 155px;/);
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
    // Nothing of ours is seen yet, the big clock neither: the panel's small one stays.
    fake.laters.run();
    assert.equal(layer(fake.screenShield._lockDialogGroup).opacity, 0);
    assert.equal(smallClock(fake).visible, true, 'a clock at every moment');
    fake.screenShield._dialog._userSelectionBox.hide();
    fake.screenShield._dialog._authPrompt.show();
    fake.laters.run();
    assert.equal(ours().find(a => a.name === 'fedora-glass-login-card').visible, false, 'no card on no glass');
    fake.timeouts.run(4000);
    fake.laters.run();
    await settle();
    assert.equal(fake.bgManagers.size, 0, 'the glow needs no picture');
    assert.ok(sheets().length === 1 && sheets().every(s => s.visible), 'the glow shows');
    assert.equal(layer(fake.screenShield._lockDialogGroup).opacity, 255);
    assert.equal(smallClock(fake).visible, false, 'the big clock is up: the small one goes');
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
    fake.laters.run();
    d._userSelectionBox.hide();
    prompt.show();
    fake.laters.run();
    fake.now = 300000;      // from the user list's shape to the prompt's
    fake.timeouts.run(16);
    // Content: avatar 400..528, entry row 540..580, from x 800 to 1120; 40 px above and
    // below, 28 px beside.
    assert.deepEqual(placed.at(-1), [772, 360, 376, 260]);
    prompt._message.text = 'Sorry, that didn’t work. Please try again.';
    fake.laters.run();
    assert.ok(fake.timeouts.list.size > 0, 'it eases');
    fake.now = 380000;
    fake.timeouts.run(16);
    const mid = placed.at(-1)[3];
    assert.ok(mid > 260 && mid < 320, `half way: ${mid}`);
    fake.now = 500000;
    fake.timeouts.run(16);
    assert.deepEqual(placed.at(-1), [772, 360, 376, 320], 'to the message’s foot (640) + 40');
    prompt._message.text = '';
    fake.laters.run();
    fake.now = 700000;
    fake.timeouts.run(16);
    assert.deepEqual(placed.at(-1), [772, 360, 376, 260]);
    // Animations off (GNOME's own setting): there in one step, no timer.
    fake.stSettings.enable_animations = false;
    prompt._message.text = 'Caps Lock is on.';
    const before = fake.timeouts.list.size;
    fake.laters.run();
    assert.deepEqual(placed.at(-1), [772, 360, 376, 320]);
    assert.equal(fake.timeouts.list.size, before);
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
