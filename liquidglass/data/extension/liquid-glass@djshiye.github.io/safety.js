// Safe mode: when the glass keeps failing, it turns itself off and the desktop
// carries on with plain tinted panels and menus (the Shell theme's own fill).
//
// It turns on when
//  - the glass code hits ERROR_LIMIT errors within ERROR_WINDOW_US, or
//  - GNOME Shell stopped within STABLE_S of starting the glass, RESTART_LIMIT
//    times in a row (a crash loop), so the next start is a safe one. A clean stop
//    (restarting the PC, logging out) is not a crash: GNOME says so with its
//    'shutdown' signal, the same one it uses for its own crash check.
// Desktop behaviour (start on the desktop, no overview), the ArcMenu helper and
// the lock screen keep working. The Fedora Glass app shows a note with a button
// that writes ~/.config/liquid-glass/safe-mode-reset.json ({"id": "<16 hex>"}),
// which turns the glass back on. The state lives in
// ~/.cache/liquid-glass/safe-mode.json (only this user can read it).

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

export const ERROR_LIMIT = 3;
export const ERROR_WINDOW_US = 120e6;
export const STABLE_S = 60;
export const RESTART_LIMIT = 2;
const RESET = 'safe-mode-reset.json';
const ID = /^[0-9a-f]{16}$/;

// The one in use, so that any module can report an error to it.
let current = null;

/** Report an error from the glass. Safe to call at any time, with or without safe mode running. */
export function report(where, error) {
    try {
        console.error(`Fedora Glass: ${where}: ${error}${error?.stack ? `\n${error.stack}` : ''}`);
    } catch {}
    current?._error(where, error);
}

/** fn, with any error it throws reported instead of thrown. */
export function guarded(where, fn) {
    return (...args) => {
        try {
            return fn(...args);
        } catch (e) {
            report(where, e);
            return undefined;
        }
    };
}

function readJson(file, max) {
    try {
        const info = file.query_info('standard::size,standard::type', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, null);
        if (info.get_file_type() !== Gio.FileType.REGULAR || info.get_size() > max)
            return null;
        const [, bytes] = file.load_contents(null);
        const v = JSON.parse(new TextDecoder().decode(bytes));
        return v && typeof v === 'object' ? v : null;
    } catch {
        return null;
    }
}

