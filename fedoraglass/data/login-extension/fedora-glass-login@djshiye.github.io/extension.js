// Fedora Glass on the GDM login screen. Installed by the Fedora Glass package into
// GDM's own extension folder and switched on by its root helper (fedora-glass-login),
// which writes /etc/fedora-glass/login/look.json and the picture. Runs only in the
// "gdm" session mode.
//
// Kept small on purpose: it says "starting" in the health note before anything else,
// then builds the glass (login.js) inside a try. Should the last start with this same
// look never have finished (GNOME Shell went down with it), or the last runs have ended
// without a clean stop UNCLEAN_LIMIT times in a row in this boot (a crash that comes
// later, say when the prompt opens), it draws nothing at all.
// No look.json at all (switched off; it is gone before the greeter's next start): it
// draws nothing and writes nothing.
// Any error takes everything away again and says "error"; the root helper's boot guard
// reads the note and turns the glass off for good when it must. Nobody is ever left
// without a working login screen.

import GLib from 'gi://GLib';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

import {Health, RunNote, lookMissing, mustStaySafe, readLook, tokenOf} from './health.js';

const OK_AFTER_MS = 2000;     // built and still running this long: the start finished

export default class FedoraGlassLogin extends Extension {
    enable() {
        // Each start has its own number: a slow import that lands after disable(), or
        // after the next enable(), finds its number out of date and draws nothing.
        this._run = (this._run ?? 0) + 1;
        const run = this._run;
        this._glass = null;
        this._okId = 0;
        this._health = null;
        this._runNote = null;
        let raw = null;
        try {
            if (lookMissing()) {
                // Switched off while this greeter still has the add-on on: nothing to do,
                // nothing to say (the root helper no longer reads the note).
                console.log('Fedora Glass login: switched off (no look.json)');
                return;
            }
            raw = readLook();
            const token = tokenOf(raw);
            this._health = new Health({token});
            this._runNote = token ? new RunNote({token, boot: this._health.boot}) : null;
            // A clean stop of GNOME Shell (it says so) is no crash.
            this._shutdownId = global.connect('shutdown', () => {
                this._runNote?.endClean();
                if (['starting', 'ok'].includes(this._health?.phase))
                    this._health.write('ok');
            });
            const crashed = mustStaySafe(this._health.previous, token, this._health.boot);
            const loop = this._runNote?.tooMany;
            this._runNote?.start();
            if (crashed || loop) {
                this._health.write('safe');
                console.warn(crashed
                    ? 'Fedora Glass login: the last start with this look did not finish, so no glass this time'
                    : `Fedora Glass login: the login screen ended without a clean stop ${this._runNote.unclean} times in a row, so no glass this time`);
                return;
            }
            this._health.write('starting');
            if (!token)
                throw new Error('no usable look.json');
        } catch (e) {
            this._failed(e, run);
            return;
        }
        import('./login.js').then(L => {
            if (run !== this._run)
                return;
            this._glass = new L.LoginGlass(raw, {
                onReady: () => this._built(run),
                onError: e => this._failed(e, run),
                onVerified: () => {
                    this._health?.markVerified();
                    this._runNote?.markVerified();
                },
            });
        }).catch(e => this._failed(e, run));
    }

    // Everything is on screen: still running OK_AFTER_MS later, the start finished.
    _built(run) {
        if (run !== this._run || this._okId)
            return;
        this._okId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, OK_AFTER_MS, () => {
            this._okId = 0;
            if (run === this._run && this._health?.phase === 'starting')
                this._health.write('ok');
            return GLib.SOURCE_REMOVE;
        });
    }

    _failed(e, run) {
        if (run !== this._run)
            return;
        console.error(`Fedora Glass login: no glass on the login screen: ${e}`);
        this._stop();
        try {
            this._health?.write('error');
        } catch {}
    }

    _stop() {
        if (this._okId)
            GLib.source_remove(this._okId);
        this._okId = 0;
        try {
            this._glass?.destroy();
        } catch (e) {
            console.error(`Fedora Glass login: ${e}`);
        }
        this._glass = null;
    }

    disable() {
        this._run = (this._run ?? 0) + 1;
        this._stop();
        if (this._shutdownId)
            global.disconnect(this._shutdownId);
        this._shutdownId = 0;
        // Turned off on purpose: a clean end of this run.
        this._runNote?.endClean();
        this._runNote = null;
        // Turned off on purpose before the 2 s were up: no crash either.
        if (this._health?.phase === 'starting')
            this._health.write('ok');
        this._health = null;
    }
}
