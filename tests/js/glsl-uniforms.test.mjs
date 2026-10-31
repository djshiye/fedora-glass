// Shader uniforms (glsl.js): every uniform the glass and genie shaders declare is
// set from JavaScript, and only ever through Shader.set, which hands GL typed
// floats (set_uniform_float). 0 arrives as 0, with no nudge.
import assert from 'node:assert/strict';
import {readFileSync, readdirSync} from 'node:fs';
import {test} from 'node:test';

import {Shader, snippet, uniformNames} from '../../liquidglass/data/extension/liquid-glass@djshiye.github.io/glsl.js';

const EXT = new URL('../../liquidglass/data/extension/liquid-glass@djshiye.github.io/', import.meta.url);
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
        assert.ok(declared.size > 10);
        assert.deepEqual([...declared].filter(k => !set.has(k)), [], 'declared but never set');
        assert.deepEqual([...set].filter(k => !declared.has(k)), [], 'set but not declared');
    });
}

test('no module sets a uniform any other way', () => {
    for (const f of readdirSync(EXT).filter(n => n.endsWith('.js'))) {
        const src = code(f);
        assert.doesNotMatch(src, /set_uniform_value|set_shader_source|Clutter\.ShaderEffect|get_static_shader_source/, f);
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

test('an unknown uniform throws; a non-finite value is skipped', () => {
    const shader = new Shader(shaderSource('glass.js', 'SHADER'));
    const e = new FakeEffect();
    assert.throws(() => shader.set(e, {nope: 1}), /no uniform nope/);
    const warn = console.warn;
    const warned = [];
    console.warn = m => warned.push(m);
    try {
        shader.set(e, {ptr_x: NaN, ptr_y: Infinity, ptr_k: 0.5, press: undefined});
    } finally {
        console.warn = warn;
    }
    assert.deepEqual(e.calls.map(c => c.values[0]), [0.5]);
    assert.equal(warned.length, 1);
});

test('build adds one replacing fragment snippet', () => {
    const shader = new Shader(shaderSource('glass.js', 'SHADER'));
    const e = new FakeEffect();
    shader.build(e);
    assert.equal(e.snippet.hook, 'fragment');
    assert.equal(e.snippet.replace, true);
    assert.equal(e.snippet.code.trim().endsWith(';'), true);
});
