// Liquid Glass for GNOME Shell. The look is set in the Liquid Glass app, which
// writes ~/.config/liquid-glass/shell-glass.json; changes show up live.
// It also decides whether GNOME starts on the desktop or in the overview.
//
// The extension also runs on the lock screen ("unlock-dialog" session mode), to
// draw the glass lock screen. While the screen is locked everything else is
// switched off: no glass on the panel, menus or windows, no copies of windows,
// no pointer or input handlers, no desktop behaviour. Only lock.js runs, and it
// copies nothing but the wallpaper.

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

import {Animations} from './animations.js';
import {Config} from './config.js';
import {DesktopBehaviour} from './desktop.js';
import {LockGlass} from './lock.js';
import {GlassManager} from './surfaces.js';

export default class LiquidGlassExtension extends Extension {
    enable() {
        this._locked = null;
        this._config = new Config(cfg => {
            this._manager?.update(cfg);
            this._desktop?.update(cfg);
            this._lock?.update(cfg);
            this._animations?.update(cfg);
        });
        this._modeId = Main.sessionMode.connect('updated', () => this._sync());
        this._sync();
    }

    _sync() {
        const locked = Main.sessionMode.isLocked;
        if (locked === this._locked)
            return;
        this._locked = locked;
        const cfg = this._config.value;
        if (locked) {
            this._stopSession();
            this._leaving?.destroy();
            this._leaving = null;
            this._lock?.destroy();
            try {
                this._lock = new LockGlass(cfg);
            } catch (e) {
                console.error(`Liquid Glass: no lock screen glass: ${e}`);
                this._lock = null;
            }
        } else {
            // The sheet slides up into the desktop, then takes itself away.
            this._leaving?.destroy();
            this._leaving = this._lock;
            this._lock = null;
            try {
                this._leaving?.unlocking();
            } catch {
                this._leaving?.destroy();
                this._leaving = null;
            }
            this._desktop = new DesktopBehaviour(cfg);
            this._manager = new GlassManager(cfg);
            this._animations = new Animations(cfg);
        }
    }

    _stopSession() {
        // First, so windows and icons mid-animation land at once and GNOME's own
        // window animations are back before the lock screen comes up.
        try {
            this._animations?.destroy();
        } catch (e) {
            logError(e, 'Liquid Glass: turning the animations off');   // the rest still turns off
        }
        this._animations = null;
        this._desktop?.destroy();
        this._desktop = null;
        this._manager?.destroy();
        this._manager = null;
    }

    // GNOME keeps this extension on while the screen is locked (session-modes has
    // "unlock-dialog") for the glass lock screen; _sync switches the rest off then.
    disable() {
        if (this._modeId)
            Main.sessionMode.disconnect(this._modeId);
        this._modeId = 0;
        this._lock?.destroy();
        this._lock = null;
        this._leaving?.destroy();
        this._leaving = null;
        this._stopSession();
        this._config?.destroy();
        this._config = null;
        this._locked = null;
    }
}
