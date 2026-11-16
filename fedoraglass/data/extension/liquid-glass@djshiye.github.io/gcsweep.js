// Keeps GNOME Shell from freezing for good when an extension's settings are freed while
// Fedora Glass writes settings (GJS + GLib deadlock, GNOME/gjs#558, not fixed in GJS 1.90).
//
// When an extension is switched off, the Gio.Settings objects it made (Dash to Panel and
// ArcMenu make a dozen each) are left for the garbage collector. GJS frees them in its
// sweep after a collection while holding its toggle-queue lock, and freeing a Gio.Settings
// takes the lock of GNOME's settings store. If dconf announces a change at that moment, its
// worker thread holds the store's lock and wants the toggle-queue lock: each thread waits
// for the other and the Shell never draws again (main thread in g_object_remove_toggle_ref
// -> g_settings_backend_watch_weak_notify; "dconf worker" spinning in ToggleQueue::lock
// under g_settings_backend_dispatch_signal -> g_weak_ref_get).
//
// GJS collects on its own up to ten seconds after such a restart, which is just when the
// Fedora Glass app writes the next batch of settings (Restore original switches the glass
// off, the next Apply writes Dash to Panel's and ArcMenu's settings). So the garbage is
// collected here instead, at once, while the app is waiting for GNOME (it asks for the
// extensions' states between its steps and writes only after the answer):
//   - when another extension has just been switched off or failed (high-priority idle:
//     before GNOME answers the app's next question about extension states),
//   - when this extension starts (it may have been restarted after another one went off),
//   - when this extension is switched off (GNOME switches off the ones after it first).
// A collection is only moved earlier: nothing is kept alive or freed that GJS would not
// free anyway.

import GLib from 'gi://GLib';
import System from 'system';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

// GNOME's ExtensionState (misc/extensionUtils.js).
export const OFF_STATES = new Set([2 /* INACTIVE */, 3 /* ERROR */]);

export function collect(gc = System.gc) {
    try {
        gc();
        return true;
    } catch (e) {
        console.warn(`Fedora Glass: could not collect garbage: ${e}`);
        return false;
    }
}

export class SettingsSweep {
    /**
     * @param {string} ownUuid this extension's uuid (its own switch-off is handled in disable)
     * @param {object} [deps] for tests: {manager, gc}
     */
    constructor(ownUuid, deps = {}) {
        this._manager = deps.manager ?? Main.extensionManager;
        this._gc = deps.gc ?? System.gc;
        this._own = ownUuid;
        this._idle = 0;
        this.collections = 0;      // read by tests and the QA tools
        this._id = this._manager.connect('extension-state-changed', (_m, ext) => {
            if (ext && ext.uuid !== this._own && OFF_STATES.has(ext.state))
                this.soon();
        });
        this.soon();
    }

    // Coalesced: GNOME switching several extensions off in one go gives one collection.
    soon() {
        if (this._idle || !this._id)
            return;
        this._idle = GLib.idle_add(GLib.PRIORITY_HIGH, () => {
            this._idle = 0;
            this.now();
            return GLib.SOURCE_REMOVE;
        });
    }

    now() {
        if (collect(this._gc))
            this.collections++;
    }

    // Switched off: one collection right now (an idle would no longer run), after this
    // extension's own objects and those of the extensions GNOME switched off before it are let go.
    destroy({collect: last = true} = {}) {
        if (this._id)
            this._manager.disconnect(this._id);
        this._id = 0;
        if (this._idle)
            GLib.source_remove(this._idle);
        this._idle = 0;
        if (last)
            this.now();
    }
}
