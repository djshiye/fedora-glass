#version 440
// Fedora Glass surface, with the same optics as the Shell extension (glass.js):
// a glass slab whose top edge rounds off in a squircle, after Kyant's
// AndroidLiquidGlass (Apache License 2.0). View rays are refracted by Snell's
// law (IOR 1.5) through the slab to the backdrop; the index follows Cauchy's
// equation at five wavelengths for dispersion; Beer-Lambert absorption darkens
// and greens the slanting paths through the edge. Nothing is painted on: the
// edge reflects the real backdrop beyond it (weighted by Fresnel), and the
// content's own colours bleed into the glass around it. One thing is painted:
// a crisp line of light about 1.5 px wide along the very edge (rimLine), as on
// Apple's glass, brightest at the corners facing the light.
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
    vec2 ptr;          // the pointer, in px on this item (the pointer light setting)
    float ptrK;        // 0..1, how far the light turns towards the pointer
    float ptrReach;    // px, how far around the pointer the rim catches more (180 desktop px)
    vec2 pressAt;      // where the glass is pressed, px on this item
    float press;       // 0..1, how far it is pressed in (a spring, as in motion.js)
    float liquid;      // how far the glass gives: 1 is the original feel (glass.js)
    vec2 pull;         // px the press is drawn out towards the pointer while dragged
    float pressScale;  // preview px per desktop px: the give reaches as far as on the desktop
    float frost;       // 0..1, weather frost (glass.js frost): the glass mists over in the cold
    float flakes;      // 0..1, and below freezing frost grows in from the edges
    float iceScale;    // preview px per desktop px, so the frost is the desktop's size
    float iceArm;      // the frost's shape (frostmath.js crystalFor): side branches 0..1,
    float iceTwig;     // branches on those 0..1,
    float iceSize;     // and how big it grows 0..1
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
const vec2 ROOM = vec2(-0.5574, -0.8302);    // the room is brighter top left
// Where the light comes from at this pixel: the room's light, turned towards the
// pointer while it is near (as motion.js and glass.js do on the desktop). Set in main().
vec2 LIGHT = ROOM;
const float REACH = 48.0;                    // px the edge sees beyond itself

// The squircle edge profile's slope, as in glass.js.
float squircleSlope(float x) {
    float x3 = x * x * x;
    float k = max(1.0 - x3 * x, 0.0);
    return x3 / max(pow(k, 0.75), 0.03);
}

// The thin line of light along the very edge, as in glass.js. 0..1.
// As in the Shell's glass.js: iOS 26's rim, gone 1.2 px in, on the sides facing the
// light and their reflection, fading over the corners between, over a half px edge.
float rimLine(float inside, vec2 n) {
    float facing = abs(dot(n, LIGHT));
    float along = inside / (1.22 * (1.0 + 0.25 * facing));
    float line = along < 1.0 ? pow(facing, 1.5) * (1.0 - pow(along, 1.5)) * smoothstep(0.0, 0.25, inside) : 0.0;
    float edge = smoothstep(0.0, 0.2, inside) * (1.0 - smoothstep(0.4, 0.9, inside));
    return line * 0.42 + edge * 0.12;
}

// The glint, as in glass.js: a light caught on the curve of the edge, a few px in,
// bright at the corner towards the light and (at 45 %) the one across from it,
// almost nothing along straight sides. 0..1.
float glint(float inside, vec2 n, float w) {
    float d = dot(n, LIGHT);
    float corner = smoothstep(0.15, 0.85, 1.0 - abs(abs(n.x) - abs(n.y)));
    float lobe = (pow(max(d, 0.0), 8.0) + 0.45 * pow(max(-d, 0.0), 8.0)) * mix(0.3, 1.0, corner);
    float u = (inside - w) / (0.5 * w);
    return lobe * exp(-u * u) * smoothstep(0.2, 1.0, inside);
}

vec4 at(vec2 p) {
    return texture(source, (p + vec2(pad)) / (size + vec2(2.0 * pad)));
}

vec2 throughGlass(vec3 N, float n, float th) {
    vec3 R = refract(vec3(0.0, 0.0, -1.0), N, 1.0 / n);
    return R.xy * th / max(-R.z, 0.2);
}

