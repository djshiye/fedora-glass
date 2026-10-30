#version 440
// Liquid Glass surface, with the same optics as the Shell extension (glass.js):
// a glass slab whose top edge rounds off in a quarter circle, after Kyant's
// AndroidLiquidGlass (Apache License 2.0). View rays are refracted by Snell's
// law (IOR 1.5) through the slab to the backdrop; the index follows Cauchy's
// equation at five wavelengths for dispersion; Beer-Lambert absorption darkens
// and greens the slanting paths through the edge. Nothing is painted on: the
// edge reflects the real backdrop beyond it (weighted by Fresnel), and the
// content's own colours bleed into the glass around it.
// `source` is the (already blurred) backdrop under the item plus `pad` px on
// every side; `content` is a blurred copy of what the item holds.
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 size;
    float radius;
    float bezel;       // width of the refracting band along the edge, px
    float refraction;  // thickness of the glass slab, px
    float magnify;     // >1 magnifies the backdrop like a lens
    float fringe;      // dispersion, 0..1
    float rimWidth;    // unused: the optics draw the edge
    float sheen;       // unused: no painted light
    vec4 tint;
    vec4 rim;          // alpha: strength of the edge reflections
    vec4 edge;         // unused: the optics draw the edge
    float mode;        // 0 = everything, 1 = body only, 2 = edge and bleed only, 3 = bleed only
    float depth;       // 0..1, how domed the top is
    float bleed;       // 0..1, how much the content's colours light up the glass
    float pad;         // px of backdrop around the item in `source`
};
layout(binding = 1) uniform sampler2D source;
layout(binding = 2) uniform sampler2D content;

