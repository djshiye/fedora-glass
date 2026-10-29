#version 440
// Specular rim and 1px edge for flat glass (cards, buttons): bright along the
// top edge, a faint return along the bottom, nothing in between.
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 size;
    float radius;
    float rimWidth;
    vec4 rim;
    vec4 edge;
};

float sdRoundRect(vec2 p, vec2 b, float r) {
    vec2 q = abs(p) - b + vec2(r);
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

void main() {
    vec2 c = size * 0.5;
    vec2 p = qt_TexCoord0 * size - c;
    float r = min(radius, min(c.x, c.y));
    float d = sdRoundRect(p, c, r);
    float cov = clamp(0.5 - d, 0.0, 1.0);
    if (cov <= 0.0) { fragColor = vec4(0.0); return; }
    vec2 n = vec2(sdRoundRect(p + vec2(0.5, 0.0), c, r) - sdRoundRect(p - vec2(0.5, 0.0), c, r),
                  sdRoundRect(p + vec2(0.0, 0.5), c, r) - sdRoundRect(p - vec2(0.0, 0.5), c, r));
    float nl = length(n);
    n = nl > 1e-4 ? n / nl : vec2(0.0);
    float inside = -d;
    float edgeLine = 1.0 - smoothstep(0.0, 1.25, inside);
    float up = max(dot(n, normalize(vec2(-0.3, -1.0))), 0.0);
    float down = max(dot(n, normalize(vec2(0.3, 1.0))), 0.0);
    float rimLine = 1.0 - smoothstep(0.0, max(rimWidth, 0.5), inside);
    float k = rimLine * clamp(0.1 + 0.9 * pow(up, 1.6) + 0.3 * pow(down, 2.0), 0.0, 1.0);
    vec4 col = edge * edgeLine;
    col = rim * k + col * (1.0 - rim.a * k);
    fragColor = col * cov * qt_Opacity;
}