// How far a ray through the squircle edge moves sideways, per px of glass, x of
// the way down the bevel, and the share of it that keeps the backdrop from folding
// over (lines turned into hairpin loops near the edge): as in glass.js.
float bendAt(float x) {
    vec3 R = refract(vec3(0.0, 0.0, -1.0), normalize(vec3(squircleSlope(x) * 1.6, 0.0, 1.0)), 1.0 / IOR);
    return -R.x / max(-R.z, 0.2);
}

float unfold(float x, float th, float bevel) {
    float K = 0.85 * bevel / max(th, 1e-3);
    float lo = 0.0, hi = 1.0;
    for (int i = 0; i < 9; i++) {
        float m = 0.5 * (lo + hi);
        if (bendAt(m + 0.004) - bendAt(m - 0.004) > K * 0.008)
            hi = m;
        else
            lo = m;
    }
    if (x <= lo)
        return 1.0;
    return min(1.0, (bendAt(lo) + K * (x - lo)) / max(bendAt(x), 1e-5));
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

// Pressed, the glass gives under the finger, as in glass.js touch() and dent():
// around the press point the edge rounds off wider and steeper and the top tilts in.
float touch(vec2 dp, float s) {
    float pl = length(pull);
    if (pl > 0.5) {
        vec2 u = pull / pl;
        float along = dot(dp, u);
        float ahead = along / (1.0 + pl / s * step(0.0, along));
        dp = u * ahead + (dp - u * along);
    }
    return press * exp(-dot(dp, dp) / (2.0 * s * s));
}

// The weather frost, word for word as frostmath.js ICE_GLSL (a test checks):
// ---- weather frost: how ice really forms on cold glass (frostmath.js) ----
// A hash with no sin(), so it is the same on every GPU (Dave Hoskins, MIT).
float iceHash(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

float iceNoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(iceHash(i), iceHash(i + vec2(1.0, 0.0)), u.x),
               mix(iceHash(i + vec2(0.0, 1.0)), iceHash(i + vec2(1.0, 1.0)), u.x), u.y);
}

// px to a line from the origin along +x, len long (p in the line's own frame).
float iceSeg(vec2 p, float len) {
    return length(vec2(p.x - clamp(p.x, 0.0, len), p.y));
}

// One frost feather, grown from the origin along +x: a stem len long with side branches
// at 60 degrees (ice is hexagonal: every branch runs along one of its six axes), longest
// part-way along and shorter to both ends, like a leaf. arm: how long the branches are;
// twig: branches on the branches, at 60 degrees again. px to the ice's edge (< 0 on it).
float iceFeather(vec2 p, float len, float gap, float arm, float twig, float seed) {
    float w = mix(0.95, 0.4, clamp(p.x / max(len, 1.0), 0.0, 1.0));
    float d = iceSeg(p, len) - w;
    if (arm < 0.02 || p.x < -2.0 || p.x > len + arm * 0.5 * len)
        return d;
    float side = p.y < 0.0 ? 1.0 : 0.0;
    float ay = abs(p.y);
    float off = side * 0.5 * gap;
    float k = floor((p.x - 0.57735 * ay - off) / gap + 0.5);
    float xb = k * gap + off;
    if (xb <= 0.0 || xb >= len)
        return d;
    float r = iceHash(vec2(k + seed, side + 3.7 * seed));
    float lb = arm * min(1.2 * xb, 0.75 * (len - xb)) * (0.55 + 0.45 * r);
    vec2 q = vec2(0.5 * (p.x - xb) + 0.866025 * ay, 0.866025 * (p.x - xb) - 0.5 * ay);
    d = min(d, iceSeg(q, lb) - 0.8 * w);
    if (twig < 0.02 || lb < 2.0 * gap || q.x < 0.0 || q.x > lb + 2.0)
        return d;
    float g2 = 0.55 * gap;
    float s2 = q.y < 0.0 ? 1.0 : 0.0;
    float ty = abs(q.y);
    float o2 = s2 * 0.5 * g2;
    float k2 = floor((q.x - 0.57735 * ty - o2) / g2 + 0.5);
    float xt = k2 * g2 + o2;
    if (xt <= 0.0 || xt >= lb)
        return d;
    float lt = twig * 0.6 * min(xt, lb - xt) * (0.5 + 0.5 * iceHash(vec2(k2 + 17.0 * r, s2 + seed)));
    vec2 t = vec2(0.5 * (q.x - xt) + 0.866025 * ty, 0.866025 * (q.x - xt) - 0.5 * ty);
    return min(d, iceSeg(t, lt) - 0.6 * w);
}

