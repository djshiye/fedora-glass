// Loads the real glass.js (the other tests get a stub of it, see shell-stubs.mjs) over
// a fake Clutter and Cogl, so a GlassPane's bookkeeping can be tested without a GPU.
// A test sets globalThis.fake (Actor, timeouts) and globalThis.global before loadGlass().
import {register} from 'node:module';

const EXTRA = {
    'system': 'export default {gc() {}};',
    'gi/Mtk': 'export default {Rectangle: class { constructor(p) { Object.assign(this, p); } }, RegionOverlap: {IN: 0, OUT: 1, PART: 2}};',
    'resource/config.js': "export const PACKAGE_VERSION = '50.0';",
    'gi/GObject': `export default {registerClass: (...a) => a[a.length - 1], signal_lookup: () => 0};`,
    // An actor and an effect that run their _init, as GObject does.
    'gi/Clutter': `
        const Base = globalThis.fake.Actor;
        class Effect { constructor(...a) { this._init(...a); } _init() {} queue_repaint() { this.repaints = (this.repaints ?? 0) + 1; } }
        export default {Actor: Base, Clone: Base, Effect, ActorBox: class {},
            EffectPaintFlags: {}, ActorNode: {}, BlurNode: {}, LayerNode: {}, PipelineNode: {}, TransformNode: {}};`,
    // A pipeline that remembers the uniforms it was given.
    'gi/Cogl': `
        class Pipeline {
            static new() { return new Pipeline(); }
            constructor() { this.uniforms = new Map(); this.names = []; }
            copy() { return new Pipeline(); }
            get_uniform_location(n) { let i = this.names.indexOf(n); if (i < 0) i = this.names.push(n) - 1; return i; }
            set_uniform_1f(i, v) { this.uniforms.set(this.names[i], v); (this.log ??= []).push([this.names[i], v]); }
            set_layer_null_texture() {} set_layer_filters() {} set_layer_wrap_mode() {}
            add_snippet() {} set_color() {}
        }
        export default {Pipeline, Color: class {}, Offscreen: {}, Texture2D: {},
            PipelineFilter: {LINEAR: 1}, PipelineWrapMode: {CLAMP_TO_EDGE: 1},
            SnippetHook: {FRAGMENT: 'f', VERTEX: 'v'},
            Snippet: {new: (hook, decls, post) => ({hook, decls, post, set_replace() {}})}};`,
};

export async function loadGlass() {
    // Hooks registered later run first, so these win over the stubs of shell-stubs.mjs.
    register('data:text/javascript,' + encodeURIComponent(`
const EXTRA = ${JSON.stringify(EXTRA)};
const pick = s => s === 'system' ? 'system' : s.startsWith('gi://') ? 'gi/' + s.slice(5)
    : s.endsWith('/misc/config.js') ? 'resource/config.js' : null;
export async function resolve(s, c, next) {
    const k = pick(s);
    return k && k in EXTRA ? {url: 'stub:glass-extra/' + k, shortCircuit: true} : next(s, c);
}
export async function load(u, c, next) {
    if (u.startsWith('stub:glass-extra/'))
        return {format: 'module', source: EXTRA[u.slice(17)], shortCircuit: true};
    return next(u, c);
}`));
    return import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/glass.js');
}
