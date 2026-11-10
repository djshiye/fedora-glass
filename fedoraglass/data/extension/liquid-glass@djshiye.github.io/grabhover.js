// Panel hover while a menu is open.
//
// While a menu holds GNOME's grab (a tray icon's menu, the calendar, Quick Settings,
// Spawn or ArcMenu), Clutter sends pointer crossings only to the menu, so the panel's
// icons never get `hover`: GNOME itself only moves from menu to menu on hover. Over a
// full-screen game the panel only shows while such a menu is open, so the icons'
// hover lift and the taskbar glide never played there. This follows the pointer over
// the given items while the stage is grabbed and says which one it is on; the panel
// effects treat that item as hovered. Nothing runs while nothing is grabbed.
//
// Public API:
//   new GrabHover(items, changed)   items(): the actors to follow (re-read on every move);
//                                   changed(item): an item's grab hover started or ended
//   grabHover.start() / stop()      follow the grab state / stop (and let go of the item)
//   grabHover.has(item): boolean    the pointer is on `item` while a menu holds the grab
//   hovered(item, grabHover)        item.hover, or its grab hover

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';

import {Signals} from './common.js';
import {report} from './safety.js';

export function hovered(item, grabHover) {
    return Boolean(item?.hover) || Boolean(grabHover?.has(item));
}

export class GrabHover {
    constructor(items, changed) {
        this._items = items;
        this._changed = changed;
        this._signals = new Signals();
        this._filterId = 0;
        this._releaseId = 0;
        this.item = null;
    }

    start() {
        if (this._signals._ids.length || !global.stage)
            return;
        this._signals.on(global.stage, 'notify::is-grabbed', () => this._sync());
        this._sync();
    }

    stop() {
        this._signals.clear();
        this._unfilter();
        this._dropRelease();
        this._set(null);
    }

    has(item) {
        return item !== null && item === this.item;
    }

    _sync() {
        if (global.stage.is_grabbed) {
            this._dropRelease();
            if (!this._filterId)
                this._filterId = Clutter.Event.add_filter(global.stage, event => this._filter(event));
            return;
        }
        this._unfilter();
        // Let go once the grab's own crossings have given the item its real hover back,
        // so an icon the pointer stays on does not drop and lift again.
        if (this.item && !this._releaseId) {
            this._releaseId = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                this._releaseId = 0;
                this._set(null);
                return GLib.SOURCE_REMOVE;
            });
        }
    }

    _unfilter() {
        if (this._filterId)
            Clutter.Event.remove_filter(this._filterId);
        this._filterId = 0;
    }

    _dropRelease() {
        if (this._releaseId)
            GLib.source_remove(this._releaseId);
        this._releaseId = 0;
    }

    _filter(event) {
        try {
            const type = event.type();
            if (type === Clutter.EventType.MOTION) {
                const [x, y] = event.get_coords();
                this._set(this._itemAt(x, y));
            } else if (type === Clutter.EventType.LEAVE && event.get_related?.() === null) {
                this._set(null);    // the pointer left the stage
            }
        } catch (e) {
            report('panel hover while a menu is open', e);
            this.stop();
        }
        return Clutter.EVENT_PROPAGATE;
    }

    _itemAt(x, y) {
        for (const item of this._items()) {
            if (!item?.is_mapped?.())
                continue;
            const r = item.get_transformed_extents();
            if (x >= r.origin.x && y >= r.origin.y &&
                x < r.origin.x + r.size.width && y < r.origin.y + r.size.height)
                return item;
        }
        return null;
    }

    _set(item) {
        if (item === this.item)
            return;
        const was = this.item;
        this.item = item;
        if (was)
            this._changed(was);
        if (item)
            this._changed(item);
    }
}
