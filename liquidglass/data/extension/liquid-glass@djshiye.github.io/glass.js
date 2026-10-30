// A Liquid Glass pane for GNOME Shell: a live copy of whatever lies behind a
// Shell surface, blurred, bent along a refracting rim, lit by a directional
// highlight and cut to the surface's rounded shape.
//
// The lens model follows Kyant's AndroidLiquidGlass (Apache License 2.0,
// https://github.com/Kyant0/AndroidLiquidGlass): a circular edge profile on a
// rounded-rectangle distance field, its gradient as the surface normal, an
// optional pull towards the centre for depth, and seven-band dispersion.

import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import Shell from 'gi://Shell';

const SHADER = `
uniform sampler2D tex;
uniform float width;
uniform float height;
uniform float pad;
uniform float r_tl;
uniform float r_tr;
uniform float r_br;
uniform float r_bl;
uniform float refr_h;
uniform float refr_amt;
uniform float depth;
uniform float dispersion;
uniform float saturation;
uniform float brightness;
uniform float tint_r;
uniform float tint_g;
uniform float tint_b;
uniform float tint_a;
uniform float hl;
uniform float hl_x;
uniform float hl_y;
uniform float hl_falloff;
uniform float rim_w;
uniform float shadow;

float radiusAt(vec2 c) {
    if (c.x >= 0.0)
        return c.y <= 0.0 ? r_tr : r_br;
    return c.y <= 0.0 ? r_tl : r_bl;
}

float sdRoundRect(vec2 p, vec2 h, float r) {
    vec2 q = abs(p) - (h - vec2(r));
    return length(max(q, 0.0)) - r + min(max(q.x, q.y), 0.0);
}

vec2 gradRoundRect(vec2 p, vec2 h, float r) {
    vec2 q = abs(p) - (h - vec2(r));
    vec2 s = vec2(p.x < 0.0 ? -1.0 : 1.0, p.y < 0.0 ? -1.0 : 1.0);
    if (q.x >= 0.0 || q.y >= 0.0)
        return s * normalize(max(q, 0.0) + vec2(1e-4));
    float gx = step(q.y, q.x);
    return s * vec2(gx, 1.0 - gx);
}

vec4 at(vec2 px) {
    vec2 size = vec2(width, height);
    return texture2D(tex, clamp(px, vec2(0.5), size - vec2(0.5)) / size);
}

void main() {
    vec2 size = vec2(width, height);
    vec2 px = cogl_tex_coord_in[0].st * size;
    vec2 c = px - size * 0.5;
    vec2 h = max(size * 0.5 - vec2(pad), vec2(1.0));
    float r = min(radiusAt(c), min(h.x, h.y));
    float sd = sdRoundRect(c, h, r);

    if (sd > 0.5) {
        // Outside the pane: only its soft shadow, a little below it.
        float s = 0.0;
        if (shadow > 0.0 && pad > 1.0) {
            float ds = sdRoundRect(c - vec2(0.0, pad * 0.2), h, r);
            s = 1.0 - smoothstep(-pad * 0.15, pad * 0.85, ds);
            s = shadow * s * s;
        }
        cogl_color_out = vec4(0.0, 0.0, 0.0, s) * cogl_color_in.a;
        return;
    }

    float cov = clamp(0.5 - sd, 0.0, 1.0);
    float inside = -min(sd, 0.0);
    float gr = min(r * 1.5, min(h.x, h.y));
    vec2 n = gradRoundRect(c, h, gr);

    vec4 col;
    if (refr_amt > 0.0 && inside < refr_h) {
        float x = 1.0 - inside / refr_h;
        float d = (1.0 - sqrt(max(0.0, 1.0 - x * x))) * refr_amt;
        vec2 g = normalize(n + depth * normalize(c + vec2(1e-4)));
        vec2 rc = px - d * g;
        if (dispersion > 0.001) {
            vec2 dc = -d * g * dispersion * (c.x * c.y) / (h.x * h.y);
            vec4 red = at(rc + dc);
            vec4 orange = at(rc + dc * (2.0 / 3.0));
            vec4 yellow = at(rc + dc * (1.0 / 3.0));
            vec4 green = at(rc);
            vec4 cyan = at(rc - dc * (1.0 / 3.0));
            vec4 blue = at(rc - dc * (2.0 / 3.0));
            vec4 purple = at(rc - dc);
            col.r = (red.r + orange.r + yellow.r) / 3.5 + purple.r / 7.0;
            col.g = orange.g / 7.0 + (yellow.g + green.g + cyan.g) / 3.5;
            col.b = (cyan.b + blue.b + purple.b) / 3.0;
            col.a = (red.a + orange.a + yellow.a + green.a + cyan.a + blue.a + purple.a) / 7.0;
        } else {
            col = at(rc);
        }
    } else {
        col = at(px);
    }

    // Vibrancy and brightness (premultiplied colour).
    float l = dot(col.rgb, vec3(0.213, 0.715, 0.072));
    col.rgb = clamp(mix(vec3(l), col.rgb, saturation) * brightness, 0.0, 1.0);
    col.rgb = min(col.rgb, vec3(col.a));

    vec4 t = vec4(tint_r, tint_g, tint_b, 1.0) * tint_a;
    col = t + col * (1.0 - t.a);

    // Highlight: brightest where the rim faces the light, a thin band plus a
    // soft glow that follows the refracting edge.
    float facing = pow(abs(dot(n, vec2(hl_x, hl_y))), hl_falloff);
    float band = 1.0 - smoothstep(0.0, max(rim_w, 0.5), inside);
    float glow = (1.0 - smoothstep(0.0, max(refr_h, 1.0), inside)) * 0.22;
    float k = clamp(hl * (band + glow) * (0.12 + 0.88 * facing), 0.0, 1.0);
    col = vec4(k) + col * (1.0 - k);

    cogl_color_out = col * cov * cogl_color_in.a;
}
`;

