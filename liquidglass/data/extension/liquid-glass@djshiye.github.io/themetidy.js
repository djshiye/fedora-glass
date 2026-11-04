// Works around a leak in GNOME's User Themes extension (gnome-shell-extensions 50).
//
// User Themes listens for its theme name with connectObject(..., this), but its
// disable() calls this._settings.disconnectObject() with no object, which
// disconnects nothing. GNOME switches User Themes off and on at every screen lock
// (and whenever an extension before it is switched off), so each lock leaves one
// more listener behind. Every one of them reloads the whole Shell theme when the
// theme name changes, and Fedora Glass changes it twice at every dark/light switch:
// after a day of locks, one switch reloaded the theme dozens of times in a row,
// each reload restyling every widget on screen (seconds of stutter).
//
// This disconnects only those stale listeners: the ones User Themes itself left on
// its own old settings objects. Its current listener is never touched, and if
// GNOME's internals look different from what is expected, nothing is done.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as SignalTracker from 'resource:///org/gnome/shell/misc/signalTracker.js';

export const USER_THEME = 'user-theme@gnome-shell-extensions.gcampax.github.com';
const SCHEMA = 'org.gnome.shell.extensions.user-theme';
const ACTIVE = 1;

/**
 * Disconnects the listeners `owner` left on settings objects other than `current`.
 * `trackers`: emitter -> signal tracker (GNOME's debugGetSignalTrackers()).
 * Returns how many old settings objects were let go.
 */
export function tidyTrackers(trackers, owner, current, isUserThemeSettings) {
    if (!owner || !trackers || typeof trackers.forEach !== 'function')
        return 0;
    const stale = [];
    trackers.forEach((tracker, emitter) => {
        if (emitter !== current && isUserThemeSettings(emitter) && tracker?._map?.has?.(owner))
            stale.push(tracker);
    });
    for (const tracker of stale)
        tracker.untrack(owner);
    return stale.length;
}

function isUserThemeSettings(obj) {
    try {
        return obj instanceof Gio.Settings && obj.schema_id === SCHEMA;
    } catch {
        return false;
    }
}

export class UserThemesTidy {
    constructor() {
        this._idle = 0;
        this.tidied = 0;    // read by the QA tools
        this._id = Main.extensionManager.connect('extension-state-changed', (_m, ext) => {
            if (ext?.uuid === USER_THEME && ext.state === ACTIVE)
                this._soon();
        });
        this._soon();
    }

    _soon() {
        if (this._idle)
            return;
        this._idle = GLib.idle_add(GLib.PRIORITY_LOW, () => {
            this._idle = 0;
            this.tidy();
            return GLib.SOURCE_REMOVE;
        });
    }

    tidy() {
        try {
            const ext = Main.extensionManager.lookup(USER_THEME);
            const owner = ext?.state === ACTIVE ? ext.stateObj : null;
            const current = owner?._settings;
            if (!(current instanceof Gio.Settings) || typeof SignalTracker.debugGetSignalTrackers !== 'function')
                return;
            const n = tidyTrackers(SignalTracker.debugGetSignalTrackers(), owner, current, isUserThemeSettings);
            if (n > 0) {
                this.tidied += n;
                console.log(`Fedora Glass: let go of ${n} stale User Themes listener${n === 1 ? '' : 's'}`);
            }
        } catch (e) {
            console.warn(`Fedora Glass: could not tidy User Themes: ${e}`);
        }
    }

    destroy() {
        if (this._idle)
            GLib.source_remove(this._idle);
        this._idle = 0;
        if (this._id)
            Main.extensionManager.disconnect(this._id);
        this._id = 0;
    }
}
