// Shared plumbing for the extension's fragment shaders.
//
// Every shader runs as a Shell.GLSLEffect: one GL program per effect class,
// built once and shared by all its instances, while each instance keeps its own
// copy of the pipeline and so its own uniform values. (A Clutter.ShaderEffect
// compiled one program per pane, which is what made Cogl warn about "over 50
// fragment shaders" on a busy desktop.)
//
// Uniforms are always set as floats through set_uniform_float, so 0 is really
// 0 and a whole number never turns into an int uniform.

import Cogl from 'gi://Cogl';

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
        throw new Error('Liquid Glass: a shader must have main() and read cogl_sampler0');
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
 * One shader, for a Shell.GLSLEffect subclass to use:
 *
 *     const MY = new Shader(SOURCE);
 *     ... extends Shell.GLSLEffect {
 *         vfunc_build_pipeline() { MY.build(this); }
 *         setFloats(values) { MY.set(this, values); }
 *     }
 *
 * build() runs once per class, on its first instance. set() sets each uniform
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
                this._warn(`Liquid Glass: no uniform ${k} in this shader; skipped`);
                continue;
            }
            if (typeof v !== 'number' || !Number.isFinite(v)) {
                this._warn(`Liquid Glass: uniform ${k} skipped, not a finite number`);
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
// size and place (a stray box inside menus and the panel). Clutter grows the frame
// by 2 px at the top left and 1 px at the bottom right, before scaling.
export function textureFrame(texW, texH, actor) {
    const s = Math.max(actor.get_resource_scale?.() ?? 1, 1e-3);
    const w = texW / s, h = texH / s;
    return {tex_w: w, tex_h: h, org_x: Math.ceil((w - actor.width) / 2), org_y: Math.ceil((h - actor.height) / 2)};
}