const GlassEffect = GObject.registerClass(
class LiquidGlassEffect extends Clutter.ShaderEffect {
    _init() {
        super._init();
        this.set_shader_source(SHADER);
    }

    setFloats(values) {
        // A whole number would reach GL as an int uniform; nudge it to a float.
        for (const [name, v] of Object.entries(values))
            this.set_uniform_value(name, Number.isInteger(v) ? v + 1e-6 : v);
        this.queue_repaint();
    }
});

export const DEFAULT_LOOK = Object.freeze({
    blur: 6,            // px
    refraction: 22,     // width of the bending rim, px
    bend: 26,           // how far the rim pulls the backdrop, px
    depth: 0.35,        // 0..1, pull towards the centre
    dispersion: 0.35,   // 0..1, rainbow split along the rim
    saturation: 1.5,    // vibrancy, 1 = unchanged
    brightness: 1.0,
    tint: [0, 0, 0, 0], // straight rgba, 0..1
    highlight: 0.55,    // 0..1
    lightAngle: -50,    // degrees, -90 = from the top
    falloff: 2.0,
    rim: 1.5,           // px
    shadow: 0,          // 0..1, drawn by the pane itself
});

/**
 * One glass pane. Its owner calls place() with the surface rectangle (in the
 * pane's parent coordinates, plus the matching stage position) whenever the
 * surface moves, and setSources() with the actors to show through it, bottom
 * first. Each source is copied with a Clutter.Clone at its stage position.
 */
