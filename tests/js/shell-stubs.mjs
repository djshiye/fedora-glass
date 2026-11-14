// Loader hooks: run extension modules under Node with a fake GNOME Shell.
// gi:// and resource:// imports, and the GPU glass itself, become the stubs below.
const STUBS = {
    'gi/GLib': `export default {
        PRIORITY_HIGH: 0, PRIORITY_DEFAULT: 0, PRIORITY_DEFAULT_IDLE: 0, SOURCE_REMOVE: false, SOURCE_CONTINUE: true,
        timeout_add: (_p, ms, fn) => globalThis.fake.timeouts.add(ms, fn),
        idle_add: (_p, fn) => globalThis.fake.timeouts.add(0, fn),
        source_remove: id => globalThis.fake.timeouts.remove(id),
        get_monotonic_time: () => globalThis.fake.now?.() ?? 0,
        get_real_time: () => globalThis.fake.realNow?.() ?? globalThis.fake.now?.() ?? 0,
        PRIORITY_LOW: 300,
        timeout_add_seconds: (_p, s, fn) => globalThis.fake.timeouts.add(s * 1000, fn),
        get_language_names: () => globalThis.fake?.languages ?? ['C'],
        get_user_cache_dir: () => '/home/u/.cache',
        get_user_config_dir: () => '/home/u/.config',
        get_user_runtime_dir: () => '/run/user/1000',
        build_filenamev: parts => parts.join('/'),
        mkdir_with_parents: () => 0,
        FileSetContentsFlags: {NONE: 0, CONSISTENT: 1},
        FileTest: {EXISTS: 16},
        file_test: path => globalThis.fake.fs?.has(path) ?? false,
        file_set_contents_full: (path, bytes, flags, mode) => {
            globalThis.fake.fs.set(path, {text: new TextDecoder().decode(bytes), mode, flags});
            return true;
        },
    };`,
    'gi/Cogl': "export default {SnippetHook: {FRAGMENT: 'fragment', VERTEX: 'vertex'}, Snippet: {new: (hook, decls, post) => ({hook, decls, post, set_replace(c) { this.replace = c; }})}};",
    'gi/Meta': `export default {LaterType: {BEFORE_REDRAW: 0},
        WindowType: {NORMAL: 0, DIALOG: 1, MODAL_DIALOG: 2, UTILITY: 3, SPLASHSCREEN: 4}};`,
    'gi/Clutter': `export default {EVENT_PROPAGATE: false, ActorAlign: {START: 1},
        EventType: {MOTION: 3, ENTER: 4, LEAVE: 5, BUTTON_PRESS: 6},
        Event: {add_filter: (_stage, fn) => globalThis.fake.filters.add(fn),
            remove_filter: id => globalThis.fake.filters.remove(id)},
        ActorBox: class { constructor(b) { Object.assign(this, b); } },
        Actor: globalThis.fake?.Actor ?? class {}, ShaderEffect: class {},
        BindCoordinate: {X: 0, Y: 1, WIDTH: 2, HEIGHT: 3, ALL: 4}, RotateAxis: {Z_AXIS: 2},
        Clone: globalThis.fake?.Actor ?? class {}, Effect: class {},
        BindConstraint: class { constructor(p = {}) { Object.assign(this, {offset: 0}, p); } }};`,
    'gi/Shell': `export default {
        AppSystem: {get_default: () => globalThis.fake.appSystem},
        WindowTracker: {get_default: () => globalThis.fake.windowTracker},
    };`,
    'gi/GObject': `export default {
        registerClass: (...a) => a[a.length - 1],
        signal_handler_find: (obj, m) => globalThis.fake.gobject.find(obj, m),
        signal_handler_block: (obj, id) => globalThis.fake.gobject.block(obj, id),
        signal_handler_unblock: (obj, id) => globalThis.fake.gobject.unblock(obj, id),
    };`,
    'gi/Graphene': 'export default {Point3D: class {}};',
    'gi/Gio': `
        const fs = () => globalThis.fake.fs;
        class File {
            constructor(path) { this.path = path; }
            get_path() { return this.path; }
            get_basename() { return this.path.split('/').pop(); }
            get_child(name) { return new File(this.path + '/' + name); }
            query_info() {
                const f = fs().get(this.path);
                if (!f) throw new Error('No such file');
                return {get_file_type: () => 1, get_size: () => f.text.length};
            }
            load_contents() { return [true, new TextEncoder().encode(fs().get(this.path).text)]; }
            replace_contents(bytes, _etag, _backup, flags) {
                fs().set(this.path, {text: new TextDecoder().decode(bytes), flags});
                return [true, null];
            }
            delete() {
                if (!fs().delete(this.path)) throw new Error('No such file');
                return true;
            }
            equal(other) { return other?.path === this.path; }
            move(dest) {
                const f = fs().get(this.path);
                if (!f) throw new Error('No such file');
                fs().delete(this.path);
                fs().set(dest.path, {...f, moved: true});
                return true;
            }
            monitor_directory() {
                const m = {handlers: [], connect(_s, fn) { this.handlers.push(fn); return this.handlers.length; },
                    disconnect() { this.handlers = []; }, cancel() { this.cancelled = true; }};
                globalThis.fake.monitors?.push([this.path, m]);
                return m;
            }
        }
        export default {
            File: {new_for_path: p => new File(p)},
            FileQueryInfoFlags: {NOFOLLOW_SYMLINKS: 1}, FileType: {REGULAR: 1}, FileMonitorFlags: {WATCH_MOVES: 8},
            FileCreateFlags: {PRIVATE: 1, REPLACE_DESTINATION: 2}, FileCopyFlags: {OVERWRITE: 1},
            Settings: globalThis.fake?.Settings ?? class {},
            // D-Bus proxies: a test that needs them sets globalThis.fake.dbus (see power.test.mjs);
            // without it no service answers, as on a PC without them.
            BusType: {SYSTEM: 1, SESSION: 2}, DBusProxyFlags: {NONE: 0, DO_NOT_AUTO_START: 4},
            DBusProxy: {
                new_for_bus: (...a) => globalThis.fake.dbus?.new_for_bus(...a),
                new_for_bus_finish: res => {
                    if (res?.error) throw res.error;
                    return res.proxy;
                },
            },
            FileIcon: class { constructor(p) { this.file = p.file; } },
            Cancellable: class { cancel() { this._c = true; } is_cancelled() { return !!this._c; } },
        };`,
    'resource/signalTracker.js': 'export const debugGetSignalTrackers = () => globalThis.fake.signalTrackers;',
    'gi/St': `export default {Corner: {TOPLEFT: 0, TOPRIGHT: 1, BOTTOMRIGHT: 2, BOTTOMLEFT: 3},
        Settings: {get: () => globalThis.fake.stSettings},
        ThemeContext: {get_for_stage: () => globalThis.fake.themeContext},
        Widget: globalThis.fake?.Widget ?? class {}};`,
    'resource/main.js': `export const layoutManager = globalThis.fake.layoutManager ??
            {uiGroup: globalThis.fake.ui, findMonitorForActor: () => null};
        export const messageTray = null;
        export const wm = globalThis.fake.wm;
        export const panel = globalThis.fake.panel ?? {statusArea: {}};
        export const extensionManager = globalThis.fake.extensionManager;
        export const overview = globalThis.fake.overview;
        export const sessionMode = globalThis.fake.sessionMode;
        export const uiGroup = globalThis.fake.uiGroup;
        export const screenshotUI = globalThis.fake.screenshotUI;`,
    'resource/quickSettings.js': `export const QuickToggle = globalThis.fake.QuickToggle ?? class {};
        export const SystemIndicator = globalThis.fake.SystemIndicator ?? class {};`,
    'resource/background.js': 'export const BackgroundManager = globalThis.fake.BackgroundManager ?? class {};',
    'resource/fileUtils.js': 'export const loadInterfaceXML = () => "";',
    'resource/overviewControls.js': 'export const ControlsState = {HIDDEN: 0, WINDOW_PICKER: 1, APP_GRID: 2};',
    'resource/boxpointer.js': 'export class BoxPointer extends globalThis.fake.Actor {}',
    'resource/switcherPopup.js': 'export class SwitcherPopup extends globalThis.fake.Actor {}',
    'resource/messageList.js': 'export const NotificationMessageGroup = globalThis.fake.NotificationMessageGroup ?? class {};',
    'glass': `export class GlassPane extends globalThis.fake.Actor {
        constructor(name) { super(); this.name = name; this.pad = 0; }
        setLook() { if (globalThis.fake.glassFails) throw new Error('forced test failure'); }
        setSources() {} setEdges() {} place() {} setMotion() {} setKeep() {} setPart() {}
    }
    export const DEFAULT_LOOK = {};
    export function windowLanded() {}
    export const copying = {pane: null};
    export function holdPanes(key) { globalThis.fake.holds?.push(['hold', key]); }
    export function releasePanes(key) { globalThis.fake.holds?.push(['release', key]); }
    export function freezeSource() {} export function thawSource() {}
    export function moving() {} export function stopMoving() {} export function releaseAllPanes() {}
    export function setQuality(l) { globalThis.fake.quality = l; }
    export function setFrost(f, k) { (globalThis.fake.frosts ??= []).push([f, k]); }
    export function getFrost() { return {frost: 0, flakes: globalThis.fake.flakes ?? 0, blur: 0}; }
    export function liquidNow(l) { return l * (1 - 0.75 * (globalThis.fake.flakes ?? 0)); }
    export function glassRenders() { return globalThis.fake.renders ?? 0; }
    export function redrawAllPanes() {}
    export function shownPanes() { return globalThis.fake.shown ?? 0; }`,
};

export async function resolve(specifier, context, next) {
    if (specifier.startsWith('gi://'))
        return {url: `stub:gi/${specifier.slice(5)}`, shortCircuit: true};
    if (specifier.startsWith('resource://'))
        return {url: `stub:resource/${specifier.split('/').pop()}`, shortCircuit: true};
    if (specifier === './glass.js')
        return {url: 'stub:glass', shortCircuit: true};
    return next(specifier, context);
}

export async function load(url, context, next) {
    if (url.startsWith('stub:')) {
        if (!(url.slice(5) in STUBS))
            throw new Error(`no stub for ${url}`);
        return {format: 'module', source: STUBS[url.slice(5)], shortCircuit: true};
    }
    return next(url, context);
}
