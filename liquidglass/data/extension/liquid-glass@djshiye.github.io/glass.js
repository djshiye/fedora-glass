// A Liquid Glass pane for GNOME Shell: a live copy of whatever lies behind a
// Shell surface, blurred, seen through a slab of glass and cut to the
// surface's rounded shape.
//
// The optics are physical, and everything the glass shows comes from real
// pixels on screen; there is no painted-on light. The pane is a glass slab
// (IOR 1.5) whose top edge rounds off in a quarter circle, after Kyant's
// AndroidLiquidGlass (Apache License 2.0, https://github.com/Kyant0/AndroidLiquidGlass):
// - each view ray is refracted at the surface by Snell's law and travels down
//   through the glass to the backdrop, so the rim bends light like a real lens;
// - the index varies with wavelength by Cauchy's equation, n = A + B / λ²,
//   sampled at five wavelengths, which splits the rim into a rainbow;
// - the Fresnel term (Schlick's approximation) decides how much the surface
//   mirrors: little head-on, nearly all at grazing angles. What it mirrors is
//   the real backdrop just beyond the edge, so the rim changes as windows move;
// - the surface's own content (icons, text) lights the glass it sits in: its
//   colours scatter into the glass around it and reflect inside the glass into
//   the nearest rim, the way a lit object tints the edge of a glass plate;
// - Beer-Lambert absorption darkens and greens the slanting paths through the edge.
//
// Sides that touch the screen edge (a docked panel's bottom) have no rim.

import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';

