// Puts glass panes behind Shell surfaces and keeps them in step: the top bar
// or Dash to Panel, every popup menu (quick settings, calendar, ArcMenu and
// app menus), notification banners, the volume OSD, Alt+Tab, app windows and
// the overview background.

import Clutter from 'gi://Clutter';
import Shell from 'gi://Shell';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {moving, stopMoving} from './glass.js';
import {WindowWatch, windowWatch, motion, wallpaper, Signals} from './common.js';
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
        windowWatch.current = new WindowWatch();
        wallpaper.current = new Wallpaper();
        motion.current = new Motion();
        this._motion = motion.current;   // reachable from Looking Glass, for testing
        this._parts = [new Panels(cfg), new Popups(cfg), new Windows(cfg), new OverviewBackdrop(cfg)];
        this._signals = new Signals();
        // Behind the panel and menus is the overview while it is open, the windows otherwise.
        for (const s of ['showing', 'shown', 'hiding', 'hidden'])
            this._signals.on(Main.overview, s, () => this._parts.forEach(p => p.sync?.()));
        // A window dragged or resized behind the glass re-renders it every frame.
        this._signals.on(global.display, 'grab-op-begin', () => moving(true));
        this._signals.on(global.display, 'grab-op-end', () => moving(false));
    }

    update(cfg) {
        this.cfg = cfg;
        this._parts.forEach(p => p.update(cfg));
    }

    destroy() {
        this._signals.clear();
        stopMoving();
        motion.current?.destroy();
        motion.current = null;
        this._parts.forEach(p => p.destroy());
        this._parts = [];
        windowWatch.current?.destroy();
        windowWatch.current = null;
        wallpaper.current?.destroy();
        wallpaper.current = null;
    }
}
