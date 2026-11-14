// The login screen's look as data: the values in look.json checked again, the glass
// values for the panes, and the stylesheet text.
//
// Pure functions and no imports, so they run (and are tested) anywhere. Only checked
// values reach the stylesheet: colours as #rrggbb and plain numbers. The message is
// never part of it; it is set as a label's text.

export const LOOK_VERSION = 1;
export const MESSAGE_MAX = 120;
const HEX = /^#[0-9a-f]{6}$/;
const TOKEN = /^[0-9a-f]{32}$/;
// Control characters (C0, DEL, C1): the root helper removes them, so one here means the
// file was not written by it.
const CONTROL = /[\u0000-\u001f\u007f-\u009f]/u;
const CHOICES = {clock: ['gnome', 'bold', 'thin'], picture: ['wallpaper', 'system', 'glow'],
    fit: ['zoom', 'spanned', 'scaled', 'stretched', 'centered', 'wallpaper']};
const NUMBERS = {tint_amount: [0, 1], frost: [0, 1], dim: [0, 0.65]};
const KEYS = ['version', 'token', 'accent', 'tint', 'tint_amount', 'frost', 'blur', 'dim', 'card', 'clock',
    'picture', 'fit', 'battery', 'message'];
// Added to the contract later (how "My wallpaper" is placed): a look.json from a helper
// that does not write it yet means GNOME's default, zoom. Present, it is checked like the rest.
const OPTIONAL = {fit: 'zoom'};

/**
 * look.json checked field by field, with the bounds of the shared contract. Returns
 * {look, problem}: look is a clean copy, or null with a short reason in problem.
 * Nothing is mended: a file the root helper did not write exactly so is refused whole.
 */
export function checkLook(raw) {
    const bad = problem => ({look: null, problem});
    if (!raw || typeof raw !== 'object' || Array.isArray(raw))
        return bad('not an object');
    for (const k of Object.keys(raw)) {
        if (!KEYS.includes(k))
            return bad(`unknown key ${k.slice(0, 20)}`);
    }
    for (const k of KEYS) {
        if (!Object.hasOwn(raw, k) && !Object.hasOwn(OPTIONAL, k))
            return bad(`missing ${k}`);
    }
    raw = {...OPTIONAL, ...raw};
    if (raw.version !== LOOK_VERSION)
        return bad('version');
    if (typeof raw.token !== 'string' || !TOKEN.test(raw.token))
        return bad('token');
    for (const k of ['accent', 'tint']) {
        if (typeof raw[k] !== 'string' || !HEX.test(raw[k].toLowerCase()))
            return bad(k);
    }
    for (const [k, [lo, hi]] of Object.entries(NUMBERS)) {
        if (typeof raw[k] !== 'number' || !Number.isFinite(raw[k]) || raw[k] < lo || raw[k] > hi)
            return bad(k);
    }
    if (!Number.isInteger(raw.blur) || raw.blur < 10 || raw.blur > 100)
        return bad('blur');
    for (const k of ['card', 'battery']) {
        if (typeof raw[k] !== 'boolean')
            return bad(k);
    }
    for (const [k, list] of Object.entries(CHOICES)) {
        if (!list.includes(raw[k]))
            return bad(k);
    }
    const m = raw.message;
    if (typeof m !== 'string' || [...m].length > MESSAGE_MAX || CONTROL.test(m))
        return bad('message');
    return {look: {...raw, accent: raw.accent.toLowerCase(), tint: raw.tint.toLowerCase()}, problem: ''};
}

// ---- values only reach the stylesheet through these two ----
function hex(v) {
    if (typeof v !== 'string' || !HEX.test(v))
        throw new Error('not a colour');
    return v;
}

function unit(v, lo = 0, hi = 1) {
    if (typeof v !== 'number' || !Number.isFinite(v))
        throw new Error('not a number');
    return Math.max(lo, Math.min(hi, v));
}