const SHADER = `
uniform sampler2D tex;
uniform float width;
uniform float height;
uniform float pad;
// The offscreen texture can be a few px larger than the pane (the blur below
// rounds its frame out); tex_* is its size and org_* where the pane starts in it.
uniform float tex_w;
uniform float tex_h;
uniform float org_x;
uniform float org_y;
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
uniform float hl;                // strength of the edge reflections
uniform float hl_x;              // where the light rests (only shapes the reflections)
uniform float hl_y;
uniform float ptr_x;              // the pointer, in px on this pane
uniform float ptr_y;
uniform float ptr_k;              // 0..1, how strongly the rim near it lights up
uniform float press;              // 0..1, held down at the pointer
uniform float env_reach;         // px, how far beyond the edge the rim sees
uniform float cheap;             // 1 while something moves behind: fewer taps
uniform float valid_x0;          // the part of the texture that is on screen
uniform float valid_y0;
uniform float valid_x1;
uniform float valid_y1;
uniform float margin;            // px at the texture's border that the blur has darkened
uniform float adapt;             // 0..1, how much the glass adjusts to its backdrop
uniform float lift;              // 0..1, light glass: how much its milk thickens over a dark backdrop
uniform float milk_r;            // the light glass's own body colour
uniform float milk_g;
uniform float milk_b;
uniform float light_glass;       // 1 for light glass (it has a milk), 0 for dark
uniform float hair;              // 0..0.3, light glass: a thin dark contact line at its edge
uniform float bleed;             // strength of the content's colour in the glass
uniform float solid;             // 1: the glass fills its pane fully (a full-screen sheet)
uniform float ceil_y;            // 0 = off; else the brightest the glass may get (linear Y),
                                 // so white text on it stays readable over any backdrop
uniform float edge_l;            // 1 where that side touches the screen edge
uniform float edge_t;
uniform float edge_r;
uniform float edge_b;
uniform float shadow;
uniform float mode;              // 0 = glass, 1 = glass under a surface, 2 = the surface's own light,
                                 // 3 = the rim over an app window

// setFloats() nudges whole numbers by 1e-6 so they reach GL as floats, so a
// uniform set to 0 arrives as 0.000001: test "is it on" against OFF, never 0.0.
// The same goes for values computed from uniforms (bevel comes from refr_h).
const float OFF = 0.001;
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
    return texture2D(tex, (clamp(px, vec2(0.5), size - vec2(0.5)) + vec2(org_x, org_y)) / vec2(tex_w, tex_h));
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

// What a ray mirrored off the edge sees: the blurred backdrop beyond the edge,
// box-filtered wide (Cogl offscreens have no mipmaps).
vec3 env(vec2 p) {
    float sp = env_reach * 0.3;
    // Stay clear of the border, where the blur has pulled in nothing from outside.
    // and off the screen, where there is nothing to see.
    p = clamp(p, max(vec2(margin + sp), vec2(valid_x0, valid_y0) + sp),
              min(vec2(width, height) - vec2(margin + sp), vec2(valid_x1, valid_y1) - sp));
    if (cheap > 0.5)
        return at(p).rgb;
    return at(p).rgb * 0.4
        + (at(p + vec2(sp, 0.0)).rgb + at(p - vec2(sp, 0.0)).rgb
         + at(p + vec2(0.0, sp)).rgb + at(p - vec2(0.0, sp)).rgb) * 0.15;
}

// 1/255 dither: no banding in big soft gradients, and a hint of grain.
// Fine material grain: interleaved gradient noise, a blue-noise-like dither
// with no clumps, so big blurred gradients never band. -0.5..0.5.
float grain(vec2 p) {
    return fract(52.9829189 * fract(dot(floor(p), vec2(0.06711056, 0.00583715)))) - 0.5;
}

// A normal jitter of a few thousandths: invisible as such, it only keeps the
// lens from looking machined.
vec2 jitter(vec2 p) {
    return vec2(grain(p), grain(p.yx + 17.0)) * 0.006;
}

// Where the light comes from: the room's light, turned towards the pointer
// while it is near, so the shadow, caustic and reflections answer to one light.
vec2 lightDir(vec2 toPtr) {
    vec2 Lp = toPtr / max(length(toPtr), 1.0);
    return normalize(mix(vec2(hl_x, hl_y), Lp, ptr_k) + vec2(1e-4));
}

// As if your head moved in front of real glass: with the pointer near, the
// reflections slide along the rim with you, as in a real mirror (parallax, no
// added light).
vec2 parallax(vec2 toPtr, vec2 h) {
    return -clamp(toPtr / max(h, vec2(1.0)), -1.0, 1.0) * env_reach * 2.0 * ptr_k;
}

// Pressed, the glass gives under the finger: around the press point the rim
// rounds off wider and steeper, so it bends and mirrors more of the real
// backdrop there. 0..1. A big pane gives over a wider area than a thin bar.
float touch(vec2 dp, float s) {
    return press * exp(-dot(dp, dp) / (2.0 * s * s));
}

// The dip a press leaves: the top tilts in towards the finger, so the backdrop
// around it is drawn in like under a lens.
vec2 dent(vec2 dp, float s, float t) {
    return -dp / s * 0.45 * t;
}

// Caustic: the rounded edge focuses light onto the backdrop on the side away
// from the light, so the shaded rim gets a soft band of the backdrop's own
// light, clearly brighter. The lift is even in lightness (L*), so it reads the
// same on every shaded side, short sides and end caps included, over dark
// backdrops and bright ones; over black there is nothing to lift. c is a
// straight (not premultiplied) colour.
vec3 caustic(vec3 c, vec2 n, vec2 L, float x, vec2 h) {
    float facing = smoothstep(-0.25, 0.35, dot(-n, L));
    // Strongest just inside the edge, fading evenly to nothing across the bevel:
    // light gathered at the rim, not a band with an inner edge. x: 1 at the
    // edge, 0 where the flat top begins.
    float gather = x * smoothstep(1.0, 0.88, x);
    float wide = smoothstep(30.0, 80.0, min(h.x, h.y));   // 0 on a thin bar, 1 on a menu
    float dL = 15.0 * facing * gather * mix(0.85, 1.0, wide);
    vec3 lin = pow(max(c, vec3(0.0)), vec3(2.2));
    float Y = max(dot(lin, vec3(0.2126, 0.7152, 0.0722)), 1e-6);
    // Gathered light is never more saturated than the light around it: ease the
    // glass's colour a little towards its own grey where the light gathers (same
    // lightness, same hue), which also leaves vivid colours room to brighten.
    // A thin bar is nearly all edge, so it eases less.
    lin = mix(vec3(Y), lin, 1.0 - 0.25 * mix(0.6, 1.0, wide) * facing * gather);
    float Ls = 116.0 * pow(Y, 1.0 / 3.0) - 16.0;
    float Ln = Ls + dL * smoothstep(0.0, 20.0, Ls);
    float Yn = pow((Ln + 16.0) / 116.0, 3.0);
    // Brighter in the backdrop's own hue, as far as its fullest channel allows;
    // past that a little of the light comes in whiter on soft colours only, so a
    // vivid colour never turns pale or dusty: there the lift stays short instead.
    float mc = max(lin.r, max(lin.g, lin.b));
    vec3 up = lin * min(Yn / Y, 1.0 / max(mc, 1e-6));
    float left = Yn - dot(up, vec3(0.2126, 0.7152, 0.0722));
    float room = dot(vec3(1.0) - up, vec3(0.2126, 0.7152, 0.0722));
    float soft = min(lin.r, min(lin.g, lin.b)) / max(mc, 1e-6);   // 1 grey, 0 vivid
    up += (vec3(1.0) - up) * clamp(left / max(room, 1e-4), 0.0, 0.08 * soft * soft);
    return pow(up, vec3(1.0 / 2.2));
}

vec3 vivid(vec3 c, float k) {
    float l = dot(c, vec3(0.213, 0.715, 0.072));
    return max(mix(vec3(l), c, k), 0.0);
}

void main() {
    vec2 size = vec2(width, height);
    vec2 px = cogl_tex_coord_in[0].st * vec2(tex_w, tex_h) - vec2(org_x, org_y);
    vec2 c = px - size * 0.5;
    vec2 h = max(size * 0.5 - vec2(pad), vec2(1.0));
    // Push sides that touch the screen edge far out, so they get no rim.
    vec2 lo = vec2(edge_l, edge_t) * 4096.0;
    vec2 hi = vec2(edge_r, edge_b) * 4096.0;
    vec2 hh = h + (lo + hi) * 0.5;
    vec2 cc = c + (lo - hi) * 0.5;
    float r = min(radiusAt(c), min(h.x, h.y));
    float sd = sdRoundRect(cc, hh, r);
    vec2 toPtr = vec2(ptr_x, ptr_y) - size * 0.5;
    vec2 L = lightDir(toPtr);

    if (sd > 0.5 && mode > 1.5) {
        cogl_color_out = vec4(0.0);
        return;
    }
    // Outside the pane: only its soft contact shadow, cast away from the light.
    // It also lies under the edge's partly covered pixels, so the rounded edge
    // stays anti-aliased against the shadow.
    float s = 0.0;
    if (shadow > OFF && pad > 1.0 && sd > -0.5) {
        float ds = sdRoundRect(cc + L * (pad * 0.25), hh, r);
        s = 1.0 - smoothstep(-pad * 0.15, pad * 0.85, ds);
        s = shadow * s * s;
    }
    if (sd > 0.5) {
        cogl_color_out = vec4(0.0, 0.0, 0.0, s) * cogl_color_in.a;
        return;
    }

    float cov = clamp(0.5 - sd, 0.0, 1.0);
    float inside = -min(sd, 0.0);
    float gr = min(r * 1.5, min(hh.x, hh.y));
    vec2 n = gradRoundRect(cc, hh, gr);

    // The glass: a slab refr_amt thick lying on the backdrop, its top edge
    // rounded off over the bevel in a quarter ellipse. A thin bar gets a thin
    // bevel, so a panel is not all rim.
    vec2 dp = px - vec2(ptr_x, ptr_y);
    float give = max(90.0, 0.6 * min(h.x, h.y));   // px, how wide a press reaches
    float tch = touch(dp, give);
    float th = refr_amt * (1.0 + tch);
    float slope = 0.0;
    float bevel = min(refr_h, 0.35 * min(h.x, h.y)) * (1.0 + 0.6 * tch);
    float x = 0.0;
    if (bevel > OFF && inside < bevel) {
        x = 1.0 - inside / bevel;                   // 1 at the edge, 0 on the flat top
        float z = sqrt(max(1.0 - x * x, 0.0));
        slope = x / max(z, 0.06);                   // -dz/dr of the rounded edge, outward
    }
    vec2 dome = depth * 0.25 * c / max(h.x, h.y);  // a gently domed top
    vec3 N = normalize(vec3(n * slope + dome + dent(dp, give, tch) + jitter(px), 1.0));
    float F = F0 + (1.0 - F0) * pow(1.0 - N.z, 5.0);
    float crest = 4.0 * x * (1.0 - x);              // peaks halfway down the rounded edge

    if (mode > 2.5) {
        // The rim over an app window. Only its outermost px, where a window draws no
        // content, mirror what lies just beyond the edge: the real wallpaper and
        // windows, in their own colours. Everything further in stays the app's own.
        float band = smoothstep(2.8, 1.2, inside);
        if (band <= 0.0 || hl <= OFF) {
            cogl_color_out = vec4(0.0);
            return;
        }
        vec3 seen = vivid(env(px + n * env_reach * 0.6), 1.3);
        float lobe = pow(max(dot(n, L), 0.0), 8.0) + 0.3 * pow(max(dot(-n, L), 0.0), 8.0);
        float a = clamp(band * min(1.0, hl * 2.2) * (0.45 + 0.6 * lobe), 0.0, 0.8);
        cogl_color_out = vec4(min(seen * (1.0 + 0.3 * lobe), vec3(1.0)) * a, a) * cov * cogl_color_in.a;
        return;
    }
    if (mode > 1.5) {
        // The surface's own light. tex holds a blurred copy of its content.
        // Light from each icon scatters into the glass around it, and light that
        // reflects inside the glass comes out at the nearest rim, mirrored there.
        vec4 g = at(px);
        // Only colour bleeds: white and grey text and icons cast nothing, or the
        // glass turns milky. What is left after taking out the grey is the colour.
        vec3 glow = (g.rgb - vec3(min(g.r, min(g.g, g.b)))) * 2.6;
        // The surface's light, caught inside the glass, leaves at the very edge: a
        // one px hairline in the surface's own colour, equally faint on every surface
        // (a fixed step in display values is a fixed step in lightness).
        float hair = smoothstep(2.2, 0.9, inside) * smoothstep(0.0, 0.6, inside);
        float gm = max(g.r, max(g.g, g.b));
        vec3 tone = mix(vec3(1.0), g.rgb / max(gm, 1e-3), 0.5 * step(0.01, gm));
        vec3 edgeLight = tone * hair * 0.065;
        if (inside < bevel + 4.0) {
            // Content near the edge, mirrored into it by reflection inside the glass.
            vec4 m = at(px - n * (2.0 * inside + 6.0));
            vec3 mc = (m.rgb - vec3(min(m.r, min(m.g, m.b)))) * 1.6;
            glow += mc * (0.25 + 0.75 * F) * max(crest, 1.0 - inside / max(bevel, 1.0)) * 1.2;
        }
        if (light_glass > 0.5) {
            // Light glass is already near white: added light would only clip, and a
            // blue icon would leave a pale cyan halo. There the colour tints the
            // milk instead, like a coloured light seen through frosted glass.
            float k = max(glow.r, max(glow.g, glow.b));
            vec3 hue = glow / max(k, 1e-3);
            float a = (1.0 - exp(-k * bleed * 4.6)) * 0.42;
            cogl_color_out = vec4(hue * a, a) * cov * cogl_color_in.a;
            return;
        }
        // Additive light: no alpha, so nothing under it is dimmed.
        glow = vec3(1.0) - exp(-glow * bleed * 4.6);   // soft-clip; it sits under the theme's veil
        cogl_color_out = vec4(glow + edgeLight, 0.0) * cov * cogl_color_in.a;
        return;
    }

    vec4 col;
    if (th > 0.01) {
        if (dispersion > 0.001 && slope > 0.02 && cheap < 0.5) {
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

    // A full-screen sheet has nothing behind it to show: where the blur thinned the
    // copy at the screen's edge, take its colour at full strength.
    if (solid > 0.5)
        col = vec4(col.rgb / max(col.a, 1e-3), 1.0);

    // Vibrancy and brightness (premultiplied colour).
    col.rgb = min(vivid(col.rgb, saturation) * brightness, vec3(col.a));

    // Beer-Lambert: light crossing the rounded edge slants through more glass than
    // light crossing the flat top, and soda-lime glass takes a little more red
    // and blue than green, so the edge is a shade darker and greener.
    vec3 Rt = refract(vec3(0.0, 0.0, -1.0), N, 1.0 / IOR);
    // Capped, so the edge only tints and never reads as a dark outline.
    float extra = min(th / max(-Rt.z, 0.2) - th, 40.0);
    col.rgb *= exp(-vec3(0.006, 0.0025, 0.004) * extra);

    vec4 t = vec4(tint_r, tint_g, tint_b, 1.0) * tint_a;
    col = t + col * (1.0 - t.a);

    // Adapt to the backdrop: over bright things the glass shades itself a little
    // so text stays readable. Dark glass is never lifted: over a dark backdrop
    // that reads milky.
    if (adapt > OFF || lift > OFF) {
        vec2 q = h * 0.5;
        float bl = dot((at(size * 0.5 + vec2(-q.x, -q.y)).rgb + at(size * 0.5 + vec2(q.x, -q.y)).rgb
                      + at(size * 0.5 + vec2(-q.x, q.y)).rgb + at(size * 0.5 + q).rgb) * 0.25,
                       vec3(0.213, 0.715, 0.072));
        float bright = smoothstep(0.45, 0.85, bl) * adapt;
        float shade = bright * (0.10 + 0.12 * (1.0 - smoothstep(0.0, 10.0, inside)));
        col.rgb = col.rgb * (1.0 - shade);
        // Light glass is milky by nature. Over a dark backdrop its milk thickens, the
        // way frosted glass looks whiter in front of something dark, so it stays light
        // glass and dark text on it stays readable. It raises lightness evenly and
        // keeps the backdrop's colour (only a little of the milk's own tint comes
        // with it): no glow, no brighter edge. Over a bright backdrop it stays thin.
        float m = lift * (1.0 - smoothstep(0.06, 0.5, bl));
        vec3 milk = vec3(milk_r, milk_g, milk_b);
        const vec3 Y = vec3(0.2126, 0.7152, 0.0722);
        float gap = max(dot(milk, Y) - dot(col.rgb / max(col.a, 1e-3), Y), 0.0);
        vec3 up = col.rgb + vec3(gap * m) * col.a;
        col.rgb = min(mix(up, milk * col.a, 0.3 * m), vec3(col.a));
    }

    // A ceiling on brightness, for glass that carries white text over any backdrop
    // (the lock screen). Dark backdrops pass unchanged; brighter ones ease into
    // the ceiling in their own colour, so a white wallpaper gives a calm grey.
    if (ceil_y > OFF) {
        vec3 st = col.rgb / max(col.a, 1e-3);
        float Yl = dot(pow(max(st, vec3(0.0)), vec3(2.2)), vec3(0.2126, 0.7152, 0.0722));
        float knee = 0.6 * ceil_y;
        if (Yl > knee) {
            float room = ceil_y - knee;
            float Yc = knee + room * (1.0 - exp(-(Yl - knee) / room));
            col.rgb *= pow(Yc / Yl, 1.0 / 2.2);
        }
    }

    // Reflection of the real surroundings. A ray mirrored off the rounded edge
    // leaves outwards, so the rim shows the backdrop beyond the edge, and
    // changes as the windows there move. Where the edge faces the light it
    // catches more, in the backdrop's own colours.
    if (hl > OFF && slope > 0.0) {
        vec3 Rf = reflect(vec3(0.0, 0.0, -1.0), N);
        vec2 dir = Rf.xy / max(length(Rf.xy), 1e-4);
        vec3 seen = vivid(env(px + dir * env_reach * length(Rf.xy) + parallax(toPtr, h)), 1.4);
        float lobe = pow(max(dot(n, L), 0.0), 8.0) * crest;
        // The same light, reflected inside, comes out faintly at the opposite edge.
        lobe += pow(max(dot(-n, L), 0.0), 8.0) * crest * 0.3;
        // Near the pointer the rim catches more of the same reflection: a gain on
        // what it really mirrors, in the backdrop's own colours, never added light.
        // Over a black backdrop there is nothing to brighten.
        float near = ptr_k * exp(-dot(dp, dp) / 64800.0);       // sigma 180 px
        float spec = near + tch;
        // The last few px of the rounded edge are near grazing: a thin wet band
        // that mirrors the surroundings almost fully. The same hairline on every
        // surface, thin bars included; seen from close by (the pointer near) the
        // grazing band reaches further in, so what it mirrors can be seen slide.
        float wet = smoothstep(2.4 + 3.5 * near, 0.8, inside) * smoothstep(0.0, 0.6, inside);
        float a = clamp((F * 1.9 + wet * (0.3 + 1.2 * spec)) * min(1.0, hl * 2.2) * (1.0 + 2.5 * lobe + 2.0 * spec),
                        0.0, 0.92);
        // Fade in from the flat top: no hard line where the bevel starts, which a
        // press would tilt into stair-steps.
        a *= smoothstep(0.0, 0.25, x);
        // Restraint: the reflection may light the edge only a little above the glass
        // itself, so a bright backdrop gives no brighter a line than a dark one.
        vec3 base = col.rgb / max(col.a, 1e-3);
        seen = min(seen * (1.15 + 0.8 * lobe + 1.6 * spec), base + vec3(0.05 + 0.03 * lobe) + seen * 0.6 * spec);
        col.rgb = min(col.rgb * (1.0 - a) + seen * col.a * a, vec3(col.a));
        col.rgb = min(caustic(col.rgb / max(col.a, 1e-3), n, L, x, h) * col.a, vec3(col.a));
    }
    // Light glass over a light backdrop has no edge of its own, so a bar can keep
    // a thin dark contact line: darker, never lit. Sides on the screen edge have none.
    if (hair > OFF)
        col.rgb *= 1.0 - hair * smoothstep(1.6, 0.6, inside) * smoothstep(0.0, 0.4, inside);
    col.rgb += vec3(grain(px) / 255.0) * col.a;

    cogl_color_out = (col * cov + vec4(0.0, 0.0, 0.0, s) * (1.0 - cov)) * cogl_color_in.a;
}
`;

