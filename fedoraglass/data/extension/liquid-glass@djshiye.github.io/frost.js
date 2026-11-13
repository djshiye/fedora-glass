// Weather frost: the glass frosts over when it is cold where you are (set in the
// Fedora Glass app, off until you turn it on). frostmath.js says how frosty for a
// temperature; this reads the temperature and hands the frost to the glass.
//
// Where the temperature comes from, and privacy:
// - Only GNOME's own weather, the one its calendar menu shows: GNOME Weather's
//   place (or your automatic location, only if you allowed that in GNOME's
//   Location settings). Nothing new is asked about where you are, and no other
//   service is contacted: this asks that same weather to refresh every 30 minutes,
//   as GNOME's calendar menu does whenever you open it.
// - What it read is said for the app in ~/.cache/liquid-glass/weather-frost.json
//   (only you can read it): the temperatures and how frosty the glass is. Never
//   the place's name or where it is. Taken away again when weather frost is off.
//
// Cost: one wall-clock check every 10 minutes, and GNOME's weather signal. A change
// of frost eases in over a few seconds by setting two numbers on each pane (no copy
// of what is behind it); the extra blur moves in at most three steps.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {setFrost} from './glass.js';
import {between, cleanFrost, frostFor, refreshDue, stale} from './frostmath.js';

export const STATE = 'weather-frost.json';
const TICK_S = 600;
const EASE_MS = 3000;
const EASE_STEP_MS = 50;
// libgweather's GWeatherTemperatureUnit.CENTIGRADE, as a number so no extra library is
// loaded: if one were missing, the whole extension would fail to start.
const CENTIGRADE = 3;

/** The weather GNOME's calendar menu keeps for its owner, or null. Read only. */
function gnomeWeather() {
    try {
        return Main.panel?.statusArea?.dateMenu?._weatherItem?._weatherClient ?? null;
    } catch {
        return null;
    }
}

function value(fn) {
    try {
        const r = fn();
        const [ok, v] = Array.isArray(r) ? r : [false, NaN];
        return ok && Number.isFinite(v) && v > -90 && v < 70 ? Math.round(v * 10) / 10 : null;
    } catch {
        return null;
    }
}

/** What GNOME's weather says now: {status, temp, feels}. status: ok, no-weather, no-place or waiting. */
export function readWeather(client) {
    if (!client || !client.available)
        return {status: 'no-weather', temp: null, feels: null};
    if (!client.hasLocation)
        return {status: 'no-place', temp: null, feels: null};
    const info = client.info;
    if (client.loading || !info?.is_valid?.())
        return {status: 'waiting', temp: null, feels: null};
    const temp = value(() => info.get_value_temp(CENTIGRADE));
    const feels = value(() => info.get_value_apparent(CENTIGRADE));
    if (temp === null && feels === null)
        return {status: 'waiting', temp: null, feels: null};
    return {status: 'ok', temp, feels: feels ?? temp};
}

export class WeatherFrost {
    constructor(cfg) {
        this._cfg = cleanFrost(cfg?.weather);
        this._now = {frost: 0, flakes: 0};
        this._target = {frost: 0, flakes: 0};
        this._reading = null;       // the last good one: {temp, feels, at}
        this._status = 'off';
        this._written = null;
        this._client = null;
        this._clientId = 0;
        this._tick = 0;
        this._ease = 0;
        this._askedAt = 0;
        this._first = true;         // the first frost after a start shows at once
        this._start();
    }

    update(cfg) {
        const next = cleanFrost(cfg?.weather);
        if (JSON.stringify(next) === JSON.stringify(this._cfg))
            return;
        const was = this._cfg.enabled;
        this._cfg = next;
        if (next.enabled && !was) {
            this._first = true;
            this._start();
        } else if (!next.enabled && was) {
            this._stop();
        } else {
            this._sync();       // new temperatures to frost at: the glass eases to them
        }
    }

    _start() {
        if (!this._cfg.enabled) {
            this._removeState();
            return;
        }
        this._client = gnomeWeather();
        if (this._client) {
            this._clientId = this._client.connect('changed', () => this._safe(() => this._sync()));
        }
        this._tick = GLib.timeout_add_seconds(GLib.PRIORITY_LOW, TICK_S, () => {
            this._safe(() => this._refresh());
            return GLib.SOURCE_CONTINUE;
        });
        this._safe(() => {
            this._sync();
            this._refresh();
        });
    }

