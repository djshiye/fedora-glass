// Glass behind popup menus, notification banners, the OSD, the window switcher,
// Dash to Panel's window previews and the Shell's dialogs (Run, Power Off, passwords).

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

/** The box of Dash to Panel's window-preview pop-up, or null if `actor` is not one. */
export function previewBox(actor) {
    const box = actor?.menu;
    return box && typeof actor.requestPeek === 'function' && typeof box.get_parent === 'function' &&
        box.get_parent() === actor ? box : null;
}

/** The visible box of a GNOME modal dialog (.modal-dialog), or null. */
export function dialogBox(dialog) {
    const box = dialog?.dialogLayout?._dialog;
    return box && typeof box.has_style_class_name === 'function' && box.has_style_class_name('modal-dialog') &&
        dialog.contains?.(box) ? box : null;
}

// Dash to Panel paints each window preview's title strip and close-button corner in
// its own inline style, fully opaque, which no theme rule can override: a solid dark
// bar on the glass. Give them the pop-up's own see-through tint instead.
const SOLID = /rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*1(?:\.0+)?\s*\)/g;
const PREVIEW_PARTS = ['preview-header-box', 'preview-close-btn-container'];

/** `style` with every opaque rgba() colour at `alpha` instead. */
export function seeThrough(style, alpha) {
    if (typeof style !== 'string' || !Number.isFinite(alpha))
        return style;
    const a = Math.max(0, Math.min(1, alpha)).toFixed(3);
    return style.replace(SOLID, (_m, r, g, b) => `rgba(${r},${g},${b},${a})`);
}

/** The alpha of a `background: rgba(...)` inline style, or null. */
export function tintOf(style) {
    const m = typeof style === 'string' && /rgba\([^)]*,\s*([\d.]+)\s*\)/.exec(style);
    const a = m ? Number(m[1]) : NaN;
    return Number.isFinite(a) && a < 1 ? a : null;
}

export class PreviewTint {
    constructor(box) {
        this._box = box;               // Dash to Panel's #preview-menu
        this._signals = new Signals();
        this._orig = new Map();        // actor -> Dash to Panel's own style
        this._watched = new Set();
        this._signals.on(box, 'destroy', () => this.destroy());
        this._walk(box);
    }

    // Previews are made as the pointer moves along the taskbar, in a box inside a scroll view.
    _walk(actor) {
        if (!actor || this._watched.has(actor))
            return;
        this._watched.add(actor);
        this._signals.on(actor, 'destroy', () => {
            this._watched.delete(actor);
            this._orig.delete(actor);
            this._signals.forget(actor);
        });
        if (PREVIEW_PARTS.some(c => actor.has_style_class_name?.(c))) {
            this._signals.on(actor, 'notify::style', () => this._tint(actor));
            this._tint(actor);
            return;
        }
        this._signals.on(actor, 'child-added', (_a, c) => this._walk(c));
        actor.get_children?.().forEach(c => this._walk(c));
    }

    _tint(actor) {
        const style = actor.get_style?.();
        const alpha = tintOf(this._box.get_style?.()) ?? 0.3;
        const glass = seeThrough(style, alpha);
        if (!style || glass === style)
            return;
        this._orig.set(actor, style);
        actor.set_style(glass);
    }

    destroy() {
        this._signals.clear();
        for (const [actor, style] of this._orig) {
            try {
                actor.set_style(style);
            } catch {}   // already gone
        }
        this._orig.clear();
        this._watched.clear();
    }
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
        this._tints = new Map();       // Dash to Panel's window previews -> PreviewTint
        // Some pop-ups (Alt+Tab) are added before they finish building, so look a moment later.
        this._signals.on(ui, 'child-added', (_p, child) => this._soon(child, () => this._consider(child)));
        ui.get_children().forEach(c => this._consider(c));
        // Run a Command, Power Off, password prompts: GNOME made them see-through for
        // glass, so without a pane the windows behind read through their text. A
        // dialog is added before its content is built, so it too is looked at a moment later.
        const dialogs = Main.layoutManager.modalDialogGroup;
        if (dialogs) {
            this._signals.on(dialogs, 'child-added', (_g, d) => this._soon(d, () => this._dialog(d)));
            dialogs.get_children().forEach(d => this._dialog(d));
        }
        // Banners come and go inside the message tray.
        const tray = Main.messageTray, bin = tray?._bannerBin;
        if (bin) {
            this._signals.on(bin, 'child-added', (_b, banner) => this._follow(banner, tray, 'calendar'));
            bin.get_children().forEach(b => this._follow(b, tray, 'calendar'));
        }
    }

    // Run fn just before the next frame, unless child is gone by then (tooltips and
    // the like can be).
    _soon(child, fn) {
        const laters = global.compositor.get_laters();
        const gone = child.connect('destroy', () => {
            laters.remove(id);
            this._laters.delete(id);
        });
        const id = laters.add(Meta.LaterType.BEFORE_REDRAW, () => {
            this._laters.delete(id);
            child.disconnect(gone);
            fn();
            return GLib.SOURCE_REMOVE;
        });
        this._laters.add(id);
    }

    _consider(child) {
        if (child.name?.startsWith('liquid-glass'))
            return;
        // Dash to Panel's window previews (hovering a taskbar icon). The pane goes inside
        // the preview pop-up, under its box: the pop-up clips its slide out of the panel,
        // and the glass then never shows over the panel.
        const previews = previewBox(child);
        if (previews) {
            this._follow(previews, previews, 'quicksettings');
            if (!this._tints.has(previews)) {
                this._tints.set(previews, new PreviewTint(previews));
                previews.connect('destroy', () => this._tints.delete(previews));
            }
            return;
        }
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

    // A Shell dialog: the glass sits over its dimmed backdrop and under its box.
    _dialog(dialog) {
        const box = dialogBox(dialog);
        if (!box)
            return;
        let a = box;
        while (a && a.get_parent() !== dialog)
            a = a.get_parent();
        if (a)
            this._follow(box, a, 'quicksettings');
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
        for (const t of this._tints.values())
            t.destroy();
        this._tints.clear();
        for (const f of [...this._followers.values()])
            f.destroy();
        this._followers.clear();
    }
}