const GlassEffect = GObject.registerClass(
class LiquidGlassEffect extends Clutter.ShaderEffect {
    _init() {
        super._init();
        this.set_shader_source(SHADER);
        this._frame = '';
    }

    vfunc_paint_target(node, paintContext) {
        // Map the texture onto the pane exactly, or every edge is smeared out by a px or two.
        const t = this.get_texture();
        const a = this.get_actor();
        if (t && a) {
            const [w, h] = [t.get_width(), t.get_height()];
            const key = `${w}x${h}/${a.width}x${a.height}`;
            if (key !== this._frame) {
                this._frame = key;
                // Clutter grows an effect's frame by 2 px at the top left and 1 px at the bottom right.
                const ox = Math.ceil((w - a.width) / 2), oy = Math.ceil((h - a.height) / 2);
                for (const [k, v] of Object.entries({tex_w: w, tex_h: h, org_x: ox, org_y: oy}))
                    this.set_uniform_value(k, v + 1e-6);
            }
        }
        super.vfunc_paint_target(node, paintContext);
    }

    vfunc_paint(node, paintContext, flags) {
        // Re-rendered for a change in part of it, the pane only gets that part's
        // wallpaper (Mutter paints the wallpaper only inside the frame's redraw
        // area). Its blur and rim reach past that part, and the copy is kept and
        // shown again later, so re-render all of it once more, in full.
        if (flags & Clutter.EffectPaintFlags.ACTOR_DIRTY) {
            this.renders = (this.renders ?? 0) + 1;    // read by the QA tools
            if (this._full)
                this._full = false;
            else
                this.get_actor()?.queueFull?.();
        }
        super.vfunc_paint(node, paintContext, flags);
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
    highlight: 0.55,    // 0..1, edge reflections
    lightAngle: -125,   // degrees, -90 = from the top: where the reflections are strongest
    bleed: 0.6,         // 0..1, how much the content's colours light up the glass
    ceiling: 0,         // 0 = off; else the brightest the glass may get (linear Y, 0..1)
    solid: 0,           // 1: fill the pane fully, for a full-screen sheet
    pointerLight: 0.5,  // 0..1, how far the light turns towards the pointer
    motion: 1,          // 0 or 1: press and open springs
    adapt: 0.35,        // 0..1, how much the glass adjusts to what's behind it
    lift: 0,            // 0..1, light glass: its milk thickens over a dark backdrop
    milk: [0.96, 0.965, 0.98], // the light glass's own body colour, rgb 0..1
    hairline: 0,        // 0..0.3, light glass: a thin dark line at its edge
    shadow: 0,          // 0..1, drawn by the pane itself
});

/**
 * One glass pane. Its owner calls place() with the surface rectangle (in the
 * pane's parent coordinates, plus the matching stage position) whenever the
 * surface moves, and setSources() with the actors to show through it, bottom
 * first. Each source is copied with a Clutter.Clone at its stage position.
 *
 * layer 'full' draws the glass and its reflections. Under a surface with its
 * own content (a menu, the panel), the owner adds a second pane, 'reflections',
 * just above the surface, whose source is that content: it draws the light the
 * icons and text cast into the glass, without dimming them.
 *
 * layer 'rim' sits over an app window and draws only the outermost px of its
 * edge reflection, where the window has no content.
 */
const LAYERS = {full: 0, glass: 1, reflections: 2, rim: 3};
const ENV_REACH = 32;   // px the rim sees beyond the edge
const GLOW_BLUR = 30;   // px the content's light spreads

// While a window is dragged or resized, every pane re-renders each frame, so they
// all drop to fewer taps until shortly after it settles. A still frame looks the same.
const panes = new Set();
let cheapTimer = 0;

export function moving(on) {
    if (cheapTimer) {
        GLib.source_remove(cheapTimer);
        cheapTimer = 0;
    }
    if (on) {
        panes.forEach(p => p._setCheap(true));
        return;
    }
    cheapTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 150, () => {
        cheapTimer = 0;
        panes.forEach(p => p._setCheap(false));
        return GLib.SOURCE_REMOVE;
    });
}

