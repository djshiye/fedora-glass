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
        export default {Actor: Base, Clone: Base, Effect, OffscreenEffect: Effect, ActorBox: class {},
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

// With paint: true, a Clutter and Cogl that can be painted with, counting each native
// object made (fake.made: {ActorBox, Color, Rectangle, PipelineNode, ...}).
const PAINT = {
    'gi/Mtk': `const made = n => (globalThis.fake.made[n] = (globalThis.fake.made[n] ?? 0) + 1);
        export default {Rectangle: class { constructor(p) { made('Rectangle'); Object.assign(this, p); } },
            RegionOverlap: {IN: 0, OUT: 1, PART: 2}};`,
    'gi/Graphene': `const made = n => (globalThis.fake.made[n] = (globalThis.fake.made[n] ?? 0) + 1);
        export default {Point3D: class { constructor() { made('Point3D'); } },
            Matrix: class { constructor() { made('Matrix'); } init_translate() {} init_scale() {} scale() {} }};`,
    'gi/Clutter': `
        const made = n => (globalThis.fake.made[n] = (globalThis.fake.made[n] ?? 0) + 1);
        const Base = globalThis.fake.Actor;
        class Effect { constructor(...a) { this.enabled = true; this._init(...a); } _init() {}
            queue_repaint() { this.repaints = (this.repaints ?? 0) + 1; } }
        const node = n => (...a) => { made(n); return {kind: n, args: a, kids: [], add_child(c) { this.kids.push(c); },
            add_rectangle() {}, add_texture_rectangle(...r) { this.rect = r; }}; };
        export default {Actor: Base, Clone: Base, Effect, OffscreenEffect: Effect,
            ActorBox: class { constructor(b) { made('ActorBox'); Object.assign(this, b); } },
            EffectPaintFlags: {ACTOR_DIRTY: 1, BYPASS_EFFECT: 2},
            ActorNode: {new: node('ActorNode')}, BlurNode: {new: node('BlurNode')},
            LayerNode: {new_to_framebuffer: node('LayerNode')}, PipelineNode: {new: node('PipelineNode')},
            TransformNode: {new: node('TransformNode')}};`,
    'gi/Cogl': `
        const made = n => (globalThis.fake.made[n] = (globalThis.fake.made[n] ?? 0) + 1);
        class Pipeline {
            static new() { return new Pipeline(); }
            constructor() { this.uniforms = new Map(); this.names = []; }
            copy() { return new Pipeline(); }
            get_uniform_location(n) { let i = this.names.indexOf(n); if (i < 0) i = this.names.push(n) - 1; return i; }
            set_uniform_1f(i, v) { this.uniforms.set(this.names[i], v); }
            set_uniform_float() {} set_layer_texture(_i, t) { this.tex = t; }
            set_layer_null_texture() { this.tex = null; } set_layer_filters() {} set_layer_wrap_mode() {}
            add_snippet() {} set_color(c) { this.color = c; }
        }
        export default {Pipeline, Color: class { constructor(c) { made('Color'); Object.assign(this, c); } },
            Offscreen: {new_with_texture: tex => ({tex, allocate() {}, set_projection_matrix() {}})},
            Texture2D: {new_with_size: (_c, w, h) => { made('Texture2D'); return {w, h, set_premultiplied() {}}; }},
            PipelineFilter: {LINEAR: 1}, PipelineWrapMode: {CLAMP_TO_EDGE: 1},
            SnippetHook: {FRAGMENT: 'f', VERTEX: 'v'},
            Snippet: {new: (hook, decls, post) => ({hook, decls, post, set_replace() {}})}};`,
};

export async function loadGlass({paint = false} = {}) {
    if (paint)
        Object.assign(EXTRA, PAINT);
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