    _stop() {
        if (this._clientId)
            this._client?.disconnect(this._clientId);
        this._clientId = 0;
        this._client = null;
        if (this._tick)
            GLib.source_remove(this._tick);
        this._tick = 0;
        this._reading = null;
        this._status = 'off';
        this._level = 'neutral';
        this._go({frost: 0, flakes: 0}, false);   // eases back to your look
        this._removeState();
    }

    _safe(fn) {
        try {
            fn();
        } catch (e) {
            console.error(`Fedora Glass: weather frost: ${e}`);
        }
    }

    /** Asks GNOME's weather for fresh numbers when they are due. */
    _refresh() {
        const client = this._client;
        const now = GLib.get_real_time();
        if (client?.available && client.hasLocation && refreshDue(this._askedAt, now)) {
            this._askedAt = now;
            client.update();
        }
        this._sync();   // a reading may have gone stale meanwhile
    }

    _sync() {
        if (!this._cfg.enabled)
            return;
        const now = GLib.get_real_time();
        const w = readWeather(this._client);
        if (w.status === 'ok')
            this._reading = {temp: w.temp, feels: w.feels, at: now};
        // A refresh that is still loading, or failed (offline), keeps the last reading a while.
        const r = this._reading && !stale(this._reading.at, now) ? this._reading : null;
        if (!r)
            this._reading = null;
        this._status = r ? 'ok' : w.status === 'ok' ? 'waiting' : w.status;
        const t = r ? (this._cfg.feelsLike ? r.feels : r.temp) : null;
        const f = frostFor(t, this._cfg);
        this._level = f.level;
        this._go({frost: f.frost, flakes: f.flakes}, this._first);
        if (r)
            this._first = false;
        this._writeState(r, f.level);
    }

    /** Eases the glass to `target` over a few seconds, or at once. */
    _go(target, now) {
        this._target = target;
        if (this._ease)
            GLib.source_remove(this._ease);
        this._ease = 0;
        const from = {...this._now};
        if (now || (from.frost === target.frost && from.flakes === target.flakes)) {
            this._set(target);
            return;
        }
        const t0 = GLib.get_monotonic_time();
        this._ease = GLib.timeout_add(GLib.PRIORITY_DEFAULT_IDLE, EASE_STEP_MS, () => {
            const k = (GLib.get_monotonic_time() - t0) / (EASE_MS * 1000);
            this._safe(() => this._set(k >= 1 ? target : between(from, target, k)));
            if (k < 1)
                return GLib.SOURCE_CONTINUE;
            this._ease = 0;
            return GLib.SOURCE_REMOVE;
        });
    }

    _set(v) {
        this._now = {frost: v.frost, flakes: v.flakes};
        setFrost(v.frost, v.flakes);
    }

    get state() {
        return {status: this._status, level: this._level ?? 'neutral', ...this._now, reading: this._reading};
    }

    _stateFile() {
        return GLib.build_filenamev([GLib.get_user_cache_dir(), 'liquid-glass', STATE]);
    }

    _writeState(r, level) {
        const text = JSON.stringify({
            version: 1, status: this._status, level,
            temp: r?.temp ?? null, feels: r?.feels ?? null, feelsLike: this._cfg.feelsLike,
            frost: this._target.frost, flakes: this._target.flakes,
            at: r ? Math.round(r.at / 1e6) : null,
        });
        if (text === this._written)
            return;
        try {
            const dir = GLib.build_filenamev([GLib.get_user_cache_dir(), 'liquid-glass']);
            GLib.mkdir_with_parents(dir, 0o700);
            GLib.file_set_contents_full(this._stateFile(), new TextEncoder().encode(text),
                GLib.FileSetContentsFlags.CONSISTENT, 0o600);
            this._written = text;
        } catch (e) {
            console.warn(`Fedora Glass: could not say the weather frost for the app: ${e}`);
        }
    }

    _removeState() {
        this._written = null;
        try {
            Gio.File.new_for_path(this._stateFile()).delete(null);
        } catch {}     // no file: nothing to take away
    }

    /** Weather frost turns off (the lock screen, Shell parts stopping): the glass is as you set it. */
    destroy() {
        if (this._ease)
            GLib.source_remove(this._ease);
        this._ease = 0;
        const was = this._cfg.enabled;
        if (this._clientId)
            this._client?.disconnect(this._clientId);
        this._clientId = 0;
        this._client = null;
        if (this._tick)
            GLib.source_remove(this._tick);
        this._tick = 0;
        this._set({frost: 0, flakes: 0});
        // The lock screen ends the session's parts: the file stays for the app while it is
        // on, and goes only when it is turned off.
        if (!was)
            this._removeState();
    }
}