// Windows mid-animation (opening, minimizing, closing): panes that show them behind
// glass stop copying them until they land, then copy them once more. Otherwise every
// frame of the animation re-renders the glass of every window above them.
const frozen = new Set();
let freezing = true;

// For QA: compare with and without the freeze in one session.
export function qaFreeze(on) {
    freezing = Boolean(on);
}

export function freezeSource(actor) {
    if (!freezing || frozen.has(actor))
        return;
    frozen.add(actor);
    panes.forEach(p => p._clones.has(actor) && p._syncClones());
}

export function thawSource(actor) {
    if (!frozen.delete(actor))
        return;
    panes.forEach(p => p._clones.has(actor) && p._syncClones());
}

/**
 * A window's effect (open, minimize, restore, close; GNOME's or ours) just ended
 * over the stage rectangle r: redraw all of each pane it touched. Its frames only
 * redrew the window's own spot, and a pane drawn that way can keep a patch there.
 */
export function windowLanded(r) {
    for (const p of panes) {
        if (!p._stage || !p._size || !p.mapped)
            continue;
        const [x, y] = p._stage, [w, h] = p._size;
        if (r.x < x + w && r.x + r.width > x && r.y < y + h && r.y + r.height > y)
            p.queueFull();
    }
}

export function stopMoving() {
    if (cheapTimer)
        GLib.source_remove(cheapTimer);
    cheapTimer = 0;
}