float sdRoundRect(vec2 p, vec2 b, float r) {
    vec2 q = abs(p) - b + vec2(r);
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

vec2 gradRoundRect(vec2 p, vec2 b, float r) {
    vec2 q = abs(p) - (b - vec2(r));
    vec2 s = vec2(p.x < 0.0 ? -1.0 : 1.0, p.y < 0.0 ? -1.0 : 1.0);
    if (q.x >= 0.0 || q.y >= 0.0)
        return s * normalize(max(q, 0.0) + vec2(1e-4));
    float gx = step(q.y, q.x);
    return s * vec2(gx, 1.0 - gx);
}

// Qt hands colour uniforms over premultiplied; k scales the layer's strength.
vec4 over(vec4 dst, vec4 c, float k) {
    return c * k + dst * (1.0 - c.a * k);
}

const float IOR = 1.5;
const float F0 = 0.04;
const vec2 LIGHT = vec2(-0.5574, -0.8302);   // the room is brighter top left
const float REACH = 48.0;                    // px the edge sees beyond itself

vec4 at(vec2 p) {
    return texture(source, (p + vec2(pad)) / (size + vec2(2.0 * pad)));
}

vec2 throughGlass(vec3 N, float n, float th) {
    vec3 R = refract(vec3(0.0, 0.0, -1.0), N, 1.0 / n);
    return R.xy * th / max(-R.z, 0.2);
}

float cauchy(float um, float B) {
    return IOR + B * (1.0 / (um * um) - 1.0 / 0.3025);
}

// Premultiplied: alpha tells how much of the sample found a backdrop at all
// (past the preview's own edge there is none).
vec4 env(vec2 p) {
    float sp = REACH * 0.3;
    return at(p) * 0.4
        + (at(p + vec2(sp, 0.0)) + at(p - vec2(sp, 0.0))
         + at(p + vec2(0.0, sp)) + at(p - vec2(0.0, sp))) * 0.15;
}

vec3 vivid(vec3 c, float k) {
    float l = dot(c, vec3(0.213, 0.715, 0.072));
    return max(mix(vec3(l), c, k), 0.0);
}

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

// Caustic: the rounded edge focuses light onto the backdrop on the side away
// from the light, a soft band of the backdrop's own light. The lift is even in
// lightness (L*), so every shaded side reads the same; over black there is
// nothing to lift. c is a straight (not premultiplied) colour.
vec3 caustic(vec3 c, vec2 n, float x, vec2 h) {
    float facing = smoothstep(-0.25, 0.35, dot(-n, LIGHT));
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

// The content's light: each coloured icon lights the glass around it, and light
// caught inside the glass comes out at the nearest edge, mirrored there. Only
// colour bleeds (white and grey cast nothing, or the glass turns milky); the
// surface's light also leaves at the very edge as a faint one px hairline.
vec3 glow(vec2 px, vec2 n, float inside, float bev, float F, float crest) {
    vec4 g = texture(content, px / size);
    vec3 c = (g.rgb - vec3(min(g.r, min(g.g, g.b)))) * 2.86;
    if (inside < bev + 4.0) {
        vec4 m = texture(content, (px - n * (2.0 * inside + 6.0)) / size);
        vec3 mc = (m.rgb - vec3(min(m.r, min(m.g, m.b)))) * 1.6;
        c += mc * (0.25 + 0.75 * F) * max(crest, 1.0 - inside / max(bev, 1.0)) * 1.2;
    }
    float hair = smoothstep(2.2, 0.9, inside) * smoothstep(0.0, 0.6, inside);
    float gm = max(g.r, max(g.g, g.b));
    vec3 tone = mix(vec3(1.0), g.rgb / max(gm, 1e-3), 0.5 * step(0.01, gm));
    return vec3(1.0) - exp(-c * bleed * 2.6) + tone * hair * 0.065;
}

void main() {
    vec2 c = size * 0.5;
    vec2 px0 = qt_TexCoord0 * size;
    vec2 p = px0 - c;
    float r = min(radius, min(c.x, c.y));
    float d = sdRoundRect(p, c, r);
    float cov = clamp(0.5 - d, 0.0, 1.0);
    if (cov <= 0.0) {
        fragColor = vec4(0.0);
        return;
    }

    float gr = min(r * 1.5, min(c.x, c.y));
    vec2 n = gradRoundRect(p, c, gr);
    float inside = -d;

    // A thin bar gets a thin bevel, so a panel is not all rim.
    float th = refraction;
    float slope = 0.0;
    float x = 0.0;
    float bev = min(bezel, 0.35 * min(size.x, size.y));
    if (bev > 0.0 && inside < bev) {
        x = 1.0 - inside / bev;
        float z = sqrt(max(1.0 - x * x, 0.0));
        slope = x / max(z, 0.06);
    }
    vec2 dome = depth * 0.25 * p / max(c.x, c.y);
    vec3 N = normalize(vec3(n * slope + dome + jitter(px0), 1.0));
    float F = F0 + (1.0 - F0) * pow(1.0 - N.z, 5.0);
    float crest = 4.0 * x * (1.0 - x);

    if (mode > 2.5) {
        vec3 b = glow(px0, n, inside, bev, F, crest);
        fragColor = vec4(b, 0.0) * cov * qt_Opacity;     // added light: nothing under it dims
        return;
    }

    vec2 px = c + p / max(magnify, 0.01);
    vec4 col = vec4(0.0);
    if (mode < 1.5) {
        if (th > 0.01 && fringe > 0.001 && slope > 0.02) {
            float B = 0.08 * fringe;
            vec4 s450 = at(px + throughGlass(N, cauchy(0.45, B), th));
            vec4 s500 = at(px + throughGlass(N, cauchy(0.50, B), th));
            vec4 s550 = at(px + throughGlass(N, IOR, th));
            vec4 s600 = at(px + throughGlass(N, cauchy(0.60, B), th));
            vec4 s650 = at(px + throughGlass(N, cauchy(0.65, B), th));
            col.r = (0.05 * s450.r + 0.15 * s550.r + 0.85 * s600.r + s650.r) / 2.05;
            col.g = (0.6 * s500.g + s550.g + 0.35 * s600.g) / 1.95;
            col.b = (s450.b + 0.4 * s500.b) / 1.4;
            col.a = (s450.a + s500.a + s550.a + s600.a + s650.a) / 5.0;
        } else if (th > 0.01) {
            col = at(px + throughGlass(N, IOR, th));
        } else {
            col = at(px);
        }
        vec3 Rt = refract(vec3(0.0, 0.0, -1.0), N, 1.0 / IOR);
        col.rgb *= exp(-vec3(0.006, 0.0025, 0.004) * min(th / max(-Rt.z, 0.2) - th, 40.0));
        col.rgb = min(caustic(col.rgb / max(col.a, 1e-3), n, x, c) * col.a, vec3(col.a));
        col = over(col, tint, 1.0);
    }
    if (mode > 0.5 && mode < 1.5) {
        col.rgb += vec3(grain(px0) / 255.0) * col.a;
        fragColor = col * cov * qt_Opacity;
        return;
    }

    // Reflection of the real surroundings: a ray mirrored off the rounded edge
    // leaves outwards, so the edge shows the backdrop beyond it, in its own
    // colours, brighter where the edge faces the brighter side of the room.
    float hl = rim.a;
    vec3 seen = vec3(0.0);
    float a = 0.0;
    if (hl > 0.0 && slope > 0.0) {
        vec3 Rf = reflect(vec3(0.0, 0.0, -1.0), N);
        vec2 dir = Rf.xy / max(length(Rf.xy), 1e-4);
        vec4 e = env(px0 + dir * REACH * length(Rf.xy));
        seen = vivid(e.rgb / max(e.a, 1e-3), 1.4);
        float lobe = pow(max(dot(n, LIGHT), 0.0), 8.0) * crest;
        lobe += pow(max(dot(-n, LIGHT), 0.0), 8.0) * crest * 0.3;
        // The last few px of the rounded edge are near grazing: a thin wet band
        // that mirrors the surroundings almost fully.
        float wet = smoothstep(2.4, 0.8, inside) * smoothstep(0.0, 0.6, inside);
        a = clamp((F * 1.9 + wet * 0.3) * min(1.0, hl * 2.2) * (1.0 + 2.5 * lobe), 0.0, 0.92) * clamp(e.a, 0.0, 1.0);
        // Restraint: the reflection lights the edge only a little above the glass
        // itself, so a bright backdrop gives no brighter a line than a dark one.
        vec4 under = mode > 1.5 ? at(px0) : col;
        vec3 base = under.rgb / max(under.a, 1e-3);
        seen = min(seen * (1.15 + 0.8 * lobe), base + vec3(0.05 + 0.03 * lobe));
    }
    vec3 b = mode > 1.5 ? glow(px0, n, inside, bev, F, crest) : vec3(0.0);
    if (mode > 1.5) {
        // Over the content: the reflection blends in, the bleed adds light.
        fragColor = vec4(min(seen * a, vec3(1.0)) + b, a) * cov * qt_Opacity;
        return;
    }
    col.rgb = min(col.rgb * (1.0 - a) + seen * col.a * a, vec3(col.a));
    col.rgb += vec3(grain(px0) / 255.0) * col.a;
    fragColor = col * cov * qt_Opacity;
}