export const GlassPane = GObject.registerClass(
class LiquidGlassPane extends Clutter.Actor {
    _init() {
        super._init({name: 'liquid-glass-pane', clip_to_allocation: true, reactive: false});
        this._blur = new Shell.BlurEffect({mode: Shell.BlurMode.ACTOR, radius: 0, brightness: 1});
        this.add_effect_with_name('liquid-glass-blur', this._blur);
        this._glass = new GlassEffect();
        this.add_effect_with_name('liquid-glass-lens', this._glass);
        this._look = {...DEFAULT_LOOK};
        this._radii = [0, 0, 0, 0];
        this._pad = 0;
        this._stage = [0, 0];
        this._size = [1, 1];
        this._clones = new Map();   // source actor -> clone
        this._placed = '';
        this._applyLook();
        this.connect('destroy', () => this._clones.clear());
    }

    get pad() {
        return this._pad;
    }

    setSources(actors) {
        const keep = new Set(actors);
        for (const [src, clone] of this._clones) {
            if (!keep.has(src)) {
                this._clones.delete(src);
                clone.destroy();
            }
        }
        let below = null;
        for (const src of actors) {
            let clone = this._clones.get(src);
            if (!clone) {
                clone = new Clutter.Clone({source: src});
                // A clone outlives its source, so a source that goes away takes its copy with it.
                const id = src.connect('destroy', () => {
                    if (this._clones.get(src) === clone) {
                        this._clones.delete(src);
                        clone.destroy();
                    }
                });
                clone.connect('destroy', () => {
                    if (this._clones.get(src) === clone)
                        this._clones.delete(src);
                    try {
                        src.disconnect(id);
                    } catch {}   // the source is already gone
                });
                this._clones.set(src, clone);
                this.add_child(clone);
            }
            if (below)
                this.set_child_above_sibling(clone, below);
            else
                this.set_child_below_sibling(clone, null);
            below = clone;
        }
        this._syncClones();
    }

    setLook(look) {
        this._look = {...DEFAULT_LOOK, ...look};
        this._applyLook();
    }

    /** x, y, w, h: the surface in parent coordinates; sx, sy: its stage position. */
    place(x, y, w, h, radii, sx, sy) {
        const p = this._pad;
        const key = [x, y, w, h, sx, sy, p, ...radii].map(v => Math.round(v * 4)).join();
        if (key === this._placed) {
            this._syncClones();   // windows behind may still have moved
            return;
        }
        this._placed = key;
        this._radii = radii.map(r => Math.max(0, Math.min(r, w / 2, h / 2)));
        this.set_position(Math.round(x - p), Math.round(y - p));
        this._size = [Math.max(1, Math.round(w + 2 * p)), Math.max(1, Math.round(h + 2 * p))];
        this.set_size(...this._size);
        this._stage = [Math.round(sx - p), Math.round(sy - p)];
        this._syncClones();
        this._applyShape();
    }

    _syncClones() {
        for (const [src, clone] of this._clones) {
            if (!src.get_stage()) {
                clone.hide();
                continue;
            }
            // A window actor catches up with its window only at the next frame; the window knows now.
            const r = src.meta_window?.get_buffer_rect();
            const [bx, by] = r ? [r.x, r.y] : src.get_transformed_position();
            clone.set_position(Math.round(bx - this._stage[0]), Math.round(by - this._stage[1]));
            clone.set_size(r ? r.width : src.width, r ? r.height : src.height);
            clone.show();
        }
    }

    _applyLook() {
        const L = this._look;
        const blur = Math.max(0, Math.min(100, L.blur));
        this._blur.radius = blur;
        this._blur.enabled = blur > 0.5;
        // Room around the surface for the blur to see past the edge and for the shadow.
        this._pad = Math.ceil(Math.max(blur, L.shadow > 0 ? 18 : 0, 2));
        const a = L.lightAngle * Math.PI / 180;
        const [tr, tg, tb, ta] = L.tint;
        this._glass.setFloats({
            refr_h: Math.max(0, L.refraction),
            refr_amt: Math.max(0, L.bend),
            depth: Math.max(0, Math.min(1, L.depth)),
            dispersion: Math.max(0, Math.min(1, L.dispersion)),
            saturation: Math.max(0, Math.min(3, L.saturation)),
            brightness: Math.max(0, Math.min(2, L.brightness)),
            tint_r: tr, tint_g: tg, tint_b: tb, tint_a: Math.max(0, Math.min(1, ta)),
            hl: Math.max(0, Math.min(1, L.highlight)),
            hl_x: Math.cos(a), hl_y: Math.sin(a),
            hl_falloff: Math.max(0.25, L.falloff),
            rim_w: Math.max(0, L.rim),
            shadow: Math.max(0, Math.min(1, L.shadow)),
        });
        this._applyShape();
    }

    _applyShape() {
        const [tl, tr, br, bl] = this._radii;
        this._glass.setFloats({
            width: this._size[0], height: this._size[1], pad: this._pad,
            r_tl: tl, r_tr: tr, r_br: br, r_bl: bl,
        });
    }
});