export const GlassPane = GObject.registerClass(
class LiquidGlassPane extends Clutter.Actor {
    _init(layer = 'full') {
        // Hidden until placed: an effect on an empty actor asks Cogl for a 0×0 texture.
        super._init({name: `liquid-glass-${layer}`, clip_to_allocation: true, reactive: false, visible: false});
        this._layer = LAYERS[layer] ?? 0;
        this._blur = new Shell.BlurEffect({mode: Shell.BlurMode.ACTOR, radius: 0, brightness: 1});
        if (this._layer === LAYERS.reflections) {
            // Its source is the surface's own content; a black background keeps it
            // painted (an empty actor gets no offscreen) and adds no light.
            this.background_color = new Cogl.Color({red: 0, green: 0, blue: 0, alpha: 255});
        }
        // The lens goes on first: the first effect is the outermost, so the lens
        // reads the blurred backdrop and its edges and reflections stay sharp.
        this._glass = new GlassEffect();
        this.add_effect_with_name('liquid-glass-lens', this._glass);
        this.add_effect_with_name('liquid-glass-blur', this._blur);
        this._look = {...DEFAULT_LOOK};
        this._radii = [0, 0, 0, 0];
        this._pad = 0;
        this._stage = [0, 0];
        this._size = [1, 1];
        this._clones = new Map();   // source actor -> clone
        this._placed = '';
        this._edges = '';
        this.setEdges([false, false, false, false]);
        this._cheap = false;
        this._motion = {sx: 0, sy: 0, k: 0, press: 0, open: 1};
        this._applyLook();
        panes.add(this);
        this._fullLater = 0;
        this.connect('destroy', () => {
            if (this._fullLater)
                global.compositor.get_laters().remove(this._fullLater);
            this._fullLater = 0;
            panes.delete(this);
            this._clones.clear();
        });
    }

    get pad() {
        return this._pad;
    }

    /** Redraw all of the pane (see LiquidGlassEffect.vfunc_paint), before the next frame. */
    queueFull() {
        if (this._fullLater)
            return;
        this._fullLater = global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
            this._fullLater = 0;
            this._glass._full = true;
            this.queue_redraw();
            return GLib.SOURCE_REMOVE;
        });
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
                const ids = [src.connect('destroy', () => {
                    if (this._clones.get(src) === clone) {
                        this._clones.delete(src);
                        clone.destroy();
                    }
                })];
                // The wallpaper paints only inside the frame's redraw area, so a pane
                // re-rendered for a small change in a window behind would lose the
                // wallpaper around it, and its blur and rim would read black there.
                // Redraw the whole pane whenever a window behind changes.
                if (GObject.signal_lookup('damaged', src.constructor.$gtype))
                    ids.push(src.connect('damaged', () => frozen.has(src) || this.queueFull()));
                // A source made in the same frame (the wallpaper, right after the
                // extension is turned on) has no place yet: copy it once it has one.
                if (!src.meta_window)
                    ids.push(src.connect('notify::allocation', () => this._stage && this._syncClones()));
                clone.connect('destroy', () => {
                    if (this._clones.get(src) === clone)
                        this._clones.delete(src);
                    for (const id of ids) {
                        try {
                            src.disconnect(id);
                        } catch {}   // the source is already gone
                    }
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

    /** Which sides touch the screen edge ([left, top, right, bottom], booleans): those get no rim. */
    setEdges(edges) {
        const key = edges.map(Number).join();
        if (key === this._edges)
            return;
        this._edges = key;
        const [l, t, r, b] = edges.map(e => (e ? 1 : 0));
        this._glass.setFloats({edge_l: l, edge_t: t, edge_r: r, edge_b: b});
    }

    _setCheap(on) {
        if (on === this._cheap)
            return;
        this._cheap = on;
        this._glass.setFloats({cheap: on ? 1 : 0});
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
        const [W, H] = global.stage.get_size();
        this._glass.setFloats({
            valid_x0: Math.max(0, -this._stage[0]), valid_y0: Math.max(0, -this._stage[1]),
            valid_x1: Math.min(this._size[0], W - this._stage[0]), valid_y1: Math.min(this._size[1], H - this._stage[1]),
        });
        this._syncClones();
        this._applyShape();
        if (this._motion.k > 0)
            this._applyMotion();   // the pointer is held in this pane's own px
    }

    _syncClones() {
        for (const [src, clone] of this._clones) {
            if (!src.get_stage() || frozen.has(src)) {
                if (clone.visible)
                    this.queueFull();
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
            const [cx, cy] = [Math.round(bx - this._stage[0]), Math.round(by - this._stage[1])];
            const [cw, ch] = [r ? r.width : src.width, r ? r.height : src.height];
            // Moved behind the pane: redraw all of it, for the same reason as 'damaged' above.
            const moved = clone.x !== cx || clone.y !== cy || clone.width !== cw || clone.height !== ch || !clone.visible;
            clone.set_position(cx, cy);
            clone.set_size(cw, ch);
            clone.show();
            if (moved)
                this.queueFull();
        }
    }

    _applyLook() {
        const L = this._look;
        const top = this._layer === LAYERS.reflections;
        // The reflections layer blurs a copy of the content into a glow map.
        // The rim over a window mirrors the backdrop sharp: it needs no blur of its own.
        const blur = top ? GLOW_BLUR : this._layer === LAYERS.rim ? 0 : Math.max(0, Math.min(100, L.blur));
        this._blur.radius = blur;
        this._blur.enabled = blur > 0.5;
        // Room around the surface for the blur and the edge reflections to see past
        // the edge, and for the shadow.
        this._pad = Math.ceil(Math.min(64, Math.max(blur, top ? 0 : blur * 0.5 + ENV_REACH, L.shadow > 0 ? 18 : 0, 2)));
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
            solid: L.solid > 0.5 ? 1 : 0,
            ceil_y: this._layer >= LAYERS.reflections ? 0 : Math.max(0, Math.min(1, L.ceiling)),
            hl_x: Math.cos(a), hl_y: Math.sin(a),
            env_reach: ENV_REACH,
            margin: blur * 0.5,
            adapt: Math.max(0, Math.min(1, L.adapt)),
            // The content's light layer and a window's rim have no body: they never thicken.
            lift: this._layer >= LAYERS.reflections ? 0 : Math.max(0, Math.min(1, L.lift)),
            milk_r: L.milk[0], milk_g: L.milk[1], milk_b: L.milk[2],
            light_glass: L.lift > 0 ? 1 : 0,
            hair: this._layer >= LAYERS.reflections ? 0 : Math.max(0, Math.min(0.3, L.hairline)),
            bleed: this._layer === LAYERS.reflections ? Math.max(0, Math.min(1, L.bleed)) : 0,
            shadow: this._layer === LAYERS.reflections ? 0 : Math.max(0, Math.min(1, L.shadow)),
            mode: this._layer,
            cheap: this._cheap ? 1 : 0,
        });
        this._applyMotion();
        this._applyShape();
    }

    // Pointer light, parallax, press and open: set by the motion controller in
    // motion.js. Only lens uniforms change, so the blur is not re-run.
    setMotion(m) {
        Object.assign(this._motion, m);
        this._applyMotion();
    }

    _applyMotion() {
        const L = this._look, m = this._motion;
        const [ox, oy] = this._stage ?? [0, 0];
        this._glass.setFloats({
            ptr_x: m.sx - ox, ptr_y: m.sy - oy, ptr_k: Math.max(0, Math.min(1, m.k)),
            press: Math.max(0, Math.min(1, m.press)),
            refr_h: Math.max(0, L.refraction) * Math.max(0, m.open),
            // Pressed, the slab gives: a deeper bend and a fuller dome you can see.
            refr_amt: Math.max(0, L.bend) * (1 + 0.3 * m.press),
            depth: Math.max(0, Math.min(1, L.depth + 0.25 * m.press)),
        });
        // All of the pane shows the new shape in the same frame, not only the part
        // the stage happens to redraw (around a pressed button, say).
        this.queue_redraw();
    }

    _applyShape() {
        const [tl, tr, br, bl] = this._radii;
        this._glass.setFloats({
            width: this._size[0], height: this._size[1], pad: this._pad,
            r_tl: tl, r_tr: tr, r_br: br, r_bl: bl,
        });
    }
});
