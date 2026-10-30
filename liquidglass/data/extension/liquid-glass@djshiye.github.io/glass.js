// A Liquid Glass pane for GNOME Shell: a live copy of whatever lies behind a
// Shell surface, blurred, seen through a slab of glass and cut to the
// surface's rounded shape.
//
// The optics are physical. The pane is a glass slab (IOR 1.5) whose top edge
// rounds off in a quarter circle, over a slightly domed top, after Kyant's
// AndroidLiquidGlass (Apache License 2.0, https://github.com/Kyant0/AndroidLiquidGlass):
// - each view ray is refracted at the surface by Snell's law and travels down
//   through the glass to the backdrop, so the rim bends light like a real lens;
// - the index varies with wavelength by Cauchy's equation, n = A + B / λ²,
//   sampled at five wavelengths, which splits the rim into a rainbow;
// - the Fresnel term (Schlick's approximation) decides how much light the
//   surface reflects: little head-on, nearly all at grazing angles, which is
//   what makes real glass edges glow;
// - a key light gives a Blinn-Phong specular highlight on the facing rim and,
//   after reflecting inside the glass, a dimmer one on the opposite rim;
// - Beer-Lambert absorption darkens light a little along longer paths.

import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';
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
uniform float mode;              // 0 = glass and reflections, 1 = glass only, 2 = reflections only

const float IOR = 1.5;           // crown glass at 550 nm
const float F0 = 0.04;           // ((IOR - 1) / (IOR + 1))^2, head-on reflectance

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

// Where a view ray, refracted into glass of index n at normal N, meets the
// backdrop under a thickness th.
vec2 throughGlass(vec3 N, float n, float th) {
    vec3 R = refract(vec3(0.0, 0.0, -1.0), N, 1.0 / n);
    return R.xy * th / max(-R.z, 0.2);
}

// Cauchy's equation, fitted so n(550 nm) = IOR; B grows with dispersion.
float cauchy(float um, float B) {
    return IOR + B * (1.0 / (um * um) - 1.0 / 0.3025);
}

void main() {
    vec2 size = vec2(width, height);
    vec2 px = cogl_tex_coord_in[0].st * size;
    vec2 c = px - size * 0.5;
    vec2 h = max(size * 0.5 - vec2(pad), vec2(1.0));
    float r = min(radiusAt(c), min(h.x, h.y));
    float sd = sdRoundRect(c, h, r);

    if (sd > 0.5 && mode > 1.5) {
        cogl_color_out = vec4(0.0);
        return;
    }
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

    // The glass: a slab refr_amt thick lying on the backdrop, its top edge
    // rounded off over refr_h in a quarter ellipse, like a glass paperweight.
    float th = refr_amt;
    float slope = 0.0;
    float bevel = min(refr_h, min(h.x, h.y));       // a thin bar rounds off over its whole height
    if (bevel > 0.0 && inside < bevel) {
        float x = 1.0 - inside / bevel;            // 1 at the edge, 0 on the flat top
        float z = sqrt(max(1.0 - x * x, 0.0));
        slope = x / max(z, 0.06);                   // -dz/dr of the rounded edge, outward
    }
    vec2 dome = depth * 0.25 * c / max(h.x, h.y);  // a gently domed top
    vec3 N = normalize(vec3(n * slope + dome, 1.0));

    vec4 col = vec4(0.0);
    if (mode > 1.5) {
        // The reflections are drawn on their own, above the surface's content.
    } else if (th > 0.01) {
        if (dispersion > 0.001 && slope > 0.02) {
            // Five wavelengths, each refracted by its own index, then mixed back to RGB.
            float B = 0.08 * dispersion;   // crown glass is ~0.004, dense flint ~0.015: exaggerated, as Apple does
            vec4 s450 = at(px + throughGlass(N, cauchy(0.45, B), th));
            vec4 s500 = at(px + throughGlass(N, cauchy(0.50, B), th));
            vec4 s550 = at(px + throughGlass(N, IOR, th));
            vec4 s600 = at(px + throughGlass(N, cauchy(0.60, B), th));
            vec4 s650 = at(px + throughGlass(N, cauchy(0.65, B), th));
            col.r = (0.05 * s450.r + 0.15 * s550.r + 0.85 * s600.r + s650.r) / 2.05;
            col.g = (0.6 * s500.g + s550.g + 0.35 * s600.g) / 1.95;
            col.b = (s450.b + 0.4 * s500.b) / 1.4;
            col.a = (s450.a + s500.a + s550.a + s600.a + s650.a) / 5.0;
        } else {
            col = at(px + throughGlass(N, IOR, th));
        }
    } else {
        col = at(px);
    }
    if (mode < 1.5) {
        // Vibrancy and brightness (premultiplied colour).
        float l = dot(col.rgb, vec3(0.213, 0.715, 0.072));
        col.rgb = clamp(mix(vec3(l), col.rgb, saturation) * brightness, 0.0, 1.0);
        col.rgb = min(col.rgb, vec3(col.a));

        // Beer-Lambert: a faint, slightly green absorption along the path in the glass.
        float path = th / max(N.z, 0.2);
        col.rgb *= exp(-vec3(0.0016, 0.0009, 0.0013) * path);

        vec4 t = vec4(tint_r, tint_g, tint_b, 1.0) * tint_a;
        col = t + col * (1.0 - t.a);
    }
    if (mode > 0.5 && mode < 1.5) {
        cogl_color_out = col * cov * cogl_color_in.a;
        return;
    }

    // Reflection. Fresnel decides how much of the surroundings the surface
    // mirrors; the surroundings are a soft sky, brighter above.
    float cosi = N.z;
    float F = F0 + (1.0 - F0) * pow(1.0 - cosi, 5.0);
    vec3 Rf = reflect(vec3(0.0, 0.0, -1.0), N);
    float sky = 0.35 + 0.65 * clamp(0.5 - 0.5 * Rf.y, 0.0, 1.0);
    // A low key light from lightAngle, far brighter than the sky, so the rim
    // facing it catches a sharp highlight.
    vec3 L = normalize(vec3(hl_x, hl_y, 0.2));
    vec3 H = normalize(L + vec3(0.0, 0.0, 1.0));
    float shin = 6.0 * hl_falloff * hl_falloff;
    float norm = (shin + 8.0) / 25.0;               // energy-conserving Blinn-Phong
    float spec = pow(max(dot(N, H), 0.0), shin) * norm;
    // The same light, reflected inside the glass, leaves through the opposite rim.
    vec3 Ni = vec3(-N.xy, N.z);
    float inner = pow(max(dot(Ni, H), 0.0), shin) * norm * (1.0 - F) * 0.5;
    // A crisp line where the surface turns vertical: there glass reflects almost everything.
    float band = 1.0 - smoothstep(0.0, max(rim_w, 0.5), inside);
    float facing = pow(abs(dot(n, vec2(hl_x, hl_y))), hl_falloff);
    float k = hl * (0.5 * F * sky + 22.0 * F * (spec + inner) + band * (0.15 + 0.6 * facing));
    k = clamp(k, 0.0, 1.0);
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
    refraction: 22,     // width of the rounded edge, px
    bend: 26,           // thickness of the glass slab, px
    depth: 0.35,        // 0..1, how domed the top is
    dispersion: 0.35,   // 0..1, rainbow split along the rim
    saturation: 1.5,    // vibrancy, 1 = unchanged
    brightness: 1.0,
    tint: [0, 0, 0, 0], // straight rgba, 0..1
    highlight: 0.55,    // 0..1
    lightAngle: -125,   // degrees, -90 = from the top
    falloff: 2.0,
    rim: 1.5,           // px
    shadow: 0,          // 0..1, drawn by the pane itself
});

