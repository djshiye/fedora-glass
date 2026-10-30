// Liquid Glass for GNOME Shell. The look is set in the Liquid Glass app, which
// writes ~/.config/liquid-glass/shell-glass.json; changes show up live.
// It also decides whether GNOME starts on the desktop or in the overview.

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

import {Config} from './config.js';
import {DesktopBehaviour} from './desktop.js';
import {GlassManager} from './surfaces.js';

export default class LiquidGlassExtension extends Extension {
    enable() {
        this._config = new Config(cfg => {
            this._manager?.update(cfg);
            this._desktop?.update(cfg);
        });
        this._desktop = new DesktopBehaviour(this._config.value);
        this._manager = new GlassManager(this._config.value);
    }

    disable() {
        this._desktop?.destroy();
        this._desktop = null;
        this._config?.destroy();
        this._config = null;
        this._manager?.destroy();
        this._manager = null;
    }
}
