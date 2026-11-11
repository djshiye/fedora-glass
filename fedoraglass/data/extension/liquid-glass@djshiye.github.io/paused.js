// While the glass is paused (the Quick Settings tile) or in safe mode, nothing blurs what
// is under the panel, menus, Quick Settings, Alt+Tab and OSDs. The FedoraGlass Shell theme
// still paints them about 30 % see-through, which only works over the glass: without it
// the windows behind showed sharp and text on top was hard to read. So, until the glass
// is back, these surfaces get the theme's own colours nearly solid:
//
// - a stylesheet (pausedCss in shell-glass.json, rendered from the theme's tokens) loaded
//   by the same loader as the pop-up rules (popupstyle.js), in a file of its own;
// - Dash to Panel's panel. Dash to Panel paints its panel colour itself, as an inline
//   style (trans-bg-color at trans-panel-opacity, which Fedora Glass sets to the theme's
//   see-through panel colour). An inline style wins over every stylesheet, so instead the
//   opacity Dash to Panel works out is lifted to pausedAlpha, and put back afterwards.
//
// The glass's own pop-up sheet and this one are never loaded together (extension.js).

import {PopupStyle} from './popupstyle.js';

/**
 * Lift one Dash to Panel panel's opacity (its DynamicTransparency) to at least `alpha`.
 * Returns how to undo it, or null if this is not a Dash to Panel we know. Kept free of
 * GNOME imports so the tests can check the wrap and undo on plain objects.
 */
export function liftPanel(dt, alpha, warn = () => {}) {
    if (!dt || typeof dt._updateAlpha !== 'function' || typeof dt._updateAlphaAndSet !== 'function')
        return null;
    const own = Object.hasOwn(dt, '_updateAlpha');
    const original = dt._updateAlpha;
    let live = true;
    const wrapper = function (...args) {
        original.apply(this, args);
        // A panel the user made more solid than this stays as it is.
        if (live && !(this.alpha >= alpha))
            this.alpha = alpha;
    };
    dt._updateAlpha = wrapper;
    dt._updateAlphaAndSet();
    return () => {
        live = false;
        if (dt._updateAlpha === wrapper) {
            if (own)
                dt._updateAlpha = original;
            else
                delete dt._updateAlpha;
        } else {
            // Someone wrapped on top of ours: ours stays under theirs, inert.
            warn("Dash to Panel's _updateAlpha was wrapped again after Fedora Glass; leaving it as it is");
        }
        dt._updateAlphaAndSet();   // its own colour again
    };
}

export class PausedStyle {
    constructor(cfg) {
        this._alpha = cfg?.pausedAlpha ?? 0.96;
        this._lifted = new Map();   // DynamicTransparency -> undo
        this._dtp = null;
        this._dtpId = 0;
        this._sheet = new PopupStyle(cfg, {key: 'pausedCss', file: 'paused.css', settleMs: 0});
        this._liftPanels();
    }

    update(cfg) {
        this._sheet?.update(cfg);
        const alpha = cfg?.pausedAlpha ?? 0.96;
        if (alpha !== this._alpha) {
            this._dropPanels();
            this._alpha = alpha;
        }
        this._liftPanels();
    }

    _liftPanels() {
        const dtp = global.dashToPanel;
        // Dash to Panel builds its panels again (monitors, settings): lift the new ones too.
        if (dtp !== this._dtp) {
            this._disconnectDtp();
            if (typeof dtp?.connect === 'function') {
                try {
                    this._dtpId = dtp.connect('panels-created', () => this._liftPanels());
                    this._dtp = dtp;
                } catch {
                    this._dtpId = 0;
                }
            }
        }
        for (const p of dtp?.panels ?? []) {
            const dt = p?.dynamicTransparency;
            if (!dt || this._lifted.has(dt))
                continue;
            try {
                const undo = liftPanel(dt, this._alpha, m => console.warn(`Fedora Glass: ${m}`));
                if (undo)
                    this._lifted.set(dt, undo);
            } catch (e) {
                console.error(`Fedora Glass: no solid Dash to Panel panel: ${e}`);
            }
        }
    }

    _dropPanels() {
        for (const undo of this._lifted.values()) {
            try {
                undo();
            } catch {}   // that panel is gone
        }
        this._lifted.clear();
    }

    _disconnectDtp() {
        if (this._dtp && this._dtpId) {
            try {
                this._dtp.disconnect(this._dtpId);
            } catch {}   // Dash to Panel is gone
        }
        this._dtp = null;
        this._dtpId = 0;
    }

    // Locking: as PopupStyle.destroyLater. The panel is hidden by the lock screen already.
    destroyLater(done) {
        this._disconnectDtp();
        this._dropPanels();
        this._sheet.destroyLater(done);
    }

    destroy() {
        this._disconnectDtp();
        this._dropPanels();
        this._sheet.destroy();
    }
}
