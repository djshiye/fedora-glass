// Glass behind the snap preview: the box GNOME shows where a window dragged to a screen
// edge will go (left or right half, or the whole screen at the top edge). GNOME paints it
// as a flat accent rectangle (.tile-preview); with glass behind it, the theme makes the box
// itself nearly clear with a thin accent rim, like a pane of the menus' glass.
//
// GNOME 50 and 51 make one TilePreview (Main.wm._tilePreview) the first time a window is
// dragged to an edge, a child of the window group, kept just below the dragged window. It
// slides and grows from the window to its place, and fades in and out. The pane follows
// its allocation and opacity like a menu's (follower.js): signals while it moves, nothing
// at all while it stands or is hidden.

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {Follower} from './follower.js';
import {sourcesFor} from './common.js';
import {report} from './safety.js';

// Set on the preview while it has glass behind it: the theme makes it nearly clear only
// then. Without it (glass paused, safe mode, menu glass off, another extension's own
// preview) the theme's rule keeps a visible tinted box.
export const GLASS_CLASS = 'fedora-glass-tile';

/** GNOME's snap preview, or null: one St widget with a parent (another tiling extension may have none). */
export function tilePreviewOf(wm) {
    const p = wm?._tilePreview;
    return p && typeof p.get_parent === 'function' && typeof p.add_style_class_name === 'function' &&
        p.get_parent() ? p : null;
}

/**
 * What the glass behind the preview shows: what sourcesFor gives at its place, without the
 * windows stacked at or above it (the window being dragged sits right above it, and the
 * glass must never show that window inside its own snap preview). `kids` is the window
 * group's children, bottom first.
 */
export function behindPreview(sources, preview, kids) {
    const at = kids.indexOf(preview);
    if (at < 0)
        return sources.slice(0, 1);   // not in the window group: the wallpaper only
    return sources.filter((s, i) => {
        if (i === 0)
            return true;            // the wallpaper
        const k = kids.indexOf(s);
        return k >= 0 && k < at;
    });
}

export class TileGlass {
    constructor(cfg) {
        this.cfg = cfg;
        this._follower = null;
        this._preview = null;
        this._wm = global.window_manager;
        this._showId = 0;
        try {
            // Connected after GNOME's own handler, so the preview is made and placed by
            // the time this runs.
            this._showId = this._wm.connect('show-tile-preview', () => {
                try {
                    this._shown();
                } catch (e) {
                    report('snap preview glass', e);
                }
            });
        } catch (e) {
            this._showId = 0;
            report('snap preview glass', e);
        }
        // A preview already made before the glass started: glass from its next showing.
        if (tilePreviewOf(Main.wm))
            this._shown();
    }

    _settings() {
        return this.cfg.parts?.quicksettings ?? this.cfg.menus;
    }

    _shown() {
        const preview = tilePreviewOf(Main.wm);
        if (!preview)
            return;    // a tiling extension that shows its own preview: left as it is
        if (this._follower && this._preview !== preview)
            this._drop();
        if (!this._follower) {
            let f;
            try {
                f = new Follower(preview, preview, this._settings(), () => {
                    if (this._follower === f)
                        this._gone();
                }, {sources: () => this._sources(preview)});
            } catch (e) {
                report('snap preview shown without glass', e);
                return;
            }
            f.part = 'quicksettings';
            this._follower = f;
            this._preview = preview;
        }
        this._mark();
        // GNOME put the preview right below the dragged window again: the glass goes with it.
        this._follower.sync();
    }

    _sources(preview) {
        const [x, y] = preview.get_transformed_position();
        const [w, h] = preview.get_transformed_size();
        const all = sourcesFor(this._settings().behind, x, y, w, h);
        const group = preview.get_parent();
        return behindPreview(all, preview, group?.get_children?.() ?? []);
    }

    // Nearly clear while there is glass behind it; GNOME's tinted box otherwise.
    _mark() {
        const p = this._preview;
        if (!p)
            return;
        try {
            if (this._settings().enabled)
                p.add_style_class_name(GLASS_CLASS);
            else
                p.remove_style_class_name(GLASS_CLASS);
        } catch {}   // gone
    }

    _gone() {
        this._follower = null;
        this._unmark();
        this._preview = null;
    }

    _unmark() {
        try {
            this._preview?.remove_style_class_name(GLASS_CLASS);
        } catch {}   // gone with the Shell
    }

    _drop() {
        const f = this._follower;
        this._follower = null;
        this._unmark();
        this._preview = null;
        f?.destroy();
    }

    update(cfg) {
        this.cfg = cfg;
        this._follower?.update(this._settings());
        this._mark();
    }

    sync() {
        this._follower?.queue();
    }

    destroy() {
        if (this._showId)
            this._wm.disconnect(this._showId);
        this._showId = 0;
        this._drop();
    }
}
