// The health note: how the login screen glass is doing, for the root helper's guard.
//
// Written into the greeter's own state folder ($XDG_STATE_HOME, which GDM gives each
// seat's greeter, 0700), atomically and tiny:
//   {"v": 1, "token": "<look.json's token>", "boot": "<boot id>",
//    "phase": "starting" | "ok" | "safe" | "error", "verified": "<token>" or ""}
// starting: first thing as the add-on starts, before anything is drawn.
// ok:       everything was built and ran 2 s without an error (and at a clean stop).
// safe:     the last start with this token never finished (a crash): nothing is drawn.
// error:    building or running failed; everything the add-on drew is gone again.
// verified: a password (or fingerprint) check succeeded on this login screen.
//
// Gio and GLib only, so this loads even when the rest of the add-on cannot.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

export const LOOK_PATH = '/etc/fedora-glass/login/look.json';
export const PHASES = ['starting', 'ok', 'safe', 'error'];
const TOKEN = /^[0-9a-f]{32}$/;
const BOOT = /^[0-9a-f-]{36}$/;
const NOTE_MAX = 1024;
const LOOK_MAX = 4096;

/** A small regular file read as JSON, or null (missing, too big, a link, not JSON). */
export function readJson(path, max) {
    try {
        const file = Gio.File.new_for_path(path);
        const info = file.query_info('standard::size,standard::type', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, null);
        if (info.get_file_type() !== Gio.FileType.REGULAR || info.get_size() > max)
            return null;
        const [, bytes] = file.load_contents(null);
        const v = JSON.parse(new TextDecoder().decode(bytes));
        return v && typeof v === 'object' && !Array.isArray(v) ? v : null;
    } catch {
        return null;
    }
}

/** Whether there is no look.json at all (the glass is switched off): no file and no link. */
export function lookMissing(path = LOOK_PATH) {
    try {
        Gio.File.new_for_path(path).query_info('standard::type', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, null);
        return false;
    } catch (e) {
        return e?.matches?.(Gio.IOErrorEnum, Gio.IOErrorEnum.NOT_FOUND) ?? /No such file/.test(String(e));
    }
}

/** look.json as the root helper wrote it (checked in full later, by style.js), or null. */
export function readLook(path = LOOK_PATH) {
    return readJson(path, LOOK_MAX);
}

/** The token in look.json, or '' when it has none that could be one. */
export function tokenOf(look) {
    return typeof look?.token === 'string' && TOKEN.test(look.token) ? look.token : '';
}

/** This boot's id (changes with every boot), or ''. */
export function bootId() {
    try {
        const [, bytes] = GLib.file_get_contents('/proc/sys/kernel/random/boot_id');
        const id = new TextDecoder().decode(bytes).trim();
        return BOOT.test(id) ? id : '';
    } catch {
        return '';
    }
}

/**
 * Whether to draw nothing (safe) this start, from the note the last start left:
 * - it says `starting` with this token: that start never finished, the Shell went
 *   down with it (a crash), so not again;
 * - it says `safe` with this token, in this same boot: stay safe. Otherwise a crash
 *   would be followed by a plain login screen, then the glass and a crash again, every
 *   other time. The root helper's guard turns the glass off at the next boot.
 */
export function mustStaySafe(prev, token, boot) {
    if (!prev || !token || prev.token !== token)
        return false;
    return prev.phase === 'starting' || (prev.phase === 'safe' && prev.boot === boot);
}

export class Health {
    /** dir: the note's folder (default: the greeter's state folder). */
    constructor({dir = null, token = '', boot = null} = {}) {
        this._dir = dir ?? GLib.build_filenamev([GLib.get_user_state_dir(), 'fedora-glass-login']);
        this._path = GLib.build_filenamev([this._dir, 'health.json']);
        this.token = TOKEN.test(token) ? token : '';
        this.boot = boot ?? bootId();
        this.phase = '';
        this.previous = readJson(this._path, NOTE_MAX);
        // A check that already succeeded with this look is still true after a restart.
        const v = this.previous?.verified;
        this.verified = this.token && this.previous?.token === this.token && v === this.token ? v : '';
    }