/**
 * One glass pane. Its owner calls place() with the surface rectangle (in the
 * pane's parent coordinates, plus the matching stage position) whenever the
 * surface moves, and setSources() with the actors to show through it, bottom
 * first. Each source is copied with a Clutter.Clone at its stage position.
 *
 * layer 'full' draws the glass and its reflections. Where the surface paints
 * its own tinted background, the reflections would sit under that tint, so
 * the owner uses two panes: 'glass' below the surface and 'reflections' (no
 * sources, no blur) above it, as light reflects off the top of real glass.
 */
const LAYERS = {full: 0, glass: 1, reflections: 2};

export const GlassPane = GObject.registerClass(
class LiquidGlassPane extends Clutter.Actor {
    _init(layer = 'full') {
        // Hidden until placed: an effect on an empty actor asks Cogl for a 0×0 texture.
        super._init({name: `liquid-glass-${layer}`, clip_to_allocation: true, reactive: false, visible: false});
        this._layer = LAYERS[layer] ?? 0;
        this._blur = new Shell.BlurEffect({mode: Shell.BlurMode.ACTOR, radius: 0, brightness: 1});
        if (this._layer === LAYERS.reflections) {
            // Nothing to show through; a background gives the shader something to paint over.
            this.background_color = new Cogl.Color({red: 0, green: 0, blue: 0, alpha: 255});
        } else {
            this.add_effect_with_name('liquid-glass-blur', this._blur);
        }
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
            if (!Number.isFinite(bx) || !Number.isFinite(by)) {
                clone.hide();   // not allocated yet
                continue;
            }
            clone.set_position(Math.round(bx - this._stage[0]), Math.round(by - this._stage[1]));
            clone.set_size(r ? r.width : src.width, r ? r.height : src.height);
            clone.show();
        }
    }

    _applyLook() {
        const L = this._look;
        const blur = this._layer === LAYERS.reflections ? 0 : Math.max(0, Math.min(100, L.blur));
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
            shadow: this._layer === LAYERS.reflections ? 0 : Math.max(0, Math.min(1, L.shadow)),
            mode: this._layer,
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
