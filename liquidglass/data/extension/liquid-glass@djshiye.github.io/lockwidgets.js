// Widgets on the lock screen: a greeting above GNOME's clock, and under it the
// battery, the weather and a message of the owner's choosing, each on a small
// glass chip. Set in the Lock screen tab of the Fedora Glass app.
//
// Privacy and safety:
// - Everything here is off by default except the battery, which says nothing about
//   the owner. The weather (and its place name) and the message are opt-in.
// - Only GNOME's own clock box gets new children, and only labels and icons: no
//   buttons, no input, no focus, no grabs. GNOME's password prompt is never touched.
// - Nothing is read from the session behind the lock (windows, notifications, apps).
//   The weather is the one GNOME's own calendar menu already fetched for the owner.
// - The message is shown as plain text, never as markup.
// - Anything that goes wrong takes the widgets away and leaves GNOME's lock screen.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {loadInterfaceXML} from 'resource:///org/gnome/shell/misc/fileUtils.js';

import {Signals} from './common.js';

const TICK_S = 60;                 // the greeting follows the time of day (when GNOME's clock can't say)
const WEATHER_EVERY_US = 30 * 60 * 1000000;   // ask GNOME's weather for fresh numbers every 30 minutes
export const MESSAGE_MAX = 120;

// UPower's device states (UPowerGlib.DeviceState), as numbers so this file needs no
// extra library: if one were missing, the whole extension would fail to load.
const CHARGING = 1, FULLY_CHARGED = 4;

const UPOWER = 'org.freedesktop.UPower';
const DISPLAY_DEVICE = '/org/freedesktop/UPower/devices/DisplayDevice';
let DeviceProxy = null;
function deviceProxy() {
    DeviceProxy ??= Gio.DBusProxy.makeProxyWrapper(loadInterfaceXML('org.freedesktop.UPower.Device'));
    return DeviceProxy;
}

const TEXT = 'color: #ffffff; font-weight: 600; text-shadow: 0 1px 3px rgba(0,0,0,0.35);';
const STYLES = {
    // A small pane of glass: lighter than the frosted sheet under it, a bright top rim,
    // a soft shadow. The sheet's own ceiling keeps the white text readable on it.
    chips: {
        row: 'spacing: 10px; margin-top: 22px;',
        chip: 'background-color: rgba(255,255,255,0.11); border: 1px solid rgba(255,255,255,0.17); ' +
            'border-top-color: rgba(255,255,255,0.32); border-radius: 999px; padding: 7px 16px 7px 13px; ' +
            'spacing: 8px; box-shadow: 0 3px 12px rgba(0,0,0,0.16);',
        message: 'background-color: rgba(255,255,255,0.09); border: 1px solid rgba(255,255,255,0.14); ' +
            'border-top-color: rgba(255,255,255,0.26); border-radius: 16px; padding: 9px 16px; margin-top: 12px;',
    },
    plain: {
        row: 'spacing: 22px; margin-top: 18px;',
        chip: 'spacing: 8px; padding: 2px 0;',
        message: 'margin-top: 10px; padding: 2px 0;',
    },
};

export function greetingFor(hour) {
    if (hour >= 5 && hour < 12)
        return 'Good morning';
    if (hour >= 12 && hour < 17)
        return 'Good afternoon';
    if (hour >= 17 && hour < 22)
        return 'Good evening';
    return 'Good night';
}

/**
 * Whether the weather is due for fresh numbers. By the wall clock, which keeps running
 * while the PC sleeps: 1.5.7 counted minutes awake, so after a night asleep the lock
 * screen showed last evening's weather for up to half an hour.
 */
export function weatherDue(lastUs, nowUs) {
    return !lastUs || nowUs - lastUs >= WEATHER_EVERY_US || nowUs < lastUs;
}

export function batteryIcon(percent, state) {
    const level = 10 * Math.floor(Math.max(0, Math.min(100, percent)) / 10);
    if (state === FULLY_CHARGED || (state === CHARGING && level === 100))
        return 'battery-level-100-charged-symbolic';
    return `battery-level-${level}${state === CHARGING ? '-charging' : ''}-symbolic`;
}

/** The weather GNOME's calendar menu keeps for its owner, or null. Read only. */
function gnomeWeather() {
    try {
        return Main.panel?.statusArea?.dateMenu?._weatherItem?._weatherClient ?? null;
    } catch {
        return null;
    }
}

export function weatherText(info, withPlace) {
    let temp = (info.get_temp_summary?.() ?? '').trim();
    // "14 °C" reads as "14°" on a chip.
    temp = temp.replace(/\s*°\s*[CFK]$/u, '°');
    let sky = (info.get_conditions?.() ?? '').trim();
    if (!sky || sky === '-')
        sky = (info.get_sky?.() ?? '').trim();
    if (sky === '-')
        sky = '';
    const place = withPlace ? (info.get_location_name?.() ?? '').trim() : '';
    return [temp, sky, place].filter(s => s).join('  ·  ');
}

