// Desktop behaviour set in the Fedora Glass app: start on the desktop instead
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
const LAUNCHERS = ['arcmenu@arcmenu.com', 'spawn@djshiye.github.io'];
const ACTIVE = 1;

// Modules stay loaded for the whole Shell session, so this tells the first enable
// after login apart from a later one (after unlocking, say).
let firstEnable = true;

function running(uuids) {
    return uuids.some(uuid => Main.extensionManager.lookup(uuid)?.state === ACTIVE);
}

// GNOME's dash in the overview fills itself in the first time it is drawn: each app
// icon makes its picture once GNOME has worked out its style, which happens when the
// overview first shows. Starting on the desktop skips that first showing, and the dash
// then fills itself in while hidden: it finds its first icon without a picture, stops
// with an error (dash.js _adjustIconSize), and its app icons stay invisible, all but
// "Show Apps" (stock GNOME, where the dash is on screen; Dash to Panel and Dash to Dock
// hide it). Working out the icons' style first, and showing the ones it left hidden,
// puts them back.
function styleDashItem(item) {
    try {
        item.child?.ensure_style?.();
        item.child?._delegate?.icon?.ensure_style?.();
    } catch {}
}

export function repairDash() {
    const dash = Main.overview?.dash;
    const box = dash?._box;
    if (!box)
        return false;
    let fixed = false;
    for (const item of box.get_children()) {
        if (!item.child)
            continue;
        styleDashItem(item);
        if (item.scale_x === 0 && !item.animatingOut && typeof item.show === 'function' &&
            item.constructor?.name === 'DashItemContainer') {
            item.show(false);
            fixed = true;
        }
    }
    if (fixed) {
        try {
            dash._adjustIconSize?.();
        } catch (e) {
            console.warn(`Fedora Glass: the dash could not size its icons: ${e}`);
        }
    }
    return fixed;
}

// Switched on in the settings and installed. GNOME keeps the name of an extension that
// was removed on its list, and one that no longer exists never takes this over. GNOME
// knows every installed extension before it starts the first one, so one that starts
// after us is found here too.
function enabledInSettings(uuids) {
    const on = global.settings.get_strv('enabled-extensions');
    const off = global.settings.get_strv('disabled-extensions') ?? [];
    return uuids.some(uuid => on.includes(uuid) && !off.includes(uuid) &&
        installed(uuid));
}

function installed(uuid) {
    try {
        return Boolean(Main.extensionManager.lookup(uuid));
    } catch {
        return true;    // can't tell: go by the settings, as before
    }
}

export class DesktopBehaviour {
    constructor(cfg) {
        this._patched = null;
        this._startupId = 0;
        this._closeAfterStartupId = 0;
        this._realHasOverview = null;
        this._dashId = 0;
        this._dashAddId = 0;
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
        // Each app icon the dash adds while hidden gets its style at once, so the dash
        // finds a picture on it (see repairDash).
        const box = Main.overview?.dash?._box;
        if (typeof box?.connect === 'function') {
            box.get_children().forEach(styleDashItem);
            this._dashBox = box;
            this._dashAddId = box.connect('child-added', (_b, item) => styleDashItem(item));
        }
        this._repairDashOnShow();
        // Another extension that manages this may load after us, so go by the
        // settings list rather than what is running yet.
        if (!enabledInSettings(MANAGES_STARTUP)) {
            this._realHasOverview = Main.sessionMode.hasOverview;
            Main.sessionMode.hasOverview = false;
        }
        this._startupId = Main.layoutManager.connect('startup-complete', () => {
            this._endStartup();
            repairDash();
            // From GNOME 50 the startup animation can already be running when
            // extensions load, so the overview may have opened anyway.
            if (Main.overview.visible)
                Main.overview.hide();
        });
    }

    // The dash can also fill itself in later, still hidden (GNOME waits up to 20 s
    // for it): check it again when the overview first opens.
    _repairDashOnShow() {
        if (this._dashId || typeof Main.overview?.connect !== 'function')
            return;
        this._dashId = Main.overview.connect('showing', () => {
            Main.overview.disconnect(this._dashId);
            this._dashId = 0;
            this._stopStylingDash();
            repairDash();
        });
    }

    _stopStylingDash() {
        if (this._dashAddId) {
            try {
                this._dashBox.disconnect(this._dashAddId);
            } catch {}   // the dash went
        }
        this._dashAddId = 0;
        this._dashBox = null;
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
            this._closeOverview();
    }

    _closeOverview() {
        // While GNOME is starting, the overview that shows is its startup
        // animation. Closing it before its first layout leaves GNOME waiting
        // for that layout for good: start-up never finishes, the second
        // screen keeps no wallpaper and the overview stays off for the session.
        // So close it once start-up has finished.
        if (!Main.layoutManager._startingUp) {
            Main.overview.hide();
            return;
        }
        if (this._closeAfterStartupId)
            return;
        this._closeAfterStartupId = Main.layoutManager.connect('startup-complete', () => {
            Main.layoutManager.disconnect(this._closeAfterStartupId);
            this._closeAfterStartupId = 0;
            if (this._patched && Main.overview.visible)
                Main.overview.hide();
        });
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
        // Locked: GNOME's panel has just hidden every button the lock screen doesn't
        // have (its own session-mode handler runs before ours). Showing Activities again
        // here would put it on the lock screen's top bar; unlocking shows it by itself.
        if (this._activities && this._activitiesWas && !Main.sessionMode.isLocked)
            this._activities.show();
        this._activities = null;
    }

    destroy() {
        this._endStartup();
        if (this._dashId)
            Main.overview.disconnect(this._dashId);
        this._dashId = 0;
        if (this._closeAfterStartupId)
            Main.layoutManager.disconnect(this._closeAfterStartupId);
        this._closeAfterStartupId = 0;
        this._allowOverview();
    }
}
