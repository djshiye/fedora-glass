// A fake greeter for the login screen add-on's tests: an actor tree that keeps parents and
// children, signals, timers and laters run by hand, a file system in a Map, and GNOME's
// lock dialog group with a login dialog in it (the parts the add-on relies on).
import {register} from 'node:module';

export const TOKEN = '0123456789abcdef0123456789abcdef';
export const LOOK_PATH = '/etc/fedora-glass/login/look.json';
export const NOTE_PATH = '/var/lib/gdm/seat0/state/fedora-glass-login/health.json';
export const CSS_PATH = '/run/user/42/fedora-glass-login/login.css';
export const BOOT = '11111111-2222-3333-4444-555555555555';
export const RUN_PATH = '/var/lib/gdm/seat0/state/fedora-glass-login/run.json';
export const PICTURE_PATH = '/etc/fedora-glass/login/picture.png';
export const LOOK = Object.freeze({version: 1, token: TOKEN, accent: '#3584e4', tint: '#1e1e2a', tint_amount: 0.2,
    frost: 0.35, blur: 60, dim: 0.28, card: true, clock: 'bold', picture: 'wallpaper', fit: 'zoom', battery: true,
    message: 'Hello'});

class Emitter {
    constructor() {
        this._handlers = new Map();
        this._next = 1;
    }

    connect(signal, fn) {
        const id = this._next++;
        this._handlers.set(id, [signal, fn]);
        return id;
    }

    disconnect(id) {
        if (!this._handlers.delete(id))
            throw new Error(`no handler ${id}`);
    }

    emit(signal, ...args) {
        for (const [s, fn] of [...this._handlers.values()]) {
            if (s === signal)
                fn(this, ...args);
        }
    }

    handlerCount() {
        return this._handlers.size;
    }
}

export class Actor extends Emitter {
    constructor(p = {}) {
        super();
        Object.assign(this, {name: '', reactive: false, can_focus: false, opacity: 255, x: 0, y: 0, width: 0, height: 0,
            style: null, style_class: null, margin_top: 0, margin_bottom: 0}, p);
        this._visible = p.visible ?? true;
        this._children = [];
        this._parent = null;
    }

    get visible() {
        return this._visible;
    }

    set visible(v) {
        if (v === this._visible)
            return;
        this._visible = v;
        this.emit('notify::visible');
    }

    // As Clutter: laid out (shown, in something, and not waiting for a new layout).
    has_allocation() {
        return this._visible && Boolean(this._parent) && !this.needsLayout;
    }

    get mapped() {
        return this._visible && !this.destroyed && (this._parent ? this._parent.mapped : this._root === true);
    }

    show() {
        this.visible = true;
    }

    hide() {
        this.visible = false;
    }

    add_child(c) {
        this.insert_child_at_index(c, this._children.length);
    }

    insert_child_above(c, sibling) {
        const i = this._children.indexOf(sibling);
        this.insert_child_at_index(c, i < 0 ? this._children.length : i + 1);
    }

    set_clip(x, y, w, h) {
        this._clip = [x, y, w, h];
    }

    get has_clip() {
        return Boolean(this._clip);
    }

    get_clip() {
        return this._clip;
    }

    insert_child_at_index(c, i) {
        c._parent = this;
        this._children.splice(i, 0, c);
        this.emit('child-added', c);
    }

    get_children() {
        return [...this._children];
    }

    get_first_child() {
        return this._children[0] ?? null;
    }

    get_n_children() {
        return this._children.length;
    }

    get_parent() {
        return this._parent;
    }

    // As Clutter: 'destroy' is said first, while the children still stand, then they go.
    destroy() {
        if (this.destroyed || this._destroying)
            return;
        this._destroying = true;
        this.emit('destroy');
        for (const c of [...this._children])
            c.destroy();
        this.destroyed = true;
        if (this._parent)
            this._parent._children = this._parent._children.filter(x => x !== this);
        this._parent = null;
    }

    set_position(x, y) {
        [this.x, this.y] = [x, y];
    }

    // GNOME's ease() as with animations off: there at once. What was asked is kept in `eased`.
    ease(p) {
        const {duration, mode: _mode, onComplete, ...to} = p;
        this.eased = {duration, ...to};
        Object.assign(this, to);
        onComplete?.();
    }

    // As Clutter: a box is as wide as the widest child that shows (nothing shows: 0),
    // and what holds text says it is 0 px tall when asked at no width.
    get_preferred_width() {
        if (this.prefW === undefined && this._children.length)
            return [0, Math.max(0, ...this._children.filter(c => c.visible).map(c => c.get_preferred_width(-1)[1]))];
        return [0, this.prefW ?? 400];
    }

