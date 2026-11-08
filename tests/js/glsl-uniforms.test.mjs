// Shader uniforms (glsl.js): every uniform the glass and genie shaders declare is
// set from JavaScript, and only ever through Shader.set, which hands GL typed
// floats (set_uniform_float). 0 arrives as 0, with no nudge.
import assert from 'node:assert/strict';
import {readFileSync, readdirSync} from 'node:fs';
import {test} from 'node:test';

import {Shader, ShaderBase, snippet, textureFrame, uniformNames, withShader} from '../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/glsl.js';

const EXT = new URL('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/', import.meta.url);
const read = f => readFileSync(new URL(f, EXT), 'utf8');
// The source without its // comments (shader text included).
const code = f => read(f).replace(/\/\/[^\n]*/g, '');

function shaderSource(file, name) {
    const m = read(file).match(new RegExp(`const ${name} = \`([^\`]*)\`;`));
    assert.ok(m, `${name} in ${file}`);
    return m[1];
}

// The keys of every object literal passed to one of `calls`, e.g. setFloats({a: 1})
// or GLASS.set(this, {a: 1}).
function keysSet(file, calls) {
    const src = code(file);
    const keys = new Set();
    for (const call of calls) {
        const re = new RegExp(`${call.replace('.', '\\.')}\\((?:this,\\s*)?\\{`, 'g');
        for (const m of src.matchAll(re)) {
            let i = m.index + m[0].length, depth = 1, body = '';
            for (; depth > 0; i++) {
                const ch = src[i];
                depth += '([{'.includes(ch) ? 1 : ')]}'.includes(ch) ? -1 : 0;
                body += depth === 1 ? ch : ' ';
            }
            for (const k of body.matchAll(/(?:^|,)\s*([A-Za-z_]\w*)\s*:/g))
                keys.add(k[1]);
        }
    }
    return keys;
}

class FakeEffect {
    constructor() {
        this.slots = new Map();
        this.calls = [];
    }
    get_uniform_location(name) {
        if (!this.slots.has(name))
            this.slots.set(name, this.slots.size);
        return this.slots.get(name);
    }
    set_uniform_float(loc, n, values) {
        this.calls.push({loc, n, values});
    }
    add_glsl_snippet(hook, decls, code, replace) {
        this.snippet = {hook, decls, code, replace};
    }
}

const SHADERS = [
    {file: 'glass.js', name: 'SHADER', calls: ['setFloats', 'GLASS.set']},
    {file: 'animations.js', name: 'GENIE_SHADER', calls: ['_set', 'GENIE.set']},
];