// Frost grows in from one edge: along it, s px; in from it, u px. Window frost starts at
// the edges, the coldest part of the glass, from specks on it (dust, fine scratches; some
// of nature's best ice seeds are pollen and bacteria). Not every speck seeds: more do as
// it gets colder. Each feather leans a little and sweeps in a gentle curve.
float iceEdge(float s, float u, float sid, float reach, float grow, float arm, float twig, float size) {
    float g = mix(14.0, 30.0, size);
    float gap = mix(9.0, 4.2, arm);
    float i0 = floor(s / g);
    float best = 1e4;
    for (int j = -2; j <= 2; j++) {
        vec2 id = vec2(i0 + float(j), sid);
        if (iceHash(id * 1.7 + 0.3) > 0.35 + 0.5 * grow)
            continue;
        float r2 = iceHash(id * 2.3 + 5.1);
        float r3 = iceHash(id * 3.1 + 9.7);
        float len = reach * (0.45 + 0.55 * r3) * grow;
        vec2 dv = vec2(s - (id.x + 0.15 + 0.7 * r2) * g, u);
        if (len < 2.0 || abs(dv.x) > 0.8 * len + 4.0)
            continue;
        float a = (r2 - 0.5) * 0.9;
        vec2 dir = vec2(sin(a), cos(a));
        vec2 p = vec2(dot(dv, dir), dir.x * dv.y - dir.y * dv.x);
        p.y += (r3 - 0.5) * mix(0.1, 0.8, arm) * p.x * p.x / len;     // needles grow straight
        best = min(best, iceFeather(p, len, gap, arm, twig, id.x * 0.37 + sid));
    }
    return best;
}

// The frost on a pane: px to the nearest ice (< 0 on it). c: px from the pane's middle;
// h: half its size. reach: how far in the frost grows at its fullest; grow 0..1 how far
// it has.
float iceFrost(vec2 c, vec2 h, float reach, float grow, float arm, float twig, float size) {
    float ux = h.x - abs(c.x);
    float uy = h.y - abs(c.y);
    float d = 1e4;
    float pad = reach + 8.0;
    if (uy < pad)
        d = iceEdge(c.x + h.x, uy, c.y < 0.0 ? 1.0 : 2.0, reach, grow, arm, twig, size);
    if (ux < pad)
        d = min(d, iceEdge(c.y + h.y, ux, c.x < 0.0 ? 3.0 : 4.0, reach, grow, arm, twig, size));
    return d;
}

// How thick the ice glaze is, 0..1. Frost on glass is a coat of countless tiny crystals:
// it scatters light, so it reads as a soft icy sheen rather than as lines. It builds up
// thickest along the edges (the coldest glass, thicker still in the corners), its inner
// edge wavering, and reaches further in as soft feathers where the crystals branch
// (iceD: px to them). inside: px in from the edge; q: px on the glass, fixed to it.
float iceFrosting(vec2 c, vec2 h, float inside, vec2 q, float reach, float grow, float iceD) {
    float n = 0.6 * iceNoise(q * 0.035) + 0.4 * iceNoise(q * 0.11);
    float corner = 1.0 - smoothstep(0.0, 1.6 * reach, max(h.x - abs(c.x), h.y - abs(c.y)));
    float edge = (0.06 + 0.5 * n * n + 0.3 * corner) * reach * (0.45 + 0.55 * grow);
    float rim = 1.0 - smoothstep(0.2 * edge, 1.15 * edge + 4.0, inside);
    float fern = (1.0 - smoothstep(-0.5, 1.5 + 2.0 * grow, iceD)) * (1.0 - 0.55 * smoothstep(0.0, reach, inside));
    float grain = 0.75 + 0.25 * iceNoise(q * 0.7);
    return clamp(max(0.9 * rim, 0.6 * fern) * grain, 0.0, 1.0);
}