    /** Says phase (one of PHASES). Returns whether it was written. */
    write(phase) {
        if (!PHASES.includes(phase))
            throw new Error(`no such phase ${phase}`);
        this.phase = phase;
        return this._save();
    }

    /** A password or fingerprint check succeeded: kept through later phases. */
    markVerified() {
        if (!this.token || this.verified === this.token)
            return false;
        this.verified = this.token;
        return this._save();
    }

    note() {
        return {v: 1, token: this.token, boot: this.boot, phase: this.phase, verified: this.verified};
    }

    _save() {
        try {
            GLib.mkdir_with_parents(this._dir, 0o700);
            // CONSISTENT: a temporary file renamed over the old one, flushed to the disk,
            // so a crash right after leaves either note, whole.
            GLib.file_set_contents_full(this._path, new TextEncoder().encode(JSON.stringify(this.note())),
                GLib.FileSetContentsFlags.CONSISTENT, 0o644);
            return true;
        } catch (e) {
            console.warn(`Fedora Glass login: could not write the health note: ${e}`);
            return false;
        }
    }
}

/**
 * The run note: the greeter's own record of how its runs ended, private to it (0600, next
 * to health.json; root never reads it). It catches a crash that comes later than the
 * 2 s after which a start counts as finished (say when the password prompt opens), which
 * would otherwise come back at every start of the login screen:
 *   {"v": 1, "boot": "<boot id>", "token": "<look's token>", "clean": bool,
 *    "verified": bool, "unclean": <runs in a row that ended without a clean stop>}
 * A run that ends without GNOME Shell's clean stop (shutdown) or disable(), and without a
 * successful login, counts; UNCLEAN_LIMIT in a row in one boot with one look: safe.
 * A clean end, a successful login, a new boot or a new look starts the count again.
 */
export const UNCLEAN_LIMIT = 2;
const RUN_MAX = 512;

/** How many runs in a row ended badly, counting the last one, from the note it left. */
export function uncleanBefore(prev, token, boot) {
    if (!prev || prev.v !== 1 || prev.boot !== boot || prev.token !== token || !boot || !token)
        return 0;
    if (prev.clean === true || prev.verified === true)
        return 0;
    const n = Number.isInteger(prev.unclean) && prev.unclean >= 0 ? Math.min(prev.unclean, 100) : 0;
    return n + 1;
}

export class RunNote {
    constructor({dir = null, token = '', boot = null} = {}) {
        this._dir = dir ?? GLib.build_filenamev([GLib.get_user_state_dir(), 'fedora-glass-login']);
        this._path = GLib.build_filenamev([this._dir, 'run.json']);
        this.token = TOKEN.test(token) ? token : '';
        this.boot = boot ?? bootId();
        this.previous = readJson(this._path, RUN_MAX);
        this.unclean = uncleanBefore(this.previous, this.token, this.boot);
        this.clean = false;
        this.verified = false;
    }

    /** Too many bad ends in a row: draw nothing this start. */
    get tooMany() {
        return this.unclean >= UNCLEAN_LIMIT;
    }

    /** This run starts (and has not ended cleanly yet). */
    start() {
        this.clean = false;
        this.verified = false;
        return this._save();
    }

    endClean() {
        if (this.clean)
            return false;
        this.clean = true;
        return this._save();
    }

    markVerified() {
        if (this.verified)
            return false;
        this.verified = true;
        return this._save();
    }

    note() {
        return {v: 1, boot: this.boot, token: this.token, clean: this.clean, verified: this.verified,
            unclean: this.unclean};
    }

    _save() {
        try {
            GLib.mkdir_with_parents(this._dir, 0o700);
            GLib.file_set_contents_full(this._path, new TextEncoder().encode(JSON.stringify(this.note())),
                GLib.FileSetContentsFlags.CONSISTENT, 0o600);
            return true;
        } catch (e) {
            console.warn(`Fedora Glass login: could not write the run note: ${e}`);
            return false;
        }
    }
}