export class Safety {
    /** onChange(tripped) is called when safe mode turns on or off. */
    constructor(onChange) {
        this._onChange = onChange;
        this._errors = [];
        this._dir = GLib.build_filenamev([GLib.get_user_cache_dir(), 'liquid-glass']);
        this._file = Gio.File.new_for_path(GLib.build_filenamev([this._dir, 'safe-mode.json']));
        this._configDir = Gio.File.new_for_path(GLib.build_filenamev([GLib.get_user_config_dir(), 'liquid-glass']));
        const last = readJson(this._file, 16 * 1024) ?? {};
        this.tripped = last.tripped === true;
        this.reason = typeof last.reason === 'string' ? last.reason : '';
        this._at = Number.isFinite(last.at) ? last.at : 0;
        this._resetId = typeof last.resetId === 'string' ? last.resetId : '';
        this._where = this.tripped && typeof last.where === 'string' ? last.where.slice(0, 80) : '';
        // The last session started the glass and stopped before it ran for STABLE_S.
        let restarts = Number.isFinite(last.restarts) ? last.restarts : 0;
        restarts = last.running && !last.stable ? restarts + 1 : 0;
        this._restarts = restarts;
        if (!this.tripped && restarts >= RESTART_LIMIT) {
            this.tripped = true;
            this.reason = 'restarts';
            this._where = 'restarts';
            this._at = Math.floor(Date.now() / 1000);
        }
        // A reset asked for before this start (the app wrote it while the Shell was down) counts now.
        const req = this._request();
        if (this.tripped && req && req !== this._resetId) {
            this._resetId = req;
            this._clearState();
        } else if (req) {
            this._resetId = req;
        }
        this._running = !this.tripped;
        this._stable = false;
        this._write();
        current = this;
        this._stableId = this._running ? GLib.timeout_add_seconds(GLib.PRIORITY_LOW, STABLE_S, () => {
            this._stableId = 0;
            this._stable = true;
            this._restarts = 0;
            this._write();
            return GLib.SOURCE_REMOVE;
        }) : 0;
        try {
            this._monitor = this._configDir.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, null);
            this._monitorId = this._monitor.connect('changed', (_m, file, other) => {
                if (file?.get_basename() === RESET || other?.get_basename() === RESET)
                    this._onReset();
            });
        } catch {
            this._monitor = null;
        }
        // GNOME Shell is stopping on purpose (the PC restarts, the user logs out). Without
        // this, two quick restarts after logging in read as a crash loop (1.5.2).
        try {
            this._shutdownId = global.connect('shutdown', () => this._cleanStop());
        } catch {
            this._shutdownId = 0;
        }
    }

    _cleanStop() {
        this._running = false;
        this._restarts = 0;
        this._write();
    }

    _clearState() {
        this.tripped = false;
        this.reason = '';
        this._at = 0;
        this._restarts = 0;
        this._where = '';
        this._errors = [];
    }

    _request() {
        const id = readJson(this._configDir.get_child(RESET), 1024)?.id;
        return typeof id === 'string' && ID.test(id) ? id : null;
    }

    _onReset() {
        const id = this._request();
        if (!id || id === this._resetId)
            return;
        this._resetId = id;
        if (!this.tripped)
            return;
        this._clearState();
        this._running = true;
        this._stable = true;     // turned on by hand: a restart now is not a crash loop
        this._write();
        this._onChange?.(false);
    }

    _error(where, _e) {
        if (this.tripped)
            return;
        const t = GLib.get_monotonic_time();
        this._errors.push(t);
        this._errors = this._errors.filter(x => x > t - ERROR_WINDOW_US);
        if (this._errors.length >= ERROR_LIMIT)
            this._trip('errors', where, true);
    }

    /** The glass could not even start: turn it off now. */
    startFailed() {
        if (!this.tripped)
            this._trip('start', 'start', false);
    }

    _trip(reason, where, notify) {
        this.tripped = true;
        this.reason = reason;
        this._where = String(where).slice(0, 80);
        this._at = Math.floor(Date.now() / 1000);
        this._running = false;
        this._write();
        console.warn(`Fedora Glass: the glass kept failing (last in ${this._where}), so it is off (safe mode)`);
        if (!notify)
            return;
        // Not from inside the failing code: on the next main-loop turn.
        if (this._idleId)
            return;
        this._idleId = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
            this._idleId = 0;
            this._onChange?.(this.tripped);
            return GLib.SOURCE_REMOVE;
        });
    }

    _write() {
        const state = {version: 1, tripped: this.tripped, reason: this.reason, at: this._at,
            where: this._where, restarts: this._restarts, running: this._running, stable: this._stable,
            resetId: this._resetId};
        try {
            GLib.mkdir_with_parents(this._dir, 0o700);
            GLib.file_set_contents_full(this._file.get_path(), new TextEncoder().encode(JSON.stringify(state)),
                GLib.FileSetContentsFlags.CONSISTENT, 0o600);
        } catch (e) {
            console.warn(`Fedora Glass: could not write the safe mode state: ${e}`);
        }
    }

    /** The extension is turned off on purpose: not a crash. */
    destroy() {
        if (this._idleId)
            GLib.source_remove(this._idleId);
        this._idleId = 0;
        if (this._stableId)
            GLib.source_remove(this._stableId);
        this._stableId = 0;
        if (this._monitor) {
            this._monitor.disconnect(this._monitorId);
            this._monitor.cancel();
            this._monitor = null;
        }
        if (this._shutdownId)
            global.disconnect(this._shutdownId);
        this._shutdownId = 0;
        this._cleanStop();
        if (current === this)
            current = null;
        this._onChange = null;
    }
}
