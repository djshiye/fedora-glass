// Brings ArcMenu back after a known ArcMenu bug (ArcMenu 70, GNOME 50).
//
// When an extension is switched off, GNOME quietly switches off every extension
// that started after it and then on again, in start order ("rebase", see
// extensionSystem.js). It does this without changing their state, so if ArcMenu
// comes back before Dash to Panel, ArcMenu still sees Dash to Panel as running,
// finds no panels and stops with "this.panel is undefined" (menuController.js).
// GNOME then marks it as failed, and only a new login brought it back.
//
// This waits until Dash to Panel has its panels again and starts ArcMenu once
// more. Only that error is handled, a few times per session at most, and only
// ArcMenu is ever touched.

import GLib from 'gi://GLib';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

export const ARCMENU = 'arcmenu@arcmenu.com';
export const DASH_TO_PANEL = 'dash-to-panel@jderose9.github.com';
// GNOME's ExtensionState (misc/extensionUtils.js).
export const State = {ACTIVE: 1, INACTIVE: 2, ERROR: 3};
export const MAX_RESCUES = 3;         // per Shell session
export const POLL_MS = 250;
export const GIVE_UP_MS = 15000;      // Dash to Panel never came back: leave ArcMenu as it is

// The one ArcMenu failure this knows how to undo.
export function isPanelRace(ext) {
    return ext?.uuid === ARCMENU && ext.state === State.ERROR &&
        /this\.panel is undefined|can't access property "statusArea"/.test(String(ext.error ?? ''));
}

// Module scope: the count survives this extension being switched off and on in a rebase.
let rescues = 0;

export function resetForTests() {
    rescues = 0;
}

export class ArcMenuRescue {
    constructor() {
        this._manager = Main.extensionManager;
        this._wait = 0;
        this._waited = 0;
        this._id = this._manager.connect('extension-state-changed', (_m, ext) => {
            if (isPanelRace(ext))
                this._schedule();
        });
        // This extension may have been in the same rebase and come back after
        // ArcMenu failed, so look once now too.
        if (isPanelRace(this._manager.lookup(ARCMENU)))
            this._schedule();
    }

    _dtpReady() {
        const dtp = this._manager.lookup(DASH_TO_PANEL);
        return dtp?.state === State.ACTIVE && (global.dashToPanel?.panels?.length ?? 0) > 0;
    }

    _schedule() {
        if (this._wait || rescues >= MAX_RESCUES)
            return;
        this._waited = 0;
        // Let GNOME finish the rebase first: Dash to Panel comes back after ArcMenu.
        this._wait = GLib.timeout_add(GLib.PRIORITY_DEFAULT, POLL_MS, () => {
            this._waited += POLL_MS;
            const ext = this._manager.lookup(ARCMENU);
            if (!isPanelRace(ext)) {
                this._wait = 0;            // fixed or changed by someone else
                return GLib.SOURCE_REMOVE;
            }
            if (!this._dtpReady()) {
                if (this._waited < GIVE_UP_MS)
                    return GLib.SOURCE_CONTINUE;
                this._wait = 0;
                return GLib.SOURCE_REMOVE;
            }
            this._wait = 0;
            this._rescue(ext);
            return GLib.SOURCE_REMOVE;
        });
    }

    _rescue(ext) {
        rescues++;
        // Undo what ArcMenu set up before it failed, so starting it again adds nothing twice.
        try {
            ext.stateObj?.disable();
        } catch {}
        // GNOME's restart in start order keeps ArcMenu's stylesheet loaded, and
        // starting ArcMenu loads it again. Loaded twice, a later switch-off leaves an
        // empty entry in the Shell's list that breaks the next theme reload (User
        // Themes then fails and the Shell theme is gone until a restart).
        try {
            this._manager._unloadExtensionStylesheet?.(ext);
        } catch {}
        // GNOME keeps a failed extension in its start order; it is added again when it starts.
        const order = this._manager._extensionOrder;
        const at = order?.indexOf(ARCMENU) ?? -1;
        if (at >= 0)
            order.splice(at, 1);
        ext.error = '';
        this._manager._changeExtensionState(ext, State.INACTIVE);
        console.log('Fedora Glass: restarting ArcMenu, which GNOME restarted before Dash to Panel');
        Promise.resolve(this._manager._callExtensionEnable(ARCMENU)).catch(e =>
            console.error(`Fedora Glass: ArcMenu did not restart: ${e}`));
    }

    destroy() {
        if (this._id)
            this._manager.disconnect(this._id);
        this._id = 0;
        if (this._wait)
            GLib.source_remove(this._wait);
        this._wait = 0;
    }
}