// Fog on cold glass is droplets (breath figures): too small to see one by one at first,
// growing and merging as it gets colder, biggest towards the colder edge. Each droplet is a
// little lens: dark at its rim, where light bends away, with a bright point on the side
// facing the light. Returns (how much of a droplet is here, its shade -1..1).
vec2 iceDew(vec2 q, float cell, float big, vec2 L) {
    vec2 i0 = floor(q / cell);
    float best = 9.0;
    vec2 bd = vec2(0.0);
    float br = 1.0;
    for (int y = -1; y <= 1; y++) {
        for (int x = -1; x <= 1; x++) {
            vec2 id = i0 + vec2(float(x), float(y));
            vec2 at = (id + 0.2 + 0.6 * vec2(iceHash(id + 1.7), iceHash(id + 4.3))) * cell;
            float rad = cell * big * (0.2 + 0.32 * iceHash(id + 7.9));
            vec2 d = (q - at) / rad;
            float e = length(d);
            if (e < best) {
                best = e;
                bd = d;
                br = rad;
            }
        }
    }
    float on = clamp((1.0 - best) * br + 0.5, 0.0, 1.0);
    float ring = smoothstep(0.5, 0.95, best);
    float spot = 1.0 - smoothstep(0.0, 0.42, length(bd - 0.45 * L));
    return vec2(on, on * (spot - 0.7 * ring));
}

