// How the lock screen's glass looks: the sheet over the wallpaper, the card behind
// the password prompt, the big clock and the small glass chips. Shared by the lock
// screen (lock.js, lockwidgets.js) and the login screen add-on, which copies this
// file next to its own, so both screens look the same.
//
// Plain values and pure functions only: no imports, so it loads anywhere (the login
// screen runs a GNOME Shell without the desktop extension).

export const CARD_PAD = 28;            // px of glass around the password prompt
export const CLOCK_STYLES = {
    bold: {time: 'font-size: 96pt; font-weight: 800;', date: 'font-weight: 600;'},
    thin: {time: 'font-size: 92pt; font-weight: 200;', date: 'font-weight: 400;'},
};

// The sheet is calm: no pointer light, no motion, no colour bleed. Its ceiling
// keeps the white clock readable on any wallpaper: at most linear Y 0.13, which
// is 5.8:1 against white.
export const SHEET_CEILING = 0.13;
// The card sits a little deeper than the sheet on bright wallpapers (6.6:1), so the
// name, the messages and GNOME's lighter password field on it stay readable too.
export const CARD_CEILING = 0.11;

/** c: {blur, dim (sheet brightness), tint: [r, g, b, a]} */
export function sheetLook(c) {
    return {blur: c.blur, refraction: 34, bend: 40, depth: 0.2, dispersion: 0.25, saturation: 1.35,
        brightness: c.dim, tint: c.tint, highlight: 0.5, bleed: 0, pointerLight: 0, motion: 0,
        adapt: 0, shadow: 0, ceiling: SHEET_CEILING, solid: 1, rim: 0};
}

export function cardLook(c) {
    const [r, g, b, a] = c.tint;
    // A shallow lens: on a plain backdrop a deep edge only reads as darker bands.
    return {...sheetLook(c), refraction: 12, bend: 16, depth: 0.12, dispersion: 0.15,
        brightness: Math.min(1, c.dim + 0.12), tint: [r, g, b, Math.min(1, a * 0.6)], highlight: 0.55,
        ceiling: CARD_CEILING, solid: 0, rim: 0.6};
}

// The small glass chips under the clock (the battery): white text, and a pane of glass
// lighter than the frosted sheet under it, with a bright top rim and a soft shadow.
// The sheet's own ceiling keeps the white text readable on it.
export const CHIP_TEXT = 'color: #ffffff; font-weight: 600; text-shadow: 0 1px 3px rgba(0,0,0,0.35);';
export const CHIP = 'background-color: rgba(255,255,255,0.11); border: 1px solid rgba(255,255,255,0.17); ' +
    'border-top-color: rgba(255,255,255,0.32); border-radius: 999px; padding: 7px 16px 7px 13px; ' +
    'spacing: 8px; box-shadow: 0 3px 12px rgba(0,0,0,0.16);';
// The owner's message under the clock, on a wider, quieter pane of the same glass.
export const MESSAGE = 'background-color: rgba(255,255,255,0.09); border: 1px solid rgba(255,255,255,0.14); ' +
    'border-top-color: rgba(255,255,255,0.26); border-radius: 16px; padding: 9px 16px; margin-top: 12px;';

// UPower's device states (UPowerGlib.DeviceState), as numbers so no extra library is
// needed: if one were missing, the whole extension would fail to load.
export const CHARGING = 1, FULLY_CHARGED = 4;

/** The name of GNOME's battery icon for a charge (percent) and UPower state. */
export function batteryIcon(percent, state) {
    const level = 10 * Math.floor(Math.max(0, Math.min(100, percent)) / 10);
    if (state === FULLY_CHARGED || (state === CHARGING && level === 100))
        return 'battery-level-100-charged-symbolic';
    return `battery-level-${level}${state === CHARGING ? '-charging' : ''}-symbolic`;
}
