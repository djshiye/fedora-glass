// A window that really moves or resizes, not only one that is held.
//
// Mutter starts a window move ("grab op") as soon as a button goes down on a title
// bar, and Dash to Panel (like GNOME's own top bar) starts one when you press an
// empty part of the taskbar above a maximized window. That window may never move:
// a maximized window only comes loose when it is pulled up or down, so a press
// dragged sideways along the taskbar holds it for the whole drag. The glass used to
// switch to its lighter "something moves" look on every such press and back just
// after letting go, so the taskbar's edge flickered while you dragged along it.
// Here the glass hears that a window moves only once it really does.
//
// Public API:
//   new GrabMove(display, changed)   changed(true) once the grabbed window moves or
//                                    resizes, changed(false) when that grab ends
//   grabMove.destroy()               stop listening (changed is not called again)

const MOVES = ['position-changed', 'size-changed'];

export class GrabMove {
    constructor(display, changed) {
        this._display = display;
        this._changed = changed;
        this._window = null;
        this._ids = [];
        this.on = false;
        this._displayIds = [
            display.connect('grab-op-begin', (_d, window) => this._begin(window)),
            display.connect('grab-op-end', () => this._end()),
        ];
    }

    _begin(window) {
        this._unwatch();
        if (this.on)
            return;     // a new grab while one still moves: it goes on
        if (typeof window?.connect !== 'function') {
            this._set(true);    // nothing to watch: count it as a move, as before
            return;
        }
        this._window = window;
        const moved = () => {
            this._unwatch();
            this._set(true);
        };
        this._ids = MOVES.map(s => window.connect(s, moved));
        // Closed while held: nothing more to wait for.
        this._ids.push(window.connect('unmanaged', () => this._unwatch()));
    }

    _end() {
        this._unwatch();
        if (this.on)
            this._set(false);
    }

    _set(on) {
        this.on = on;
        this._changed(on);
    }

    _unwatch() {
        for (const id of this._ids) {
            try {
                this._window.disconnect(id);
            } catch {}   // the window is already gone
        }
        this._ids = [];
        this._window = null;
    }

    destroy() {
        this._unwatch();
        for (const id of this._displayIds)
            this._display.disconnect(id);
        this._displayIds = [];
        this.on = false;
    }
}
