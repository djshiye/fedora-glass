// Who holds the glass, and the hard time limit on a hold (see holdPanes in
// glass.js). Kept apart from Clutter so it can be tested on its own.

import GLib from 'gi://GLib';

// The longest the glass is ever held. The limit counts from the moment the glass
// is first held and is never pushed back, so a stream of short effects (menus and
// tooltips also 'map') can't keep an old picture up: when it runs out, everything
// is let go and caught up, and a later hold starts a fresh limit.
export const HOLD_LIMIT_MS = 1500;

export class HoldState {
    /** onHold() runs when the glass becomes held; onRelease(now) when it is let go. */
    constructor(onHold, onRelease) {
        this._onHold = onHold;
        this._onRelease = onRelease;
        this.keys = new Set();
        this.held = false;
        this.enabled = true;
        this._timer = 0;
    }

    hold(key) {
        if (!this.enabled)
            return;
        this.keys.add(key);
        if (this.held)
            return;
        this.held = true;
        this._timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, HOLD_LIMIT_MS, () => {
            this._timer = 0;
            this.releaseAll();
            return GLib.SOURCE_REMOVE;
        });
        this._onHold();
    }

    release(key) {
        if (this.keys.delete(key) && !this.keys.size)
            this.releaseAll();
    }

    releaseAll(now = false) {
        this.keys.clear();
        if (this._timer)
            GLib.source_remove(this._timer);
        this._timer = 0;
        if (!this.held)
            return;
        this.held = false;
        this._onRelease(now);
    }
}
