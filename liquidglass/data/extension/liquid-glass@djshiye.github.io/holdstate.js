// When the glass is held and how it catches up (see holdPanes in glass.js), kept
// apart from Clutter so it can be tested on its own. glass.js passes the pane
// operations in.

import GLib from 'gi://GLib';

// The longest the glass is held at a time. The limit counts from the moment the
// glass is first held and is never pushed back, so a stream of short effects
// (menus and tooltips also 'map') can't keep an old picture up: when it runs out,
// everything is let go and caught up, and a later hold starts a fresh limit.
export const HOLD_LIMIT_MS = 1500;
// The longest a pane waits in the catch-up for the one before it.
export const CATCH_UP_STEP_MS = 100;

/**
 * ops: panes() lists the panes; alive(p); isStale(p); rank(p), lower first;
 * keep(p) holds a pane (again); free(p) lets one go and has it render now;
 * renders(p) counts its renders; endAll() lets every pane go at the end;
 * afterFrame(fn) runs fn after each frame and returns an id for cancelFrame(id).
 */
export class GlassHold {
    constructor(ops) {
        this._ops = ops;
        this.keys = new Set();
        this.holding = false;     // within a hold
        this.enabled = true;
        this.manual = false;      // QA: the catch-up moves only on step()
        this._limit = 0;
        this._queue = null;       // the catch-up, while it runs: panes still to let go
        this._freed = new Set();  // panes this catch-up has let go
        this._wait = null;
    }

    /** Panes are held: within a hold, or still catching up. */
    get held() {
        return this.holding || this._queue !== null;
    }

    hold(key) {
        if (!this.enabled)
            return;
        this.keys.add(key);
        if (this.holding)
            return;
        this.holding = true;
        this._limit = GLib.timeout_add(GLib.PRIORITY_DEFAULT, HOLD_LIMIT_MS, () => {
            this._limit = 0;
            this.releaseAll();
            return GLib.SOURCE_REMOVE;
        });
        // A catch-up already running goes on: the panes it has let go finish, the
        // others are held for this hold too.
        for (const p of this._ops.panes()) {
            if (!this._freed.has(p))
                this._ops.keep(p);
        }
    }

    release(key) {
        if (this.keys.delete(key) && !this.keys.size)
            this.releaseAll();
    }

    /** With `now` (turning off), every pane is let go at once, without a catch-up. */
    releaseAll(now = false) {
        this.keys.clear();
        if (this._limit)
            GLib.source_remove(this._limit);
        this._limit = 0;
        const was = this.holding;
        this.holding = false;
        if (now) {
            if (this.held || was)
                this._finish(true);
            return;
        }
        if (was)
            this._enqueue();
    }

    /** QA, with manual on: let the next pane go. Returns it, or null when done. */
    step() {
        if (!this._queue)
            return null;
        return this._next();
    }

    // Stale panes go one per frame, bottom window first: a window's glass shows the
    // windows below it, glass included; the panel and menus come last.
    _enqueue() {
        const ops = this._ops;
        const fresh = !this._queue;
        if (fresh) {
            this._queue = [];
            this._freed = new Set();
        }
        for (const p of ops.panes()) {
            if (ops.isStale(p) && !this._queue.includes(p) && !this._freed.has(p))
                this._queue.push(p);
        }
        this._queue.sort((a, b) => ops.rank(a) - ops.rank(b));
        if (fresh && !this.manual)
            this._next();
    }

    _next() {
        const ops = this._ops;
        this._cancelWait();
        let p;
        do
            p = this._queue.shift();
        while (p && !ops.alive(p));
        if (!p) {
            this._finish(false);
            return null;
        }
        this._freed.add(p);
        const before = ops.renders(p);
        ops.free(p);
        if (this.manual)
            return p;
        // On to the next once this one has rendered, or after a short wait (it may
        // be off screen, and then it doesn't render).
        const wait = {frame: 0, timer: 0};
        this._wait = wait;
        wait.frame = ops.afterFrame(() => {
            if (this._wait === wait && ops.renders(p) > before)
                this._next();
        });
        wait.timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, CATCH_UP_STEP_MS, () => {
            wait.timer = 0;
            if (this._wait === wait)
                this._next();
            return GLib.SOURCE_REMOVE;
        });
        return p;
    }

    _cancelWait() {
        const w = this._wait;
        this._wait = null;
        if (!w)
            return;
        if (w.frame)
            this._ops.cancelFrame(w.frame);
        if (w.timer)
            GLib.source_remove(w.timer);
    }

    _finish(now) {
        this._cancelWait();
        const freed = this._freed;
        this._queue = null;
        this._freed = new Set();
        if (this.holding && !now) {
            // A hold came in meanwhile: what this catch-up let go is held for it too.
            freed.forEach(p => this._ops.alive(p) && this._ops.keep(p));
            return;
        }
        this._ops.endAll();
    }
}
