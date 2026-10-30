// The real settings live in the Liquid Glass app; this page just opens it.

import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';

import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

function launcher() {
    const local = GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', 'liquid-glass']);
    return GLib.file_test(local, GLib.FileTest.IS_EXECUTABLE) ? local : GLib.find_program_in_path('liquid-glass');
}

export default class LiquidGlassPrefs extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const page = new Adw.PreferencesPage();
        const group = new Adw.PreferencesGroup({
            title: 'Liquid Glass',
            description: 'Everything is set in the Liquid Glass app, with a live preview.',
        });
        const row = new Adw.ActionRow({title: 'Open Liquid Glass'});
        const button = new Gtk.Button({label: 'Open', valign: Gtk.Align.CENTER, css_classes: ['suggested-action']});
        const path = launcher();
        button.sensitive = path !== null;
        if (path === null)
            row.subtitle = 'The Liquid Glass app is not installed.';
        button.connect('clicked', () => {
            Gio.Subprocess.new([path, 'gui'], Gio.SubprocessFlags.NONE);
            window.close();
        });
        row.add_suffix(button);
        row.activatable_widget = button;
        group.add(row);
        page.add(group);
        window.add(page);
    }
}
