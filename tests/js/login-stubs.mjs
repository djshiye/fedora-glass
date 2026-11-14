// Loader hooks for the login screen add-on's tests, on top of shell-stubs.mjs (register()
// this one after it: it is asked first). A fake greeter: GNOME Shell's Main with a screen
// shield and its login dialog, St and Clutter actors that keep a real tree, GLib with the
// folders and timers the add-on uses, and the few Shell modules it imports.
const STUBS = {
    'gi/GLib': `export default {
        PRIORITY_HIGH: 0, PRIORITY_DEFAULT: 0, PRIORITY_LOW: 300, SOURCE_REMOVE: false, SOURCE_CONTINUE: true,
        timeout_add: (_p, ms, fn) => globalThis.fake.timeouts.add(ms, fn),
        timeout_add_seconds: (_p, s, fn) => globalThis.fake.timeouts.add(s * 1000, fn),
        idle_add: (_p, fn) => globalThis.fake.timeouts.add(0, fn),
        source_remove: id => globalThis.fake.timeouts.remove(id),
        get_monotonic_time: () => globalThis.fake.now ?? 0,
        get_user_state_dir: () => '/var/lib/gdm/seat0/state',
        get_user_runtime_dir: () => '/run/user/42',
        build_filenamev: parts => parts.join('/'),
        mkdir_with_parents: () => 0,
        FileSetContentsFlags: {NONE: 0, CONSISTENT: 1},
        file_get_contents: path => {
            const f = globalThis.fake.fs.get(path);
            if (!f) throw new Error('No such file');
            return [true, new TextEncoder().encode(f.text)];
        },
        file_set_contents_full: (path, bytes, flags, mode) => {
            if (globalThis.fake.readOnly) throw new Error('Read-only file system');
            globalThis.fake.fs.set(path, {text: new TextDecoder().decode(bytes), mode, flags});
            globalThis.fake.writes?.push(path);
            return true;
        },
    };`,
    'gi/Clutter': `export default {ActorAlign: {START: 1, CENTER: 2}, Orientation: {HORIZONTAL: 0, VERTICAL: 1},
        AnimationMode: {EASE_OUT_QUAD: 3},
        Actor: globalThis.fake.Actor, Clone: globalThis.fake.Clone, Text: class {}};`,
    'gi/St': `const A = globalThis.fake.Actor;
        export default {Widget: A, BoxLayout: A, Bin: A, Label: globalThis.fake.Label, Icon: globalThis.fake.Icon,
            Entry: globalThis.fake.Entry, Button: globalThis.fake.Button,
            Side: {TOP: 0, RIGHT: 1, BOTTOM: 2, LEFT: 3},
            Settings: {get: () => globalThis.fake.stSettings},
            ThemeContext: {get_for_stage: () => globalThis.fake.themeContext}};`,
    // A picture "decodes" when its text starts with PICTURE.
    'gi/GdkPixbuf': `export default {Pixbuf: {
        new_from_stream_at_scale_async: (stream, _w, _h, _k, _c, cb) => setTimeout(() => cb(null, {stream}), 0),
        new_from_stream_finish: r => {
            if (!r.stream.text.startsWith('PICTURE')) throw new Error('not an image');
            return {};
        }}};`,
    // Gio as in shell-stubs.mjs, with what the add-on adds: GSettings from fake.gsettings,
    // file URIs and reading a file in the background.
    'gi/Gio': `import Base from 'stub:gi/GioBase';
        const proto = Object.getPrototypeOf(Base.File.new_for_path('/'));
        proto.read_async = function (_p, _c, cb) { setTimeout(() => cb(this, {}), 0); };
        proto.read_finish = function () {
            const f = globalThis.fake.fs.get(this.path);
            if (!f) throw new Error('No such file');
            return {text: f.text, close() {}};
        };
        export default {...Base,
            File: {...Base.File, new_for_uri: u => Base.File.new_for_path(u.replace(/^file:\\/\\//, ''))},
            Settings: class {
                constructor({schema_id}) { this.schema = schema_id; this._h = new Map(); this._n = 1;
                    (globalThis.fake.settingsLive ??= new Set()).add(this); }
                get_string(k) { return globalThis.fake.gsettings?.[this.schema]?.[k] ?? ''; }
                get_double(k) {
                    const v = globalThis.fake.gsettings?.[this.schema]?.[k];
                    if (typeof v !== 'number') throw new Error('no such key ' + k);
                    return v;
                }
                connect(s, fn) { this._h.set(this._n, [s, fn]); return this._n++; }
                disconnect(id) { if (!this._h.delete(id)) throw new Error('no handler ' + id); }
                // As GSettings: says 'changed::key' to whoever listens to that key.
                emit(s) { for (const [k, fn] of [...this._h.values()]) if (k === s) fn(this, s.split('::')[1]); }
                get listeners() { return this._h.size; }
            }};`,
    // Live: each test makes a fresh greeter (globalThis.fake), and Main follows it.
    'resource/main.js': `const live = k => new Proxy({}, {get: (_t, p) => globalThis.fake[k][p],
            set: (_t, p, v) => { globalThis.fake[k][p] = v; return true; }});
        export const layoutManager = live('layoutManager');
        export const panel = live('panel');
        export const screenShield = live('screenShield');`,
    'resource/extension.js': 'export class Extension { constructor(m) { this.metadata = m; } }',
    // Says 'loaded' a moment after it is made, as GNOME's does (unless fake.bgNeverLoads).
    'resource/background.js': `export class BackgroundManager {
        constructor(p) { this.p = p; this.actor = new globalThis.fake.Actor({name: 'bg'}); p.container.add_child(this.actor);
            this._h = new Map(); this._n = 1;
            globalThis.fake.bgManagers.add(this);
            if (!globalThis.fake.bgNeverLoads) setTimeout(() => this.emit('loaded'), 0); }
        connect(s, fn) { this._h.set(this._n, [s, fn]); return this._n++; }
        disconnect(id) { if (!this._h.delete(id)) throw new Error('no handler ' + id); }
        emit(s) { for (const [k, fn] of [...this._h.values()]) if (k === s) fn(this); }
        destroy() { this.actor.destroy(); globalThis.fake.bgManagers.delete(this); } }`,
    'resource/dateUtils.js': `export const formatTime = () => '09:41';
        export const formatDateWithCFormatString = (_d, f) => 'Friday ' + f;`,
    'gettext': 'export const dgettext = (_d, s) => s;',
};

// Modules the package copies from the desktop extension into the add-on's folder.
const SHARED = new URL('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/', import.meta.url);

export async function resolve(specifier, context, next) {
    if (specifier === 'stub:gi/GioBase')
        return {url: specifier, shortCircuit: true};
    if (context.parentURL?.includes('/login-extension/') && ['./locklook.js', './holdstate.js', './glsl.js'].includes(specifier))
        return {url: new URL(specifier.slice(2), SHARED).href, shortCircuit: true};
    if (specifier === 'gettext')
        return {url: 'stub:gettext', shortCircuit: true};
    if (specifier.startsWith('resource://') && specifier.split('/').pop() in {'extension.js': 1, 'dateUtils.js': 1})
        return {url: `stub:resource/${specifier.split('/').pop()}`, shortCircuit: true};
    return next(specifier, context);
}

export async function load(url, context, next) {
    if (url === 'stub:gi/GioBase')
        return next('stub:gi/Gio', context);
    if (url.startsWith('stub:') && url.slice(5) in STUBS)
        return {format: 'module', source: STUBS[url.slice(5)], shortCircuit: true};
    return next(url, context);
}
