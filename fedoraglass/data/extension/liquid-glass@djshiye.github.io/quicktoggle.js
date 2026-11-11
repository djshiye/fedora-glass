// The "Glass" tile in GNOME's Quick Settings: pauses all of Fedora Glass's glass for this
// session, and turns it back on. A pause, not a setting: settings.json and shell-glass.json
// stay as they are, so nothing needs Apply, and the next login starts with the glass on.
// While paused, extension.js takes the glass down the way safe mode does.
//
// The tile is GNOME's own QuickToggle, added the way GNOME asks extensions to (a
// SystemIndicator handed to Quick Settings), so it looks like GNOME's tiles and sits with
// them. Only while the session is unlocked: on the lock screen there is no Quick Settings.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {QuickToggle, SystemIndicator} from 'resource:///org/gnome/shell/ui/quickSettings.js';
import {_} from './strings.js';

export const ICON = 'glass-symbolic.svg';
// GNOME's own icon, should the extension's be missing.
const FALLBACK_ICON = 'display-brightness-symbolic';

function icon(dir) {
    try {
        const path = dir ? GLib.build_filenamev([dir, ICON]) : null;
        if (path && GLib.file_test(path, GLib.FileTest.EXISTS))
            return {gicon: new Gio.FileIcon({file: Gio.File.new_for_path(path)})};
    } catch {}
    return {iconName: FALLBACK_ICON};
}

/** The subtitle under "Glass": why there is no glass, or nothing while it shows. */
export function subtitleFor(paused, safeMode) {
    if (paused)
        return _('Paused');
    return safeMode ? _('Safe mode') : null;
}

/** Whether the tile shows as on: only while the glass really shows. */
export function isOn(paused, safeMode) {
    return !paused && !safeMode;
}

export class GlassSwitch {
    /**
     * dir: the extension's folder (for its icon). onPause(paused) is called when the user
     * flips the tile: true to pause the glass, false to turn it back on.
     */
    constructor(dir, onPause) {
        this._onPause = onPause;
        this._paused = false;
        this._safe = false;
        this._indicator = new SystemIndicator();
        this._toggle = new QuickToggle({title: _('Glass'), toggleMode: true, ...icon(dir)});
        this._toggle.accessible_name = _('Glass');
        // St.Button has flipped `checked` by the time it says clicked: on means glass.
        this._clickedId = this._toggle.connect('clicked', () => {
            const pause = !this._toggle.checked;
            try {
                this._onPause?.(pause);
            } catch (e) {
                logError(e, 'Fedora Glass: the Quick Settings switch');
            }
            this._show();      // what really happened, should the change have failed
        });
        this._indicator.quickSettingsItems.push(this._toggle);
        const qs = Main.panel.statusArea.quickSettings;
        if (typeof qs?.addExternalIndicator === 'function') {
            qs.addExternalIndicator(this._indicator);
        } else {
            // Older Quick Settings had no addExternalIndicator: the same two steps by hand.
            qs._indicators.add_child(this._indicator);
            qs._addItems(this._indicator.quickSettingsItems);
        }
        this._show();
    }

    /** Whether the glass is paused, and whether safe mode keeps it off. */
    setState(paused, safeMode) {
        this._paused = !!paused;
        this._safe = !!safeMode;
        this._show();
    }

    _show() {
        if (!this._toggle)
            return;
        // In safe mode there is no glass to show: the tile says so, off, and has nothing to
        // pause (the glass comes back from the Fedora Glass app). A pause can still be ended.
        this._toggle.checked = isOn(this._paused, this._safe);
        this._toggle.reactive = this._paused || !this._safe;
        this._toggle.subtitle = subtitleFor(this._paused, this._safe);
    }

    destroy() {
        if (this._clickedId)
            this._toggle?.disconnect(this._clickedId);
        this._clickedId = 0;
        this._indicator?.quickSettingsItems.forEach(item => item.destroy());
        this._indicator?.destroy();
        this._indicator = null;
        this._toggle = null;
        this._onPause = null;
    }
}
