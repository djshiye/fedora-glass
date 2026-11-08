// Notifications from one app stack up in the calendar: the newest card in front, the
// others laid out behind it, a few px lower, peeking out under it. GNOME draws them
// whole, trusting the front card to cover them. Ours is see-through glass, so the cards
// behind showed through it: a second card frame, its picture and its text, a little
// below and beside the real ones (plain to see over anything bright). Each card behind
// is cut to the part that peeks out under the front card.

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {NotificationMessageGroup} from 'resource:///org/gnome/shell/ui/messageList.js';

import {report} from './safety.js';

/**
 * The part of a stacked card that shows under the front card, in the card's own px:
 * [x, y, w, h], or null for no cut (the card is not behind the front card).
 * `card` and `front` are allocation boxes {y1, y2} in the group, `width` the card's.
 */
export function peek(card, front, width) {
    const h = card.y2 - card.y1;
    if (!(h > 0) || !(width > 0))
        return null;
    const top = Math.min(h, Math.max(0, front.y2 - card.y1));
    return [0, top, width, h - top];
}

/** The front card and the stacked ones of a group: GNOME keeps them as [front, cover, ...stack, header]. */
export function stackOf(group) {
    const kids = group.get_children?.() ?? [];
    if (kids.length < 3)
        return {front: null, stack: []};
    return {front: kids[0], stack: kids.slice(2, -1)};
}

export class StackClip {
    constructor(_cfg) {
        this._items = new Map();    // stacked card -> its signal ids
        const proto = NotificationMessageGroup?.prototype;
        const fade = proto?._updateStackedMessagesFade;
        if (typeof fade !== 'function')
            return;    // a GNOME that stacks its notifications some other way
        const self = this;
        this._proto = proto;
        this._fade = fade;
        // GNOME calls this whenever a stack changes: a card added or gone, the group
        // expanded or collapsed. Same name, so it is put back as it was.
        this._ours = function (...args) {
            const r = fade.apply(this, args);
            try {
                self._sync(this);
            } catch (e) {
                report('stacked notifications', e);
            }
            return r;
        };
        proto._updateStackedMessagesFade = this._ours;
        // Stacks already there (the glass turned on with notifications waiting).
        try {
            this._walk(Main.layoutManager.uiGroup);
        } catch (e) {
            report('stacked notifications', e);
        }
    }

    _walk(actor) {
        if (actor === global.window_group)
            return;
        if (actor instanceof NotificationMessageGroup) {
            this._sync(actor);
            return;
        }
        actor.get_children?.().forEach(c => this._walk(c));
    }

    _sync(group) {
        const {front, stack} = stackOf(group);
        const behind = new Set(group.expanded || !front ? [] : stack);
        for (const item of [front, ...stack]) {
            if (!item)
                continue;
            if (behind.has(item))
                this._watch(item, group, front);
            else
                this._unwatch(item);
        }
        // Cards that left this group for good.
        for (const [item, w] of this._items) {
            if (w.group === group && !behind.has(item))
                this._unwatch(item);
        }
    }

    _watch(item, group, front) {
        const w = this._items.get(item);
        if (w && w.front === front) {
            this._cut(item, front);
            return;
        }
        this._unwatch(item);
        const ids = [
            [item, item.connect('notify::allocation', () => this._cut(item, front))],
            [front, front.connect('notify::allocation', () => this._cut(item, front))],
            [item, item.connect('destroy', () => this._unwatch(item))],
        ];
        this._items.set(item, {group, front, ids});
        this._cut(item, front);
    }

    _cut(item, front) {
        const r = peek(item.get_allocation_box(), front.get_allocation_box(), item.get_allocation_box().get_width());
        if (r)
            item.set_clip(...r);
        else
            item.remove_clip();
    }

    _unwatch(item) {
        const w = this._items.get(item);
        if (!w)
            return;
        this._items.delete(item);
        for (const [obj, id] of w.ids) {
            try {
                obj.disconnect(id);
            } catch {}   // already gone
        }
        try {
            item.remove_clip();
        } catch {}
    }

    update(_cfg) {}

    sync() {}

    destroy() {
        if (this._proto && this._proto._updateStackedMessagesFade === this._ours)
            this._proto._updateStackedMessagesFade = this._fade;
        this._proto = this._fade = this._ours = null;
        for (const item of [...this._items.keys()])
            this._unwatch(item);
    }
}
