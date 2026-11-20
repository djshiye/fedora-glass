// Fedora Glass for GNOME Shell. The look is set in the Fedora Glass app, which
// writes ~/.config/liquid-glass/shell-glass.json; changes show up live.
// It also decides whether GNOME starts on the desktop or in the overview.
//
// The extension also runs on the lock screen ("unlock-dialog" session mode), to
// draw the glass lock screen. While the screen is locked everything else is
// switched off: no glass on the panel, menus or windows, no copies of windows,
// no pointer or input handlers, no desktop behaviour. Only lock.js runs, and it
// copies nothing but the wallpaper.
//
// The "Glass" tile in Quick Settings (quicktoggle.js) pauses the glass for the rest of
// the session: it comes down as in safe mode, and the next login starts with it on again.
// The pause is said in ~/.cache/liquid-glass/paused.json for the Fedora Glass app, which
// can ask for the glass back (pausestate.js).

import GLib from 'gi://GLib';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

import {Animations} from './animations.js';
import {ArcMenuRescue} from './arcrescue.js';
import {Config} from './config.js';
import {DesktopBehaviour} from './desktop.js';
import {SettingsSweep} from './gcsweep.js';
import {WeatherFrost} from './frost.js';
import {LockGlass} from './lock.js';
import {LockWidgets} from './lockwidgets.js';
import {PausedStyle} from './paused.js';
import {PauseState} from './pausestate.js';
import {PopupStyle} from './popupstyle.js';
import {GlassSwitch} from './quicktoggle.js';
import {Safety, guarded} from './safety.js';
import {Speed} from './speed.js';
import {GlassManager} from './surfaces.js';
import {UserThemesTidy} from './themetidy.js';
import {effectiveConfig} from './tuning.js';
import {Windows, allSolid} from './windows.js';

// GNOME switches this extension off and straight on again whenever an extension that was
// started before it is switched off ("rebase"): at the first lock of a session, when Dash
// to Panel, ArcMenu and User Themes leave for the lock screen, and when one of them is
// restarted. That is no new start: a pause from Quick Settings and the level the speed watch
// had settled on carry over it. Up to 1.7.8 the first lock took the pause away: the lock
// screen drew glass and all the glass was back after unlocking. Module scope: it outlives
// the extension object, and a new Shell (the next login) starts without it.
const BACK_SOON_US = 10e6;
let left = null;        // {at, paused} of the last disable()

