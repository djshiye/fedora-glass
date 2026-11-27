// Lock screen widgets (lockwidgets.js): the greeting, the battery icon and the weather
// line, and the message cleaning in config.js.
import assert from 'node:assert/strict';
import {test} from 'node:test';

globalThis.fake = {timeouts: {add: () => 1, remove() {}}, Actor: class {}};
globalThis.global = {stage: {}};
const W = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/lockwidgets.js');
const C = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/config.js');

test('the greeting follows the time of day', () => {
    assert.equal(W.greetingFor(4), 'Good night');
    assert.equal(W.greetingFor(5), 'Good morning');
    assert.equal(W.greetingFor(12), 'Good afternoon');
    assert.equal(W.greetingFor(17), 'Good evening');
    assert.equal(W.greetingFor(22), 'Good night');
});

test('the battery icon is one GNOME has', () => {
    assert.equal(W.batteryIcon(83, 2), 'battery-level-80-symbolic');
    assert.equal(W.batteryIcon(47, 1), 'battery-level-40-charging-symbolic');
    assert.equal(W.batteryIcon(100, 1), 'battery-level-100-charged-symbolic');
    assert.equal(W.batteryIcon(64, 4), 'battery-level-100-charged-symbolic');
    assert.equal(W.batteryIcon(3, 2), 'battery-level-0-symbolic');
    assert.equal(W.batteryIcon(140, 2), 'battery-level-100-symbolic');
});

const info = (temp, cond, sky, place) => ({get_temp_summary: () => temp, get_conditions: () => cond,
    get_sky: () => sky, get_location_name: () => place});

test('the weather line is short and names the place only when asked', () => {
    assert.equal(W.weatherText(info('14 °C', '-', 'Partly cloudy', 'Zagreb'), false), '14°  ·  Partly cloudy');
    assert.equal(W.weatherText(info('57 °F', 'Light rain', 'Overcast', 'Zagreb'), true), '57°  ·  Light rain  ·  Zagreb');
    assert.equal(W.weatherText(info('', '-', '-', ''), true), '');
});

test('the message reaching the Shell is plain, short text', () => {
    const cfg = C.parse(JSON.stringify({lock: {widgets: {message: 'a\nb\u0007c  ' + 'x'.repeat(300), weather: 'yes',
        style: 'neon', battery: false}}}));
    const w = cfg.lock.widgets;
    assert.ok(w.message.startsWith('a b c x'));
    assert.equal([...w.message].length, 120);
    assert.equal(w.weather, false);          // only true booleans switch a widget on
    assert.equal(w.style, 'chips');
    assert.equal(w.battery, false);
    assert.deepEqual(C.parse('{}').lock.widgets, {battery: true, weather: false, weatherPlace: false, greeting: false,
        message: '', style: 'chips', hideNotifications: false});
    assert.equal(C.cleanMessage(42), '');
});

test('the weather is refreshed by the wall clock, so a night asleep counts', () => {
    const min = 60 * 1000000;
    assert.equal(W.weatherDue(0, 5), true);                 // never asked yet
    assert.equal(W.weatherDue(100 * min, 110 * min), false);
    assert.equal(W.weatherDue(100 * min, 130 * min), true);
    assert.equal(W.weatherDue(100 * min, 100 * min + 8 * 60 * min), true);   // woke up 8 hours later
    assert.equal(W.weatherDue(100 * min, 90 * min), true);  // the clock was set back
});

// GNOME's NotificationsBox: its wake-up method lives on the class, as in unlockDialog.js.
class FakeNotificationsBox {
    constructor() {
        this.visible = true;
        this.size = null;
    }

    hide() { this.visible = false; }
    show() { this.visible = true; }
    set_size(w, h) { this.size = [w, h]; }
    connect() { return 1; }
    disconnect() {}
    _updateVisibility() { this.visible = true; }
    _wakeUpScreenForSource() { this.woke = true; }
}
const box = () => new FakeNotificationsBox();

test('hidden notifications take no room and do not wake the screen, until shown again', () => {
    const w = new W.LockWidgets({lock: {widgets: {battery: false, weather: false, weatherPlace: false, greeting: false,
        message: '', style: 'chips', hideNotifications: true}}});
    const b = box();
    w._hideNotifications({_notificationsBox: b});
    assert.equal(b.visible, false);
    assert.deepEqual(b.size, [0, 0]);                         // the clock stays where GNOME puts it
    b._wakeUpScreenForSource({});
    assert.equal(b.woke, undefined);                         // a new one doesn't light up the screen
    w._detach();
    assert.deepEqual(b.size, [-1, -1]);                       // GNOME's own size again
    assert.equal(b.visible, true);
    b._wakeUpScreenForSource({});
    assert.equal(b.woke, true);
});

// GNOME's WeatherClient, which says "loading" the moment a refresh starts and answers a
// second later; the lock screen asks for one as it comes up.
function weatherChip(temp) {
    const make = t => ({
        is_valid: () => t !== null, get_temp_summary: () => `${t} °C`, get_conditions: () => '-', get_sky: () => 'Clear sky',
        get_symbolic_icon_name: () => 'weather-clear-symbolic', get_location_name: () => 'X',
    });
    const client = {available: true, hasLocation: true, loading: false, info: make(temp), make};
    const chip = {visible: false, icon: {}, label: {text: ''}};
    const w = {cfg: {weatherPlace: false}, _weatherClient: client, _weatherChip: chip};
    const sync = () => W.LockWidgets.prototype._syncWeather.call(w);
    return {client, chip, sync};
}

test('the weather chip stays while the numbers refresh, and shows the new ones', () => {
    const {client, chip, sync} = weatherChip(-4);
    sync();
    assert.equal(chip.visible, true);
    assert.equal(chip.label.text, '-4°  ·  Clear sky');
    client.loading = true;
    sync();
    assert.equal(chip.visible, true, 'no blink while it loads');
    assert.equal(chip.label.text, '-4°  ·  Clear sky');
    client.loading = false;
    client.info = client.make(-7);
    sync();
    assert.equal(chip.visible, true);
    assert.equal(chip.label.text, '-7°  ·  Clear sky');
});

test('the weather chip goes when the refresh finds nothing', () => {
    const {client, chip, sync} = weatherChip(-4);
    sync();
    client.loading = true;
    sync();
    client.loading = false;
    client.info = client.make(null);
    sync();
    assert.equal(chip.visible, false);
});

test('a weather chip with nothing to show yet stays hidden while it loads', () => {
    const {client, chip, sync} = weatherChip(null);
    client.loading = true;
    sync();
    assert.equal(chip.visible, false);
    client.loading = false;
    client.info = client.make(3);
    sync();
    assert.equal(chip.visible, true);
    assert.equal(chip.label.text, '3°  ·  Clear sky');
});
