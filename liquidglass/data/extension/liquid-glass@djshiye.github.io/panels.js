// Glass behind the top bar and Dash to Panel.

import GLib from 'gi://GLib';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {Signals} from './common.js';
import {Follower} from './follower.js';

// ---- top bar and Dash to Panel ------------------------------------------------
export class Panels {
    constructor(cfg) {
        this.cfg = cfg;
        this._followers = [];
        this._signals = new Signals();
        this._dtpId = 0;
        this._rescanId = 0;
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

    rescan() {
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
        this._signals.clear();
        this._followers.forEach(f => f.destroy());
        this._followers = [];
    }
}
