// Liquid Glass for GNOME Shell. The look is set in the Liquid Glass app, which
// writes ~/.config/liquid-glass/shell-glass.json; changes show up live.
// It also decides whether GNOME starts on the desktop or in the overview.

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

import {Animations} from './animations.js';
import {Config} from './config.js';
import {DesktopBehaviour} from './desktop.js';
import {GlassManager} from './surfaces.js';

export default class LiquidGlassExtension extends Extension {
    enable() {
        this._config = new Config(cfg => {
            this._manager?.update(cfg);
            this._desktop?.update(cfg);
            this._animations?.update(cfg);
        });
        this._desktop = new DesktopBehaviour(this._config.value);
        this._manager = new GlassManager(this._config.value);
        this._animations = new Animations(this._config.value);
    }

    disable() {
        // Windows and icons mid-animation land at once, and GNOME's own animations come back.
        try {
            this._animations?.destroy();
        } catch (e) {
            logError(e, 'Liquid Glass: turning the animations off');   // the rest still turns off
        }
        this._animations = null;
        this._desktop?.destroy();
        this._desktop = null;
        this._config?.destroy();
        this._config = null;
        this._manager?.destroy();
        this._manager = null;
    }
}
