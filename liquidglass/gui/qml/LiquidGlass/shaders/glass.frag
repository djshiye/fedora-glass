#version 440
// Liquid Glass surface, with the same physical optics as the Shell extension
// (glass.js): a glass slab whose top edge rounds off in a quarter circle, after
// Kyant's AndroidLiquidGlass (Apache License 2.0). View rays are refracted by
// Snell's law (IOR 1.5) through the slab to the backdrop; the index follows
// Cauchy's equation at five wavelengths for dispersion; Fresnel (Schlick)
// weights the reflection of a studio in front of the screen (a bright soft
// box top left, a dim ceiling, a dark floor); Beer-Lambert absorption darkens
// and greens the slanting paths through the edge. `source` is the (already
// blurred) backdrop lying exactly under the item.
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
    float sheen;       // soft top-down gloss, 0..1
    vec4 tint;
    vec4 rim;
    vec4 edge;         // unused: the optics draw the edge
    float mode;        // 0 = everything, 1 = body only, 2 = rim and edge only
    float depth;       // 0..1, how domed the top is
};
layout(binding = 1) uniform sampler2D source;

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

vec2 throughGlass(vec3 N, float n, float th) {
    vec3 R = refract(vec3(0.0, 0.0, -1.0), N, 1.0 / n);
    return R.xy * th / max(-R.z, 0.2);
}

float cauchy(float um, float B) {
    return IOR + B * (1.0 / (um * um) - 1.0 / 0.3025);
}

const vec2 LIGHT = vec2(-0.5574, -0.8302);   // from the top left

vec3 softbox(vec3 R) {
    vec3 K = normalize(vec3(LIGHT, 0.45));
    return vec3(1.0, 0.98, 0.95) * 18.0 * smoothstep(0.88, 0.991, dot(R, K));
}

vec3 studio(vec3 R) {
    if (R.z < 0.0)
        return vec3(0.22);
    float up = clamp(-R.y, 0.0, 1.0);
    float room = 0.06 + 0.5 * up * up;
    float bounce = 0.7 * smoothstep(0.75, 0.97, dot(R, normalize(vec3(-LIGHT, 0.45))));
    return vec3(0.92, 0.96, 1.0) * (room + bounce) + softbox(R);
}

void main() {
    vec2 c = size * 0.5;
    vec2 p = qt_TexCoord0 * size - c;
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

    float th = refraction;
    float slope = 0.0;
    float bev = min(bezel, min(c.x, c.y));
    if (bev > 0.0 && inside < bev) {
        float x = 1.0 - inside / bev;
        float z = sqrt(max(1.0 - x * x, 0.0));
        slope = x / max(z, 0.06);
    }
    vec2 dome = depth * 0.25 * p / max(c.x, c.y);
    vec3 N = normalize(vec3(n * slope + dome, 1.0));

    vec2 px = c + p / max(magnify, 0.01);
    vec4 s = vec4(0.0);
    if (mode < 1.5) {
        if (th > 0.01 && fringe > 0.001 && slope > 0.02) {
            float B = 0.08 * fringe;
            vec4 s450 = texture(source, (px + throughGlass(N, cauchy(0.45, B), th)) / size);
            vec4 s500 = texture(source, (px + throughGlass(N, cauchy(0.50, B), th)) / size);
            vec4 s550 = texture(source, (px + throughGlass(N, IOR, th)) / size);
            vec4 s600 = texture(source, (px + throughGlass(N, cauchy(0.60, B), th)) / size);
            vec4 s650 = texture(source, (px + throughGlass(N, cauchy(0.65, B), th)) / size);
            s.r = (0.05 * s450.r + 0.15 * s550.r + 0.85 * s600.r + s650.r) / 2.05;
            s.g = (0.6 * s500.g + s550.g + 0.35 * s600.g) / 1.95;
            s.b = (s450.b + 0.4 * s500.b) / 1.4;
            s.a = (s450.a + s500.a + s550.a + s600.a + s650.a) / 5.0;
        } else if (th > 0.01) {
            s = texture(source, (px + throughGlass(N, IOR, th)) / size);
        } else {
            s = texture(source, px / size);
        }
        vec3 Rt = refract(vec3(0.0, 0.0, -1.0), N, 1.0 / IOR);
        s.rgb *= exp(-vec3(0.018, 0.008, 0.012) * (th / max(-Rt.z, 0.2) - th));
    }

    vec4 col = s;
    if (mode < 1.5) {
        col = over(col, tint, 1.0);
        float gloss = sheen * smoothstep(0.55, 0.0, qt_TexCoord0.y) * 0.16;
        col = over(col, vec4(1.0), gloss);
    }
    if (mode > 0.5 && mode < 1.5) {
        fragColor = col * cov * qt_Opacity;
        return;
    }

    // Reflections of a studio in front of the screen, weighted by Fresnel; the
    // rim colour's alpha is their strength. No drawn outline: the edge is lit
    // where it faces the light and shaded where it faces the floor.
    float hl = rim.a;
    float F = F0 + (1.0 - F0) * pow(1.0 - N.z, 5.0);
    vec3 refl = studio(reflect(vec3(0.0, 0.0, -1.0), N)) * F;
    refl += softbox(reflect(vec3(0.0, 0.0, -1.0), vec3(-N.xy, N.z))) * (1.0 - F) * 0.05;
    float a = clamp(F * hl, 0.0, 1.0);
    col = vec4(min(col.rgb * (1.0 - a) + refl * hl, vec3(1.0)), col.a * (1.0 - a) + a);

    fragColor = col * cov * qt_Opacity;
}
