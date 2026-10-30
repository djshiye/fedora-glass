// Desktop behaviour set in the Liquid Glass app: start on the desktop instead
// of the Activities overview, and optionally keep the overview closed for good.
//
// Dash to Panel and Just Perfection have their own "start on the desktop"
// options that save and restore Main.sessionMode.hasOverview. Changing it
// under them could leave the overview switched off for the whole session, so
// with either one running we never touch it; the app turns their option on
// instead, and we only close an overview that still opened.

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {ControlsState} from 'resource:///org/gnome/shell/ui/overviewControls.js';

const MANAGES_STARTUP = ['dash-to-panel@jderose9.github.com', 'just-perfection-desktop@just-perfection'];
// Menus that can launch apps. Without one, the app grid stays reachable even with
// the overview off, so there is always a way to open an app.
const LAUNCHERS = ['arcmenu@arcmenu.com'];
const ACTIVE = 1;

// Modules stay loaded for the whole Shell session, so this tells the first enable
// after login apart from a later one (after unlocking, say).
let firstEnable = true;

function running(uuids) {
    return uuids.some(uuid => Main.extensionManager.lookup(uuid)?.state === ACTIVE);
}

function enabledInSettings(uuids) {
    const on = global.settings.get_strv('enabled-extensions');
    return uuids.some(uuid => on.includes(uuid));
}

export class DesktopBehaviour {
    constructor(cfg) {
        this._patched = null;
        this._startupId = 0;
        this._realHasOverview = null;
        this.update(cfg);
        const atLogin = firstEnable;
        firstEnable = false;
        if (!cfg.desktop.startOnDesktop || !atLogin)
            return;
        if (Main.layoutManager._startingUp)
            this._skipStartupOverview();
        else if (Main.overview.visible)
            Main.overview.hide();   // GNOME 50 can finish its startup before extensions load
    }

    _skipStartupOverview() {
        // Another extension that manages this may load after us, so go by the
        // settings list rather than what is running yet.
        if (!enabledInSettings(MANAGES_STARTUP)) {
            this._realHasOverview = Main.sessionMode.hasOverview;
            Main.sessionMode.hasOverview = false;
        }
        this._startupId = Main.layoutManager.connect('startup-complete', () => {
            this._endStartup();
            // From GNOME 50 the startup animation can already be running when
            // extensions load, so the overview may have opened anyway.
            if (Main.overview.visible)
                Main.overview.hide();
        });
    }

    _endStartup() {
        if (this._startupId)
            Main.layoutManager.disconnect(this._startupId);
        this._startupId = 0;
        if (this._realHasOverview !== null)
            Main.sessionMode.hasOverview = this._realHasOverview;
        this._realHasOverview = null;
    }

    update(cfg) {
        if (cfg.desktop.overviewOff)
            this._blockOverview();
        else
            this._allowOverview();
    }

    _blockOverview() {
        if (this._patched)
            return;
        const ov = Main.overview;
        const show = ov.show;
        // Ours are own properties over the prototype's methods; deleting them puts the originals back.
        this._patched = {
            show(state = ControlsState.WINDOW_PICKER) {
                if (state === ControlsState.APP_GRID && !running(LAUNCHERS))
                    show.call(ov, state);
            },
            showApps() {
                ov.show(ControlsState.APP_GRID);
            },
            toggle() {
                if (ov.visible)
                    ov.hide();
                else
                    ov.show();
            },
            // The hot corner and the Activities button ask this before opening the overview.
            shouldToggleByCornerOrButton() {
                return false;
            },
        };
        Object.assign(ov, this._patched);
        if (ov._swipeTracker) {
            this._swipeWas = ov._swipeTracker.enabled;
            ov._swipeTracker.enabled = false;           // three-finger swipe up
        }
        this._activities = Main.panel.statusArea.activities?.container ?? null;
        if (this._activities) {
            this._activitiesWas = this._activities.visible;
            this._activities.hide();
        }
        if (ov.visible)
            ov.hide();
    }

    _allowOverview() {
        if (!this._patched)
            return;
        const ov = Main.overview;
        for (const [name, fn] of Object.entries(this._patched)) {
            if (Object.hasOwn(ov, name) && ov[name] === fn)
                delete ov[name];
        }
        this._patched = null;
        if (ov._swipeTracker && this._swipeWas !== undefined)
            ov._swipeTracker.enabled = this._swipeWas;
        this._swipeWas = undefined;
        if (this._activities && this._activitiesWas)
            this._activities.show();
        this._activities = null;
    }

    destroy() {
        this._endStartup();
        this._allowOverview();
    }
}
