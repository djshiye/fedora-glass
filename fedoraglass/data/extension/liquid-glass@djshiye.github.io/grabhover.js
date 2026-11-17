// Panel hover while a menu is open.
//
// While a menu holds GNOME's grab (a tray icon's menu, the calendar, Quick Settings,
// Spawn or ArcMenu), Clutter sends pointer crossings only to the menu, so the panel's
// icons never get `hover`: GNOME itself only moves from menu to menu on hover. Over a
// full-screen game the panel only shows while such a menu is open, so the icons'
// hover lift and the taskbar glide never played there. This follows the pointer over
// the given items while the stage is grabbed and says which one it is on; the panel
// effects treat that item as hovered. Nothing runs while nothing is grabbed, nor while the
// grab is a window being dragged or resized: no icon lifts under a window on its way, and
// up to 1.7.7 every pointer move of a drag measured every icon of the panel (and left
// seven native objects per icon for GNOME's clean-up).
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
        this._unfilterId = 0;
        this._asked = false;       // whether this grab was asked if it is a window's drag
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
            if (!this._filterId && !this._windowDrag()) {
                this._asked = false;
                this._filterId = Clutter.Event.add_filter(global.stage, event => this._filter(event));
            }
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
        if (this._unfilterId)
            GLib.source_remove(this._unfilterId);
        this._unfilterId = 0;
    }

    /** Whether the grab is a window being moved or resized (Mutter says so only once the drag is on). */
    _windowDrag() {
        try {
            return Boolean(global.display?.is_grabbed?.());
        } catch {
            return false;
        }
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
                if (this._unfilterId)
                    return Clutter.EVENT_PROPAGATE;
                if (!this._asked) {
                    // A window's drag: not followed. Let go of the events outside this call
                    // (Clutter is walking its list of filters right now).
                    this._asked = true;
                    if (this._windowDrag()) {
                        this._set(null);
                        this._unfilterId = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
                            this._unfilterId = 0;
                            this._unfilter();
                            return GLib.SOURCE_REMOVE;
                        });
                        return Clutter.EVENT_PROPAGATE;
                    }
                }
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
            // Not get_transformed_extents(): its box, origin and size are three native
            // objects per item per pointer move. The items are never turned, so this is the same box.
            const [ix, iy] = item.get_transformed_position();
            if (x < ix || y < iy)
                continue;
            const [w, h] = item.get_transformed_size();
            if (x < ix + w && y < iy + h)
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
