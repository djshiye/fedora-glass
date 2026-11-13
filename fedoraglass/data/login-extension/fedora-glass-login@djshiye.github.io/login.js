// Glass on the GDM login screen: the same frosted sheet as the lock screen over a
// picture, one glass card in the middle behind the user list and the password prompt,
// a big clock above it, the owner's message and the battery.
//
// Safety:
// - Everything drawn here lives in ONE container, the bottom child of the lock dialog
//   group, under GNOME's own login dialog. It takes no input, no key focus and no
//   grab, so nothing here can cover the prompt or change how a login works.
// - The glass copies only our own copy of the picture (in that same container).
// - GNOME's own login dialog is only restyled (a stylesheet built from checked values,
//   which also sets how much room it keeps above its prompt) and its small panel clock
//   hidden while the big clock shows; nothing else of it is changed. The password
//   check is only watched, to tell the root helper that a login worked with the glass on.
// - Any error takes everything away (the plain login screen) and says so (onError).
// - High contrast on: no glass at all, followed live.

import Clutter from 'gi://Clutter';
import GdkPixbuf from 'gi://GdkPixbuf';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Graphene from 'gi://Graphene';
import Meta from 'gi://Meta';
import St from 'gi://St';
import * as Gettext from 'gettext';

import * as Background from 'resource:///org/gnome/shell/ui/background.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {formatDateWithCFormatString, formatTime} from 'resource:///org/gnome/shell/misc/dateUtils.js';

import {GlassPane} from './glass.js';
import {CARD_PAD, CHIP, CHIP_TEXT, CLOCK_STYLES, MESSAGE, batteryIcon, cardLook, sheetLook} from './locklook.js';
import {checkLook, glassValues, glowStyles, promptPlace, stylesheet} from './style.js';

const STYLE_DIR = GLib.build_filenamev([GLib.get_user_runtime_dir(), 'fedora-glass-login']);
const STYLE_FILE = Gio.File.new_for_path(GLib.build_filenamev([STYLE_DIR, 'login.css']));
const WAIT_DIALOG_S = 30;     // GNOME makes its login dialog within moments of starting
const TOP_GAP = 24;          // px kept free between the clock (with its message) and the card or the login dialog
const TOP_MOVE_MS = 200;     // the clock making room, or taking it back
const PICTURE_WAIT_S = 4;     // the picture not loaded by then: the glow instead, for this start
const MIRROR = 128;          // px of a screen's own picture mirrored over its seams (> any pane's padding)
const FADE_MS = 400;         // the glass coming up once its picture is there
const PROMPT_PAD = 40;       // px of card above the avatar and under the field (CARD_PAD on its sides, and around the user list)
const PROMPT_SPARE = 8;      // px GNOME's prompt must stay clear of the screen's bottom, or it gets GNOME's own place back
const CARD_EASE_MS = 160;    // the card growing or shrinking with what is in it
const CARD_MOVE_MS = 250;    // the card going from the user list to the prompt and back (GNOME fades its prompt in as long)
const CARD_HOLD_MS = 1000;   // the card staying where it is while GNOME asks GDM and brings the prompt
const UPOWER = 'org.freedesktop.UPower';
const DISPLAY_DEVICE = '/org/freedesktop/UPower/devices/DisplayDevice';

/**
 * Connections that run their handler through owner._safe and can all be let go at once.
 * An actor destroyed by someone else (GNOME Shell shutting down takes the whole stage
 * away) is let go of by itself and noted in owner._gone, so nothing touches it again.
 */
class Signals {
    constructor(owner) {
        this._owner = owner;
        this._ids = [];
    }

    on(obj, signal, fn) {
        if (obj instanceof Clutter.Actor && !this._ids.some(([o]) => o === obj)) {
            this._ids.push([obj, obj.connect('destroy', () => {
                this._owner._gone.add(obj);
                this._ids = this._ids.filter(([o]) => o !== obj);
            })]);
        }
        this._ids.push([obj, obj.connect(signal, (...args) => this._owner._safe(() => fn(...args)))]);
    }

    clear() {
        for (const [obj, id] of this._ids) {
            try {
                obj.disconnect(id);
            } catch {}   // gone already
        }
        this._ids = [];
    }
}

/**
 * A copy of (part of) the picture. Its paint volume is its clip, so a mirrored copy is
 * never left out of a frame for lying mostly off the stage.
 */
const PictureCopy = GObject.registerClass(
class FedoraGlassLoginPictureCopy extends Clutter.Clone {
    vfunc_get_paint_volume(volume) {
        if (!this.has_clip)
            return super.vfunc_get_paint_volume(volume);
        const [x, y, w, h] = this.get_clip();
        volume.set_origin(new Graphene.Point3D({x, y, z: 0}));
        volume.set_width(Math.max(0, w));
        volume.set_height(Math.max(0, h));
        return true;
    }
});

/** The ways GNOME's login dialog is put together that we rely on, or a reason it is not so. */
export function dialogProblem(shield) {
    const group = shield?._lockDialogGroup;
    const dialog = shield?._dialog;
    if (!group || !dialog)
        return 'no login dialog';
    if (dialog.get_parent?.() !== group)
        return 'the login dialog is somewhere else';
    for (const part of ['_authPrompt', '_userSelectionBox', '_userList'])
        if (!dialog[part])
            return `no ${part}`;
    return '';
}

