// A whole copy of the wallpaper for the glass behind app windows.

import Clutter from 'gi://Clutter';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Background from 'resource:///org/gnome/shell/ui/background.js';

// ---- the wallpaper behind app windows ------------------------------------------------
/**
 * A copy of the wallpaper for the glass behind windows. The Shell's own wallpaper
 * skips whatever an opaque window covers, so glass that copies it has holes there
 * and shows the window below. This one is outside the window stack, so it is
 * always whole. It is never seen itself (opacity 0); only the panes copy it.
 */
export class Wallpaper {
    constructor() {
        this.actor = new Clutter.Actor({name: 'liquid-glass-wallpaper', opacity: 0, reactive: false});
        this._managers = [];
        Main.layoutManager.uiGroup.insert_child_at_index(this.actor, 0);
        this._monitorsId = Main.layoutManager.connect('monitors-changed', () => this._build());
        this._build();
    }

    _build() {
        this._managers.forEach(m => m.destroy());
        this._managers = [];
        this.actor.set_size(...global.stage.get_size());
        for (let i = 0; i < Main.layoutManager.monitors.length; i++) {
            this._managers.push(new Background.BackgroundManager({
                container: this.actor, monitorIndex: i, vignette: false, controlPosition: true,
            }));
        }
    }

    destroy() {
        Main.layoutManager.disconnect(this._monitorsId);
        this._managers.forEach(m => m.destroy());
        this._managers = [];
        this.actor.destroy();
    }
}
