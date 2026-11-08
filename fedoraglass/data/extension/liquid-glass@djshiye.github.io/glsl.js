// Shared plumbing for the extension's fragment shaders.
//
// Every shader runs with one GL program per effect class, built once and shared by
// all its instances, while each instance keeps its own uniform values. On GNOME 50
// that is a Shell.GLSLEffect. GNOME 51 removed Shell.GLSLEffect: there it is a
// Clutter.ShaderEffect whose snippet comes from get_static_snippet, which Clutter
// also asks for once per class. (GNOME 50's Clutter.ShaderEffect compiled one
// program per pane, which made Cogl warn about "over 50 fragment shaders".)
//
// Uniforms are always set as floats through set_uniform_float, so 0 is really
// 0 and a whole number never turns into an int uniform.

import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';
import Shell from 'gi://Shell';

/** True on GNOME 50 (Shell.GLSLEffect), false on GNOME 51 and later. */
export const SHELL_GLSL = typeof Shell?.GLSLEffect === 'function';

/** The base class for the extension's shader effects on this GNOME. */
export const ShaderBase = SHELL_GLSL ? Shell.GLSLEffect : Clutter.ShaderEffect;

/**
 * Gives an effect class the one virtual function its base needs to get the shader,
 * before GObject.registerClass sees it (a vfunc the base lacks is an error there):
 *
 *     const MY = new Shader(SOURCE);
 *     const MyEffect = GObject.registerClass(withShader(class extends ShaderBase { ... }, MY));
 */
export function withShader(klass, shader) {
    // defineProperty, not assignment: GJS ignores a plain assignment of a vfunc the
    // parent class already has a slot for (seen on GNOME 51), and the class would
    // then have no shader at all.
    const [name, fn] = SHELL_GLSL
        ? ['vfunc_build_pipeline', function () {
            shader.build(this);
        }]
        : ['vfunc_get_static_snippet', function () {
            return shader.cogl();
        }];
    Object.defineProperty(klass.prototype, name, {value: fn, writable: true, configurable: true, enumerable: false});
    return klass;
}

/**
 * Splits a shader written as declarations plus `void main() { ... }` into the
 * two parts a Cogl snippet takes: the declarations, and main's body (which
 * replaces the fragment hook, so `return` leaves it early). The texture is
 * read through Cogl's own `cogl_sampler0`; the source must not declare one.
 */
export function snippet(source) {
    const head = 'void main() {';
    const at = source.indexOf(head);
    const end = source.lastIndexOf('}');
    if (at < 0 || end < at || /uniform\s+sampler2D/.test(source))
        throw new Error('Fedora Glass: a shader must have main() and read cogl_sampler0');
    return {decls: source.slice(0, at), code: source.slice(at + head.length, end)};
}

/** The names of the float uniforms a shader declares, in order. */
export function uniformNames(source) {
    const names = [];
    for (const m of source.matchAll(/^\s*uniform\s+float\s+([^;]+);/gm))
        names.push(...m[1].split(',').map(s => s.trim()));
    return names;
}

/**
 * One shader, for an effect class made with withShader() to use:
 *
 *     setFloats(values) { MY.set(this, values); }
 *
 * build() (GNOME 50) and cogl() (GNOME 51) run once per class. set() sets each uniform
 * as a float. It runs while a frame is painted, so it never throws: a name the
 * shader does not declare, or a value that is not a finite number (NaN from a
 * bad measurement), is left out with one warning per shader, so the uniform
 * keeps its last good value and the frame still draws. The unit tests check
 * that every name the code sets is declared.
 */
export class Shader {
    constructor(source) {
        Object.assign(this, snippet(source));
        this.names = new Set(uniformNames(source));
    }

    build(effect) {
        effect.add_glsl_snippet(Cogl.SnippetHook.FRAGMENT, this.decls, this.code, true);
    }

    /** The same shader as a Cogl snippet (GNOME 51's Clutter.ShaderEffect). */
    cogl() {
        const snip = Cogl.Snippet.new(Cogl.SnippetHook.FRAGMENT, this.decls, null);
        snip.set_replace(this.code);
        return snip;
    }

    _warn(message) {
        if (this._warned)
            return;
        this._warned = true;
        console.warn(message);
    }

    set(effect, values) {
        effect._uniformAt ??= new Map();
        for (const [k, v] of Object.entries(values)) {
            if (!this.names.has(k)) {
                this._warn(`Fedora Glass: no uniform ${k} in this shader; skipped`);
                continue;
            }
            if (typeof v !== 'number' || !Number.isFinite(v)) {
                this._warn(`Fedora Glass: uniform ${k} skipped, not a finite number`);
                continue;
            }
            if (typeof effect.get_uniform_location !== 'function') {
                // GNOME 51's Clutter.ShaderEffect looks the name up itself, once per pipeline.
                effect.set_uniform_float(k, 1, [v]);
                continue;
            }
            let loc = effect._uniformAt.get(k);
            if (loc === undefined) {
                loc = effect.get_uniform_location(k);
                effect._uniformAt.set(k, loc);
            }
            // -1: Cogl has no slot for the name; there is nothing to set.
            if (loc >= 0)
                effect.set_uniform_float(loc, 1, [v]);
        }
    }
}

// Where an actor sits in its effect's texture, in the actor's own (logical) pixels.
// The texture is in screen pixels, so at a fractional scale such as 125 % it is
// bigger than the actor by that factor; mixing the two drew the glass at the wrong
// size and place (a stray box inside menus and the panel). Clutter frames the
// actor's paint area, its clip if it has one, and grows it as
// _clutter_actor_box_enlarge_for_effects does (clutter-actor-box.c): about 2 px at
// the top left and 1 px at the bottom right.
export function textureFrame(texW, texH, actor) {
    const s = Math.max(actor.get_resource_scale?.() ?? 1, 1e-3);
    const w = texW / s, h = texH / s;
    let [x1, y1, x2, y2] = [0, 0, actor.width, actor.height];
    if (actor.has_clip) {
        const [cx, cy, cw, ch] = actor.get_clip();
        [x1, y1, x2, y2] = [Math.max(x1, cx), Math.max(y1, cy), Math.min(x2, cx + cw), Math.min(y2, cy + ch)];
    }
    const fx = Math.ceil(x2 + 0.75) - Math.round(x2 - x1) - 3;
    const fy = Math.ceil(y2 + 0.75) - Math.round(y2 - y1) - 3;
    return {tex_w: w, tex_h: h, org_x: -fx, org_y: -fy};
}