export class LoginGlass {
    /**
     * raw: look.json as read. Throws when it is refused or the login screen is not as
     * expected (nothing is drawn then). onReady(): everything is built and on screen.
     * onError(e): it failed later and took everything away. onVerified(): a password or
     * fingerprint check succeeded.
     */
    constructor(raw, {onReady = () => {}, onError = () => {}, onVerified = () => {}} = {}) {
        const {look, problem} = checkLook(raw);
        if (!look)
            throw new Error(`look.json refused (${problem})`);
        this.look = look;
        this._values = glassValues(look);
        this._css = stylesheet(look);          // throws on a value that must not reach a stylesheet
        this._glowStyles = glowStyles(look);
        this._fallback = false;      // the picture would not load: the glow for this start
        this._pictureWait = 0;
        this._onReady = onReady;
        this._onError = onError;
        this._onVerified = onVerified;
        this._ended = false;
        this._gone = new WeakSet();              // actors destroyed by someone else
        this._signals = new Signals(this);       // for as long as this runs
        this._drawn = new Signals(this);         // for what is on screen now
        this._verifierSignals = new Signals(this);
        this._waitSignals = new Signals(this);
        this._layer = null;
        this._dialog = null;
        this._later = 0;
        this._rebuildLater = 0;
        this._waitLater = 0;
        this._waitId = 0;
        this._tickId = 0;
        this._theme = null;
        this._loading = false;
        this._group = Main.screenShield?._lockDialogGroup;
        if (!this._group)
            throw new Error('the login screen is not as expected: no lock dialog group');
        try {
            if (Main.screenShield._dialog) {
                this._start();
                return;
            }
            // GNOME Shell starts the extensions a moment before it makes its login dialog:
            // wait for it (it is in the group before it is built, so look once it is).
            this._waitSignals.on(this._group, 'child-added', () => {
                if (this._waitLater)
                    return;
                this._waitLater = global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
                    this._waitLater = 0;
                    this._safe(() => {
                        if (!this._dialog && Main.screenShield._dialog)
                            this._start();
                    });
                    return GLib.SOURCE_REMOVE;
                });
            });
            // Never a login screen at all is not one we know.
            this._waitId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, WAIT_DIALOG_S, () => {
                this._waitId = 0;
                this._safe(() => {
                    throw new Error('the login screen is not as expected: no login dialog');
                });
                return GLib.SOURCE_REMOVE;
            });
        } catch (e) {
            this.destroy();
            throw e;
        }
    }

    _stopWaiting() {
        this._waitSignals.clear();
        if (this._waitLater)
            global.compositor.get_laters().remove(this._waitLater);
        this._waitLater = 0;
        if (this._waitId)
            GLib.source_remove(this._waitId);
        this._waitId = 0;
    }

    _start() {
        this._stopWaiting();
        const why = dialogProblem(Main.screenShield);
        if (why)
            throw new Error(`the login screen is not as expected: ${why}`);
        this._dialog = Main.screenShield._dialog;
        this._settings = St.Settings.get();
        this._context = St.ThemeContext.get_for_stage(global.stage);
        this._signals.on(this._settings, 'notify::high-contrast', () => this._queueRebuild());
        // A screen plugged in, taken away or rescaled: everything again, in the new places.
        this._signals.on(Main.layoutManager, 'monitors-changed', () => this._queueRebuild());
        // A theme reload (high contrast, light and dark) builds a new theme; GNOME copies
        // our sheet into it, but make sure it is there.
        this._signals.on(this._context, 'changed', () => this._loadStyle());
        // Large Text switched on or off at the login screen: the clock's size and the
        // prompt's place follow (everything again, as for a new screen).
        this._interface = new Gio.Settings({schema_id: 'org.gnome.desktop.interface'});
        this._signals.on(this._interface, 'changed::text-scaling-factor', () => {
            if (this._textScaling() !== this._textScale)
                this._queueRebuild();
        });
        // GNOME's login dialog going away takes our layer with it: let go of the rest.
        this._signals.on(this._dialog, 'destroy', () => this.destroy());
        this._watchVerifier();
        this._build();
        this.ready = true;
        this._onReady();
    }

    // Every handler and timer runs in here: one failure takes everything away.
    _safe(fn) {
        if (this._ended)
            return undefined;
        try {
            return fn();
        } catch (e) {
            this._fail(e);
            return undefined;
        }
    }

    _fail(e) {
        if (this._ended)
            return;
        console.error(`Fedora Glass login: the glass is off: ${e}${e?.stack ? `\n${e.stack}` : ''}`);
        this.destroy();
        try {
            this._onError(e);
        } catch {}
    }

    // ---- the password check: only watched ----
    _watchVerifier() {
        const prompt = this._dialog._authPrompt;
        const attach = () => {
            const v = prompt._userVerifier;
            if (!v || v === this._verifier)
                return;
            this._verifierSignals.clear();
            this._verifier = v;
            this._verifierSignals.on(v, 'verification-complete', () => this._onVerified());
        };
        attach();
        // GNOME makes the verifier once with the prompt; should a later GNOME make a new
        // one, the prompt is reset with it: look again then.
        this._signals.on(prompt, 'reset', () => attach());
        if (!this._verifier)
            console.warn('Fedora Glass login: the password check cannot be watched; the boot guard will judge the trial');
    }

    get verifier() {
        return this._verifier ?? null;
    }

    // ---- building ----
    _queueRebuild() {
        if (this._rebuildLater || this._ended)
            return;
        this._rebuildLater = global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
            this._rebuildLater = 0;
            this._safe(() => {
                this._takeDown();
                this._build();
            });
            return GLib.SOURCE_REMOVE;
        });
    }

    _build() {
        // High contrast: no glass at all, GNOME's own login screen.
        if (this._ended || this._settings.high_contrast)
            return;
        const [W, H] = global.stage.get_size();
        // Nothing of it is seen before its picture is there; then it all comes up together.
        const layer = new St.Widget({
            name: 'fedora-glass-login', reactive: false, can_focus: false, track_hover: false,
            x: 0, y: 0, width: W, height: H, opacity: 0,
        });
        this._layer = layer;
        // Destroyed with the group (GNOME Shell shutting down): let go of everything while
        // what is in it still stands (the handlers run before the children go).
        layer.connect('destroy', () => {
            if (this._layer !== layer)
                return;   // our own taking down
            this._layer = null;
            this.destroy();
        });
        // The very bottom: under GNOME's login dialog and anything else in the group.
        this._group.insert_child_at_index(layer, 0);
        this._picture = this._makePicture(layer);
        // Each screen's sheet blurs what lies around it too. With a picture of its own on
        // each screen (zoom, scaled...) the next screen's picture does not go on from this
        // one, and its blur drew a dark or light stripe along the seam: there each sheet
        // sees its own picture mirrored over the seam instead. A spanned picture does go on
        // across the seam, so there the sheets see it as it is.
        const monitors = Main.layoutManager.monitors;
        const own = monitors.length > 1 && !this._spanned();
        this._sheets = [];
        for (const m of monitors) {
            const sheet = new GlassPane('full');
            sheet.name = 'fedora-glass-login-sheet';
            sheet.setLook(sheetLook(this._values));
            layer.add_child(sheet);
            sheet.setSources([own ? this._ownPicture(layer, m) : this._picture]);
            // The sheet fills its screen: no rim.
            sheet.setEdges([true, true, true, true]);
            sheet.place(m.x, m.y, m.width, m.height, [0, 0, 0, 0], m.x, m.y);
            sheet.hide();   // until its picture is there (_showGlass)
            this._sheets.push(sheet);
        }
        if (this.look.card) {
            this._card = new GlassPane('full');
            this._card.name = 'fedora-glass-login-card';
            this._card.setLook(cardLook(this._values));
            layer.add_child(this._card);
            this._card.setSources([this._picture]);
        }
        this._makeTop(layer);
        this._place = this._promptPlace();
        this._css = stylesheet(this.look, {margin: this._place.margin});
        this._writeStyle();
        this._loadStyle();
        this._followDialog();
        // No glass before its picture is there: GNOME's plain background shows meanwhile.
        this._whenPictureReady(() => this._showGlass());
        this._queue();
    }

    _showGlass() {
        this._pictureReady = true;
        for (const sheet of this._sheets) {
            sheet.show();
            sheet.queueFull?.();
        }
        // Up softly, as GNOME brings its own dialog (at once where animations are off).
        this._layer.ease({opacity: 255, duration: FADE_MS, mode: Clutter.AnimationMode.EASE_OUT_QUAD});
        this._syncSmallClock();
        this._queue();
    }

    /**
     * How much room to keep above GNOME's prompt so that what it shows stands in the
     * middle of the screen, or under the big clock where the screen is too short for
     * both (see promptPlace in style.js).
     */
    _promptPlace(own = false) {
        const textScale = this._textScale = this._textScaling();
        const m = Main.layoutManager.primaryMonitor;
        // What the clock needs from the screen's top to where the prompt begins (a few
        // px to spare: the prompt is placed by a rounded margin).
        const clockH = this._clockBox ? this._clockBox.get_preferred_height(-1)[1] : 0;
        const above = clockH ? this._topLeast() + clockH + TOP_GAP + (this._card ? PROMPT_PAD : 0) + 4 : 0;
        return promptPlace({
            fixedTop: typeof this._dialog._getFixedTopActorAllocation === 'function',
            scale: this._context.scale_factor, textScale, screen: m?.height ?? global.stage.height, above, own,
        });
    }

    /** The text scaling factor (Large Text is 1.25), 1 where it cannot be read. */
    _textScaling() {
        try {
            return this._interface.get_double('text-scaling-factor');
        } catch {
            return 1;
        }
    }

    /** The clock never stands higher than this (px from the screen's top): clear of the panel. */
    _topLeast() {
        return (Main.layoutManager.panelBox?.height ?? 0) + 16;
    }

    /** Whether GNOME spans the picture over all screens (the greeter's own setting). */
    _spanned() {
        if (this._usesGlow())
            return false;
        try {
            return new Gio.Settings({schema_id: 'org.gnome.desktop.background'}).get_string('picture-options') === 'spanned';
        } catch {
            return false;
        }
    }

    _usesGlow() {
        return this.look.picture === 'glow' || this._fallback;
    }

    /** What one screen's sheet sees: that screen's picture, mirrored over each seam. */
    _ownPicture(layer, m) {
        const [W, H] = global.stage.get_size();
        const src = new Clutter.Actor({name: 'fedora-glass-login-source', opacity: 0, reactive: false,
            x: 0, y: 0, width: W, height: H});
        layer.insert_child_above(src, this._picture);
        const copy = (clip, x, y, sx, sy) => {
            const c = new PictureCopy({source: this._picture, x, y, scale_x: sx, scale_y: sy});
            c.set_clip(...clip);
            src.add_child(c);
        };
        const [l, t, r, b] = [m.x, m.y, m.x + m.width, m.y + m.height];
        const P = Math.min(MIRROR, m.width, m.height);
        copy([l, t, m.width, m.height], 0, 0, 1, 1);
        // Mirrored at x = l: what lies at l + d shows at l - d (and so on for each side).
        if (l > 0)
            copy([l, t, P, m.height], 2 * l, 0, -1, 1);
        if (r < W)
            copy([r - P, t, P, m.height], 2 * r, 0, -1, 1);
        if (t > 0)
            copy([l, t, m.width, P], 0, 2 * t, 1, -1);
        if (b < H)
            copy([l, b - P, m.width, P], 0, 2 * b, 1, -1);
        return src;
    }

    // ---- the picture: loaded, or the glow ----
    /**
     * Calls ready() once GNOME has loaded the picture for every screen and the picture
     * really is one (it decodes). A picture that does not decode, or is not there within
     * PICTURE_WAIT_S, gives the glow for this start instead: never a black login screen.
     */
    _whenPictureReady(ready) {
        this._pictureReady = false;
        if (!this._managers.length) {
            ready();
            return;
        }
        let pending = this._managers.length;
        let decoded = null;
        const check = () => {
            if (pending > 0 || decoded === null || this._pictureReady)
                return;
            if (decoded) {
                this._stopPictureWait();
                ready();
            } else {
                this._pictureFailed('it does not decode');
            }
        };
        for (const m of this._managers) {
            let seen = false;
            this._drawn.on(m, 'loaded', () => {
                if (seen)
                    return;
                seen = true;
                pending--;
                check();
            });
        }
        this._decodePicture(ok => {
            decoded = ok;
            check();
        });
        this._pictureWait = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, PICTURE_WAIT_S, () => {
            this._pictureWait = 0;
            this._safe(() => {
                if (!this._pictureReady)
                    this._pictureFailed(`it did not load within ${PICTURE_WAIT_S} s`);
            });
            return GLib.SOURCE_REMOVE;
        });
    }

    _stopPictureWait() {
        if (this._pictureWait)
            GLib.source_remove(this._pictureWait);
        this._pictureWait = 0;
        this._decodeCancel?.cancel();
        this._decodeCancel = null;
    }

    _pictureFailed(why) {
        this._stopPictureWait();
        if (this._fallback || this._ended)
            return;
        console.warn(`Fedora Glass login: the login screen picture is not used (${why}): the glow instead`);
        this._fallback = true;
        this._queueRebuild();
    }

    /**
     * Our own picture (the root helper's JPEG or PNG), decoded small to see that it is one;
     * ok(true|false). The greeter's own ("system") picture is GNOME's business: it may be
     * in a format only GNOME's own loader reads, and GNOME shows its colour without it.
     */
    _decodePicture(ok) {
        if (this.look.picture !== 'wallpaper') {
            ok(true);
            return;
        }
        let file = null;
        try {
            const bg = new Gio.Settings({schema_id: 'org.gnome.desktop.background'});
            const scheme = new Gio.Settings({schema_id: 'org.gnome.desktop.interface'}).get_string('color-scheme');
            const uri = bg.get_string(scheme === 'prefer-dark' ? 'picture-uri-dark' : 'picture-uri');
            const options = bg.get_string('picture-options');
            if (uri && options !== 'none')
                file = Gio.File.new_for_uri(uri);
        } catch {}
        if (!file) {
            ok(true);    // no picture: GNOME's colour, which is fine
            return;
        }
        if (file.get_basename()?.endsWith('.xml')) {
            ok(true);    // a timed slide show: GNOME's own business
            return;
        }
        const cancel = new Gio.Cancellable();
        this._decodeCancel = cancel;
        const failed = () => this._safe(() => {
            if (!cancel.is_cancelled())
                ok(false);
        });
        file.read_async(GLib.PRIORITY_DEFAULT, cancel, (_f, res) => {
            let stream;
            try {
                stream = file.read_finish(res);
            } catch {
                failed();
                return;
            }
            GdkPixbuf.Pixbuf.new_from_stream_at_scale_async(stream, 64, 64, true, cancel, (_s, r) => {
                let pixbuf = null;
                try {
                    pixbuf = GdkPixbuf.Pixbuf.new_from_stream_finish(r);
                } catch {}
                try {
                    stream.close(null);
                } catch {}
                if (!pixbuf) {
                    failed();
                    return;
                }
                this._safe(() => {
                    if (!cancel.is_cancelled())
                        ok(true);
                });
            });
        });
    }

    /** Our own copy of the picture the glass shows: never seen itself (opacity 0). */
    _makePicture(layer) {
        const pic = new Clutter.Actor({name: 'fedora-glass-login-picture', opacity: 0, reactive: false,
            x: 0, y: 0, width: layer.width, height: layer.height});
        layer.add_child(pic);
        this._managers = [];
        Main.layoutManager.monitors.forEach((m, i) => {
            if (this._usesGlow()) {
                // The glow: a gradient of the tint, and a round light of the accent low in the middle.
                const g = this._glowStyles;
                pic.add_child(new St.Widget({style: g.base, x: m.x, y: m.y, width: m.width, height: m.height}));
                pic.add_child(new St.Widget({style: g.glow, x: m.x - m.width * 0.15,
                    y: m.y + m.height * 0.3, width: m.width * 1.3, height: m.height * 1.1}));
            } else {
                // The greeter's own background settings: the root helper points them at
                // the picture for "wallpaper"; "system" is whatever they say.
                this._managers.push(new Background.BackgroundManager({
                    container: pic, monitorIndex: i, vignette: false, controlPosition: true,
                }));
            }
        });
        return pic;
    }

    // ---- the clock, the message and the battery at the top ----
    _makeTop(layer) {
        const look = this.look;
        const style = CLOCK_STYLES[look.clock];
        const box = new St.BoxLayout({name: 'fedora-glass-login-top', orientation: Clutter.Orientation.VERTICAL,
            reactive: false, x_align: Clutter.ActorAlign.CENTER});
        this._top = box;
        this._time = this._date = this._message = this._batteryChip = this._batteryRow = this._clockBox = null;
        this._batteryPresent = false;
        this._topY = null;
        if (style) {
            // GNOME's own lock screen clock classes, so it is the same clock as there.
            const clock = new St.BoxLayout({style_class: 'unlock-dialog-clock', orientation: Clutter.Orientation.VERTICAL,
                style: 'margin-top: 0; color: #ffffff;', x_align: Clutter.ActorAlign.CENTER});
            this._time = new St.Label({style_class: 'unlock-dialog-clock-time', style: style.time,
                x_align: Clutter.ActorAlign.CENTER});
            this._date = new St.Label({style_class: 'unlock-dialog-clock-date', style: style.date,
                x_align: Clutter.ActorAlign.CENTER});
            clock.add_child(this._time);
            clock.add_child(this._date);
            box.add_child(clock);
            this._clockBox = clock;
        }
        if (look.battery) {
            const row = new St.BoxLayout({style: 'spacing: 10px; margin-top: 22px;', x_align: Clutter.ActorAlign.CENTER});
            const chip = new St.BoxLayout({style: CHIP});
            chip.icon = new St.Icon({icon_size: 16, style: 'color: #ffffff;', y_align: Clutter.ActorAlign.CENTER});
            chip.label = new St.Label({style: `${CHIP_TEXT} font-size: 11.5pt;`, y_align: Clutter.ActorAlign.CENTER});
            chip.add_child(chip.icon);
            chip.add_child(chip.label);
            row.add_child(chip);
            row.visible = false;
            box.add_child(row);
            this._batteryRow = row;
            this._batteryChip = chip;
            this._watchBattery();
        }
        if (look.message) {
            const msg = new St.Label({
                name: 'fedora-glass-login-message',
                // More air under the date than the lock screen's 12 px: here the pill stands alone.
                style: `${CHIP_TEXT} font-size: 11.5pt; font-weight: 500; ${MESSAGE} margin-top: 20px; ` +
                    'max-width: 520px; text-align: center;',
                x_align: Clutter.ActorAlign.CENTER,
            });
            // Plain text only: the owner's words are never read as markup.
            msg.clutter_text.use_markup = false;
            msg.clutter_text.line_wrap = true;
            msg.text = look.message;
            box.add_child(msg);
            this._message = msg;
        }
        if (!box.get_n_children()) {
            box.destroy();
            this._top = null;
            return;
        }
        layer.add_child(box);
        this._drawn.on(box, 'notify::allocation', () => this._queue());
        if (this._time)
            this._tick();
    }

    _tick() {
        if (!this._time)
            return;
        const now = new Date();
        this._time.text = formatTime(now, {timeOnly: true});
        // The lock screen's date format, in GNOME's own words for this language.
        this._date.text = formatDateWithCFormatString(now, Gettext.dgettext('gnome-shell', '%A %B %-d'));
        // Next on the minute: no timer runs more often than that.
        const ms = (60 - now.getSeconds()) * 1000 - now.getMilliseconds() + 50;
        this._tickId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, Math.max(1000, ms), () => {
            this._tickId = 0;
            this._safe(() => this._tick());
            return GLib.SOURCE_REMOVE;
        });
    }

    // The panel's small clock is hidden only while the big one is seen: not before the
    // glass is up (so there is a clock at every moment), and it comes back with ours gone.
    _syncSmallClock() {
        const big = Boolean(this._pictureReady && this._clockBox?.visible);
        if (big === Boolean(this._smallClock))
            return;
        if (big)
            this._hideSmallClock();
        else
            this._showSmallClock();
    }

    _hideSmallClock() {
        const c = Main.panel?.statusArea?.dateMenu?.container;
        if (!c)
            return;
        if (this._smallClock !== c)
            this._smallClockWas = c.visible;
        this._smallClock = c;
        c.hide();
        // GNOME shows its panel's parts again when the session mode updates.
        if (!this._smallClockWatched) {
            this._smallClockWatched = true;
            this._drawn.on(c, 'notify::visible', () => {
                if (c.visible && this._smallClock === c)
                    c.hide();
            });
        }
    }

    _showSmallClock() {
        const c = this._smallClock;
        this._smallClock = null;
        if (c && this._smallClockWas && !this._gone.has(c))
            c.show();
    }

    _watchBattery() {
        this._cancel = new Gio.Cancellable();
        // The system's combined battery. A PC without one shows no chip.
        Gio.DBusProxy.new_for_bus(Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, null, UPOWER, DISPLAY_DEVICE,
            'org.freedesktop.UPower.Device', this._cancel, (_o, res) => this._safe(() => {
                let proxy;
                try {
                    proxy = Gio.DBusProxy.new_for_bus_finish(res);
                } catch {
                    return;    // no UPower, or cancelled: no chip
                }
                if (this._ended || !this._batteryChip)
                    return;
                this._battery = proxy;
                this._batterySignals = new Signals(this);
                this._batterySignals.on(proxy, 'g-properties-changed', () => this._syncBattery());
                this._syncBattery();
            }));
    }

    _syncBattery() {
        const p = this._battery, chip = this._batteryChip;
        if (!p || !chip)
            return;
        const get = n => p.get_cached_property(n)?.unpack() ?? null;
        const pct = get('Percentage');
        // Type 2 is a battery; a UPS (3) counts too. Nothing else is worth a chip.
        const present = get('IsPresent') === true && Number.isFinite(pct) && [2, 3].includes(get('Type'));
        this._batteryPresent = present;
        this._queue();
        if (!present)
            return;
        chip.icon.icon_name = batteryIcon(pct, get('State'));
        chip.label.text = `${Math.round(pct)}%`;
    }

    // ---- following GNOME's login dialog ----
    _followDialog() {
        const d = this._dialog, prompt = d._authPrompt;
        for (const s of ['notify::visible', 'notify::opacity', 'notify::allocation'])
            this._drawn.on(prompt, s, () => this._queue());
        // The user list too: its rows come a moment after the dialog (the card goes around them).
        for (const a of [d, d._userSelectionBox, d._userList, d._notListedButton, d._bannerView]
            .filter(x => x instanceof Clutter.Actor))
            for (const s of ['notify::visible', 'notify::opacity', 'notify::allocation'])
                this._drawn.on(a, s, () => this._queue());
        // What is in the prompt (the card hugs it): a message appearing, a list of
        // ways to log in, a button showing.
        const parts = [prompt._userWell, prompt._inputWell, prompt._mainBox, prompt._message, prompt._authList,
            prompt._timedLoginIndicator, prompt._capsLockWarningLabel, prompt._webLoginDialog, prompt.cancelButton,
            prompt._defaultButtonWell].filter(a => a instanceof Clutter.Actor);
        for (const a of parts) {
            for (const s of ['notify::visible', 'notify::opacity', 'notify::allocation'])
                this._drawn.on(a, s, () => this._queue());
            if (a instanceof St.Label)
                this._drawn.on(a, 'notify::text', () => this._queue());
        }
    }

    _queue() {
        if (this._later || !this._layer)
            return;
        this._later = global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
            this._later = 0;
            this._safe(() => this._sync());
            return GLib.SOURCE_REMOVE;
        });
    }

    /** Stage rectangle [x, y, w, h] of an actor that has a place on screen (seen or not), or null. */
    static frame(a) {
        if (!a?.mapped)
            return null;
        const [x, y] = a.get_transformed_position();
        const [w, h] = a.get_transformed_size();
        return [x, y, w, h].every(Number.isFinite) && w > 1 && h > 1 ? [x, y, w, h] : null;
    }

    /** Stage rectangle [x, y, w, h] of a shown actor, or null. */
    static box(a) {
        return a && a.opacity !== 0 ? LoginGlass.frame(a) : null;
    }

    /** Where GNOME's login dialog starts showing something on screen (its top), or null. */
    _contentTop() {
        const d = this._dialog;
        const parts = [...(d._userList?._box?.get_children() ?? []), d._notListedButton, d._bannerView,
            ...(d._authPrompt?.get_children() ?? [])];
        const tops = parts.map(a => LoginGlass.box(a)).filter(b => b).map(b => b[1]);
        return tops.length ? Math.min(...tops) : null;
    }

    _sync() {
        if (!this._layer)
            return;
        this._givePromptRoom();
        this._placeTop();
        this._placeCard();
    }

    /**
     * The room we put above GNOME's prompt must never push what GNOME shows under the
     * field (a long message, a list of ways to log in) below the screen. When it would,
     * the prompt gets GNOME's own, higher place back for as long as this is drawn, and
     * the clock makes room by itself (_placeTop).
     */
    _givePromptRoom() {
        if (this._place.margin === null)
            return;
        const m = Main.layoutManager.primaryMonitor;
        const prompt = this._dialog._authPrompt;
        // Only where GNOME has laid it out: until then it says how tall it would like to
        // be, the room above it included, and this is decided once.
        const f = prompt.has_allocation() ? LoginGlass.frame(prompt) : null;
        if (!m || !f || f[1] + f[3] <= m.y + m.height - PROMPT_SPARE)
            return;
        this._place = this._promptPlace(true);
        this._css = stylesheet(this.look, {margin: null});
        this._unloadStyle();
        this._writeStyle();
        this._loadStyle();
    }

    _placeTop() {
        const top = this._top;
        if (!top)
            return;
        const m = Main.layoutManager.primaryMonitor;
        if (!m)
            return;
        // Each part is asked itself. The block leaves out what is hidden, and a text asked
        // how tall it is at no width says 0: asked through the block, a clock that had
        // given way would seem to fit again, and come and go without end.
        const height = a => (a ? a.get_preferred_height(a.get_preferred_width(-1)[1])[1] : 0);
        const clockH = height(this._clockBox);
        const extras = [this._batteryRow, this._message].filter(a => a);
        const extrasH = extras.reduce((h, a) => h + (this._wantShown(a) ? height(a) : 0), 0);
        // It stands in the middle of the room above the card. That room ends where the
        // prompt's card begins, also while the (shorter) user list shows, so the clock
        // stays where it is when one gives way to the other; a long user list ends it sooner.
        const d = this._dialog;
        const rest = m.y + this._place.top - (this._card ? PROMPT_PAD : 0);
        const content = this._contentTop();
        const pad = !this._card ? 0 : d._userSelectionBox?.visible ? CARD_PAD : PROMPT_PAD;
        const limit = Math.min(rest, content === null ? Infinity : content - pad);
        const least = m.y + this._topLeast();
        // Where a block h px tall goes, or null when there is no room for it.
        const fit = h => {
            const y = Math.max(least, Math.round(m.y + (limit - m.y - h) / 2));
            return y + h + TOP_GAP <= limit ? y : null;
        };
        // On a smaller screen, or over a long user list, the message and the battery give
        // way first, and then the clock (the panel's small clock shows again), never the
        // other way round.
        const all = fit(clockH + extrasH);
        const clockOnly = all === null && this._clockBox ? fit(clockH) : null;
        const showExtras = all !== null;
        const showClock = Boolean(this._clockBox) && (all !== null || clockOnly !== null);
        this._extrasShown = showExtras;
        for (const a of extras) {
            const want = showExtras && this._wantShown(a);
            if (a.visible !== want)
                a.visible = want;
        }
        if (this._clockBox && this._clockBox.visible !== showClock)
            this._clockBox.visible = showClock;
        this._syncSmallClock();
        const [, natW] = top.get_preferred_width(-1);     // of what shows now
        this._moveTop(Math.round(m.x + (m.width - natW) / 2), all ?? clockOnly ?? least);
    }

    // To its place at once while nothing of it is seen yet, softly once it is.
    _moveTop(x, y) {
        const top = this._top;
        if (this._topY === null || !this._pictureReady) {
            top.set_position(x, y);
        } else {
            top.x = x;
            if (y !== this._topY)
                top.ease({y, duration: TOP_MOVE_MS, mode: Clutter.AnimationMode.EASE_OUT_QUAD});
        }
        this._topY = y;
    }

    // The battery row only with a battery to show.
    _wantShown(a) {
        return a !== this._batteryRow || Boolean(this._batteryPresent);
    }

    /**
     * The stage rectangle of what the prompt shows ([x0, y0, x1, y1]): the avatar, the
     * name, the entry and its buttons, a message only while it has text, and whatever
     * else is visible in it. GNOME keeps room under the entry for messages that may
     * come; the card does not cover that room while it is empty.
     */
    static contentRect(prompt) {
        let r = null;
        const add = b => {
            if (!b)
                return;
            const [x, y, w, h] = b;
            r = r ? [Math.min(r[0], x), Math.min(r[1], y), Math.max(r[2], x + w), Math.max(r[3], y + h)]
                : [x, y, x + w, y + h];
        };
        const paints = a => {
            try {
                const n = a.get_theme_node();
                return n.get_background_color().alpha > 0 || Boolean(n.get_background_image());
            } catch {
                return false;
            }
        };
        const walk = a => {
            if (!a.visible || a.opacity === 0)
                return;
            if (a instanceof St.Label) {
                if (a.text)
                    add(LoginGlass.box(a));
                return;
            }
            // A whole control counts as one, with its own frame.
            if (a instanceof St.Entry || a instanceof St.Button || a instanceof St.Icon) {
                add(LoginGlass.box(a));
                return;
            }
            const kids = a.get_children();
            if (kids.length) {
                kids.forEach(walk);
                if (a instanceof St.Widget && paints(a))
                    add(LoginGlass.box(a));
            } else if (a instanceof St.Widget && paints(a)) {
                add(LoginGlass.box(a));   // a picture drawn as a background (a user's avatar)
            }
        };
        prompt.get_children().forEach(walk);
        return r;
    }

    /**
     * What the card goes around now: {rect: [x0, y0, x1, y1] on the stage, mid: its
     * middle sideways, list: it is the user list}. The user list is the rows that show
     * with "Not listed?" under them; the prompt is what it shows (contentRect). Null
     * while neither is there.
     */
    _cardContent() {
        const d = this._dialog, prompt = d._authPrompt;
        if (d._userSelectionBox?.visible) {
            const list = LoginGlass.box(d._userList);
            if (!list)
                return null;
            const rect = [list[0], list[1], list[0] + list[2], list[1] + list[3]];
            const link = LoginGlass.box(d._notListedButton);
            if (link) {
                rect[0] = Math.min(rect[0], link[0]);
                rect[2] = Math.max(rect[2], link[0] + link[2]);
                rect[3] = Math.max(rect[3], link[1] + link[3]);
            }
            return {rect, mid: list[0] + list[2] / 2, list: true};
        }
        // Only a prompt that is seen: one GNOME keeps at no opacity has no card (it waits
        // where it is for a moment, then goes: _placeCard).
        const box = LoginGlass.box(prompt);
        const rect = box ? LoginGlass.contentRect(prompt) : null;
        return rect ? {rect, mid: box[0] + box[2] / 2, list: false} : null;
    }

    _placeCard() {
        const card = this._card;
        if (!card)
            return;
        const now = this._pictureReady ? this._cardContent() : null;
        if (!now) {
            // Between the user list and the prompt GNOME shows neither for a moment (it
            // asks GDM first): the card stays where it is meanwhile, and goes when
            // nothing comes.
            if (card.visible && this._pictureReady && !this._cardHeld) {
                this._cardHold ||= GLib.timeout_add(GLib.PRIORITY_DEFAULT, CARD_HOLD_MS, () => {
                    this._cardHold = 0;
                    this._cardHeld = true;
                    this._safe(() => this._queue());
                    return GLib.SOURCE_REMOVE;
                });
                return;
            }
            this._stopCardHold();
            this._stopCardEase();
            this._cardRect = null;
            this._cardSolid = false;
            card.hide();
            return;
        }
        this._stopCardHold();
        // CARD_PAD around the rows, as the lock screen's card around its prompt; a little
        // more above the avatar and under the field, which stand alone in the card's
        // width. Sideways it stays centred (on the rows; on the avatar and the name), as
        // wide as the farther side needs: the back button sits on the left of the entry only.
        const {rect: c, mid} = now;
        const half = Math.max(mid - c[0], c[2] - mid) + CARD_PAD;
        const pad = now.list ? CARD_PAD : PROMPT_PAD;
        const target = [mid - half, c[1] - pad, 2 * half, c[3] - c[1] + 2 * pad];
        // With the user list it is simply there. Around a prompt it comes up as GNOME
        // fades the prompt in, unless it stood already: then it only changes its shape.
        const prompt = this._dialog._authPrompt;
        if (now.list || prompt.opacity === 255)
            this._cardSolid = true;
        card.opacity = this._cardSolid ? 255 : prompt.opacity;
        const from = this._cardRect;
        const moved = this._cardList !== undefined && now.list !== this._cardList;
        this._cardList = now.list;
        if (!from || !card.visible) {
            this._stopCardEase();
            this._setCard(target);
            card.show();
            return;
        }
        if (target.every((v, i) => Math.abs(v - (this._cardTo ?? from)[i]) < 0.5))
            return;
        // From the user list to the prompt and back, a message appearing or going: to
        // its new shape, not in one jump.
        const long = moved || this._cardMoving;
        this._stopCardEase();
        // As GNOME's own animations: in one step where they are off, slower where they are slowed.
        if (this._settings.enable_animations === false) {
            this._setCard(target);
            return;
        }
        const ms = (long ? CARD_MOVE_MS : CARD_EASE_MS) * (this._settings.slow_down_factor || 1);
        this._cardMoving = long;
        this._cardTo = target;
        const start = GLib.get_monotonic_time();
        const step = () => {
            const t = Math.min(1, (GLib.get_monotonic_time() - start) / (ms * 1000));
            const k = 1 - (1 - t) ** 3;
            this._setCard(from.map((v, i) => v + (target[i] - v) * k));
            if (t < 1)
                return GLib.SOURCE_CONTINUE;
            this._cardEase = 0;
            this._cardTo = null;
            this._cardMoving = false;
            return GLib.SOURCE_REMOVE;
        };
        this._cardEase = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 16, () => this._safe(step) ?? GLib.SOURCE_REMOVE);
    }

    _setCard([x, y, w, h]) {
        const [ok, lx, ly] = this._layer.transform_stage_point(x, y);
        if (!ok)
            return;
        this._cardRect = [x, y, w, h];
        const r = Math.min(32, h / 2);
        this._card.place(lx, ly, w, h, [r, r, r, r], x, y);
    }

    _stopCardEase() {
        if (this._cardEase)
            GLib.source_remove(this._cardEase);
        this._cardEase = 0;
        this._cardTo = null;
        this._cardMoving = false;
    }

    _stopCardHold() {
        if (this._cardHold)
            GLib.source_remove(this._cardHold);
        this._cardHold = 0;
        this._cardHeld = false;
    }

    // ---- the stylesheet ----
    _writeStyle() {
        // Private to the greeter: the folder is 0700 and the file 0600.
        GLib.mkdir_with_parents(STYLE_DIR, 0o700);
        STYLE_FILE.replace_contents(new TextEncoder().encode(this._css), null, false,
            Gio.FileCreateFlags.PRIVATE | Gio.FileCreateFlags.REPLACE_DESTINATION, null);
        this._styleOn = true;
    }

    _loadStyle() {
        // Loading a stylesheet makes the theme context say it changed: only act when the
        // theme really is another one, or this would call itself forever.
        const theme = this._context.get_theme();
        if (this._loading || !this._styleOn || !theme || theme === this._theme)
            return;
        this._loading = true;
        try {
            // A theme reload copies our sheet into the new theme already; loading it twice
            // would leave an empty entry and break every later reload.
            if (!theme.get_custom_stylesheets().some(f => f?.equal(STYLE_FILE)))
                theme.load_stylesheet(STYLE_FILE);
            this._theme = theme;
        } finally {
            this._loading = false;
        }
    }

    _unloadStyle() {
        this._styleOn = false;
        // From the theme in use too: GNOME copies custom stylesheets into each new theme.
        for (const theme of new Set([this._theme, this._context?.get_theme()])) {
            try {
                theme?.unload_stylesheet(STYLE_FILE);
            } catch {}   // that theme is gone
        }
        this._theme = null;
        try {
            STYLE_FILE.delete(null);
        } catch {}   // already gone
    }

    // ---- taking it all away ----
    _takeDown() {
        if (this._later)
            global.compositor.get_laters().remove(this._later);
        this._later = 0;
        if (this._tickId)
            GLib.source_remove(this._tickId);
        this._tickId = 0;
        this._cancel?.cancel();
        this._cancel = null;
        this._stopPictureWait();
        this._pictureReady = false;
        this._stopCardEase();
        this._stopCardHold();
        this._cardRect = null;
        this._cardSolid = false;
        this._cardList = undefined;
        this._batterySignals?.clear();
        this._batterySignals = null;
        this._battery = null;
        this._drawn.clear();
        this._smallClockWatched = false;
        this._showSmallClock();
        this._unloadStyle();
        for (const m of this._managers ?? []) {
            try {
                m.destroy();
            } catch {}
        }
        this._managers = [];
        const layer = this._layer;
        this._layer = null;
        layer?.destroy();
        this._layer = this._picture = this._card = this._top = null;
        this._time = this._date = this._message = this._batteryChip = this._batteryRow = this._clockBox = null;
        this._sheets = [];
    }

    /** True while something of ours is on screen. */
    get drawn() {
        return Boolean(this._layer);
    }

    destroy() {
        if (this._ended)
            return;
        this._ended = true;
        this._stopWaiting();
        if (this._rebuildLater)
            global.compositor.get_laters().remove(this._rebuildLater);
        this._rebuildLater = 0;
        this._signals.clear();
        this._interface = null;
        this._verifierSignals.clear();
        this._verifier = null;
        this._takeDown();
    }
}
