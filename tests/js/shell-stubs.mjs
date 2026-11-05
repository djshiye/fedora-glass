// Loader hooks: run extension modules under Node with a fake GNOME Shell.
// gi:// and resource:// imports, and the GPU glass itself, become the stubs below.
const STUBS = {
    'gi/GLib': `export default {
        PRIORITY_HIGH: 0, PRIORITY_DEFAULT: 0, PRIORITY_DEFAULT_IDLE: 0, SOURCE_REMOVE: false, SOURCE_CONTINUE: true,
        timeout_add: (_p, ms, fn) => globalThis.fake.timeouts.add(ms, fn),
        idle_add: (_p, fn) => globalThis.fake.timeouts.add(0, fn),
        source_remove: id => globalThis.fake.timeouts.remove(id),
        get_monotonic_time: () => globalThis.fake.now?.() ?? 0,
        PRIORITY_LOW: 300,
        timeout_add_seconds: (_p, s, fn) => globalThis.fake.timeouts.add(s * 1000, fn),
        get_user_cache_dir: () => '/home/u/.cache',
        get_user_config_dir: () => '/home/u/.config',
        get_user_runtime_dir: () => '/run/user/1000',
        build_filenamev: parts => parts.join('/'),
        mkdir_with_parents: () => 0,
        FileSetContentsFlags: {CONSISTENT: 1},
        file_set_contents_full: (path, bytes, _flags, mode) => {
            globalThis.fake.fs.set(path, {text: new TextDecoder().decode(bytes), mode});
            return true;
        },
    };`,
    'gi/Cogl': "export default {SnippetHook: {FRAGMENT: 'fragment'}, Snippet: {new: (hook, decls, post) => ({hook, decls, post, set_replace(c) { this.replace = c; }})}};",
    'gi/Meta': 'export default {LaterType: {BEFORE_REDRAW: 0}};',
    'gi/Clutter': `export default {EVENT_PROPAGATE: false, ActorAlign: {START: 1},
        ActorBox: class { constructor(b) { Object.assign(this, b); } },
        Actor: globalThis.fake?.Actor ?? class {}, ShaderEffect: class {},
        BindCoordinate: {X: 0, Y: 1, WIDTH: 2, HEIGHT: 3},
        BindConstraint: class { constructor(p = {}) { Object.assign(this, {offset: 0}, p); } }};`,
    'gi/Shell': `export default {
        AppSystem: {get_default: () => globalThis.fake.appSystem},
        WindowTracker: {get_default: () => globalThis.fake.windowTracker},
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
            FileCreateFlags: {PRIVATE: 1, REPLACE_DESTINATION: 2},
            Settings: globalThis.fake?.Settings ?? class {},
        };`,
    'resource/signalTracker.js': 'export const debugGetSignalTrackers = () => globalThis.fake.signalTrackers;',
    'gi/St': `export default {Corner: {TOPLEFT: 0, TOPRIGHT: 1, BOTTOMRIGHT: 2, BOTTOMLEFT: 3},
        Settings: {get: () => globalThis.fake.stSettings},
        ThemeContext: {get_for_stage: () => globalThis.fake.themeContext},
        Widget: globalThis.fake?.Widget ?? class {}};`,
    'resource/main.js': `export const layoutManager = {uiGroup: globalThis.fake.ui, findMonitorForActor: () => null};
        export const messageTray = null;
        export const wm = globalThis.fake.wm;
        export const panel = {statusArea: {}};
        export const extensionManager = globalThis.fake.extensionManager;
        export const overview = globalThis.fake.overview;
        export const sessionMode = globalThis.fake.sessionMode;`,
    'resource/overviewControls.js': 'export const ControlsState = {HIDDEN: 0, WINDOW_PICKER: 1, APP_GRID: 2};',
    'resource/boxpointer.js': 'export class BoxPointer extends globalThis.fake.Actor {}',
    'glass': `export class GlassPane extends globalThis.fake.Actor {
        constructor(name) { super(); this.name = name; this.pad = 0; }
        setLook() { if (globalThis.fake.glassFails) throw new Error('forced test failure'); }
        setSources() {} setEdges() {} place() {} setMotion() {}
    }
    export const DEFAULT_LOOK = {};
    export function windowLanded() {}
    export function holdPanes(key) { globalThis.fake.holds?.push(['hold', key]); }
    export function releasePanes(key) { globalThis.fake.holds?.push(['release', key]); }`,
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
    if (url.startsWith('stub:'))
        return {format: 'module', source: STUBS[url.slice(5)], shortCircuit: true};
    return next(url, context);
}
