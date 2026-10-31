// Loader hooks: run extension modules under Node with a fake GNOME Shell.
// gi:// and resource:// imports, and the GPU glass itself, become the stubs below.
const STUBS = {
    'gi/GLib': `export default {
        PRIORITY_HIGH: 0, PRIORITY_DEFAULT: 0, PRIORITY_DEFAULT_IDLE: 0, SOURCE_REMOVE: false,
        timeout_add: (_p, ms, fn) => globalThis.fake.timeouts.add(ms, fn),
        idle_add: (_p, fn) => globalThis.fake.timeouts.add(0, fn),
        source_remove: id => globalThis.fake.timeouts.remove(id),
        get_monotonic_time: () => globalThis.fake.now?.() ?? 0,
    };`,
    'gi/Meta': 'export default {LaterType: {BEFORE_REDRAW: 0}};',
    'gi/Clutter': `export default {EVENT_PROPAGATE: false, ActorAlign: {START: 1},
        Actor: globalThis.fake.Actor ?? class {}};`,
    'gi/Shell': `export default {
        AppSystem: {get_default: () => globalThis.fake.appSystem},
        WindowTracker: {get_default: () => globalThis.fake.windowTracker},
    };`,
    'gi/Graphene': 'export default {Point3D: class {}};',
    'gi/Gio': 'export default {};',
    'gi/St': `export default {Corner: {TOPLEFT: 0, TOPRIGHT: 1, BOTTOMRIGHT: 2, BOTTOMLEFT: 3},
        Settings: {get: () => globalThis.fake.stSettings},
        Widget: globalThis.fake.Widget ?? class {}};`,
    'resource/main.js': `export const layoutManager = {uiGroup: globalThis.fake.ui, findMonitorForActor: () => null};
        export const messageTray = null;
        export const panel = {statusArea: {}};`,
    'resource/boxpointer.js': 'export class BoxPointer extends globalThis.fake.Actor {}',
    'glass': `export class GlassPane extends globalThis.fake.Actor {
        constructor(name) { super(); this.name = name; this.pad = 0; }
        setLook() { if (globalThis.fake.glassFails) throw new Error('forced test failure'); }
        setSources() {} setEdges() {} place() {} setMotion() {}
    }
    export const DEFAULT_LOOK = {};
    export function windowLanded() {}`,
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