function rgb(h) {
    h = hex(h);
    return [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
}

/** a and b (#rrggbb) mixed, t of the way from a to b, as #rrggbb. */
export function mix(a, b, t) {
    const [x, y] = [rgb(a), rgb(b)];
    t = unit(t);
    return `#${x.map((v, i) => Math.round(v + (y[i] - v) * t).toString(16).padStart(2, '0')).join('')}`;
}

function rgba(h, a) {
    return `rgba(${rgb(h).join(', ')}, ${unit(a).toFixed(3)})`;
}

const white = a => `rgba(255, 255, 255, ${unit(a).toFixed(3)})`;

/**
 * What the glass panes need, with the lock screen's maths: the sheet's brightness is
 * 1 - dim (never under 0.35), the tint is the tint colour at tint_amount * 0.4 (never
 * over 0.6).
 */
export function glassValues(look) {
    const [r, g, b] = rgb(look.tint).map(v => Math.round(v / 255 * 10000) / 10000);
    return {
        blur: Math.round(unit(look.blur, 10, 100)),
        dim: Math.max(0.35, Math.min(1, 1 - unit(look.dim, 0, 0.65))),
        tint: [r, g, b, Math.min(0.6, unit(look.tint_amount) * 0.4)],
    };
}

/**
 * The "glow" picture: a soft light of the accent rising into the tint colour. Two
 * inline styles, for a full-screen gradient and a round glow over it. The glass blurs
 * and dims both, as it does a wallpaper.
 */
export function glowStyles(look) {
    const black = '#000000';
    const top = mix(look.tint, black, 0.55);
    const bottom = mix(mix(look.tint, look.accent, 0.35), black, 0.25);
    return {
        base: `background-gradient-direction: vertical; background-color: ${top}; ` +
            `background-gradient-start: ${top}; background-gradient-end: ${bottom};`,
        glow: `background-gradient-direction: radial; background-color: transparent; ` +
            `background-gradient-start: ${rgba(look.accent, 0.55)}; background-gradient-end: ${rgba(look.accent, 0)};`,
    };
}

// Every login screen element we style, under .login-dialog (the panel has its own).
const ROW = '.login-dialog .login-dialog-user-list-view .login-dialog-user-list .login-dialog-user-list-item';
const LINK = '.login-dialog .login-dialog-not-listed-button';
const WAYS = '.login-dialog .login-dialog-auth-list-item';
const BACK = '.login-dialog .login-dialog-button.cancel-button';
const BUTTONS = ['a11y-button', 'switch-user-button', 'login-dialog-auth-menu-button',
    'login-dialog-session-list-button'].map(c => `.login-dialog .login-dialog-button.${c}`);
const sel = (list, state = '') => list.map(s => s + state).join(',\n');

// ---- where the password prompt stands ----
// The card belongs in the middle of the screen, as on the lock screen. GNOME puts its
// prompt higher: on GNOME 51 and later its top is fixed FIXED_TOP stage px above the
// middle, on GNOME 50 it is centred with the room it keeps under the field for messages.
// A margin above it (a style, nothing is moved by hand) sets it right in both.
export const FIXED_TOP = 275;
// What the prompt shows, from the avatar's top to the field's bottom, in px: the avatar
// (128) and the gap under it (16) as set below, and the name and the field's row, which
// grow with the font (px at the usual 11pt font, times the text scaling factor). Under
// the field GNOME keeps room for its messages (the same way).
const PROMPT_FIXED = 144;
const PROMPT_TEXT = {fixedTop: 96, centred: 92};
const PROMPT_ROOM = {fixedTop: 74, centred: 67};
// The room GNOME 51's own theme keeps above its prompt, in px (GNOME 50: none).
const OWN_MARGIN = 80;

/**
 * The margin above GNOME's prompt that brings what it shows to the middle of its screen:
 * {margin (px as in a stylesheet), content (how tall that is, the same px), top (where it
 * then begins, stage px from the screen's top)}.
 *
 * fixedTop: GNOME places the prompt's top at a fixed height (GNOME 51+). scale: the
 * theme's scale factor. textScale: the text scaling factor. screen: the screen's height
 * in stage px. above: stage px to keep free above it (the big clock on a short screen):
 * then it stands lower than the middle, as long as GNOME's messages under the field still
 * fit on the screen.
 *
 * own: leave the prompt where GNOME puts it (margin null: no margin of ours). GNOME's
 * place is higher, so more fits under the field; login.js asks for it when what GNOME
 * shows there would end below the screen. top is then only a guess (for the clock).
 */
export function promptPlace({fixedTop = true, scale = 1, textScale = 1, screen = 1080, above = 0, own = false} = {}) {
    scale = unit(scale, 1, 4);
    textScale = unit(textScale, 0.5, 3);
    screen = unit(screen, 200, 20000);
    above = unit(above, 0, 20000);
    const way = fixedTop ? 'fixedTop' : 'centred';
    const content = Math.round(PROMPT_FIXED + PROMPT_TEXT[way] * textScale);
    const room = PROMPT_ROOM[way] * textScale;
    const middle = screen / 2;
    if (own) {
        return {margin: null, content, top: Math.round(fixedTop ? middle - FIXED_TOP + OWN_MARGIN * scale
            : middle - (content + room) * scale / 2)};
    }
    let top = middle - content * scale / 2;
    if (above > top && above + (content + room + 16) * scale <= screen)
        top = above;
    // GNOME 51+: the margin is what lies between its fixed top and ours. GNOME 50: the
    // prompt (margin, content and room) is centred, so every 2 px of margin lower it by 1.
    const margin = Math.round(unit(fixedTop ? (top - (middle - FIXED_TOP)) / scale
        : 2 * (top - middle) / scale + content + room, 0, 600));
    top = fixedTop ? middle - FIXED_TOP + margin * scale : middle + (margin - content - room) * scale / 2;
    return {margin, content, top: Math.round(top)};
}

// ---- where the list of users stands ----
/**
 * The margin above GNOME's list of users (px as in a stylesheet) that lets a long list
 * grow downward. GNOME keeps the list in the middle of its dialog, so a long one reaches
 * as far up as down. The margin lowers it until it begins at `top`, as far as it then
 * still ends by `bottom`; a list that begins lower than `top` anyway (a short one) gets
 * none and stays in the middle. GNOME centres the list with its margin, so every 2 px of
 * margin lower it by 1.
 *
 * middle: the middle of GNOME's dialog; height: how tall the list is with "Not listed?";
 * top: where the list should begin; bottom: where it must end (all stage px down the
 * screen). scale: the theme's scale factor.
 */
export function listMargin({scale = 1, middle, height, top, bottom} = {}) {
    if (![scale, middle, height, top, bottom].every(Number.isFinite) || height <= 0)
        return 0;
    const lower = Math.min(top - (middle - height / 2), bottom - (middle + height / 2));
    return lower >= 1 ? Math.round(unit(2 * lower / unit(scale, 1, 4), 0, 4000)) : 0;
}

/**
 * The stylesheet for the login screen, from checked values. The user list and the
 * password prompt each sit on one card of real glass (drawn under them by login.js), so
 * what is on the card is quiet: a user is a plain row that lights up softly under the
 * pointer and when chosen, "Not listed?" is a line of text under the rows, and the back
 * button is a faint disc. The password field is the lock screen's pill, and the avatar,
 * the other buttons and a list of ways to log in are small panes of glass: a little
 * white that is lighter at the top, a bright rim and a soft shadow. Without the card
 * (look.card off) each user is such a pane too. The glass is always dark (its ceiling
 * keeps white text at 5.8:1 or more), so every text is set white, in dark and in light
 * style alike: the light style's dark text would not read on it.
 *
 * margin: px above GNOME's prompt (promptPlace), or null to leave it where GNOME puts it.
 * list: px above GNOME's list of users (listMargin), 0 to leave it in the middle.
 */
export function stylesheet(look, {margin = null, list = 0} = {}) {
    const accent = hex(look.accent);
    const frost = unit(look.frost);
    const pane = 0.07 + 0.07 * frost;         // white in each pane: clear glass to frost
    const hover = pane + 0.05;
    const lit = pane + 0.08;                  // the top of a pane, where the light falls
    const edge = 0.20 + 0.10 * frost;         // a bright rim, as on the desktop's glass
    const shine = Math.min(0.30, edge + 0.10);  // the rim's top edge catches the most light
    const glass = `  background-color: ${white(pane)};
  background-gradient-direction: vertical;
  background-gradient-start: ${white(lit)};
  background-gradient-end: ${white(pane)};
  border: 1px solid ${white(edge)};
  border-top-color: ${white(shine)};`;
    const raised = `  background-gradient-start: ${white(lit + 0.05)};
  background-gradient-end: ${white(hover)};`;
    // A row on the card: nothing until it is pointed at or chosen. Pointed at, it gets a
    // little light; the row that has the keyboard is lit more and has a clear white rim,
    // so the two are never mistaken for each other. GNOME's accent ring around it is
    // taken off (!important, as GNOME sets it so): the lit rim says the same on glass.
    const rows = look.card ? `${ROW} {
  background-color: transparent;
  background-gradient-direction: none;
  border: 1px solid transparent;
  border-radius: 16px;
  box-shadow: none;
  color: #ffffff; }
${ROW}:hover {
  background-color: ${white(0.07)}; }
${ROW}:selected,
${ROW}:focus {
  background-color: ${white(0.12)};
  border-color: ${white(0.38)};
  border-top-color: ${white(0.58)};
  box-shadow: none !important; }
${ROW}:selected:hover,
${ROW}:focus:hover {
  background-color: ${white(0.16)}; }
${ROW}:active,
${ROW}:active:hover,
${ROW}:active:focus {
  background-color: ${white(0.21)}; }` : `${ROW} {
${glass}
  color: #ffffff;
  border-radius: 18px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.28); }
${ROW}:hover {
${raised} }
${ROW}:selected,
${ROW}:focus {
${raised}
  border-color: ${white(0.46)};
  border-top-color: ${white(0.62)};
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.28) !important; }`;
    // GNOME 50 gives the box inside its prompt the prompt's own style class: the room is
    // for the prompt only.
    const place = margin === null ? ['', ''] : [`
  margin-top: ${Math.round(unit(margin, 0, 600))}px;`, `
.login-dialog .login-dialog-prompt-layout .login-dialog-prompt-layout {
  margin-top: 0px; }`];
    const listPlace = Math.round(unit(list, 0, 4000));
    return `/* Fedora Glass login screen (made by the add-on from look.json). */
.login-dialog {
  background-color: transparent;
  background-gradient-direction: none;
  color: #ffffff; }
.login-dialog .login-dialog-prompt-layout {
  width: 25em;
  min-width: 25em;
  padding: 0;${place[0]}
  background-color: transparent;
  border-width: 0;
  box-shadow: none; }${place[1]}
.login-dialog .login-dialog-user-selection-box {
  padding-top: 4em;
  padding-bottom: 4em;${listPlace ? `
  margin-top: ${listPlace}px;` : ''} }
.login-dialog .login-dialog-user-list-view .login-dialog-user-list {
  margin: 0;
  spacing: ${look.card ? 4 : 12}px; }
${rows}
${LINK} {
  width: 25em;
  margin: 6px 0px 0px 0px;
  padding: 0;
  background-color: transparent;
  border-width: 0;
  border-radius: 12px;
  box-shadow: none; }
${LINK}:hover {
  background-color: ${white(0.08)}; }
${LINK}:focus,
${LINK}:focus:hover {
  background-color: ${white(0.12)};
  box-shadow: inset 0 0 0 1px ${white(0.46)} !important; }
${LINK}:active,
${LINK}:active:hover,
${LINK}:active:focus {
  background-color: ${white(0.21)}; }
.login-dialog .login-dialog-not-listed-label {
  padding: 6px;
  font-weight: 500;
  text-align: center;
  color: ${white(0.86)}; }
${LINK}:focus .login-dialog-not-listed-label,
${LINK}:hover .login-dialog-not-listed-label {
  color: #ffffff; }
${WAYS} {
${glass}
  color: #ffffff;
  border-radius: 18px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.28); }
${WAYS}:hover {
${raised} }
${WAYS}:focus {
${raised}
  border-color: ${accent}; }
.login-dialog .login-dialog-prompt-entry {
${glass}
  border-radius: 999px;
  padding: 9px 14px;
  min-width: 14em;
  color: #ffffff;
  caret-color: #ffffff;
  selection-background-color: ${accent};
  selected-color: #ffffff;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.30); }
.login-dialog .login-dialog-prompt-entry:hover {
${raised} }
.login-dialog .login-dialog-prompt-entry:focus {
${raised}
  border-color: ${accent};
  box-shadow: inset 0 0 0 2px ${rgba(accent, 0.85)} !important; }
.login-dialog .login-dialog-prompt-entry StLabel.hint-text {
  color: ${white(0.70)}; }
.login-dialog .login-dialog-prompt-entry StIcon,
.login-dialog .login-dialog-button.next-button StIcon {
  color: #ffffff; }
${BACK} {
  background-color: ${white(0.06)};
  background-gradient-direction: none;
  border: 1px solid transparent;
  color: ${white(0.82)}; }
${BACK}:hover,
${BACK}:focus:hover {
  background-color: ${white(0.15)};
  color: #ffffff; }
${BACK}:focus {
  background-color: ${white(0.10)};
  border-color: ${accent};
  color: #ffffff; }
${BACK}:active,
${BACK}:active:hover,
${BACK}:active:focus {
  background-color: ${white(0.22)}; }
${sel(BUTTONS)} {
${glass}
  color: #ffffff; }
${sel(BUTTONS, ':hover')} {
${raised} }
${sel(BUTTONS, ':focus')} {
  border-color: ${accent}; }
.login-dialog .user-widget .user-icon {
  background-color: ${white(pane)};
  background-gradient-direction: vertical;
  background-gradient-start: ${white(lit + 0.09)};
  background-gradient-end: ${white(pane - 0.03)};
  border: 1px solid ${white(edge)};
  border-top-color: ${white(Math.min(0.5, shine + 0.14))};
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.32); }
.login-dialog .login-dialog-user-list-item .user-widget .user-icon {
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.22); }
.login-dialog .user-widget .user-icon StIcon {
  color: #ffffff; }
.login-dialog .user-widget.vertical .user-icon {
  icon-size: 128px; }
.login-dialog .user-widget.vertical .user-icon StIcon {
  padding: 24px; }
.login-dialog .user-widget.vertical {
  spacing: 16px; }
.login-dialog .user-widget-label,
.login-dialog .login-dialog-user-list-item .user-widget-label,
.login-dialog .login-dialog-banner,
.login-dialog .login-dialog-auth-list-label,
.login-dialog .login-dialog-auth-list-title {
  color: #ffffff; }
.login-dialog .user-widget.vertical .user-widget-label {
  margin-bottom: 0.4em;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.35); }
.login-dialog .login-dialog-message,
.login-dialog .login-dialog-message-hint {
  color: ${white(0.88)}; }
.login-dialog .login-dialog-message-warning,
.login-dialog .caps-lock-warning-label {
  color: #f8e45c; }
#panel.login-screen {
  background-color: transparent; }
#panel.login-screen .panel-button,
#panel.login-screen .panel-button .system-status-icon,
#panel.login-screen .panel-button .clock {
  color: #ffffff; }
`;
}
