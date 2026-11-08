// The real settings live in the Fedora Glass app; this page just opens it.

import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';

import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

function launcher() {
    // fedora-glass, or liquid-glass from before the rename.
    for (const name of ['fedora-glass', 'liquid-glass']) {
        const local = GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', name]);
        if (GLib.file_test(local, GLib.FileTest.IS_EXECUTABLE))
            return local;
    }
    return GLib.find_program_in_path('fedora-glass') ?? GLib.find_program_in_path('liquid-glass');
}

export default class FedoraGlassPrefs extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const page = new Adw.PreferencesPage();
        const group = new Adw.PreferencesGroup({
            title: 'Fedora Glass',
            description: 'Everything is set in the Fedora Glass app, with a live preview.',
        });
        const row = new Adw.ActionRow({title: 'Open Fedora Glass'});
        const button = new Gtk.Button({label: 'Open', valign: Gtk.Align.CENTER, css_classes: ['suggested-action']});
        const path = launcher();
        button.sensitive = path !== null;
        if (path === null)
            row.subtitle = 'The Fedora Glass app is not installed.';
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
