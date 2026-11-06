// Puts glass panes behind Shell surfaces and keeps them in step: the top bar
// or Dash to Panel, every popup menu (quick settings, calendar, ArcMenu, Spawn
// and app menus), notification banners, the volume OSD, Alt+Tab, app windows and
// the overview background.

import Clutter from 'gi://Clutter';
import Shell from 'gi://Shell';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {moving, stopMoving, releaseAllPanes} from './glass.js';
import {WindowWatch, windowWatch, motion, wallpaper, Signals} from './common.js';
import {WindowAnimationHold} from './hold.js';
import {Motion} from './motion.js';
import {Panels} from './panels.js';
import {Popups} from './popups.js';
import {Wallpaper} from './wallpaper.js';
import {Windows} from './windows.js';

// ---- overview background ---------------------------------------------------------------
class OverviewBackdrop {
    constructor(cfg) {
        this.actor = new Clutter.Actor({name: 'liquid-glass-overview', clip_to_allocation: true, reactive: false});
        this.actor.add_constraint(new Clutter.BindConstraint({source: global.stage, coordinate: Clutter.BindCoordinate.ALL}));
        this._clone = new Clutter.Clone({source: Main.layoutManager._backgroundGroup});
        this.actor.add_child(this._clone);
        this._blur = new Shell.BlurEffect({mode: Shell.BlurMode.ACTOR});
        this.actor.add_effect(this._blur);
        Main.layoutManager.overviewGroup.insert_child_at_index(this.actor, 0);
        this.update(cfg);
    }

    update(cfg) {
        const o = cfg.overview;
        this.actor.visible = o.enabled;
        this._blur.radius = o.blur;
        this._blur.brightness = o.brightness;
    }

    destroy() {
        this.actor.destroy();
    }
}

export class GlassManager {
    constructor(cfg) {
        this.cfg = cfg;
        this._parts = [];
        this._hold = null;
        this._signals = new Signals();
        // A start that fails halfway takes down what it built: nothing is left
        // running that no one would ever turn off.
        try {
            windowWatch.current = new WindowWatch();
            wallpaper.current = new Wallpaper();
            motion.current = new Motion();
            this._motion = motion.current;   // reachable from Looking Glass, for testing
            for (const Part of [Panels, Popups, Windows, OverviewBackdrop])
                this._parts.push(new Part(cfg));
            // While a window animates, the glass keeps its picture (see glass.js holdPanes).
            this._hold = new WindowAnimationHold();
            // Behind the panel and menus is the overview while it is open, the windows otherwise.
            for (const s of ['showing', 'shown', 'hiding', 'hidden'])
                this._signals.on(Main.overview, s, () => this._parts.forEach(p => p.sync?.()));
            // A window dragged or resized behind the glass re-renders it every frame.
            this._signals.on(global.display, 'grab-op-begin', () => moving(true));
            this._signals.on(global.display, 'grab-op-end', () => moving(false));
        } catch (e) {
            try {
                this.destroy();
            } catch (e2) {
                logError(e2, 'Fedora Glass: taking down a glass that failed to start');
            }
            throw e;
        }
    }

    update(cfg) {
        this.cfg = cfg;
        this._parts.forEach(p => p.update(cfg));
    }

    destroy() {
        this._signals.clear();
        this._hold?.destroy();
        this._hold = null;
        releaseAllPanes(true);
        stopMoving();
        // Each part goes even if another one fails to.
        const parts = [motion.current, ...this._parts, windowWatch.current, wallpaper.current];
        motion.current = null;
        this._parts = [];
        windowWatch.current = null;
        wallpaper.current = null;
        let error = null;
        for (const p of parts) {
            try {
                p?.destroy();
            } catch (e) {
                error ??= e;
            }
        }
        if (error)
            throw error;
    }
}
