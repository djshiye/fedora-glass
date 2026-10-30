// Glass behind the top bar and Dash to Panel.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {Signals} from './common.js';
import {wrapAnimator} from './dtpquiet.js';
import {Follower} from './follower.js';

// ---- Dash to Panel's attention wiggle -------------------------------------------
// While an app wants attention (an urgent notification, such as "Files is
// ready"), Dash to Panel wiggles its icon for half a second every 3 s. Its
// timeline still sets the icon's rotation on every frame of the other 2.5 s,
// to 0 each time, and Clutter redraws the icon for each set, which makes the
// panel's reflections pane re-render about 16 times a second for as long as
// the app wants attention. Each icon it wiggles drops sets that change nothing.
const Z = Clutter.RotateAxis.Z_AXIS;
const QUIET = {
    configurable: true,
    get() {
        return this.get_rotation_angle(Z);
    },
    set(v) {
        if (v !== this.get_rotation_angle(Z))
            this.set_rotation_angle(Z, v);
    },
};

function quiet(target) {
    if (!Object.hasOwn(target, 'rotation_angle_z'))
        Object.defineProperty(target, 'rotation_angle_z', QUIET);
}

let warned = false;
function warnOnce(msg) {
    if (!warned)
        console.warn(`Liquid Glass: ${msg}`);
    warned = true;
}

function unquiet(target) {
    if (Object.getOwnPropertyDescriptor(target, 'rotation_angle_z')?.set === QUIET.set)
        delete target.rotation_angle_z;
}

// ---- top bar and Dash to Panel ------------------------------------------------
export class Panels {
    constructor(cfg) {
        this.cfg = cfg;
        this._followers = [];
        this._signals = new Signals();
        this._dtpId = 0;
        this._rescanId = 0;
        this._quieted = new Map();   // Dash to Panel IconAnimator -> undo
        this._signals.on(Main.extensionManager, 'extension-state-changed', () => this.rescanSoon());
        this.rescan();
    }

    _panels() {
        const dtp = global.dashToPanel;
        if (dtp?.panels?.length) {
            if (dtp !== this._dtp && typeof dtp.connect === 'function') {
                // Dash to Panel makes a new object each time it is enabled.
                this._disconnectDtp();
                try {
                    this._dtpId = dtp.connect('panels-created', () => this.rescanSoon());
                    this._dtp = dtp;
                } catch {
                    this._dtpId = 0;
                }
            }
            return dtp.panels.filter(p => p.panel && p.panelBox?.get_parent())
                .map(p => [p.panel, p.panelBox]);
        }
        const box = Main.layoutManager.panelBox;
        return box?.get_parent() ? [[Main.panel, box]] : [];
    }

    _disconnectDtp() {
        if (this._dtp && this._dtpId) {
            try {
                this._dtp.disconnect(this._dtpId);
            } catch {}
        }
        this._dtp = null;
        this._dtpId = 0;
    }

    rescanSoon() {
        if (this._rescanId)
            return;
        this._rescanId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 400, () => {
            this._rescanId = 0;
            this.rescan();
            return GLib.SOURCE_REMOVE;
        });
    }

    _quietIcons() {
        const live = new Set((global.dashToPanel?.panels ?? []).map(p => p.taskbar?.iconAnimator).filter(Boolean));
        for (const [anim, undo] of this._quieted) {
            if (!live.has(anim)) {
                this._quieted.delete(anim);
                try {
                    undo();
                } catch {}   // Dash to Panel already destroyed it
            }
        }
        for (const anim of live) {
            if (this._quieted.has(anim))
                continue;
            try {
                const undo = wrapAnimator(anim, quiet, unquiet, warnOnce);
                if (undo)
                    this._quieted.set(anim, undo);
            } catch (e) {
                logError(e, 'Liquid Glass: could not quiet Dash to Panel icon animations');
            }
        }
    }

    _unquietIcons() {
        for (const undo of this._quieted.values()) {
            try {
                undo();
            } catch {}
        }
        this._quieted.clear();
    }

    rescan() {
        this._quietIcons();
        this._followers.forEach(f => f.destroy());
        this._followers = [];
        for (const [target, anchor] of this._panels()) {
            this._followers.push(new Follower(target, anchor, this.cfg.parts.panel,
                f => (this._followers = this._followers.filter(x => x !== f))));
        }
    }

    update(cfg) {
        this.cfg = cfg;
        this._followers.forEach(f => f.update(cfg.parts.panel));
    }

    sync() {
        this._followers.forEach(f => f.queue());
    }

    destroy() {
        if (this._rescanId)
            GLib.source_remove(this._rescanId);
        this._disconnectDtp();
        this._unquietIcons();
        this._signals.clear();
        this._followers.forEach(f => f.destroy());
        this._followers = [];
    }
}
