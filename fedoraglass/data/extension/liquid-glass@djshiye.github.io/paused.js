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
// And the gliding taskbar highlight (glide.js) carries on. It is no glass, it stands in for
// Dash to Panel's own hover highlight (the app sets that one's colour to clear while the
// glide is switched on), and it goes down with the animations when the glass stops: up to
// 1.7.10 a taskbar icon under the pointer showed nothing at all while the glass was paused.
//
// The glass's own pop-up sheet and this one are never loaded together (extension.js).

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {disposed, dtpPanels} from './common.js';
import {HoverGlide} from './glide.js';
import {PopupStyle} from './popupstyle.js';

const DASH_TO_PANEL = 'dash-to-panel@jderose9.github.com';
const ACTIVE = 1;   // GNOME's ExtensionState.ACTIVE

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

// A destroyed panel still answers, and every call on it only fills the log.
function deadPanel(panel) {
    return disposed(panel) || disposed(panel.panelBox ?? panel);
}

export class PausedStyle {
    constructor(cfg) {
        this._alpha = cfg?.pausedAlpha ?? 0.96;
        this._lifted = new Map();   // DynamicTransparency -> [its panel, undo]
        this._dtp = null;
        this._dtpId = 0;
        // Dash to Panel switched off and on again is a new object with new panels, which
        // nothing else here would notice until the next Apply.
        this._managerId = 0;
        this._manager = Main.extensionManager ?? null;
        try {
            this._managerId = this._manager?.connect('extension-state-changed', (_m, ext) => {
                if (ext?.uuid === DASH_TO_PANEL && ext.state === ACTIVE)
                    this._liftPanels();
            }) ?? 0;
        } catch {
            this._managerId = 0;
        }
        this._sheet = new PopupStyle(cfg, {key: 'pausedCss', file: 'paused.css', settleMs: 0});
        this._liftPanels();
        this._glide = null;
        this._syncGlide(cfg);
    }

    update(cfg) {
        this._sheet?.update(cfg);
        const alpha = cfg?.pausedAlpha ?? 0.96;
        if (alpha !== this._alpha) {
            this._dropPanels();
            this._alpha = alpha;
        }
        this._liftPanels();
        this._syncGlide(cfg);
    }

    // The gliding highlight while the glass is down, when the user has it switched on. On its
    // own: without it the rest of the paused look still stands.
    _syncGlide(cfg) {
        const look = cfg?.glide;
        try {
            if (look?.enabled) {
                this._glide ??= new HoverGlide();
                this._glide.update(look);
            } else {
                this._dropGlide();
            }
        } catch (e) {
            console.error(`Fedora Glass: no gliding highlight while paused: ${e}`);
            this._dropGlide();
        }
    }

    _dropGlide() {
        const glide = this._glide;
        this._glide = null;
        try {
            glide?.destroy();
        } catch (e) {
            console.error(`Fedora Glass: removing the gliding highlight: ${e}`);
        }
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
        // Panels Dash to Panel took down since: nothing to put back, and nothing to keep.
        for (const [dt, [panel]] of [...this._lifted]) {
            if (deadPanel(panel))
                this._lifted.delete(dt);
        }
        for (const p of dtpPanels()) {   // never the ones Dash to Panel already destroyed
            const dt = p?.dynamicTransparency;
            if (!dt || this._lifted.has(dt))
                continue;
            try {
                const undo = liftPanel(dt, this._alpha, m => console.warn(`Fedora Glass: ${m}`));
                if (undo)
                    this._lifted.set(dt, [p, undo]);
            } catch (e) {
                console.error(`Fedora Glass: no solid Dash to Panel panel: ${e}`);
            }
        }
    }

    _dropPanels() {
        for (const [panel, undo] of this._lifted.values()) {
            // A panel Dash to Panel took down meanwhile (a screen re-plugged, its settings
            // changed): touching it only fills the log.
            if (deadPanel(panel))
                continue;
            try {
                undo();
            } catch {}   // that panel is gone
        }
        this._lifted.clear();
    }

    _disconnectManager() {
        if (this._manager && this._managerId) {
            try {
                this._manager.disconnect(this._managerId);
            } catch {}
        }
        this._managerId = 0;
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
        this._dropGlide();
        this._disconnectManager();
        this._disconnectDtp();
        this._dropPanels();
        this._sheet.destroyLater(done);
    }

    destroy() {
        this._dropGlide();
        this._disconnectManager();
        this._disconnectDtp();
        this._dropPanels();
        this._sheet.destroy();
    }
}