    get_preferred_height(forWidth) {
        return [0, forWidth === 0 ? 0 : this.prefH ?? 100];
    }

    // As St: the room a style keeps inside the widget, by side (St.Side: top 0 ... left 3).
    // `pad` is [top, bottom] in px. Nothing here says what it paints.
    // `themeHeight`: a fixed height the theme gives it (stage px), none (-1) unless set.
    get_theme_node() {
        const pad = side => (side === 0 ? this.pad?.[0] : side === 2 ? this.pad?.[1] : 0) ?? 0;
        return {get_padding: pad, get_border_width: () => 0, get_height: () => this.themeHeight ?? -1};
    }

    get_transformed_position() {
        return [this.x, this.y];
    }

    get_transformed_size() {
        return [this.width, this.height];
    }

    transform_stage_point(x, y) {
        return [true, x, y];
    }

    /** Every actor under this one, itself included. */
    all() {
        return [this, ...this._children.flatMap(c => c.all())];
    }
}

export class Label extends Actor {
    constructor(p = {}) {
        super({text: '', ...p});
        this.clutter_text = {};
    }

    set text(t) {
        this._text = t;
        this.emit('notify::text');
    }

    get text() {
        return this._text;
    }
}
export class Icon extends Actor {}
export class Entry extends Actor {}
export class Button extends Actor {}
export class Clone extends Actor {}

export function makeTimers() {
    const t = new Map();
    let next = 1;
    let clock = 0;
    return {
        list: t,
        get clock() {
            return clock;
        },
        add(ms, fn) {
            const id = next++;
            t.set(id, {ms, fn, at: clock + ms});
            return id;
        },
        remove(id) {
            t.delete(id);
        },
        /** Runs the timers due within ms (each once; a repeat is added again). No time passes. */
        run(ms = Infinity) {
            for (const [id, {ms: due, fn}] of [...t]) {
                if (due <= ms && t.has(id)) {
                    t.delete(id);
                    if (fn())
                        t.set(id, {ms: due, fn, at: clock + due});
                }
            }
        },
        /**
         * Lets ms of time pass: each timer runs when it is due, the earlier one first (one
         * added meanwhile too, a repeat again and again), as on a real clock.
         */
        advance(ms) {
            const end = clock + ms;
            for (let n = 0; n < 100000; n++) {
                let first = null;
                for (const [id, e] of t) {
                    if (e.at <= end && (!first || e.at < first[1].at))
                        first = [id, e];
                }
                if (!first)
                    break;
                const [id, e] = first;
                clock = Math.max(clock, e.at);
                t.delete(id);
                if (e.fn())
                    t.set(id, {...e, at: clock + Math.max(e.ms, 1)});
            }
            clock = end;
        },
    };
}

// What GNOME's prompt shows with its own theme (as the add-on's promptPlace counts it, px at
// the usual text size and per unit of text scale), the room it keeps under the field, and
// the fixed height GNOME 51.1's theme gives it.
const PROMPT = {
    '50': {fixed: 144, text: 92, room: 67},
    '51.0': {fixed: 144, text: 96, room: 74},
    '51.1': {fixed: 153, text: 96, room: 74, height: 550},
};

/**
 * A fresh greeter. dialog: false = the login dialog is not made yet. gnome: whose login
 * dialog, '51.0' (a fixed top for the prompt), '50' (centred: also gnome50) or '51.1'
 * (centred by the fixed height its theme gives the prompt, 50 px lower).
 *
 * layout: the prompt is laid out as that GNOME does, each time a stylesheet comes or goes
 * (and fake.relayout()), with the margin our stylesheet asks for; otherwise it stays where
 * it is made. foreign: a theme of someone else's on top of GNOME's (a smaller avatar, a
 * bigger name, a taller field and more room for messages). ignoreMargin: a layout that
 * takes no notice of the margin (St still puts it on the prompt).
 */
