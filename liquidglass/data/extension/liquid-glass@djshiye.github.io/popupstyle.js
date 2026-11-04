// The theme's pop-up rules (OSD, Alt+Tab) loaded again as this extension's own
// stylesheet. GNOME ranks extension stylesheets above the Shell theme, so only
// from here can they win over another extension's (Just Perfection's theme
// paints these pop-ups black, which covers the glass under them).
//
// The rules come in shell-glass.json, not as a stylesheet.css in the extension
// folder: GNOME re-reads every loaded stylesheet whenever the theme reloads, and
// Restore original deletes the extension's files while it is still loaded. So the
// file lives in the user's private runtime folder, written and removed only here,
// and is unloaded before it is removed.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

const DIR = GLib.build_filenamev([GLib.get_user_runtime_dir(), 'fedora-glass']);
const FILE = Gio.File.new_for_path(GLib.build_filenamev([DIR, 'popups.css']));

export class PopupStyle {
    constructor(cfg) {
        this._css = '';
        this._theme = null;
        this._loading = false;
        this._context = St.ThemeContext.get_for_stage(global.stage);
        // A theme reload (User Themes, light and dark) builds a new theme; GNOME copies
        // our sheet into it, but make sure it is there.
        this._changedId = this._context.connect('changed', () => this._load());
        this.update(cfg);
    }

    update(cfg) {
        const css = cfg?.popupCss ?? '';
        if (css === this._css)
            return;
        this._unload();
        this._css = css;
        if (!css) {
            this._remove();
            return;
        }
        // Private to the user: the folder is 0700 and the file 0600.
        GLib.mkdir_with_parents(DIR, 0o700);
        FILE.replace_contents(new TextEncoder().encode(css), null, false,
            Gio.FileCreateFlags.PRIVATE | Gio.FileCreateFlags.REPLACE_DESTINATION, null);
        this._load();
    }

    _load() {
        // Loading a stylesheet makes the theme context say it changed: only act when
        // the theme really is another one, or this would call itself forever.
        const theme = this._context.get_theme();
        if (this._loading || !this._css || !theme || theme === this._theme)
            return;
        this._loading = true;
        try {
            // A theme reload copies our sheet into the new theme already. Loading it
            // again would make every widget on screen restyle twice more, and theme
            // reloads come in bursts (Restore original, light and dark).
            // The list can hold empty entries (seen while the screen is locked).
            if (!theme.get_custom_stylesheets().some(f => f?.equal(FILE)))
                theme.load_stylesheet(FILE);
            this._theme = theme;
        } catch (e) {
            console.error(`Fedora Glass: no pop-up styles: ${e}`);
        } finally {
            this._loading = false;
        }
    }

    _unload() {
        // From the theme in use too: GNOME copies custom stylesheets into each new theme.
        for (const theme of new Set([this._theme, this._context.get_theme()])) {
            try {
                theme?.unload_stylesheet(FILE);
            } catch {}   // that theme is gone
        }
        this._theme = null;
    }

    _remove() {
        try {
            FILE.delete(null);
        } catch {}   // already gone
    }

    destroy() {
        if (this._changedId)
            this._context.disconnect(this._changedId);
        this._changedId = 0;
        this._unload();
        this._remove();
        this._css = '';
    }
}