void main() {
    vec2 c = size * 0.5;
    vec2 px0 = qt_TexCoord0 * size;
    vec2 p = px0 - c;
    if (ptrK > 0.001) {
        vec2 toPtr = ptr - px0;
        LIGHT = normalize(mix(ROOM, toPtr / max(length(toPtr), 1.0), ptrK) + vec2(1e-4));
    }
    float r = min(radius, min(c.x, c.y));
    float d = sdRoundRect(p, c, r);
    float cov = clamp(0.5 - d, 0.0, 1.0);
    if (cov <= 0.0) {
        fragColor = vec4(0.0);
        return;
    }

    float inside = -d;

    // The bevel is a share of the short side, as in glass.js: a quarter on a
    // menu, more on a thin bar; the bezel setting is the least it may be.
    vec2 dp = px0 - pressAt;
    float give = max(90.0 * pressScale, 0.6 * min(c.x, c.y)) * sqrt(max(liquid, 0.0));
    float deep = min(liquid, 1.0) + 0.35 * max(liquid - 1.0, 0.0);   // as in glass.js
    float tch = press > 0.001 ? touch(dp, give) : 0.0;
    float th = refraction * (1.0 + 0.3 * deep * press) * (1.0 + deep * tch);
    float slope = 0.0;
    float x = 0.0;
    float shortSide = 2.0 * min(c.x, c.y);
    float share = mix(0.36, 0.25, smoothstep(48.0, 160.0, shortSide));
    float bev = bezel > 0.0 ? min(clamp(share * shortSide, bezel, 2.6 * bezel), 0.45 * shortSide) : 0.0;
    bev *= 1.0 + 0.6 * deep * tch;
    float gr = min(max(r * 1.5, bev * 1.15), min(c.x, c.y));
    vec2 n = gradRoundRect(p, c, gr);
    if (bev > 0.0 && inside < bev) {
        x = 1.0 - inside / bev;
        slope = squircleSlope(x) * 1.6;
    }
    vec2 dome = min(1.0, depth + 0.25 * deep * press) * 0.25 * p / max(c.x, c.y);
    vec2 dent = -dp / give * 0.45 * deep * tch;
    vec3 N = normalize(vec3(n * slope + dome + dent + jitter(px0), 1.0));
    float F = F0 + (1.0 - F0) * pow(1.0 - N.z, 5.0);
    float crest = 4.0 * x * (1.0 - x);

    if (mode > 2.5) {
        vec3 b = glow(px0, n, inside, bev, F, crest);
        fragColor = vec4(b, 0.0) * cov * qt_Opacity;     // added light: nothing under it dims
        return;
    }

    vec2 px = c + p / max(magnify, 0.01);
    vec4 col = vec4(0.0);
    float keep = slope > 0.0 && th > 0.01 ? unfold(x, th, bev) : 1.0;
    if (mode < 1.5) {
        if (th > 0.01 && fringe > 0.001 && slope > 0.02) {
            float B = 0.08 * fringe;
            vec4 s450 = at(px + throughGlass(N, cauchy(0.45, B), th) * keep);
            vec4 s500 = at(px + throughGlass(N, cauchy(0.50, B), th) * keep);
            vec4 s550 = at(px + throughGlass(N, IOR, th) * keep);
            vec4 s600 = at(px + throughGlass(N, cauchy(0.60, B), th) * keep);
            vec4 s650 = at(px + throughGlass(N, cauchy(0.65, B), th) * keep);
            col.r = (0.05 * s450.r + 0.15 * s550.r + 0.85 * s600.r + s650.r) / 2.05;
            col.g = (0.6 * s500.g + s550.g + 0.35 * s600.g) / 1.95;
            col.b = (s450.b + 0.4 * s500.b) / 1.4;
            col.a = (s450.a + s500.a + s550.a + s600.a + s650.a) / 5.0;
        } else if (th > 0.01) {
            col = at(px + throughGlass(N, IOR, th) * keep);
        } else {
            col = at(px);
        }
        vec3 Rt = refract(vec3(0.0, 0.0, -1.0), N, 1.0 / IOR);
        col.rgb *= exp(-vec3(0.006, 0.0025, 0.004) * min(th / max(-Rt.z, 0.2) - th, 40.0));
        float xc = bev > 0.0 ? clamp(1.0 - inside / min(bev, 18.0), 0.0, 1.0) : 0.0;
        col.rgb = min(caustic(col.rgb / max(col.a, 1e-3), n, xc, c) * col.a, vec3(col.a));
        col = over(col, tint, 1.0);
        // The calm sheen on the side of the top that faces the light, as in glass.js.
        if (rim.a > 0.0)
            col.rgb = min(col.rgb + vec3(0.07 * min(1.0, 0.45 + 1.1 * rim.a) * smoothstep(-0.4, 1.1, dot(p / c, LIGHT))) * col.a, vec3(col.a));
        // Weather frost: the same droplets, mist and frosting as on the desktop (glass.js), at
        // the desktop's size: worked out in desktop px (q, cq, hq, inq), drawn in preview px.
        float k = max(iceScale, 0.05);
        vec2 q = px0 / k;
        vec2 hq = c / k;
        vec2 cq = p / k;
        float inq = inside / k;
        float shortIce = shortSide / k;
        float lightGlass = smoothstep(0.35, 0.7, dot(col.rgb / max(col.a, 1e-3), vec3(0.2126, 0.7152, 0.0722)));
        if (frost > 0.001) {
            vec3 st = col.rgb / max(col.a, 1e-3);
            float rimF = 1.0 - smoothstep(0.0, max(10.0, 0.25 * shortIce), inq);
            vec3 ice = mix(vec3(0.58, 0.66, 0.76), vec3(0.93, 0.965, 1.0), lightGlass);
            float m = frost * mix(0.17 + 0.36 * rimF, 0.30 + 0.36 * rimF, lightGlass);
            st = mix(vivid(st, 1.0 - 0.5 * frost), ice, m);
            st += vec3((iceHash(floor(q)) - 0.5) * 0.07 * frost);
            float dewIn = shortIce * mix(0.1, 0.3, frost) * (1.0 - smoothstep(0.0, 0.6, flakes));
            if (inq < dewIn) {
                float e = 1.0 - inq / dewIn;
                vec2 dw = iceDew(q, mix(3.5, 7.0, frost), mix(0.65, 1.15, e), LIGHT);
                // Droplets too small to see in a small preview melt into the mist, as they would.
                float see = smoothstep(1.5, 4.0, mix(3.5, 7.0, frost) * k);
                st += vec3(dw.y * 0.25 * dw.x * min(1.0, 0.4 + frost) * smoothstep(0.0, 0.5, e) * see);
            }
            col.rgb = clamp(st, 0.0, 1.0) * col.a;
        }
        float iceReach = min(0.42 * shortIce, 18.0 + 46.0 * iceSize);
        if (flakes > 0.001 && inq < iceReach + 8.0) {
            float iceD = iceFrost(cq, hq, iceReach, flakes, iceArm, iceTwig, iceSize);
            float fa = iceFrosting(cq, hq, inq, q, iceReach, flakes, iceD) * (0.36 + 0.26 * flakes);
            float vein = clamp(0.5 - iceD * k, 0.0, 1.0) * 0.38 * smoothstep(0.0, 0.3, flakes);
            vec3 glaze = mix(vec3(0.84, 0.91, 1.0), vec3(0.78, 0.85, 0.93), lightGlass);
            vec3 veinC = mix(vec3(0.95, 0.98, 1.0), vec3(0.66, 0.75, 0.87), lightGlass);
            col.rgb = mix(col.rgb, glaze * col.a, fa);
            col.rgb = mix(col.rgb, veinC * col.a, vein);
        }
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
        // Near the pointer the rim catches more of the same reflection, as in glass.js:
        // a gain on what it really mirrors, never added light.
        vec2 dp = px0 - ptr;
        float near = ptrK > 0.001 ? ptrK * exp(-dot(dp, dp) / max(2.0 * ptrReach * ptrReach, 1.0)) : 0.0;
        // The last few px of the rounded edge are near grazing: a thin wet band
        // that mirrors the surroundings almost fully.
        float wet = smoothstep(2.4 + 3.5 * near, 0.8, inside) * smoothstep(0.0, 0.6, inside);
        a = clamp((F * 1.9 + wet * (0.3 + 1.2 * near)) * min(1.0, hl * 2.2) * (1.0 + 2.5 * lobe + 2.0 * near), 0.0, 0.92) * clamp(e.a, 0.0, 1.0);
        // Restraint: the reflection lights the edge only a little above the glass
        // itself, so a bright backdrop gives no brighter a line than a dark one.
        vec4 under = mode > 1.5 ? at(px0) : col;
        vec3 base = under.rgb / max(under.a, 1e-3);
        seen = min(seen * (1.15 + 0.8 * lobe + 1.6 * near), base + vec3(0.05 + 0.03 * lobe) + seen * 0.6 * near);
    }
    // The line of light at the very edge: the backdrop beyond it mixed most of
    // the way to white, at most a little brighter than the glass around it.
    float ln = hl > 0.0 ? min(1.0, rimLine(inside, n) * min(1.0, 0.45 + 1.1 * hl)) : 0.0;
    vec3 lc = vec3(0.0);
    if (ln > 0.0) {
        vec4 e = env(px0 + n * REACH * 0.5);
        vec4 under = mode > 1.5 ? at(px0) : col;
        vec3 base = under.rgb / max(under.a, 1e-3);
        lc = mix(e.rgb / max(e.a, 1e-3), vec3(1.0), 0.8);
    }
    vec3 b = mode > 1.5 ? glow(px0, n, inside, bev, F, crest) : vec3(0.0);
    float gw = clamp(0.008 * shortSide, 1.8, 3.5);
    float gl = hl > 0.0 && inside < 2.2 * gw ? min(1.0, glint(inside, n, gw) * 0.85 * min(1.0, 0.45 + 1.1 * hl)) : 0.0;
    if (mode > 1.5) {
        // Over the content: the reflection and the line blend in, the bleed adds light.
        vec3 c2 = min(seen * a, vec3(1.0));
        float a2 = a + (1.0 - a) * ln;
        c2 = c2 * (1.0 - ln) + lc * ln;
        c2 = c2 * (1.0 - gl) + vec3(gl);
        a2 = a2 + (1.0 - a2) * gl;
        fragColor = vec4(c2 + b, a2) * cov * qt_Opacity;
        return;
    }
    col.rgb = min(col.rgb * (1.0 - a) + seen * col.a * a, vec3(col.a));
    col.rgb = mix(col.rgb, lc * col.a, ln);
    col.rgb += (vec3(col.a) - col.rgb) * gl;
    col.rgb += vec3(grain(px0) / 255.0) * col.a;
    fragColor = col * cov * qt_Opacity;
}