for (const {file, name, calls} of SHADERS) {
    test(`${name}: splits into a Cogl snippet that reads cogl_sampler0`, () => {
        const src = shaderSource(file, name);
        const {decls, code} = snippet(src);
        assert.doesNotMatch(src, /\btex\b\s*,|sampler2D/);
        assert.match(src, /texture2D\(cogl_sampler0,/);
        assert.doesNotMatch(src, /texture2D\((?!cogl_sampler0,)/);
        assert.doesNotMatch(decls, /void main/);
        assert.match(code, /cogl_color_out/);
    });

    test(`${name}: every uniform it declares is set from ${file}, and nothing else`, () => {
        const declared = new Set(uniformNames(shaderSource(file, name)));
        const set = keysSet(file, calls);
        // The texture frame comes from glsl.js's textureFrame, handed straight to a set call.
        if (new RegExp(`(${calls.map(c => c.replace('.', '\\.')).join('|')})\\((this, )?textureFrame\\(`).test(code(file)))
            for (const k of Object.keys(textureFrame(3, 3, {width: 0, height: 0})))
                set.add(k);
        assert.ok(declared.size > 10);
        assert.deepEqual([...declared].filter(k => !set.has(k)), [], 'declared but never set');
        assert.deepEqual([...set].filter(k => !declared.has(k)), [], 'set but not declared');
    });
}

test('no module sets a uniform any other way', () => {
    for (const f of readdirSync(EXT).filter(n => n.endsWith('.js'))) {
        const src = code(f);
        // GNOME 50's Clutter.ShaderEffect source API compiles one program per pane.
        assert.doesNotMatch(src, /set_uniform_value|set_shader_source|get_static_shader_source/, f);
        if (f !== 'glsl.js')
            assert.doesNotMatch(src, /Clutter\.ShaderEffect|Shell\.GLSLEffect\b(?! copies)/, `${f} must extend ShaderBase`);
        if (f !== 'glsl.js')
            assert.doesNotMatch(src, /set_uniform_float/, `${f} must go through Shader.set`);
    }
});

test('whole numbers arrive as typed floats, 0 as exactly 0', () => {
    const shader = new Shader(shaderSource('glass.js', 'SHADER'));
    const e = new FakeEffect();
    shader.set(e, {ceil_y: 0, mode: 3, width: 1920, hl: 0.55});
    assert.deepEqual(e.calls.map(c => [c.n, c.values]), [[1, [0]], [1, [3]], [1, [1920]], [1, [0.55]]]);
    assert.ok(Object.is(e.calls[0].values[0], 0));
});

test('each effect keeps its own uniform slots; looked up once', () => {
    const shader = new Shader(shaderSource('animations.js', 'GENIE_SHADER'));
    const a = new FakeEffect(), b = new FakeEffect();
    let lookups = 0;
    const count = e => {
        const get = e.get_uniform_location.bind(e);
        e.get_uniform_location = n => (lookups++, get(n));
    };
    count(a);
    count(b);
    for (let p = 0; p <= 1; p += 0.25) {
        shader.set(a, {progress: p});
        shader.set(b, {progress: 1 - p});
    }
    assert.equal(lookups, 2);
    assert.deepEqual(a.calls.map(c => c.values[0]), [0, 0.25, 0.5, 0.75, 1]);
    assert.deepEqual(b.calls.map(c => c.values[0]), [1, 0.75, 0.5, 0.25, 0]);
});

function quietly(fn) {
    const warn = console.warn;
    const warned = [];
    console.warn = m => warned.push(m);
    try {
        fn();
    } finally {
        console.warn = warn;
    }
    return warned;
}

test('a bad name or value is skipped with one warning, never thrown (it runs mid-paint)', () => {
    const shader = new Shader(shaderSource('glass.js', 'SHADER'));
    const e = new FakeEffect();
    const warned = quietly(() => {
        assert.doesNotThrow(() => shader.set(e, {nope: 1, ptr_x: NaN, ptr_y: Infinity, ptr_k: 0.5, press: undefined}));
        assert.doesNotThrow(() => shader.set(e, {nope: 2, hl: 0.25}));
    });
    assert.deepEqual(e.calls.map(c => c.values[0]), [0.5, 0.25]);
    assert.ok(!e.slots.has('nope'));
    assert.equal(warned.length, 1);
    assert.match(warned[0], /no uniform nope/);
});

test('build adds one replacing fragment snippet', () => {
    const shader = new Shader(shaderSource('glass.js', 'SHADER'));
    const e = new FakeEffect();
    shader.build(e);
    assert.equal(e.snippet.hook, 'fragment');
    assert.equal(e.snippet.replace, true);
    assert.equal(e.snippet.code.trim().endsWith(';'), true);
});

// At a fractional display scale (Dino's 125 %) the effect texture is in screen
// pixels and the pane in logical ones; the shader works in logical pixels, or the
// glass is drawn at the wrong size and place (a stray box in menus and the panel).

test('the texture frame is in the pane\'s own pixels at any display scale', () => {
    const pane = (width, height, scale) => ({width, height, get_resource_scale: () => scale});
    assert.deepEqual(textureFrame(203, 53, pane(200, 50, 1)), {tex_w: 203, tex_h: 53, org_x: 2, org_y: 2});
    const f = textureFrame(Math.ceil(203 * 1.25), Math.ceil(53 * 1.25), pane(200, 50, 1.25));
    assert.ok(Math.abs(f.tex_w - 203) < 1 && Math.abs(f.tex_h - 53) < 1, JSON.stringify(f));
    assert.equal(f.org_x, 2);
    assert.equal(f.org_y, 2);
    assert.deepEqual(textureFrame(406, 106, pane(200, 50, 2)), {tex_w: 203, tex_h: 53, org_x: 2, org_y: 2});
});

test('both effects that map a texture onto an actor use textureFrame', () => {
    for (const f of ['glass.js', 'animations.js']) {
        assert.match(code(f), /textureFrame\(w, h, a\)/, f);
        assert.doesNotMatch(code(f), /tex_w: w/, f);
    }
});

test('a clipped pane starts where Clutter frames its clip', () => {
    // Clutter frames the clip, grown as _clutter_actor_box_enlarge_for_effects does.
    const pane = {width: 300, height: 200, has_clip: true, get_clip: () => [47, 0, 253, 200], get_resource_scale: () => 1};
    const f = textureFrame(256, 203, pane);
    assert.equal(f.org_x, -45);    // the texture starts 2 px before the clip, 45 px into the pane
    assert.equal(f.org_y, 2);
});


// GNOME 51 removed Shell.GLSLEffect; the same shaders run as a Clutter.ShaderEffect.
test('on GNOME 51 uniforms are set by name, as floats', () => {
    const shader = new Shader(shaderSource('glass.js', 'SHADER'));
    const calls = [];
    const e = {set_uniform_float: (name, n, values) => calls.push([name, n, values])};
    shader.set(e, {ceil_y: 0, width: 1920, nope: 1, hl: NaN});
    assert.deepEqual(calls, [['ceil_y', 1, [0]], ['width', 1, [1920]]]);
});

test('each GNOME gets the one shader vfunc its base class has', () => {
    const shader = new Shader(shaderSource('glass.js', 'SHADER'));
    const K = withShader(class extends ShaderBase {}, shader);
    // The test stubs have no Shell.GLSLEffect, like GNOME 51.
    assert.equal(typeof K.prototype.vfunc_get_static_snippet, 'function');
    assert.equal(K.prototype.vfunc_build_pipeline, undefined);
});

test('the GNOME 51 snippet carries the same shader, replacing the fragment hook', () => {
    const src = shaderSource('glass.js', 'SHADER');
    const shader = new Shader(src);
    const snip = shader.cogl();
    const parts = snippet(src);
    assert.equal(snip.hook, 'fragment');
    assert.equal(snip.decls, parts.decls);
    assert.equal(snip.post, null);
    assert.equal(snip.replace, parts.code);
});