export default class FedoraGlassExtension extends Extension {
    enable() {
        // First, so it also sees the extensions GNOME restarts after this one starts.
        try {
            this._sweep = new SettingsSweep(this.uuid);
        } catch (e) {
            console.error(`Fedora Glass: no settings sweep: ${e}`);
            this._sweep = null;
        }
        this._locked = null;
        const back = left && GLib.get_monotonic_time() - left.at < BACK_SOON_US ? left : null;
        left = null;
        if (!back)
            Speed.forget?.();       // switched off and on by hand: the speed watch begins afresh
        // Paused from Quick Settings: held here, so it lasts through locking the screen and
        // is gone at the next login. Only said for the app (pausestate.js), never read back.
        this._paused = back?.paused === true;
        try {
            this._pauseState = new PauseState(() => this._setPaused(false));
            if (this._paused)
                this._pauseState.set(true);
        } catch (e) {
            console.error(`Fedora Glass: the app can't see a pause: ${e}`);
            this._pauseState = null;
        }
        // Safe mode: if the glass keeps failing it is turned off (plain panels and
        // menus) until the Fedora Glass app turns it back on.
        this._safety = new Safety(tripped => this._safeMode(tripped));
        // Each part follows a settings change on its own: one that throws must not stop the
        // others from getting it. Up to 1.7.4 the first failure left every part after it on
        // the old settings until the next change. It still counts as one error for safe mode.
        this._config = new Config(guarded('settings change', cfg => {
            let failed = null;
            const part = (name, fn) => {
                try {
                    fn();
                } catch (e) {
                    if (failed)
                        console.error(`Fedora Glass: settings change (${name}) failed too: ${e}`);
                    else
                        failed = new Error(`${name}: ${e?.message ?? e}`, {cause: e});
                }
            };
            // The glass is updated with the new level just below, so the speed callback
            // must not update all of it a second time meanwhile.
            this._inConfigChange = true;
            try {
                part('speed', () => this._speed?.update(cfg));
            } finally {
                this._inConfigChange = false;
            }
            part('glass', () => this._manager?.update(this._effective(cfg)));
            part('frost', () => this._frost?.update(cfg));
            part('desktop', () => this._desktop?.update(cfg));
            part('lock', () => this._lock?.update(cfg));
            part('widgets', () => this._widgets?.update(cfg));
            part('animations', () => this._animations?.update(cfg));
            part('popups', () => this._popupStyle?.update(cfg));
            part('paused style', () => this._pausedStyle?.update(cfg));
            part('solid windows', () => this._solidWindows?.update(allSolid(cfg)));
            part('switch', () => {
                if (this._locked === false)
                    this._syncSwitch(cfg);
            });
            if (failed)
                throw failed;
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
            // The pop-up sheet goes once the lock screen is up (see PopupStyle.destroyLater).
            // Only one of the two sheets is ever loaded.
            const popups = this._popupStyle ?? this._pausedStyle;
            this._popupStyle = null;
            this._pausedStyle = null;
            this._stopSession();
            this._popupsLater(popups);
            this._leaving?.destroy();
            this._leaving = null;
            this._lock?.destroy();
            this._lock = null;
            this._startLock(cfg);
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
            // Start on the desktop and overview off: like each part here, a failure
            // must not take the glass and the rest down with it.
            try {
                this._desktop = new DesktopBehaviour(cfg);
            } catch (e) {
                console.error(`Fedora Glass: no desktop behaviour (start on the desktop, overview off): ${e}`);
                this._desktop = null;
            }
            // How much the glass draws (the glass quality setting, or auto when frames drop).
            try {
                this._speed = new Speed(cfg, guarded('speed change',
                    () => {
                        if (!this._inConfigChange)
                            this._manager?.update(this._effective(this._config.value));
                    }));
            } catch (e) {
                console.error(`Fedora Glass: no speed check or auto quality: ${e}`);
                this._speed = null;
            }
            this._startGlass(cfg);
            this._syncPausedStyle();
            this._syncSwitch(cfg);
            try {
                this._rescue = new ArcMenuRescue();
            } catch (e) {
                console.error(`Fedora Glass: no ArcMenu restart helper: ${e}`);
                this._rescue = null;
            }
        }
    }

    _startLock(cfg) {
        if (this._paused)
            return;     // the Quick Settings tile promised all glass is paused, the lock screen's too
        try {
            this._lock = new LockGlass(cfg);
        } catch (e) {
            console.error(`Fedora Glass: no lock screen glass: ${e}`);
            this._lock = null;
        }
    }

    _popupsLater(popups) {
        if (!popups)
            return;
        this._dropLeavingPopups();
        this._leavingPopups = popups;
        try {
            popups.destroyLater(() => {
                if (this._leavingPopups === popups)
                    this._leavingPopups = null;
            });
        } catch (e) {
            logError(e, 'Fedora Glass: removing the pop-up styles');
            this._dropLeavingPopups();
        }
    }

    _dropLeavingPopups() {
        try {
            this._leavingPopups?.destroy();
        } catch (e) {
            logError(e, 'Fedora Glass: removing the pop-up styles');
        }
        this._leavingPopups = null;
    }

    _effective(cfg) {
        return effectiveConfig(cfg, this._speed?.level ?? 0);
    }

    _startGlass(cfg) {
        if (this._paused)
            return;     // paused from Quick Settings until the user turns it back on
        if (this._safety?.tripped) {
            console.warn('Fedora Glass: safe mode is on, so the glass stays off. Turn it back on in the Fedora Glass app.');
            return;
        }
        // From here on the Shell stopping soon after is a crash of the glass (safety.js),
        // also one in the middle of starting it.
        this._safety?.glassStarted();
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
        // The solid sheet of a paused glass goes first, so the two are never loaded together.
        // An unlock right after a lock: the old sheet goes first (both use the same file).
        this._dropPausedStyle();
        this._dropLeavingPopups();
        // Weather frost: off unless the user turned it on. With the glass, so a pause or
        // safe mode takes it away too, and the lock screen's glass never gets it.
        try {
            this._frost = new WeatherFrost(cfg);
        } catch (e) {
            console.error(`Fedora Glass: no weather frost: ${e}`);
            this._frost = null;
        }
        try {
            this._popupStyle = new PopupStyle(cfg);
        } catch (e) {
            console.error(`Fedora Glass: no pop-up styles: ${e}`);
            this._popupStyle = null;
        }
    }

    _stopGlass() {
        try {
            this._frost?.destroy();
        } catch (e) {
            logError(e, 'Fedora Glass: turning the weather frost off');
        }
        this._frost = null;
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
        this._syncPausedStyle();
        this._showSwitch();
    }

    // ---- solid surfaces while the glass is paused or in safe mode (paused.js) ----------
    /** On the desktop with the glass paused or in safe mode, the theme's see-through surfaces
     *  go nearly solid; with the glass back, or on the lock screen, they are as the theme has them. */
    _syncPausedStyle() {
        const want = this._locked === false && !this._manager && (this._paused || !!this._safety?.tripped);
        if (!want) {
            this._dropPausedStyle();
            return;
        }
        this._syncSolidWindows();
        if (this._pausedStyle)
            return;
        // At once, not after a lock's later removal: that one is the glass's own sheet.
        this._dropLeavingPopups();
        try {
            this._pausedStyle = new PausedStyle(this._config.value);
        } catch (e) {
            console.error(`Fedora Glass: no solid surfaces while paused: ${e}`);
            this._pausedStyle = null;
        }
    }

    _dropPausedStyle() {
        try {
            this._pausedStyle?.destroy();
        } catch (e) {
            logError(e, 'Fedora Glass: removing the solid surfaces');
        }
        this._pausedStyle = null;
        this._dropSolidWindows();
    }

    // ---- app windows while the glass is paused or in safe mode --------------------------
    /** The GTK, Qt and terminal themes paint app windows partly see-through for the glass
     *  to frost what is behind them. With the glass paused or in safe mode nothing was behind
     *  them, so even Frosted or Solid showed the windows below sharp through every window.
     *  Until the glass is back, each such window gets a plain solid backdrop in the theme's
     *  window colour (as for an app on the user's no-glass list; see windows.js allSolid). */
    _syncSolidWindows() {
        if (this._solidWindows)
            return;
        try {
            this._solidWindows = new Windows(allSolid(this._config.value));
        } catch (e) {
            console.error(`Fedora Glass: no solid app windows while the glass is off: ${e}`);
            this._dropSolidWindows();
        }
    }

    _dropSolidWindows() {
        try {
            this._solidWindows?.destroy();
        } catch (e) {
            logError(e, 'Fedora Glass: removing the solid app window backdrops');
        }
        this._solidWindows = null;
    }

    // ---- the Quick Settings switch ----------------------------------------------------
    /** The tile is there while the setting says so; turned off while paused, the glass comes back. */
    _syncSwitch(cfg) {
        const want = cfg?.quickToggle?.enabled !== false;
        if (!want) {
            this._dropSwitch();
            if (this._paused)
                this._setPaused(false);
            return;
        }
        if (!this._switch) {
            try {
                this._switch = new GlassSwitch(this.path, paused => this._setPaused(paused));
            } catch (e) {
                console.error(`Fedora Glass: no Glass switch in Quick Settings: ${e}`);
                this._switch = null;
            }
        }
        this._showSwitch();
    }

    _showSwitch() {
        try {
            this._switch?.setState(this._paused, !!this._safety?.tripped);
        } catch (e) {
            logError(e, 'Fedora Glass: the Quick Settings switch');
        }
    }

    _dropSwitch() {
        try {
            this._switch?.destroy();
        } catch (e) {
            logError(e, 'Fedora Glass: removing the Quick Settings switch');
        }
        this._switch = null;
    }

    /** Pause the glass (the safe mode path: it all comes down), or start it again. */
    _setPaused(paused) {
        if (paused === this._paused)
            return;
        this._paused = paused;
        try {
            this._pauseState?.set(paused);
        } catch (e) {
            logError(e, 'Fedora Glass: saying the glass is paused');
        }
        if (paused) {
            this._stopGlass();
            // A Shell that stops while paused is no crash of the glass (safety.js).
            this._safety?.glassStopped();
        } else if (this._locked === false && !this._manager) {
            this._startGlass(this._config.value);
        } else if (this._locked === true && !this._lock) {
            this._startLock(this._config.value);
        }
        this._syncPausedStyle();
        this._showSwitch();
    }

    _stopSession() {
        // No Quick Settings on the lock screen; a pause carries on after it.
        this._dropSwitch();
        // Glass first, so GNOME's own window animations are back before the lock screen comes up.
        this._stopGlass();
        this._dropPausedStyle();
        this._safety?.glassStopped();
        // Each one on its own, as the glass above: one that fails must not keep the rest on.
        try {
            this._rescue?.destroy();
        } catch (e) {
            logError(e, 'Fedora Glass: removing the ArcMenu restart helper');
        }
        this._rescue = null;
        try {
            this._desktop?.destroy();
        } catch (e) {
            logError(e, 'Fedora Glass: putting the overview back');
        }
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
        // Each part goes even if one before it fails to: up to 1.7.8 one that threw here
        // left the glass, its file watchers and safe mode running after the switch-off.
        try {
            this._tidy?.destroy();
        } catch (e) {
            logError(e, 'Fedora Glass: removing the User Themes tidy-up');
        }
        this._tidy = null;
        try {
            this._lock?.destroy();
        } catch (e) {
            logError(e, 'Fedora Glass: removing the lock screen glass');
        }
        this._lock = null;
        try {
            this._leaving?.destroy();
        } catch (e) {
            logError(e, 'Fedora Glass: removing the lock screen glass');
        }
        this._leaving = null;
        try {
            this._widgets?.destroy();
        } catch (e) {
            logError(e, 'Fedora Glass: removing the lock screen widgets');
        }
        this._widgets = null;
        try {
            this._leavingWidgets?.destroy();
        } catch (e) {
            logError(e, 'Fedora Glass: removing the lock screen widgets');
        }
        this._leavingWidgets = null;
        this._stopSession();
        // (The speed watch is forgotten at the next start that is no quick return: see enable.)
        WeatherFrost.forget?.();
        this._dropLeavingPopups();
        try {
            this._config?.destroy();
        } catch (e) {
            logError(e, 'Fedora Glass: no longer watching the settings');
        }
        this._config = null;
        try {
            this._safety?.destroy();
        } catch (e) {
            logError(e, 'Fedora Glass: turning safe mode off');
        }
        this._safety = null;
        try {
            this._pauseState?.destroy();
        } catch (e) {
            logError(e, 'Fedora Glass: saying the glass is no longer paused');
        }
        this._pauseState = null;
        left = {at: GLib.get_monotonic_time(), paused: this._paused};
        this._paused = false;
        this._locked = null;
        // Last, so everything let go above is collected too (see gcsweep.js).
        this._sweep?.destroy();
        this._sweep = null;
    }
}
