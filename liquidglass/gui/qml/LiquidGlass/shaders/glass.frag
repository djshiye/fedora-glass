#version 440
// Liquid Glass surface: refracting bezel, tint, 1px edge and a directional
// specular rim, all inside an antialiased rounded rectangle. `source` is the
// (already blurred) backdrop that lies exactly under the item.
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 size;
    float radius;
    float bezel;       // width of the refracting band along the edge, px
    float refraction;  // how far the bezel bends the backdrop, px
    float magnify;     // >1 magnifies the backdrop like a lens
    float fringe;      // chromatic split of the bent light, 0..1
    float rimWidth;    // px
    float sheen;       // soft top-down gloss, 0..1
    vec4 tint;
    vec4 rim;
    vec4 edge;
    float mode;        // 0 = everything, 1 = body only, 2 = rim and edge only
};
layout(binding = 1) uniform sampler2D source;

float sdRoundRect(vec2 p, vec2 b, float r) {
    vec2 q = abs(p) - b + vec2(r);
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

// Qt hands colour uniforms over premultiplied; k scales the layer's strength.
vec4 over(vec4 dst, vec4 c, float k) {
    return c * k + dst * (1.0 - c.a * k);
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

    vec2 n = vec2(sdRoundRect(p + vec2(0.5, 0.0), c, r) - sdRoundRect(p - vec2(0.5, 0.0), c, r),
                  sdRoundRect(p + vec2(0.0, 0.5), c, r) - sdRoundRect(p - vec2(0.0, 0.5), c, r));
    float nl = length(n);
    n = nl > 1e-4 ? n / nl : vec2(0.0);

    float inside = -d;
    float t = clamp(inside / max(bezel, 1.0), 0.0, 1.0);
    float u = 1.0 - t;
    float bend = 1.0 - sqrt(max(0.0, 1.0 - u * u));   // circular lens profile

    vec2 uv = (c + p / max(magnify, 0.01)) / size;
    vec2 off = -n * refraction * bend / size;
    vec4 s;
    if (mode > 1.5) {
        s = vec4(0.0);
    } else if (fringe > 0.001) {
        vec2 f = off * fringe;
        vec4 g = texture(source, uv + off);
        s = vec4(texture(source, uv + off + f).r, g.g, texture(source, uv + off - f).b, g.a);
    } else {
        s = texture(source, uv + off);
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

    float edgeLine = 1.0 - smoothstep(0.0, 1.25, inside);
    col = over(col, edge, edgeLine);

    float up = max(dot(n, normalize(vec2(-0.4, -1.0))), 0.0);
    float down = max(dot(n, normalize(vec2(0.4, 1.0))), 0.0);
    float rimLine = 1.0 - smoothstep(0.0, max(rimWidth, 0.5), inside);
    float glow = u * u * u * 0.35;
    float rimAmt = clamp((rimLine + glow) * (0.18 + 0.82 * pow(up, 1.4) + 0.38 * pow(down, 2.0)), 0.0, 1.0);
    col = over(col, rim, rimAmt);

    fragColor = col * cov * qt_Opacity;
}
