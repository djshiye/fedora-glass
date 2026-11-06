// Fedora Glass for GNOME Shell. The look is set in the Fedora Glass app, which
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
import {LockWidgets} from './lockwidgets.js';
import {PopupStyle} from './popupstyle.js';
import {Safety, guarded} from './safety.js';
import {Speed} from './speed.js';
import {GlassManager} from './surfaces.js';
import {UserThemesTidy} from './themetidy.js';
import {effectiveConfig} from './tuning.js';

export default class LiquidGlassExtension extends Extension {
    enable() {
        this._locked = null;
        // Safe mode: if the glass keeps failing it is turned off (plain panels and
        // menus) until the Fedora Glass app turns it back on.
        this._safety = new Safety(tripped => this._safeMode(tripped));
        this._config = new Config(guarded('settings change', cfg => {
            this._speed?.update(cfg);
            this._manager?.update(this._effective(cfg));
            this._desktop?.update(cfg);
            this._lock?.update(cfg);
            this._widgets?.update(cfg);
            this._animations?.update(cfg);
            this._popupStyle?.update(cfg);
        }));
        this._modeId = Main.sessionMode.connect('updated', () => this._sync());
        // User Themes leaves a listener behind at every lock (see themetidy.js).
        try {
            this._tidy = new UserThemesTidy();
        } catch (e) {
            console.error(`Fedora Glass: no User Themes tidy-up: ${e}`);
            this._tidy = null;
        }
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
                console.error(`Fedora Glass: no lock screen glass: ${e}`);
                this._lock = null;
            }
            // Widgets come with or without the glass (GNOME's own lock screen gets them too).
            try {
                this._leavingWidgets?.destroy();
                this._widgets?.destroy();
            } catch (e) {
                console.error(`Fedora Glass: removing old lock screen widgets: ${e}`);
            }
            this._leavingWidgets = null;
            try {
                this._widgets = new LockWidgets(cfg);
            } catch (e) {
                console.error(`Fedora Glass: no lock screen widgets: ${e}`);
                this._widgets = null;
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
            // They ride up with the sheet and go with GNOME's lock screen.
            try {
                this._leavingWidgets?.destroy();
            } catch {}
            this._leavingWidgets = this._widgets;
            this._widgets = null;
            try {
                this._leavingWidgets?.unlocking();
            } catch {
                this._leavingWidgets?.destroy();
                this._leavingWidgets = null;
            }
            this._desktop = new DesktopBehaviour(cfg);
            // How much the glass draws (the glass quality setting, or auto when frames drop).
            try {
                this._speed = new Speed(cfg, guarded('speed change',
                    () => this._manager?.update(this._effective(this._config.value))));
            } catch (e) {
                console.error(`Fedora Glass: no speed check or auto quality: ${e}`);
                this._speed = null;
            }
            this._startGlass(cfg);
            try {
                this._rescue = new ArcMenuRescue();
            } catch (e) {
                console.error(`Fedora Glass: no ArcMenu restart helper: ${e}`);
                this._rescue = null;
            }
        }
    }

    _effective(cfg) {
        return effectiveConfig(cfg, this._speed?.level ?? 0);
    }

    _startGlass(cfg) {
        if (this._safety?.tripped) {
            console.warn('Fedora Glass: safe mode is on, so the glass stays off. Turn it back on in the Fedora Glass app.');
            return;
        }
        try {
            this._manager = new GlassManager(this._effective(cfg));
            this._animations = new Animations(cfg);
        } catch (e) {
            logError(e, 'Fedora Glass: starting the glass');
            this._stopGlass();
            this._safety?.startFailed();
            return;
        }
        // Only with the glass: without it these see-through pop-ups would have nothing behind them.
        try {
            this._popupStyle = new PopupStyle(cfg);
        } catch (e) {
            console.error(`Fedora Glass: no pop-up styles: ${e}`);
            this._popupStyle = null;
        }
    }

    _stopGlass() {
        try {
            this._popupStyle?.destroy();
        } catch (e) {
            logError(e, 'Fedora Glass: removing the pop-up styles');
        }
        this._popupStyle = null;
        // Animations first, so windows and icons mid-animation land at once and
        // GNOME's own window animations are back.
        try {
            this._animations?.destroy();
        } catch (e) {
            logError(e, 'Fedora Glass: turning the animations off');   // the rest still turns off
        }
        this._animations = null;
        try {
            this._manager?.destroy();
        } catch (e) {
            logError(e, 'Fedora Glass: turning the glass off');
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
        try {
            this._speed?.destroy();
        } catch (e) {
            logError(e, 'Fedora Glass: turning the speed watch off');
        }
        this._speed = null;
    }

    // GNOME keeps this extension on while the screen is locked (session-modes has
    // "unlock-dialog") for the glass lock screen; _sync switches the rest off then.
    disable() {
        if (this._modeId)
            Main.sessionMode.disconnect(this._modeId);
        this._modeId = 0;
        this._tidy?.destroy();
        this._tidy = null;
        this._lock?.destroy();
        this._lock = null;
        this._leaving?.destroy();
        this._leaving = null;
        this._widgets?.destroy();
        this._widgets = null;
        this._leavingWidgets?.destroy();
        this._leavingWidgets = null;
        this._stopSession();
        this._config?.destroy();
        this._config = null;
        this._safety?.destroy();
        this._safety = null;
        this._locked = null;
    }
}
