// Glass behind popup menus, notification banners, the OSD and the window switcher.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Graphene from 'gi://Graphene';
import Meta from 'gi://Meta';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {BoxPointer} from 'resource:///org/gnome/shell/ui/boxpointer.js';

import {Signals, grow} from './common.js';
import {report} from './safety.js';
import {Follower} from './follower.js';

// ---- popup menus, notification banners, OSD and the window switcher ----------------
// Which part of the Shell a menu belongs to, for its own look.
export function partOf(bp) {
    const sa = Main.panel.statusArea;
    if (bp === sa.quickSettings?.menu?.actor)
        return 'quicksettings';
    if (bp === sa.dateMenu?.menu?.actor)
        return 'calendar';
    // ArcMenu's and Spawn's start menus share one look, the part called 'arcmenu'.
    if (bp.has_style_class_name?.('arcmenu-menu') || bp.has_style_class_name?.('spawn-menu-popup'))
        return 'arcmenu';
    return 'quicksettings';      // app menus and the rest look like quick settings
}

/**
 * Quick Settings places its toggle menus (Wired, Wi-Fi, ...) in an overlay beside the
 * box pointer, offset by where its grid is inside the box pointer. GNOME measures
 * that offset through the transforms in between, which includes the scale of a menu
 * that is still growing open: the toggle menus then land too low and to the side,
 * over the panel, with an empty gap where they belong. Measure it again at full size.
 */
export function placeToggleMenus(menu) {
    const ov = menu?._overlay, grid = menu?._grid, bp = menu?._boxPointer;
    if (!ov || !grid || !bp)
        return false;
    const at = grid.apply_relative_transform_to_point(bp, new Graphene.Point3D());
    let n = 0;
    for (const c of ov.get_constraints()) {
        if (!(c instanceof Clutter.BindConstraint) || c.source !== bp)
            continue;
        if (c.coordinate === Clutter.BindCoordinate.X)
            c.offset = at.x;
        else if (c.coordinate === Clutter.BindCoordinate.Y)
            c.offset = at.y;
        else
            continue;
        n++;
    }
    return n > 0;
}

export class Popups {
    constructor(cfg) {
        this.cfg = cfg;
        grow.enabled = cfg.grow?.enabled !== false;
        this._followers = new Map();   // surface -> Follower
        this._waiting = new Map();     // surface -> [signal ids], until it first opens
        this._signals = new Signals();
        const ui = Main.layoutManager.uiGroup;
        this._laters = new Set();
        this._switchers = new Map();   // Alt+Tab pop-up -> [signal ids]
        // Some pop-ups (Alt+Tab) are added before they finish building, so look a moment later.
        this._signals.on(ui, 'child-added', (_p, child) => {
            const laters = global.compositor.get_laters();
            // Tooltips and the like can be gone before the later runs.
            const gone = child.connect('destroy', () => {
                laters.remove(id);
                this._laters.delete(id);
            });
            const id = laters.add(Meta.LaterType.BEFORE_REDRAW, () => {
                this._laters.delete(id);
                child.disconnect(gone);
                this._consider(child);
                return GLib.SOURCE_REMOVE;
            });
            this._laters.add(id);
        });
        ui.get_children().forEach(c => this._consider(c));
        // Banners come and go inside the message tray.
        const tray = Main.messageTray, bin = tray?._bannerBin;
        if (bin) {
            this._signals.on(bin, 'child-added', (_b, banner) => this._follow(banner, tray, 'calendar'));
            bin.get_children().forEach(b => this._follow(b, tray, 'calendar'));
        }
    }

    _consider(child) {
        if (child.name === 'liquid-glass-pane')
            return;
        // Menus: a BoxPointer, or one wrapped in a widget (quick settings).
        const bp = child instanceof BoxPointer ? child
            : child.get_children?.().find(c => c instanceof BoxPointer) ?? null;
        if (bp) {
            this._follow(bp.bin?.get_child?.(), child, partOf(bp), () => bp._sourceActor ?? null);
            return;
        }
        // Volume and brightness pop-ups.
        const osd = child.get_children?.().find(c => c.has_style_class_name?.('osd-window'));
        if (osd) {
            this._follow(osd, child, 'quicksettings');
            return;
        }
        // Alt+Tab and friends.
        if (child._switcherList) {
            this._follow(child._switcherList, child, 'quicksettings');
            this._watchSwitcher(child);
        }
    }

    // Alt+Tab shows an app's windows in a second list under the first one, made only
    // when that app is picked: glass for it too.
    _watchSwitcher(popup) {
        if (this._switchers.has(popup))
            return;
        const added = popup.connect('child-added', (_p, c) => {
            if (c !== popup._switcherList && c.has_style_class_name?.('switcher-list'))
                this._follow(c, popup, 'quicksettings');
        });
        const gone = popup.connect('destroy', () => this._switchers.delete(popup));
        this._switchers.set(popup, [added, gone]);
    }

    _follow(surface, anchor, part = 'menus', source = null) {
        if (!surface || this._followers.has(surface) || this._waiting.has(surface))
            return;
        if (surface.mapped) {
            this._makeFollower(surface, anchor, part, source);
            return;
        }
        // Build the glass when the menu first opens, not before: menus that are made
        // but never opened (or left behind by another extension) carry no pane.
        const ids = [
            surface.connect('notify::mapped', () => {
                if (!surface.mapped)
                    return;
                this._stopWaiting(surface);
                // It is about to be seen: hold it back until its glass is up. The hold
                // gives up after HOLD_MAX_MS, and if the glass cannot be built at all
                // the menu shows as it is, without glass.
                this._makeFollower(surface, anchor, part, source)?._hold();
            }),
            surface.connect('destroy', () => this._stopWaiting(surface)),
        ];
        this._waiting.set(surface, ids);
    }

    _stopWaiting(surface) {
        const ids = this._waiting.get(surface);
        if (!ids)
            return;
        this._waiting.delete(surface);
        ids.forEach(id => surface.disconnect(id));
    }

    _makeFollower(surface, anchor, part, source = null) {
        let f;
        try {
            f = new Follower(surface, anchor, this._settings(part), () => this._followers.delete(surface));
        } catch (e) {
            report('menu shown without glass', e);
            return null;
        }
        f.part = part;
        f.condense = true;
        const qs = Main.panel.statusArea.quickSettings?.menu;
        if (qs && anchor === qs.actor)
            f.onFullSize = () => {
                try {
                    placeToggleMenus(qs);
                } catch (e) {
                    report('placing the Quick Settings toggle menus', e);
                }
            };
        f.source = source;
        this._followers.set(surface, f);
        return f;
    }

    _settings(part) {
        return this.cfg.parts[part] ?? this.cfg.menus;
    }

    update(cfg) {
        this.cfg = cfg;
        grow.enabled = cfg.grow?.enabled !== false;
        for (const f of this._followers.values())
            f.update(this._settings(f.part));
    }

    sync() {
        for (const f of this._followers.values())
            f.queue();
    }

    destroy() {
        this._signals.clear();
        const laters = global.compositor.get_laters();
        this._laters.forEach(id => laters.remove(id));
        this._laters.clear();
        for (const surface of [...this._waiting.keys()])
            this._stopWaiting(surface);
        for (const [popup, ids] of this._switchers)
            ids.forEach(id => popup.disconnect(id));
        this._switchers.clear();
        for (const f of [...this._followers.values()])
            f.destroy();
        this._followers.clear();
    }
}
