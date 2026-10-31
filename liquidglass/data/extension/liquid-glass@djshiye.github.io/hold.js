// Holds every glass pane on its last picture while GNOME's own window animations
// play (see holdPanes in glass.js). The hold ends when the window lands (Mutter's
// 'effects-completed'), or when it is destroyed mid-animation. The animations
// picked in the Liquid Glass app hold the glass themselves (glass.js freezeSource).

import Meta from 'gi://Meta';
import GLib from 'gi://GLib';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {holdPanes, releasePanes} from './glass.js';

// The window manager's signals for window effects, and the set GNOME keeps of the
// windows each one is animating.
const EFFECTS = {map: '_mapping', minimize: '_minimizing', unminimize: '_unminimizing', destroy: '_destroying',
    'size-changed': '_resizing'};

function animating(actor) {
    const wm = Main.wm;
    return Object.values(EFFECTS).some(set => wm?.[set]?.has?.(actor));
}

export class WindowAnimationHold {
    constructor() {
        this._animating = new Map();   // window actor -> its signal ids
        this._pending = new Set();
        this._later = 0;
        // Not GNOME's own handlers, so animations.js never blocks these: they see every
        // effect, whichever of GNOME or the Liquid Glass animations plays it.
        this._ids = Object.keys(EFFECTS).map(s => global.window_manager.connect(s, (_wm, actor) => this._event(actor)));
    }

    // Whether the event animates is known once the window manager has handled it,
    // which may be after this handler: look just before the next frame, which is
    // the animation's first.
    _event(actor) {
        if (!actor)
            return;
        this._pending.add(actor);
        if (this._later)
            return;
        this._later = global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
            this._later = 0;
            const actors = [...this._pending];
            this._pending.clear();
            actors.forEach(a => this._check(a));
            return GLib.SOURCE_REMOVE;
        });
    }

    _check(actor) {
        if (!animating(actor))
            return;
        // Already watched (a new effect replaced the last one): hold again until it lands.
        if (this._animating.has(actor)) {
            holdPanes(actor);
            return;
        }
        const ids = [
            actor.connect('effects-completed', () => this._landed(actor, true)),
            actor.connect('destroy', () => this._landed(actor, false)),
        ];
        this._animating.set(actor, ids);
        holdPanes(actor);
    }

    _landed(actor, alive) {
        const ids = this._animating.get(actor);
        if (!ids)
            return;
        this._animating.delete(actor);
        if (alive)
            ids.forEach(id => actor.disconnect(id));
        releasePanes(actor);
    }

    /** How many windows hold the glass now (for QA). */
    get count() {
        return this._animating.size;
    }

    destroy() {
        this._ids.forEach(id => global.window_manager.disconnect(id));
        this._ids = [];
        if (this._later)
            global.compositor.get_laters().remove(this._later);
        this._later = 0;
        this._pending.clear();
        for (const [actor, ids] of this._animating) {
            for (const id of ids) {
                try {
                    actor.disconnect(id);
                } catch {}   // the actor is already gone
            }
            releasePanes(actor);
        }
        this._animating.clear();
    }
}
