// Whether the glass is paused from Quick Settings (quicktoggle.js), said where the Fedora
// Glass app can see it, and the app's way to ask for the glass back.
//
// - ~/.cache/liquid-glass/paused.json ({"version": 1, "paused": true|false}), next to the
//   safe mode state (safety.js), only this user can read it. Written as the user pauses or
//   resumes. A pause lasts only for this session: every enable (a login, a Shell restart)
//   starts with the glass on, so a file left saying "paused" by a Shell that stopped
//   without turning the extension off is put right there and then, and disable() says
//   "not paused" too.
// - ~/.config/liquid-glass/resume-glass.json ({"id": "<16 hex>"}): the app's "Resume"
//   button writes a new id, and the glass comes back as if the tile were switched on.
//   A request from before this start counts for nothing: only a new id resumes.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

export const STATE = 'paused.json';
export const RESUME = 'resume-glass.json';
const ID = /^[0-9a-f]{16}$/;

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

export class PauseState {
    /** onResume() is called when the app asks for the glass back while it is paused. */
    constructor(onResume) {
        this._onResume = onResume;
        this._dir = GLib.build_filenamev([GLib.get_user_cache_dir(), 'liquid-glass']);
        this._file = Gio.File.new_for_path(GLib.build_filenamev([this._dir, STATE]));
        this._configDir = Gio.File.new_for_path(GLib.build_filenamev([GLib.get_user_config_dir(), 'liquid-glass']));
        this.paused = false;
        // What the file says now: only a file that says "paused" needs writing at a start.
        const last = readJson(this._file, 1024);
        this._written = last?.paused === true ? '' : null;
        this._resumeId = this._request() ?? '';
        this._write();
        try {
            this._monitor = this._configDir.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, null);
            this._monitorId = this._monitor.connect('changed', (_m, file, other) => {
                if (file?.get_basename() === RESUME || other?.get_basename() === RESUME)
                    this._onRequest();
            });
        } catch {
            this._monitor = null;
        }
    }

    /** The glass is paused (true) or back on (false). */
    set(paused) {
        this.paused = !!paused;
        this._write();
    }

    _request() {
        const id = readJson(this._configDir.get_child(RESUME), 1024)?.id;
        return typeof id === 'string' && ID.test(id) ? id : null;
    }

    _onRequest() {
        const id = this._request();
        if (!id || id === this._resumeId)
            return;
        this._resumeId = id;
        if (!this.paused)
            return;
        try {
            this._onResume?.();
        } catch (e) {
            console.error(`Fedora Glass: resuming the glass for the app: ${e}`);
        }
    }

    _write() {
        const text = JSON.stringify({version: 1, paused: this.paused});
        // null: no file, or one that says "not paused" in some way: nothing to put right.
        if (text === this._written || (this._written === null && !this.paused))
            return;
        try {
            GLib.mkdir_with_parents(this._dir, 0o700);
            GLib.file_set_contents_full(this._file.get_path(), new TextEncoder().encode(text),
                GLib.FileSetContentsFlags.CONSISTENT, 0o600);
            this._written = text;
        } catch (e) {
            console.warn(`Fedora Glass: could not say the glass is paused: ${e}`);
        }
    }

    /** The extension turns off: no pause carries on past it. */
    destroy() {
        if (this._monitor) {
            this._monitor.disconnect(this._monitorId);
            this._monitor.cancel();
            this._monitor = null;
        }
        this.paused = false;
        this._write();
        this._onResume = null;
    }
}
