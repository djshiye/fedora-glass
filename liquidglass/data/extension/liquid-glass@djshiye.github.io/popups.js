// Glass behind popup menus, notification banners, the OSD and the window switcher.

import GLib from 'gi://GLib';
import Meta from 'gi://Meta';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {BoxPointer} from 'resource:///org/gnome/shell/ui/boxpointer.js';

import {Signals} from './common.js';
import {Follower} from './follower.js';

// ---- popup menus, notification banners, OSD and the window switcher ----------------
// Which part of the Shell a menu belongs to, for its own look.
function partOf(bp) {
    const sa = Main.panel.statusArea;
    if (bp === sa.quickSettings?.menu?.actor)
        return 'quicksettings';
    if (bp === sa.dateMenu?.menu?.actor)
        return 'calendar';
    if (bp.has_style_class_name?.('arcmenu-menu'))
        return 'arcmenu';
    return 'quicksettings';      // app menus and the rest look like quick settings
}

export class Popups {
    constructor(cfg) {
        this.cfg = cfg;
        this._followers = new Map();   // surface -> Follower
        this._signals = new Signals();
        const ui = Main.layoutManager.uiGroup;
        this._laters = new Set();
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
            this._follow(bp.bin?.get_child?.(), child, partOf(bp));
            return;
        }
        // Volume and brightness pop-ups.
        const osd = child.get_children?.().find(c => c.has_style_class_name?.('osd-window'));
        if (osd) {
            this._follow(osd, child, 'quicksettings');
            return;
        }
        // Alt+Tab and friends.
        if (child._switcherList)
            this._follow(child._switcherList, child, 'quicksettings');
    }

    _follow(surface, anchor, part = 'menus') {
        if (!surface || this._followers.has(surface))
            return;
        const f = new Follower(surface, anchor, this._settings(part), () => this._followers.delete(surface));
        f.part = part;
        f.condense = true;
        this._followers.set(surface, f);
    }

    _settings(part) {
        return this.cfg.parts[part] ?? this.cfg.menus;
    }

    update(cfg) {
        this.cfg = cfg;
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
        for (const f of [...this._followers.values()])
            f.destroy();
        this._followers.clear();
    }
}