export function makeGreeter({dialog = true, look = LOOK, note = null, highContrast = false, gnome50 = false,
    gnome = gnome50 ? '50' : '51.0', layout: laidOut = false, foreign = false, ignoreMargin = false} = {}) {
    const stage = new Actor({name: 'stage', width: 1920, height: 1080});
    stage._root = true;
    const laters = new Map();
    let nextLater = 1;
    const fs = new Map();
    const fake = {
        Actor, Label, Icon, Entry, Button, Clone, fs, writes: [],
        gsettings: {
            'org.gnome.desktop.background': {'picture-uri': `file://${PICTURE_PATH}`,
                'picture-uri-dark': `file://${PICTURE_PATH}`, 'picture-options': 'zoom'},
            'org.gnome.desktop.interface': {'color-scheme': 'prefer-dark', 'text-scaling-factor': 1},
        }, bgManagers: new Set(), timeouts: makeTimers(), readOnly: false,
        laters: {
            add(_t, fn) {
                const id = nextLater++;
                laters.set(id, fn);
                return id;
            },
            remove(id) {
                laters.delete(id);
            },
            run() {
                for (let i = 0; i < 10 && laters.size; i++) {
                    for (const [id, fn] of [...laters]) {
                        laters.delete(id);
                        fn();
                    }
                }
            },
        },
    };
    if (look)
        fs.set(LOOK_PATH, {text: typeof look === 'string' ? look : JSON.stringify(look)});
    if (note)
        fs.set(NOTE_PATH, {text: JSON.stringify(note)});
    fs.set('/proc/sys/kernel/random/boot_id', {text: `${BOOT}\n`});
    fs.set(PICTURE_PATH, {text: 'PICTURE (a stand-in for a PNG)'});
    const settings = new Emitter();
    settings.high_contrast = highContrast;
    fake.stSettings = settings;
    const theme = {sheets: [], loads: 0, load_stylesheet(f) {
        this.sheets.push(f.path);
        this.loads++;
        fake.relayout?.();
        return true;
    }, unload_stylesheet(f) {
        this.sheets = this.sheets.filter(p => p !== f.path);
        fake.relayout?.();
    }, get_custom_stylesheets() {
        return this.sheets.map(p => ({path: p, equal: o => o?.path === p}));
    }};
    const ctx = new Emitter();
    ctx.theme = theme;
    ctx.scale_factor = 1;
    ctx.get_theme = () => ctx.theme;
    fake.themeContext = ctx;
    const layout = new Emitter();
    Object.assign(layout, {monitors: [{x: 0, y: 0, width: 1920, height: 1080}], panelBox: {height: 32}});
    Object.defineProperty(layout, 'primaryMonitor', {get: () => layout.monitors[0]});
    fake.layoutManager = layout;
    const clock = new Actor({name: 'panel-clock'});
    fake.panel = {statusArea: {dateMenu: {container: clock}}};
    const shield = new Actor({name: 'shield'});
    const group = new Actor({name: 'lockDialogGroup', reactive: true, can_focus: true, width: 1920, height: 1080});
    stage.add_child(shield);
    shield.add_child(group);
    fake.screenShield = {_lockDialogGroup: group, _dialog: null};
    fake.makeDialog = () => {
        const d = new Actor({name: 'LoginDialog', reactive: true});
        group.add_child(d);
        const verifier = new Emitter();
        // GNOME's prompt keeps room under the entry for messages: 300 px tall, content 180.
        const prompt = new Actor({name: 'AuthPrompt', visible: false, x: 800, y: 400, width: 320, height: 300});
        prompt._userVerifier = verifier;
        prompt._userWell = new Actor({name: 'userWell', x: 800, y: 400, width: 320, height: 120});
        prompt._userWell.add_child(new Icon({name: 'avatar', x: 896, y: 400, width: 128, height: 128}));
        prompt._inputWell = new Actor({name: 'inputWell', x: 800, y: 540, width: 320, height: 160});
        prompt._mainBox = new Actor({name: 'mainBox', x: 800, y: 540, width: 320, height: 40});
        prompt.cancelButton = new Button({name: 'cancel', x: 800, y: 540, width: 40, height: 40});
        prompt._entry = new Entry({name: 'entry', x: 850, y: 540, width: 270, height: 40});
        prompt._message = new Label({name: 'message', x: 800, y: 600, width: 320, height: 40});
        prompt._mainBox.add_child(prompt.cancelButton);
        prompt._mainBox.add_child(prompt._entry);
        prompt._inputWell.add_child(prompt._mainBox);
        prompt._inputWell.add_child(prompt._message);
        prompt.add_child(prompt._userWell);
        prompt.add_child(prompt._inputWell);
        // The user list: one row, 360 x 80 at (780, 500), and "Not listed?" 6 px under it.
        Object.assign(d, {_authPrompt: prompt, _userSelectionBox: new Actor({name: 'userSelection'}),
            _userList: new Actor({name: 'userList', x: 780, y: 500, width: 360, height: 80}),
            _notListedButton: new Button({name: 'notListed', x: 780, y: 586, width: 360, height: 30}),
            _bannerView: null});
        if (gnome === '51.0')
            d._getFixedTopActorAllocation = () => null;
        if (PROMPT[gnome].height)
            prompt.themeHeight = PROMPT[gnome].height * ctx.scale_factor;
        d._userList._box = new Actor();
        d._userList._box.add_child(new Actor({name: 'dino', x: 780, y: 500, width: 360, height: 80}));
        d._userList.add_child(d._userList._box);
        d.add_child(d._userSelectionBox);
        d._userSelectionBox.add_child(d._userList);
        d._userSelectionBox.add_child(d._notListedButton);
        d.add_child(prompt);
        fake.screenShield._dialog = d;
        if (laidOut)
            fake.relayout = () => layOut(fake, d, gnome, {foreign, ignoreMargin});
        return d;
    };
    if (dialog)
        fake.makeDialog();
    globalThis.fake = fake;
    globalThis.global = {
        stage: Object.assign(stage, {get_size: () => [1920, 1080]}),
        compositor: {get_laters: () => fake.laters},
        ...(() => {
            const e = new Emitter();
            return {connect: (s, f) => e.connect(s, f), disconnect: id => e.disconnect(id), emitShell: s => e.emit(s)};
        })(),
    };
    return fake;
}

