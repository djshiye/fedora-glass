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
import {ArcMenuRescue} from './arcrescue.js';
import {Config} from './config.js';
import {DesktopBehaviour} from './desktop.js';
import {LockGlass} from './lock.js';
import {Safety, guarded} from './safety.js';
import {GlassManager} from './surfaces.js';

export default class LiquidGlassExtension extends Extension {
    enable() {
        this._locked = null;
        // Safe mode: if the glass keeps failing it is turned off (plain panels and
        // menus) until the Liquid Glass app turns it back on.
        this._safety = new Safety(tripped => this._safeMode(tripped));
        this._config = new Config(guarded('settings change', cfg => {
            this._manager?.update(cfg);
            this._desktop?.update(cfg);
            this._lock?.update(cfg);
            this._animations?.update(cfg);
        }));
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
            this._startGlass(cfg);
            try {
                this._rescue = new ArcMenuRescue();
            } catch (e) {
                console.error(`Liquid Glass: no ArcMenu restart helper: ${e}`);
                this._rescue = null;
            }
        }
    }

    _startGlass(cfg) {
        if (this._safety?.tripped) {
            console.warn('Liquid Glass: safe mode is on, so the glass stays off. Turn it back on in the Liquid Glass app.');
            return;
        }
        try {
            this._manager = new GlassManager(cfg);
            this._animations = new Animations(cfg);
        } catch (e) {
            logError(e, 'Liquid Glass: starting the glass');
            this._stopGlass();
            this._safety?.startFailed();
        }
    }

    _stopGlass() {
        // Animations first, so windows and icons mid-animation land at once and
        // GNOME's own window animations are back.
        try {
            this._animations?.destroy();
        } catch (e) {
            logError(e, 'Liquid Glass: turning the animations off');   // the rest still turns off
        }
        this._animations = null;
        try {
            this._manager?.destroy();
        } catch (e) {
            logError(e, 'Liquid Glass: turning the glass off');
        }
        this._manager = null;
    }

    _safeMode(tripped) {
        if (tripped)
            this._stopGlass();
        else if (this._locked === false && !this._manager)
            this._startGlass(this._config.value);
    }

    _stopSession() {
        // Glass first, so GNOME's own window animations are back before the lock screen comes up.
        this._stopGlass();
        this._rescue?.destroy();
        this._rescue = null;
        this._desktop?.destroy();
        this._desktop = null;
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
        this._safety?.destroy();
        this._safety = null;
        this._locked = null;
    }
}