export class LockWidgets {
    constructor(cfg) {
        this.cfg = cfg.lock.widgets;
        this._signals = new Signals();
        this._dialogSignals = new Signals();
        this._dialog = null;
        this._actors = [];
        this._ended = false;
        this._safe(() => {
            const group = Main.screenShield?._lockDialogGroup;
            if (group) {
                // GNOME makes the unlock dialog when the screen locks; look once it is built.
                this._signals.on(group, 'child-added', () => {
                    if (this._addLater)
                        return;
                    this._addLater = global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
                        this._addLater = 0;
                        this._safe(() => this._attach());
                        return GLib.SOURCE_REMOVE;
                    });
                });
            }
            this._attach();
        });
    }

    _safe(fn) {
        try {
            fn();
        } catch (e) {
            console.error(`Fedora Glass: lock screen widgets turned off: ${e}`);
            this._detach();
        }
    }

    get _wanted() {
        const c = this.cfg;
        return c.greeting || c.battery || c.weather || c.message !== '' || c.hideNotifications;
    }

    _attach() {
        const dialog = Main.screenShield?._dialog;
        const clock = dialog?._clock;
        if (this._ended || !this._wanted || !clock || dialog === this._dialog)
            return;
        this._detach();
        this._dialog = dialog;
        this._dialogSignals.on(dialog, 'destroy', () => {
            this._dialog = null;    // our actors went with it
            this._actors = [];
            this._detach();
        });
        const style = STYLES[this.cfg.style] ?? STYLES.chips;
        const add = (actor, index) => {
            clock.insert_child_at_index(actor, index);
            this._actors.push(actor);
            return actor;
        };

        if (this.cfg.greeting) {
            this._greeting = add(new St.Label({
                name: 'liquid-glass-lock-greeting',
                style: `${TEXT} font-size: 17pt; font-weight: 500; margin-bottom: 2px;`,
                x_align: Clutter.ActorAlign.CENTER,
            }), 0);
        }
        const after = clock._date ? clock.get_children().indexOf(clock._date) + 1 : clock.get_n_children();
        const box = add(new St.BoxLayout({
            name: 'liquid-glass-lock-widgets', orientation: Clutter.Orientation.VERTICAL, x_align: Clutter.ActorAlign.CENTER,
        }), after);
        const row = new St.BoxLayout({style: style.row, x_align: Clutter.ActorAlign.CENTER});
        box.add_child(row);
        const chip = () => {
            const c = new St.BoxLayout({style: style.chip, visible: false});
            c.icon = new St.Icon({icon_size: 16, style: 'color: #ffffff;', y_align: Clutter.ActorAlign.CENTER});
            c.label = new St.Label({style: `${TEXT} font-size: 11.5pt;`, y_align: Clutter.ActorAlign.CENTER});
            c.add_child(c.icon);
            c.add_child(c.label);
            row.add_child(c);
            return c;
        };
        if (this.cfg.battery) {
            this._batteryChip = chip();
            this._watchBattery();
        }
        if (this.cfg.weather) {
            this._weatherChip = chip();
            this._watchWeather();
        }
        if (this.cfg.message) {
            const msg = new St.Label({
                name: 'liquid-glass-lock-message',
                // text-align: a message on two lines stays centred under the clock.
                style: `${TEXT} font-size: 11.5pt; font-weight: 500; ${style.message} max-width: 520px; text-align: center;`,
                x_align: Clutter.ActorAlign.CENTER,
            });
            // Plain text only: the owner's words are never read as markup.
            msg.clutter_text.use_markup = false;
            msg.clutter_text.line_wrap = true;
            msg.text = this.cfg.message;
            box.add_child(msg);
        }
        if (this.cfg.hideNotifications)
            this._hideNotifications(dialog);
        this._tick();
        // GNOME's own lock clock changes on the minute and straight after the PC wakes up
        // (a timer alone sleeps along with the PC, so the greeting and weather were stale
        // on waking): follow it, with a timer only if it isn't there.
        const wall = clock._wallClock;
        if (wall?.connect) {
            this._dialogSignals.on(wall, 'notify::clock', () => this._safe(() => this._tick()));
        } else {
            this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_LOW, TICK_S, () => {
                this._safe(() => this._tick());
                return this._timer ? GLib.SOURCE_CONTINUE : GLib.SOURCE_REMOVE;
            });
        }
    }

    _tick() {
        if (this._ended)
            return;
        if (this._greeting)
            this._greeting.text = greetingFor(GLib.DateTime.new_now_local().get_hour());
        const client = this._weatherClient;
        const now = GLib.get_real_time();
        if (client?.hasLocation && weatherDue(this._weatherAt, now)) {
            this._weatherAt = now;
            client.update();
        }
    }

    _watchBattery() {
        this._cancel = new Gio.Cancellable();
        const Proxy = deviceProxy();
        // The system's combined battery. A PC without one shows no chip.
        new Proxy(Gio.DBus.system, UPOWER, DISPLAY_DEVICE, (proxy, error) => {
            if (error || this._ended || !this._batteryChip)
                return;
            this._battery = proxy;
            this._batteryId = proxy.connect('g-properties-changed', () => this._safe(() => this._syncBattery()));
            this._safe(() => this._syncBattery());
        }, this._cancel);
    }

    _syncBattery() {
        const p = this._battery, chip = this._batteryChip;
        if (!p || !chip)
            return;
        // Type 2 is a battery; a UPS (3) counts too. Nothing else is worth a chip.
        const present = p.IsPresent && Number.isFinite(p.Percentage) && [2, 3].includes(p.Type);
        chip.visible = present;
        if (!present)
            return;
        chip.icon.icon_name = batteryIcon(p.Percentage, p.State);
        chip.label.text = `${Math.round(p.Percentage)}%`;
    }

    _watchWeather() {
        const client = gnomeWeather();
        if (!client)
            return;
        this._weatherClient = client;
        this._weatherId = client.connect('changed', () => this._safe(() => this._syncWeather()));
        this._weatherAt = 0;    // the first tick asks for fresh numbers
        this._syncWeather();
    }

    _syncWeather() {
        const client = this._weatherClient, chip = this._weatherChip;
        if (!client || !chip)
            return;
        const info = client.info;
        const ok = client.available && client.hasLocation && !client.loading && info?.is_valid();
        const text = ok ? weatherText(info, this.cfg.weatherPlace) : '';
        chip.visible = text !== '';
        if (!chip.visible)
            return;
        chip.icon.icon_name = info.get_symbolic_icon_name() || 'weather-few-clouds-symbolic';
        chip.label.text = text;
    }

    // GNOME's notifications and music controls under the clock: hidden while this is
    // on, GNOME's own again when it is off. Only shown or hidden, never changed.
    _hideNotifications(dialog) {
        const box = dialog._notificationsBox;
        if (!box)
            return;
        this._notifications = box;
        box.hide();
        // Hidden ones take no room either: 1.5.7 still lifted the clock to make space for
        // them, which told anyone looking that something had arrived.
        box.set_size(0, 0);
        // And a new one doesn't light up a sleeping screen to show nothing.
        if (typeof box._wakeUpScreenForSource === 'function')
            box._wakeUpScreenForSource = () => {};
        this._dialogSignals.on(box, 'notify::visible', () => {
            if (box.visible && this._notifications === box)
                box.hide();
        });
    }

    update(cfg) {
        this.cfg = cfg.lock.widgets;
        if (this._ended)
            return;
        this._safe(() => {
            this._detach();
            this._attach();
        });
    }

    _detach() {
        if (this._timer)
            GLib.source_remove(this._timer);
        this._timer = 0;
        this._weatherAt = 0;
        this._cancel?.cancel();
        this._cancel = null;
        // Each one on its own: one that fails must not keep the rest connected.
        try {
            if (this._batteryId)
                this._battery?.disconnect(this._batteryId);
        } catch {}
        this._batteryId = 0;
        this._battery = null;
        try {
            if (this._weatherId)
                this._weatherClient?.disconnect(this._weatherId);
        } catch {}
        this._weatherId = 0;
        this._weatherClient = null;
        this._dialogSignals.clear();
        const box = this._notifications;
        this._notifications = null;
        try {
            if (box) {
                // GNOME's own again: its size, its wake-ups, and whether it has anything to show.
                if (Object.hasOwn(box, '_wakeUpScreenForSource'))
                    delete box._wakeUpScreenForSource;
                box.set_size(-1, -1);
                box._updateVisibility ? box._updateVisibility() : box.show();
            }
        } catch {}   // gone with the dialog
        for (const a of this._actors) {
            try {
                a.destroy();
            } catch {}   // gone with the dialog
        }
        this._actors = [];
        this._greeting = this._batteryChip = this._weatherChip = null;
        this._dialog = null;
    }

    /** The screen is unlocked: stop updating, but stay on the sheet while it slides away. */
    unlocking() {
        this._ended = true;
        if (this._timer)
            GLib.source_remove(this._timer);
        this._timer = 0;
        this._signals.clear();
        if (!this._dialog)
            this.destroy();
    }

    destroy() {
        if (this._addLater)
            global.compositor.get_laters().remove(this._addLater);
        this._addLater = 0;
        this._signals.clear();
        this._detach();
        this._ended = true;
    }
}