/**
 * Where GNOME puts its prompt and what is in it, with the margin of our stylesheet (when it
 * is loaded), as loginDialog.js of that GNOME does: 51.0 from a fixed top 275 px above the
 * middle; 50 centred by its natural height, the margin included; 51.1 centred by the theme's
 * fixed height (or more, should what it shows need more) and the margin, 50 px lower. GNOME
 * rounds down; St puts the margin on the actor, and Clutter lays it out under the margin.
 */
function layOut(fake, d, gnome, {foreign, ignoreMargin}) {
    const prompt = d._authPrompt, g = PROMPT[gnome], s = fake.themeContext.scale_factor;
    const ts = fake.gsettings['org.gnome.desktop.interface']['text-scaling-factor'] ?? 1;
    const m = fake.layoutManager.primaryMonitor;
    const mid = m.y + m.height / 2;
    const css = fake.themeContext.theme.sheets.includes(CSS_PATH) ? fake.fs.get(CSS_PATH)?.text ?? '' : '';
    const ours = /prompt-layout {[^}]*margin-top: (\d+)px;/.exec(css);
    const M = (ours ? Number(ours[1]) : gnome === '51.0' ? 80 : 0) * s;
    const placed = ignoreMargin ? 0 : M;
    // From the avatar's top to the field's bottom: the avatar, the name, the field's row.
    const avatar = (foreign ? 112 : 128) * s, field = (foreign ? 46 : 40) * s;
    const content = (Math.round(g.fixed + g.text * ts) + (foreign ? 26 - 16 + 6 : 0)) * s;
    const room = (g.room * ts + (foreign ? 30 : 0)) * s;
    const box = Math.max((g.height ?? 0) * s, content + room);
    const top = gnome === '51.0' ? Math.floor(mid - 275) + placed
        : Math.floor(mid - (placed + box) / 2) + (gnome === '51.1' ? 50 : 0) + placed;
    const set = (a, y, height) => Object.assign(a, {y, height});
    prompt.margin_top = M;
    set(prompt, top, box);
    set(prompt._userWell, top, content - field - 16 * s);
    set(prompt._userWell.get_first_child(), top, avatar);
    set(prompt._inputWell, top + content - field, field + room);
    for (const a of [prompt._mainBox, prompt.cancelButton, prompt._entry])
        set(a, top + content - field, field);
    set(prompt._message, top + content + 8 * s, 40 * s);
    prompt.needsLayout = false;
    prompt.emit('notify::allocation');
}

/** Ours: the actors named fedora-glass-* anywhere under the stage. */
export function ours() {
    return globalThis.global.stage.all().filter(a => /^fedora-glass/.test(a.name ?? ''));
}

export function note() {
    const f = globalThis.fake.fs.get(NOTE_PATH);
    return f ? JSON.parse(f.text) : null;
}

let registered = false;
/** Installs the loader hooks; call before importing any add-on module. */
export function registerStubs() {
    if (registered)
        return;
    registered = true;
    register('./login-stubs.mjs', import.meta.url);
}
