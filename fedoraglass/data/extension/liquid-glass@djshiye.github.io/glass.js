// A Fedora Glass pane for GNOME Shell: a live copy of whatever lies behind a
// Shell surface, blurred, seen through a slab of glass and cut to the
// surface's rounded shape.
//
// The optics are physical, and everything the glass shows comes from real
// pixels on screen; there is no painted-on light. The pane is a glass slab
// (IOR 1.5) whose top edge rounds off in a squircle, after Kyant's
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
// Three things are not from the backdrop, all from one room light: a crisp line of
// light, about 1.5 px, along the very edge (rimLine); a glint, a small crescent of
// that light caught on the curve of the edge at the corner facing it (glint); and a
// faint sheen across the top on that side. They are what make Apple's glass read as
// glass you could touch; each stays a line or a hint, never a glow.
//
// Sides that touch the screen edge (a docked panel's bottom) have no rim.

import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';
import Mtk from 'gi://Mtk';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Graphene from 'gi://Graphene';
import Meta from 'gi://Meta';

import {PACKAGE_VERSION} from 'resource:///org/gnome/shell/misc/config.js';
import System from 'system';

import {ICE_GLSL, frostBlur} from './frostmath.js';
import {Shader} from './glsl.js';
import {GlassHold} from './holdstate.js';

const SHADER = `
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
uniform float liquid;             // how far the glass gives under a press: 1 = the original feel
uniform float pull_x;             // px the pointer runs ahead of the press point (a drag),
uniform float pull_y;             // already scaled by how liquid the glass is: 0 at 1 and below
uniform float env_reach;         // px, how far beyond the edge the rim sees
uniform float cheap;             // 1 while something moves behind: fewer taps
uniform float lite;              // 1 for lighter glass (speed.js): three wavelengths, one-tap mirror
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
uniform float haze;              // 0..1, dark glass: a grey smoke in the glass itself, so it reads as a pane over black
uniform float ceil_y;            // 0 = off; else the brightest the glass may get (linear Y),
                                 // so white text on it stays readable over any backdrop
uniform float floor_y;           // 0 = off; light glass: the darkest it may get (linear Y),
                                 // so dark text on it stays readable over any backdrop
uniform float edge_l;            // 1 where that side touches the screen edge
uniform float edge_t;
uniform float edge_r;
uniform float edge_b;
uniform float shadow;
uniform float rim;               // 0..1, the thin bright line along the very edge
uniform float veil_r;            // the theme's veil painted over this glass (straight rgb, alpha);
uniform float veil_g;            // the line is drawn so it still reads as bright through it
uniform float veil_b;
uniform float veil_a;
uniform float text_shade;
uniform float frost;             // 0..1, weather frost (frost.js): the glass mists over in the cold
uniform float flakes;            // 0..1, and below freezing it ices over from its edges
// A pane can draw one part of a bigger glass (the rim over an app window is four
// thin strips): shape_* is that whole glass, padding included, and where this pane
// starts in it. Every other pane is the whole of its glass: shape_w/h = width/height.
uniform float shape_w;
uniform float shape_h;
uniform float shape_x;
uniform float shape_y;
uniform float lens_share;        // 1: the bevel is a share of the short side (panel, menus); 0: refr_h        // 0..1, reflections layer: a soft shade behind bright text (clear glass)
uniform float mode;              // 0 = glass, 1 = glass under a surface, 2 = the surface's own light,
                                 // 3 = the rim over an app window

// Uniforms arrive as typed floats (glsl.js), so a uniform set to 0 is 0. Still
// test "is it on" against OFF, never 0.0, so a value that rounds to a hair above
// 0 stays off too. The same goes for values computed from uniforms (bevel comes
// from refr_h).
const float OFF = 0.001;
varying float fg_bl;            // the backdrop's overall brightness (ADAPT_VERTEX)
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
    return texture2D(cogl_sampler0, (clamp(px, vec2(0.5), size - vec2(0.5)) + vec2(org_x, org_y)) / vec2(tex_w, tex_h));
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
    if (cheap > 0.5 || lite > 0.5)
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
// The turn is measured against the pane's own half size (h), so it is gradual
// all the way across: the light comes from the side only with the pointer at or
// past an end, and is the room's light with the pointer in the middle. Up to
// 1.5.27 it pointed straight at the pointer from the middle: on a long, thin
// bar it swung from the side to straight above within a few px as the pointer
// passed the middle, and the taskbar's whole top edge flashed.
vec2 lightDir(vec2 toPtr, vec2 h) {
    vec2 Lp = clamp(toPtr / max(h, vec2(1.0)), -1.0, 1.0);
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
// Dragged, a more liquid glass is drawn out after the pointer like a drop: the give
// stretches from the press point towards where the pointer already is (pull).
float touch(vec2 dp, float s) {
    float pl = length(vec2(pull_x, pull_y));
    if (pl > 0.5) {
        vec2 u = vec2(pull_x, pull_y) / pl;
        float along = dot(dp, u);
        // Ahead of the press point (towards the pointer) the give reaches further.
        float ahead = along / (1.0 + pl / s * step(0.0, along));
        dp = u * ahead + (dp - u * along);
    }
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

// The rounded edge's profile: a squircle, (1 - x^4)^(1/4) with x 1 at the edge and
// 0 where the flat top begins. Flat for most of the way, then curving faster
// and faster towards the edge, with no visible line where the curve starts
// (a quarter circle bends from its first px). Returns -dz/dr, outward.
const float LENS_REACH = 0.16;
float squircleSlope(float x) {
    float x3 = x * x * x;
    float k = max(1.0 - x3 * x, 0.0);
    return x3 / max(pow(k, 0.75), 0.03);
}

// How far a ray through the rounded edge moves sideways, per px of glass, x of
// the way down the bevel (0 on the flat top, 1 at the edge), along the edge's normal.
float bendAt(float x, float squircle) {
    float s = squircle > 0.5 ? squircleSlope(x) * 1.6 : x / max(sqrt(max(1.0 - x * x, 0.0)), 0.06);
    vec3 R = refract(vec3(0.0, 0.0, -1.0), normalize(vec3(s, 0.0, 1.0)), 1.0 / IOR);
    return -R.x / max(-R.z, 0.2);
}

// The share of the bend to keep at x so the backdrop never folds over.
// Across the bevel each pixel shows the backdrop a bend further in. Near the
// edge the bend grows faster than the pixels step outwards, so going out the
// shown spot turned back inwards: a straight line behind a menu became a
// hairpin loop and the panel's top edge hooked every line (1.5.17). Here the
// bend follows the lens until it would grow faster than 0.85 px per px, and
// from there grows at that rate: the edge still squeezes the backdrop in, in
// order. The bend is convex in x, so that point is found by halving.
float unfold(float x, float th, float bevel, float squircle) {
    float K = 0.85 * bevel / max(th, 1e-3);
    float lo = 0.0, hi = 1.0;
    for (int i = 0; i < 9; i++) {
        float m = 0.5 * (lo + hi);
        if (bendAt(m + 0.004, squircle) - bendAt(m - 0.004, squircle) > K * 0.008)
            hi = m;
        else
            lo = m;
    }
    if (x <= lo)
        return 1.0;
    float g = bendAt(x, squircle);
    return min(1.0, (bendAt(lo, squircle) + K * (x - lo)) / max(g, 1e-5));
}

// A Gaussian-blurred edge: 1 well inside, 0.5 on the edge, 0 well outside, for
// a signed distance d and a blur sigma. erf by Winitzki's approximation.
float softEdge(float d, float sigma) {
    float x = -d / (sigma * 1.41421356);
    float x2 = x * x;
    float e = sqrt(1.0 - exp(-x2 * (1.2732395 + 0.147 * x2) / (1.0 + 0.147 * x2)));
    return 0.5 + 0.5 * sign(x) * e;
}

// The thin line of light along the very edge. Strongest where the edge faces the
// light and on the opposite side (at 40%), so it peaks at the corners and fades
// along straight sides, and a faint trace stays all the way round. 0..1.
// The light on the rim as iOS 26 draws it (measured by Glisse, MIT): brightest at
// the very edge and gone about 1.2 px in. It lights the sides that face the light
// and, by its reflection, the opposite ones, and fades out over the corners in
// between, so a long straight edge gets a calm line, never a glare.
float rimLine(float inside, vec2 n, vec2 L) {
    float facing = abs(dot(n, L));
    float along = inside / (1.22 * (1.0 + 0.25 * facing));
    if (along >= 1.0)
        return 0.0;
    return pow(facing, 1.5) * (1.0 - pow(along, 1.5)) * smoothstep(0.0, 0.25, inside);
}

// The glass's own edge: a half px line all the way round, faint white on dark glass.
float edgeLine(float inside) {
    return smoothstep(0.0, 0.2, inside) * (1.0 - smoothstep(0.4, 0.9, inside));
}

// The glint: a studio light caught on the rounded edge, the soft crescent that makes
// thick glass look like you could touch it. It lies a few px inside the edge, on the
// curve of the bevel, and is bright only where the edge turns to face the light (the
// corner towards it) and, at 40 %, the corner across from it. Along the straight
// sides it fades to almost nothing, so a long bar never gets a white line.
// inside: px in from the edge; reach: how far in the crescent lies (px). 0..1.
float glint(float inside, vec2 n, vec2 L, float w) {
    float d = dot(n, L);
    // 1 where the edge runs diagonally (a corner), 0 along a straight side.
    float corner = smoothstep(0.15, 0.85, 1.0 - abs(abs(n.x) - abs(n.y)));
    float lobe = (pow(max(d, 0.0), 8.0) + 0.45 * pow(max(-d, 0.0), 8.0)) * mix(0.3, 1.0, corner);
    if (lobe < 0.004)
        return 0.0;
    float u = (inside - w) / (0.5 * w);
    return lobe * exp(-u * u) * smoothstep(0.2, 1.0, inside);
}

// The theme paints a thin veil over the glass. To make a colour c (straight rgb)
// read through that veil, draw (c - v a) / (1 - a); as far as 0..1 allows.
vec3 throughVeil(vec3 c) {
    vec3 v = vec3(veil_r, veil_g, veil_b) * veil_a;
    return clamp((c - v) / max(1.0 - veil_a, 0.05), 0.0, 1.0);
}

vec3 vivid(vec3 c, float k) {
    float l = dot(c, vec3(0.213, 0.715, 0.072));
    return max(mix(vec3(l), c, k), 0.0);
}

${ICE_GLSL}
void main() {
    vec2 size = vec2(width, height);
    vec2 px = cogl_tex_coord_in[0].st * vec2(tex_w, tex_h) - vec2(org_x, org_y);
    // The shape is laid out over the whole glass; px stays this pane's own (its texture).
    vec2 whole = vec2(shape_w, shape_h);
    vec2 at0 = vec2(shape_x, shape_y);
    vec2 c = px + at0 - whole * 0.5;
    vec2 h = max(whole * 0.5 - vec2(pad), vec2(1.0));
    // Push sides that touch the screen edge far out, so they get no rim.
    vec2 lo = vec2(edge_l, edge_t) * 4096.0;
    vec2 hi = vec2(edge_r, edge_b) * 4096.0;
    vec2 hh = h + (lo + hi) * 0.5;
    vec2 cc = c + (lo - hi) * 0.5;
    float r = min(radiusAt(c), min(h.x, h.y));
    float sd = sdRoundRect(cc, hh, r);
    if (sd > 0.5 && mode > 1.5) {
        cogl_color_out = vec4(0.0);
        return;
    }
    // The rim over an app window draws only its outer 2.8 px (see below): nothing
    // else of the lens needs working out for the rest of it.
    if (mode > 2.5 && sd < -2.8) {
        cogl_color_out = vec4(0.0);
        return;
    }
    vec2 toPtr = vec2(ptr_x, ptr_y) + at0 - whole * 0.5;
    vec2 L = lightDir(toPtr, h);

    // Outside the pane: only its soft contact shadow, cast away from the light.
    // It also lies under the edge's partly covered pixels, so the rounded edge
    // stays anti-aliased against the shadow.
    // A true soft shadow (a blurred copy of the shape), set off a few px away from
    // the light, so it reads as lifted rather than outlined.
    float s = 0.0;
    if (shadow > OFF && pad > 1.0 && sd > -0.5) {
        // Over a bright backdrop (a white wallpaper) a dark shadow reads as a heavy
        // smudge around the pane: there it is lighter and tighter, as a shadow on
        // a white table is a thin soft line, not a dark halo.
        float onBright = smoothstep(0.5, 0.9, fg_bl);
        float spread = min(8.0, pad * 0.3) * (1.0 - 0.4 * onBright);
        float ds = sdRoundRect(cc + L * min(5.0, pad * 0.2) * (1.0 - 0.5 * onBright), hh, r);
        s = shadow * 0.55 * (1.0 - 0.5 * onBright) * softEdge(ds, spread);
    }
    if (sd > 0.5) {
        cogl_color_out = vec4(0.0, 0.0, 0.0, s) * cogl_color_in.a;
        return;
    }

    float cov = clamp(0.5 - sd, 0.0, 1.0);
    float inside = -min(sd, 0.0);
    // The glass: a slab refr_amt thick lying on the backdrop, its top edge
    // rounded off over the bevel in a squircle. The bevel is a share of the short
    // side, as on Apple's glass: a quarter of it on a menu, so the backdrop bends
    // in a wide band you can see, and more on a thin bar, which is nearly all
    // lens. refr_h (the app's lens width) sets the least it may be.
    vec2 dp = px - vec2(ptr_x, ptr_y);
    float give = max(90.0, 0.6 * min(h.x, h.y)) * sqrt(max(liquid, 0.0));   // px, how wide a press reaches
    // How deep it gives: as the original up to 1; past that it mostly spreads wider and
    // draws out (give, pull) and only a little deeper, or the edge folds into zigzags.
    float deep = min(liquid, 1.0) + 0.35 * max(liquid - 1.0, 0.0);
    float tch = touch(dp, give);
    float slope = 0.0;
    float shortSide = 2.0 * min(h.x, h.y);
    // How far the edge bends what is behind it. On the panel and menus it grows with
    // the glass, as Apple's does (Glisse reaches 0.45 of the short side), so a big
    // menu bends its backdrop in a band you can see, not only in its outer px.
    float th = (lens_share > 0.5 ? max(refr_amt, min(LENS_REACH * shortSide, 72.0)) : refr_amt) * (1.0 + deep * tch);
    float share = mix(0.36, 0.25, smoothstep(48.0, 160.0, shortSide));
    float bevel = lens_share > 0.5
        ? min(clamp(share * shortSide, refr_h, 2.6 * refr_h), 0.45 * shortSide)
        : min(refr_h, 0.35 * min(h.x, h.y));
    bevel *= 1.0 + 0.6 * deep * tch;
    // The edge's direction rounds off over at least the whole bevel, so a wide
    // bevel shows no mitred seam running in from its corners.
    float gr = min(max(r * 1.5, lens_share > 0.5 ? bevel * 1.15 : 0.0), min(hh.x, hh.y));
    // The edge's direction is only used within the bevel and the outer 8 px (the
    // reflections, caustic, rim line, glint and the surface's mirrored light all
    // stop there). Further in, slope is 0 and nothing reads n.
    vec2 n = inside < max(bevel, 8.0) + 4.0 ? gradRoundRect(cc, hh, gr) : vec2(0.0);
    float x = 0.0;
    if (bevel > OFF && inside < bevel) {
        x = 1.0 - inside / bevel;                   // 1 at the edge, 0 on the flat top
        // -dz/dr of the rounded edge, outward: the squircle on the panel and menus,
        // the quarter circle elsewhere (app windows, the lock screen), as before.
        slope = lens_share > 0.5 ? squircleSlope(x) * 1.6 : x / max(sqrt(max(1.0 - x * x, 0.0)), 0.06);
    }
    vec2 dome = depth * 0.25 * c / max(h.x, h.y);  // a gently domed top
    vec3 N = normalize(vec3(n * slope + dome + dent(dp, give, deep * tch) + jitter(px), 1.0));
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
        vec3 c3 = min(seen * (1.0 + 0.3 * lobe), vec3(1.0));
        // The same thin line of light as on the panel and menus, a little quieter:
        // a window is big, and the line runs right next to its own content.
        float ln = min(1.0, (rimLine(inside, n, L) * 0.42 + edgeLine(inside) * 0.12) * rim);
        if (ln > 0.0) {
            vec3 lc = min(mix(seen, vec3(1.0), 0.6), vec3(dot(seen, vec3(0.213, 0.715, 0.072)) + 0.45));
            float a2 = a + (1.0 - a) * ln;
            c3 = (c3 * a * (1.0 - ln) + lc * ln) / max(a2, 1e-3);
            a = a2;
        }
        cogl_color_out = vec4(c3 * a, a) * cov * cogl_color_in.a;
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
        // A large painted area (an accent-filled toggle, a slider fill) is paint, not
        // a light: its colour stays inside its own edge, with no halo around it. Next
        // to such an area, colour still fills the blur both half way out and all the
        // way out along some direction; next to an icon, the far sample has left it.
        // The 16 reads only matter where this pixel has colour to keep in, or near
        // the rim where the mirrored term below also uses keepIn.
        float paint = 0.0;
        float need = max(glow.r, max(glow.g, glow.b));
        // Content near the edge, mirrored into it by reflection inside the glass (used
        // below). Read first: where neither this pixel nor its mirror has any colour,
        // keepIn multiplies (next to) nothing, and the 16 reads that find it can be
        // skipped. On a thin panel the edge band is nearly all of it, and most of it is
        // grey text, symbolic icons or nothing at all. In the band the bar is low, so
        // what is skipped stays far below one step of 255.
        bool nearRim = inside < bevel + 4.0;
        vec3 mc = vec3(0.0);
        if (nearRim) {
            vec4 m = at(px - n * (2.0 * inside + 6.0));
            mc = (m.rgb - vec3(min(m.r, min(m.g, m.b)))) * 1.6;
        }
        if (need > (nearRim ? 0.0005 : 0.004) || max(mc.r, max(mc.g, mc.b)) > 0.0005) for (int i = 0; i < 8; i++) {
            vec2 d = vec2(cos(float(i) * 0.7853982), sin(float(i) * 0.7853982));
            // Samples past the pane's edge count as empty (at() would clamp them
            // back onto the edge, which in a thin panel is right next to the icon).
            vec2 p1 = px + d * 28.0, p2 = px + d * 56.0;
            float in1 = step(0.0, p1.x) * step(0.0, p1.y) * step(p1.x, size.x) * step(p1.y, size.y);
            float in2 = step(0.0, p2.x) * step(0.0, p2.y) * step(p2.x, size.x) * step(p2.y, size.y);
            vec4 a1 = at(p1);
            vec4 a2 = at(p2);
            float c1 = in1 * (max(a1.r, max(a1.g, a1.b)) - min(a1.r, min(a1.g, a1.b)));
            float c2 = in2 * (max(a2.r, max(a2.g, a2.b)) - min(a2.r, min(a2.g, a2.b)));
            paint = max(paint, min(c1, c2));
        }
        float keepIn = 1.0 - smoothstep(0.16, 0.34, paint);
        glow *= keepIn;
        // The surface's light, caught inside the glass, leaves at the very edge: a
        // one px hairline in the surface's own colour, equally faint on every surface
        // (a fixed step in display values is a fixed step in lightness).
        float hair = smoothstep(2.2, 0.9, inside) * smoothstep(0.0, 0.6, inside);
        float gm = max(g.r, max(g.g, g.b));
        vec3 tone = mix(vec3(1.0), g.rgb / max(gm, 1e-3), 0.5 * step(0.01, gm));
        vec3 edgeLight = tone * hair * 0.065;
        if (nearRim)
            glow += mc * keepIn * (0.25 + 0.75 * F) * max(crest, 1.0 - inside / max(bevel, 1.0)) * 1.2;
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
        // Clear glass has almost no veil, so bright text gets a soft shade of its own,
        // only right behind it (the blurred copy of the content is the mask).
        // A large light area (a button's own fill) is not text and keeps no shade:
        // where the copy is still light 20 and 40 px away along some direction, the
        // pixel sits on or beside such an area.
        float sh = 0.0;
        float lit = min(g.r, min(g.g, g.b));
        if (text_shade > OFF && lit > 0.01) {
            float area = 0.0;
            for (int i = 0; i < 8; i++) {
                vec2 d = vec2(cos(float(i) * 0.7853982), sin(float(i) * 0.7853982));
                vec4 b1 = at(px + d * 20.0);
                vec4 b2 = at(px + d * 40.0);
                area = max(area, min(min(b1.r, min(b1.g, b1.b)), min(b2.r, min(b2.g, b2.b))));
            }
            sh = text_shade * smoothstep(0.01, 0.12, lit) * (1.0 - smoothstep(0.04, 0.12, area));
        }
        cogl_color_out = vec4(glow * (1.0 - sh) + edgeLight, sh) * cov * cogl_color_in.a;
        return;
    }

    // Weather frost, below freezing: the glass is under a sheet of ice that has grown in
    // from its edges (frostmath.js). Where the ice is and how it slopes is worked out
    // first, because what is behind bends as it comes through it. Only the band the ice
    // can reach is worked out; weather frost off, or above freezing: skipped. No ice grows
    // in from a side that lies on the screen's edge (cc, hh: those sides are far away).
    float shortIce = 2.0 * min(h.x, h.y);
    float iceReach = min(0.3 * shortIce, 72.0);
    float iceOn = smoothstep(0.0, 0.25, flakes);     // it sets in softly at freezing
    vec3 iceF = vec3(0.0);
    vec2 pxi = px;
    if (flakes > OFF && mode < 1.5 && inside < iceReach * 1.2 + 4.0) {
        iceF = iceField(cc, hh, px + at0, iceReach, flakes);
        pxi += iceBend(iceF) * iceOn;
    }

    // The ray refracted at IOR: the main tap and Beer-Lambert below share it.
    vec3 Rt = refract(vec3(0.0, 0.0, -1.0), N, 1.0 / IOR);
    float keep = slope > 0.0 && th > 0.01 ? unfold(x, th, bevel, lens_share) : 1.0;
    vec2 thru = Rt.xy * th / max(-Rt.z, 0.2) * keep;
    vec4 col;
    if (th > 0.01) {
        if (dispersion > 0.001 && slope > 0.02 && cheap < 0.5 && lite > 0.5) {
            // Lighter glass: three wavelengths keep the rainbow edge at 3/5 of the reads.
            float B = 0.08 * dispersion;
            vec4 s450 = at(pxi + throughGlass(N, cauchy(0.45, B), th) * keep);
            vec4 s550 = at(pxi + thru);
            vec4 s630 = at(pxi + throughGlass(N, cauchy(0.63, B), th) * keep);
            col.r = (0.15 * s550.r + s630.r) / 1.15;
            col.g = s550.g;
            col.b = (s450.b + 0.15 * s550.b) / 1.15;
            col.a = (s450.a + s550.a + s630.a) / 3.0;
        } else if (dispersion > 0.001 && slope > 0.02 && cheap < 0.5) {
            // Five wavelengths, each refracted by its own index, then mixed back to RGB.
            float B = 0.08 * dispersion;   // crown glass is ~0.004, dense flint ~0.015: exaggerated, as Apple does
            vec4 s450 = at(pxi + throughGlass(N, cauchy(0.45, B), th) * keep);
            vec4 s500 = at(pxi + throughGlass(N, cauchy(0.50, B), th) * keep);
            vec4 s550 = at(pxi + thru);
            vec4 s600 = at(pxi + throughGlass(N, cauchy(0.60, B), th) * keep);
            vec4 s650 = at(pxi + throughGlass(N, cauchy(0.65, B), th) * keep);
            col.r = (0.05 * s450.r + 0.15 * s550.r + 0.85 * s600.r + s650.r) / 2.05;
            col.g = (0.6 * s500.g + s550.g + 0.35 * s600.g) / 1.95;
            col.b = (s450.b + 0.4 * s500.b) / 1.4;
            col.a = (s450.a + s500.a + s550.a + s600.a + s650.a) / 5.0;
        } else {
            col = at(pxi + thru);
        }
    } else {
        col = at(pxi);
    }

    // A full-screen sheet has nothing behind it to show: where the blur thinned the
    // copy at the screen's edge, take its colour at full strength.
    if (solid > 0.5)
        col = vec4(col.rgb / max(col.a, 1e-3), 1.0);

    // Vibrancy and brightness (premultiplied colour).
    // Light glass: colours that are already strong (an orange wallpaper) are only
    // nudged. Pushed the full way, the stock top bar over a warm wallpaper was a
    // neon strip, and orange in Activities. Dull colours still get the full lift.
    // Dark glass keeps it all: its smoke dulls colour, which this makes up for.
    float sat = saturation;
    if (light_glass > 0.5 && sat > 1.0) {
        vec3 sc = col.rgb / max(col.a, 1e-3);
        float chroma = max(sc.r, max(sc.g, sc.b)) - min(sc.r, min(sc.g, sc.b));
        sat = mix(sat, min(sat, 1.1), smoothstep(0.15, 0.5, chroma));
    }
    col.rgb = min(vivid(col.rgb, sat) * brightness, vec3(col.a));

    // Beer-Lambert: light crossing the rounded edge slants through more glass than
    // light crossing the flat top, and soda-lime glass takes a little more red
    // and blue than green, so the edge is a shade darker and greener.
    // Capped, so the edge only tints and never reads as a dark outline.
    float extra = min(th / max(-Rt.z, 0.2) - th, 40.0);
    col.rgb *= exp(-vec3(0.006, 0.0025, 0.004) * extra);

    vec4 t = vec4(tint_r, tint_g, tint_b, 1.0) * tint_a;
    col = t + col * (1.0 - t.a);

    // Adapt to the backdrop: over bright things the glass shades itself a little
    // so text stays readable. Dark glass is never lifted: over a dark backdrop
    // that reads milky.
    if (adapt > OFF || lift > OFF) {
        // How bright the backdrop is overall: the same for every pixel of the pane, so
        // it is read once per corner of the pane (ADAPT_VERTEX), not once per pixel.
        float bl = fg_bl;
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

    // Dark smoked glass (Glisse's dark glass is 40 grey at 62 %): over black it is a
    // visible grey pane, and what is behind still shows through it, sharp.
    // Toward the rounded edge the light has crossed the glass at a slant and is
    // gathered by the lens, so the smoke thins there: the outer part of the bevel
    // shows what it bends, in its own colours, like the rim of a thick lens. The
    // ceiling below still holds, so text near the edge keeps its contrast.
    float clearEdge = lens_share > 0.5 ? smoothstep(0.35, 0.95, x) : 0.0;
    if (clearEdge > 0.0)
        col.rgb = min(vivid(col.rgb, 1.0 + 0.3 * clearEdge), vec3(col.a));
    if (haze > OFF)
        col.rgb = mix(col.rgb, vec3(0.157, 0.157, 0.165) * col.a, haze * (1.0 - 0.75 * clearEdge));

    // Weather frost: cold outside, the glass mists over, whiter towards its edges where
    // it is coldest, its colours cooler and paler, with the fine even grain of frosted
    // glass. Before the ceiling, so white text on dark glass keeps its contrast; dark glass
    // mists less for that too. Below freezing the mist at the edges has frozen into the
    // ice there, which is clear. Weather frost off, or warm enough out: skipped.
    if (frost > OFF && mode < 1.5) {
        vec3 st = col.rgb / max(col.a, 1e-3);
        float rimF = (1.0 - smoothstep(0.0, max(10.0, 0.25 * shortIce), inside)) * (1.0 - 0.7 * flakes);
        vec3 ice = light_glass > 0.5 ? vec3(0.93, 0.965, 1.0) : vec3(0.58, 0.66, 0.76);
        float k = frost * (light_glass > 0.5 ? 0.30 + 0.36 * rimF : 0.17 + 0.36 * rimF);
        st = mix(vivid(st, 1.0 - 0.5 * frost), ice, k);
        st += vec3((iceHash(floor(px + at0)) - 0.5) * 0.07 * frost);
        col.rgb = clamp(st, 0.0, 1.0) * col.a;
    }

    // The top of the slab catches a little of the room's light on the side that
    // faces it, fading across the pane: a calm sheen, so even over a black
    // wallpaper the glass reads as a polished surface, not a flat dark box.
    // Dark glass only (light glass is already milky white), and before the ceiling,
    // so over a bright backdrop white text keeps its contrast.
    // Along a long bar (a panel) it stays even: faded end to end, the main screen's
    // panel went dim at its right end, right next to the bright start of the second
    // screen's panel (1.5.11). Panes up to twice as long as they are high are as before.
    if (rim > OFF && light_glass < 0.5) {
        vec2 sq = c / h * vec2(min(1.0, 2.0 * h.y / h.x), min(1.0, 2.0 * h.x / h.y));
        col.rgb = min(col.rgb + vec3(0.07 * rim * smoothstep(-0.4, 1.1, dot(sq, L))) * col.a, vec3(col.a));
    }

    // A ceiling on brightness, for glass that carries white text over any backdrop
    // (the lock screen). Dark backdrops pass unchanged; brighter ones ease into
    // the ceiling in their own colour, so a white wallpaper gives a calm grey.
    // It goes by the area around the pixel, not the pixel: a bright area is what
    // text must read over, while a star or a small light can keep its sparkle.
    if (ceil_y > OFF) {
        vec3 st = col.rgb / max(col.a, 1e-3);
        const vec3 Yw = vec3(0.2126, 0.7152, 0.0722);
        // The outer part of the lens holds no text: there it may stay brighter,
        // so the bent backdrop reads in its own colours.
        // Only colour gets this: over white or grey the lighter outer lens was a
        // soft grey band all round the pane, a smudged frame on a white wallpaper.
        float hue = max(st.r, max(st.g, st.b)) - min(st.r, min(st.g, st.b));
        float cy = ceil_y * (1.0 + 1.6 * clearEdge * clearEdge * smoothstep(0.06, 0.3, hue));
        // Over white everything bright met the same ceiling, so the pane was one
        // flat grey slab. The ceiling now falls off a little away from the light
        // (to 70 % on the far side, never above it), so even over white the pane
        // keeps the soft light-to-shade of the glass.
        vec2 sq2 = c / h * vec2(min(1.0, 2.0 * h.y / h.x), min(1.0, 2.0 * h.x / h.y));
        if (rim > OFF)      // panes with a lit edge; the lock screen's sheet stays even
            cy *= mix(0.7, 1.0, smoothstep(-0.9, 0.9, dot(sq2, L)));
        float knee = 0.6 * cy;
        // The weights add up to 1, so a pixel whose brightest channel is below the
        // knee (in display values) is below it in Y too, and is left as it is. Over
        // dark glass that is nearly every pixel: one pow instead of three, and no Y.
        if (max(st.r, max(st.g, st.b)) > pow(knee, 1.0 / 2.2)) {
            float Yp = dot(pow(max(st, vec3(0.0)), vec3(2.2)), Yw);
            // The area around is only asked about when this pixel is above the knee: the
            // ceiling takes the darker of the two, so a pixel below it is left as it is
            // whatever the area holds. Over dark glass that is nearly every pixel, and it
            // saves four texture reads each.
            float Yl = Yp;
            if (Yp > knee) {
                vec4 a1 = at(px + vec2(6.0, 0.0)), a2 = at(px - vec2(6.0, 0.0));
                vec4 a3 = at(px + vec2(0.0, 6.0)), a4 = at(px - vec2(0.0, 6.0));
                vec3 ar = (a1.rgb + a2.rgb + a3.rgb + a4.rgb) / max(a1.a + a2.a + a3.a + a4.a, 1e-3);
                float Ya = dot(pow(max(ar, vec3(0.0)), vec3(2.2)), Yw);
                Yl = max(min(Yp, Ya * 1.5), 1e-5);
            }
            if (Yl > knee) {
                float room = cy - knee;
                float Yc = knee + room * (1.0 - exp(-(Yl - knee) / room));
                col.rgb *= pow(Yc / Yl, 1.0 / 2.2);
            }
        }
    }

    // A floor on brightness, the light glass's mirror of the ceiling: dark text on
    // clear light glass over a vivid or dark backdrop (a purple wallpaper put the
    // panel clock at 3.3:1) lightens towards the glass's own milk, so the text
    // keeps 5:1 under the theme's veil. Lighter backdrops pass unchanged; darker
    // ones ease into the floor, keeping some of their colour. By the pixel, not
    // the area: light glass is blurred enough that a thin line is no text's backdrop.
    if (floor_y > OFF && light_glass > 0.5) {
        vec3 st = col.rgb / max(col.a, 1e-3);
        const vec3 Yf = vec3(0.2126, 0.7152, 0.0722);
        float knee = min(1.5 * floor_y, 0.95);
        // A pixel under the knee in Y has a channel under it: the rest skip the pows.
        if (min(st.r, min(st.g, st.b)) < pow(knee, 1.0 / 2.2)) {
            vec3 lin = pow(max(st, vec3(0.0)), vec3(2.2));
            float Yp = dot(lin, Yf);
            if (Yp < knee) {
                float room = knee - floor_y;
                float Yc = knee - room * (1.0 - exp(-(knee - Yp) / room));
                vec3 mk = pow(vec3(milk_r, milk_g, milk_b), vec3(2.2));
                float Ym = dot(mk, Yf);
                float k = clamp((Yc - Yp) / max(Ym - Yp, 1e-4), 0.0, 1.0);
                col.rgb = pow(mix(lin, mk, k), vec3(1.0 / 2.2)) * col.a;
            }
        }
    }

    // Below freezing, the ice itself (frostmath.js iceLook): clear and cool blue, a white
    // crust at the glass's edge, and a rounded front that catches the light. Worked out on
    // what shows through the theme's veil, and drawn so it reads through it. The middle,
    // where text sits, has no ice and stays clear.
    if (iceF.x > OFF) {
        vec3 seen = col.rgb / max(col.a, 1e-3) * (1.0 - veil_a) + vec3(veil_r, veil_g, veil_b) * veil_a;
        vec2 sqi = c / h * vec2(min(1.0, 2.0 * h.y / h.x), min(1.0, 2.0 * h.x / h.y));
        vec3 iced = iceLook(seen, iceF, L, light_glass, inside, iceReach, clamp(dot(sqi, L), -1.0, 1.0));
        col.rgb = throughVeil(mix(seen, iced, iceOn)) * col.a;
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
        // The caustic gathers in the outer px of the edge, however wide the bevel is.
        float xc = bevel > OFF ? clamp(1.0 - inside / min(bevel, 18.0), 0.0, 1.0) : 0.0;
        col.rgb = min(caustic(col.rgb / max(col.a, 1e-3), n, L, xc, h) * col.a, vec3(col.a));
    }
    // A thick lens is darker inside on its far side, where the light inside it
    // leaves through the edge instead of reaching the eye: a soft shade across
    // the middle of the far bevel, inside the caustic's bright band.
    if (shadow > OFF && x > 0.0) {
        float away = smoothstep(-0.1, 0.6, dot(-n, L));
        col.rgb *= 1.0 - 0.08 * away * smoothstep(0.0, 0.6, x) * smoothstep(1.0, 0.7, x);
    }
    // The line of light at the very edge: the backdrop's own reflection mixed most
    // of the way to white, at most a little brighter than the glass around it, so
    // it is a crisp line over any wallpaper and never a white glare.
    if (rim > OFF) {
        // About 0.35 white at the lit edge (rim 0.85), as iOS lays on dark glass, over
        // a 0.1 edge line all round.
        float ln = min(1.0, (rimLine(inside, n, L) * 0.42 + edgeLine(inside) * 0.12) * rim);
        // The glint sits on the curve of the bevel, a little further in than the line.
        float gw = clamp(0.008 * shortSide, 1.8, 3.5);
        float gl = inside < 2.2 * gw ? glint(inside, n, L, gw) * 0.85 * rim * (1.0 - 0.6 * light_glass) : 0.0;
        if (ln > 0.0 || gl > 0.004) {
            vec3 base = col.rgb / max(col.a, 1e-3);
            vec3 seen = env(px + n * env_reach * 0.5);
            vec3 lc = mix(seen, vec3(1.0), 0.8);
            vec3 under = base * (1.0 - veil_a) + vec3(veil_r, veil_g, veil_b) * veil_a;
            // Light adds: the glint screens over what is there, in the light's own
            // colour (mostly white, a little of the room), never darkening it.
            under = vec3(1.0) - (vec3(1.0) - under) * (vec3(1.0) - mix(seen, vec3(1.0), 0.85) * min(gl, 1.0));
            vec3 want = mix(under, lc, ln);
            col.rgb = throughVeil(want) * col.a;
        }
    }
    // Light glass over a light backdrop has no edge of its own, so a bar can keep
    // a thin dark contact line: darker, never lit. Sides on the screen edge have none.
    if (hair > OFF)
        col.rgb *= 1.0 - hair * smoothstep(1.6, 0.6, inside) * smoothstep(0.0, 0.4, inside);
    col.rgb += vec3(grain(px) / 255.0) * col.a;

    cogl_color_out = (col * cov + vec4(0.0, 0.0, 0.0, s) * (1.0 - cov)) * cogl_color_in.a;
}
`;

// The backdrop's overall brightness, for "adapt" and "lift": four reads at fixed
// points of the blurred backdrop, a quarter of the way in from each corner. They are
// the same for every pixel, so the vertex stage reads them once per corner of the
// pane and hands the result to every pixel (it was four texture reads per pixel).
const ADAPT_VERTEX = {
    decls: `
uniform float width;
uniform float height;
uniform float pad;
uniform float tex_w;
uniform float tex_h;
uniform float org_x;
uniform float org_y;
uniform float shape_w;
uniform float shape_h;
uniform float adapt;
uniform float lift;
varying float fg_bl;
vec3 fgAt(vec2 px) {
    vec2 size = vec2(width, height);
    return texture2DLod(cogl_sampler0, (clamp(px, vec2(0.5), size - vec2(0.5)) + vec2(org_x, org_y)) / vec2(tex_w, tex_h), 0.0).rgb;
}
`,
    code: `
    fg_bl = 0.0;
    if (adapt > 0.001 || lift > 0.001) {
        vec2 size = vec2(width, height);
        vec2 q = max(vec2(shape_w, shape_h) * 0.5 - vec2(pad), vec2(1.0)) * 0.5;
        fg_bl = dot((fgAt(size * 0.5 + vec2(-q.x, -q.y)) + fgAt(size * 0.5 + vec2(q.x, -q.y))
                   + fgAt(size * 0.5 + vec2(-q.x, q.y)) + fgAt(size * 0.5 + q)) * 0.25,
                    vec3(0.213, 0.715, 0.072));
    }
`,
};

const GLASS = new Shader(SHADER, ADAPT_VERTEX);

/**
 * Each screen is painted on its own, and only inside what changed on it. A pane
 * that reaches onto the next screen (a window by the seam, or the soft edge of its
 * glass) can come up for a render while that screen paints: Mutter then draws the
 * windows and wallpaper behind it only on that screen, and the glass keeps a
 * picture with the wallpaper's glow where the windows behind should be until it
 * renders again (Slack's title bar flickered as the pointer moved on the other
 * screen, 1.5.15). Returns the stage rect of the pane's part on the screen holding
 * most of it when that is not the screen being painted, else null.
 */
/**
 * Whether this frame redraws all of the pane: its redraw area holds the whole pane
 * (a pane that moved or grew, a menu opening, a frame that redraws the whole screen).
 * Then the pane already got everything behind it, and the full render queued after a
 * partial one would only draw the same picture again (the blur, copy and lens a
 * second time). Anything unsure counts as not whole, which renders again as before.
 */
function drawnWhole(paintContext, a) {
    try {
        if (!a || painting.view === null)
            return false;
        const clip = paintContext.get_redraw_clip();
        const e = a.get_transformed_extents();
        const r = new Mtk.Rectangle({
            x: Math.floor(e.get_x()), y: Math.floor(e.get_y()),
            width: Math.ceil(e.get_x() + e.get_width()) - Math.floor(e.get_x()),
            height: Math.ceil(e.get_y() + e.get_height()) - Math.floor(e.get_y()),
        });
        // No other screen may show any of it (see homeScreen): each screen redraws
        // only its own part. What lies off every screen is never drawn or seen, so
        // only the part on the screen being painted has to be in the redraw area.
        const lay = view => {
            const q = new Mtk.Rectangle();
            view.get_layout(q);
            return q;
        };
        const overlaps = (q, o) => q.x < o.x + o.width && o.x < q.x + q.width && q.y < o.y + o.height && o.y < q.y + q.height;
        for (const view of global.stage.peek_stage_views()) {
            if (view !== painting.view && overlaps(lay(view), r))
                return false;
        }
        const v = lay(painting.view);
        const x1 = Math.max(r.x, v.x), y1 = Math.max(r.y, v.y);
        const x2 = Math.min(r.x + r.width, v.x + v.width), y2 = Math.min(r.y + r.height, v.y + v.height);
        if (x2 <= x1 || y2 <= y1)
            return false;
        if (!clip)
            return true;
        const on = new Mtk.Rectangle({x: x1, y: y1, width: x2 - x1, height: y2 - y1});
        return clip.contains_rectangle(on) === Mtk.RegionOverlap.IN;
    } catch {
        return false;
    }
}

function homeScreen(a) {
    try {
        return offHome(a);
    } catch {
        return null;     // never stop the glass from rendering
    }
}

function offHome(a) {
    const view = painting.view;
    const views = a && view ? global.stage.peek_stage_views() : [];
    if (views.length < 2)
        return null;     // one screen, or drawn off screen (a screenshot): all of it is drawn
    const [x0, y0] = a.get_transformed_position();
    const [w, h] = a.get_transformed_size();
    const part = v => {
        const r = new Mtk.Rectangle();
        v.get_layout(r);
        const x = Math.max(x0, r.x), y = Math.max(y0, r.y);
        const pw = Math.min(x0 + w, r.x + r.width) - x, ph = Math.min(y0 + h, r.y + r.height) - y;
        return pw > 0 && ph > 0 ? {x, y, width: Math.ceil(pw), height: Math.ceil(ph), area: pw * ph} : {area: 0};
    };
    const here = part(view).area;
    let best = null;
    for (const v of views) {
        if (v === view)
            continue;
        const p = part(v);
        if (p.area > here && p.area > (best?.area ?? 0))
            best = p;
    }
    return best && {x: best.x, y: best.y, width: best.width, height: best.height};
}

// The screen being painted right now (null between screen paints), followed while
// any glass exists.
const painting = {view: null, ids: []};
function followPainting(on) {
    if (on && !painting.ids.length) {
        painting.ids = [
            global.stage.connect('before-paint', (_s, view) => (painting.view = view)),
            global.stage.connect('after-paint', () => (painting.view = null)),
        ];
        // The graphics driver threw the pictures away (NVIDIA, after a resume). GNOME 51
        // has no such signal.
        if (GObject.signal_lookup('gl-video-memory-purged', global.stage.constructor.$gtype)) {
            painting.ids.push(global.stage.connect('gl-video-memory-purged', () => panes.forEach(p => {
                p._glass.drop();
                p.queue_redraw();
            })));
        }
    } else if (!on && painting.ids.length) {
        painting.ids.forEach(id => global.stage.disconnect(id));
        painting.ids = [];
        painting.view = null;
    }
}

// The copy of a window behind a pane. A change anywhere in a window used to
// re-render every pane that copies it: Clutter passes each redraw of a window on
// to its copies whole, so a clock ticking at the top of a terminal re-rendered the
// glass of a window over its far corner, and the panel's, once a second (on 1.5.17
// a ticking terminal clock cost 41 % of a core here, 3 % without glass). This copy
// reports no area of its own: the redraw still reaches the pane, but adds nothing to
// what the frame redraws, so the pane renders only when the window changed where the
// pane is (Clutter paints a pane only inside the frame's redraw area). The pane then
// renders in full the frame after (see vfunc_paint), so its wallpaper stays whole.
// GNOME 51 and later only: GNOME 50 still redraws the whole pane (see setSources).
const QUIET_COPIES = (parseInt(PACKAGE_VERSION) || 0) >= 51;
const WindowCopy = GObject.registerClass(
class FedoraGlassWindowCopy extends Clutter.Clone {
    vfunc_get_paint_volume(_volume) {
        return true;    // valid and empty
    }

});

/**
 * The pane drawing its copies of what is behind it now, or null. A window's glass drawn in
 * one of its copies leaves out what the windows above it, drawn in the same pane, cover
 * (see Holder in windows.js); in anyone else's copy (Alt+Tab, the overview, Dash to Panel's
 * previews) the window is shown alone. (Marked by the pane, not by its copies: a Clutter.Clone
 * that draws through its own paint() drew the wallpaper dark.)
 */
export const copying = {pane: null};

// The lens's own pipeline: one GL program for every pane (each pane's pipeline is a
// copy of this one, with its own uniforms and texture), on GNOME 50 and 51 alike.
let lensTemplate = null;
let plainTemplate = null;
function coglContext() {
    return global.stage.get_context().get_backend().get_cogl_context();
}
function lensPipeline() {
    if (!lensTemplate) {
        lensTemplate = Cogl.Pipeline.new(coglContext());
        lensTemplate.set_layer_null_texture(0);
        lensTemplate.set_layer_filters(0, Cogl.PipelineFilter.LINEAR, Cogl.PipelineFilter.LINEAR);
        lensTemplate.set_layer_wrap_mode(0, Cogl.PipelineWrapMode.CLAMP_TO_EDGE);
        lensTemplate.add_snippet(GLASS.cogl());
        // The backdrop's overall brightness, once per corner (ADAPT_VERTEX).
        lensTemplate.add_snippet(GLASS.coglVertex());
    }
    return lensTemplate.copy();
}
function plainPipeline() {
    plainTemplate ??= Cogl.Pipeline.new(coglContext());
    return plainTemplate;
}

/**
 * The screen's own px per px of the actor: 1.25 at 125 %. Clutter's resource scale
 * rounds that up to 2, and a picture kept at 2 has 2.56 times the px the screen
 * shows. On two screens with different scales, the larger of those it is on.
 */
function screenScale(a) {
    let s = 0;
    try {
        const [x, y] = a.get_transformed_position();
        const [w, h] = a.get_transformed_size();
        for (const v of global.stage.peek_stage_views()) {
            const r = new Mtk.Rectangle();
            v.get_layout(r);
            if (x < r.x + r.width && x + w > r.x && y < r.y + r.height && y + h > r.y)
                s = Math.max(s, v.get_scale());
        }
    } catch {}   // never stop the glass from drawing
    return s > 0 && Number.isFinite(s) ? s : Math.max(1, a.get_resource_scale?.() ?? 1);
}

// Pictures are kept in sizes rounded up to this many px, so a window that is being
// resized reuses its picture instead of making a new one for every frame (Cogl
// textures are freed only when GJS collects them).
const TARGET_STEP = 32;
// How long a hidden pane keeps its picture (a menu opened again soon has it ready).
const DROP_HIDDEN_MS = 3000;

// A picture let go of is freed only when GJS collects its JS object, and GJS knows
// nothing of the graphics memory behind it: closing a few windows left hundreds of
// MB waiting. Once enough is let go of, collect it, once, when things are quiet.
const COLLECT_BYTES = 24 * 1024 * 1024;
const COLLECT_QUIET_MS = 1500;
const COLLECT_EVERY_US = 5e6;
const collect = {bytes: 0, timer: 0, last: 0};
function retire(t) {
    if (!t)
        return;
    if (!panes.size) {
        stopCollecting();    // the glass is going away: GJS collects it in its own time
        return;
    }
    collect.bytes += t.w * t.h * 8;    // colour plus depth and stencil
    if (collect.bytes < COLLECT_BYTES)
        return;
    if (collect.timer)
        GLib.source_remove(collect.timer);
    const wait = Math.max(COLLECT_QUIET_MS, (collect.last + COLLECT_EVERY_US - GLib.get_monotonic_time()) / 1000);
    collect.timer = GLib.timeout_add(GLib.PRIORITY_LOW, Math.ceil(wait), () => {
        collect.timer = 0;
        collect.bytes = 0;
        collect.last = GLib.get_monotonic_time();
        collections++;    // read by the QA tools
        System.gc();
        return GLib.SOURCE_REMOVE;
    });
}
let collections = 0;

/** Stop a collection that is waiting (the extension turns off). */
export function stopCollecting() {
    if (collect.timer)
        GLib.source_remove(collect.timer);
    collect.timer = 0;
    collect.bytes = 0;
}

/** Pictures the glass holds now, in px and as a count, and collections so far (QA tools). */
export function pictureStats() {
    let px = 0, n = 0;
    for (const p of panes) {
        for (const t of [p._glass._target, p._glass._out]) {
            if (t) {
                px += t.w * t.h;
                n++;
            }
        }
    }
    return {pictures: n, px, collections};
}

/**
 * The glass of one pane in a single step, where up to 1.5.18 it took three: GNOME's
 * blur kept its own copy of what is behind the pane, the lens copied the blurred result
 * again, and both at twice the screen's size under fractional scaling such as 125 %
 * (Clutter rounds the scale up for its offscreen effects). Here what is behind is drawn
 * once, straight into a picture at the blur's own resolution (GNOME's blur works at
 * half size and less for a wide blur, so a bigger picture holds nothing more), blurred
 * there, and the lens reads that picture as it draws the glass on screen. A maximized
 * window's glass went from about 180 MB to a few MB.
 */
const GlassEffect = GObject.registerClass(
class FedoraGlassEffect extends Clutter.Effect {
    _init() {
        super._init();
        this._frame = '';
        this._renderedAt = 0;
        this._catchUp = 0;
        this._radius = 0;
        this._target = null;     // {tex, fb, w, h, s}: the picture of what is behind
        this._targetFor = '';
        this._pipeline = lensPipeline();
        this._uniformAt = new Map();
        this._opacity = -1;
        this._keep = false;
        this._out = null;
        this._lensDirty = true;
    }

    /** µs until this pane may re-render for a change behind it (<= 0: now). */
    _rerenderWait() {
        const t = GLib.get_monotonic_time();
        // Behind a source that never stops (a video, a chat streaming for minutes),
        // catch up at half the rate once it has kept going for a while: the blur
        // hides the difference, and the glass does half the work for as long as it runs.
        const busy = this._busySince && t - this._busySince > BUSY_AFTER_US;
        const every = Math.max(dragging ? DRAG_RERENDER_US : RERENDER_US, busy ? BUSY_RERENDER_US : 0);
        return this._renderedAt + every - t;
    }

    /** Keep the picture for now, and render it in full `wait` µs from now. */
    _catchUpIn(wait) {
        this._stale = true;
        if (this._catchUp)
            return;
        this._catchUp = GLib.timeout_add(GLib.PRIORITY_DEFAULT, Math.ceil(wait / 1000), () => {
            this._catchUp = 0;
            if (this._stale)
                this.get_actor()?.queueFull?.();
            return GLib.SOURCE_REMOVE;
        });
    }

    /**
     * GNOME 50: a window behind changed (somewhere). Re-render in full now, or at
     * the next catch-up if the pane rendered too recently.
     */
    behindChanged() {
        const wait = this._picture ? this._rerenderWait() : 0;
        if (wait > 0)
            this._catchUpIn(wait);
        else
            this.get_actor()?.queueFull?.();
    }

    stopCatchUp() {
        if (this._catchUp)
            GLib.source_remove(this._catchUp);
        this._catchUp = 0;
    }

    /** Blur radius in px; 0 for none (the rim over a window mirrors the backdrop sharp). */
    set radius(r) {
        const v = r > 0.5 ? r : 0;
        if (v === this._radius)
            return;
        this._radius = v;
        this.queue_repaint();
    }

    get radius() {
        return this._radius;
    }

    /** Let go of the picture (the pane is hidden); the next paint renders a new one. */
    drop() {
        retire(this._out);
        retire(this._target);
        this._out = null;
        this._target = null;
        this._targetFor = '';
        this._pipeline.set_layer_null_texture(0);
    }

    /** px of picture per px of pane, and the picture's size, for this pane now. */
    _wants(a) {
        const w = Math.max(1, Math.ceil(a.width)), h = Math.max(1, Math.ceil(a.height));
        let s;
        if (this._radius > 0) {
            // GNOME's own rule (shell-blur-effect.c): the blur runs in the pane's
            // logical px, halved while the radius is over 12 px and the picture
            // stays over 256 px.
            let d = 1;
            while (this._radius / d > 12 && w / d > 256 && h / d > 256)
                d *= 2;
            s = 1 / d;
        } else {
            // A sharp copy, at the screen's own px (125 %: 1.25, where Clutter's
            // offscreens round up to 2).
            s = screenScale(a);
        }
        return `${w}x${h}@${s}/${this._radius}`;
    }

    _ensureTarget(a) {
        const want = this._wants(a);
        if (this._target && this._targetFor === want)
            return this._target;
        const [size, rest] = want.split('@');
        const [w, h] = size.split('x').map(Number);
        const s = Number(rest.split('/')[0]);
        const t = this._fit(this._target, w, h, s);
        if (!t) {
            this.drop();
            return null;
        }
        if (t !== this._target) {
            retire(this._target);
            this._target = t;
            this._pipeline.set_layer_texture(0, t.tex);
            this._frame = '';
            this._lensDirty = true;
        }
        this._targetFor = want;
        return t;
    }

    /** A picture for w x h px of pane at s px per px: t itself while it still fits. */
    _fit(t, w, h, s) {
        const pw = Math.max(1, Math.ceil(w * s)), ph = Math.max(1, Math.ceil(h * s));
        // Reuse the picture while the pane fits in it and fills most of it.
        if (t && t.s === s && pw <= t.w && ph <= t.h && pw * ph >= 0.6 * t.w * t.h)
            return t;
        // Growing (a window opening up or being resized larger): leave room to grow
        // into, so the next frames keep this picture instead of each making one.
        const room = t && t.s === s && (pw > t.w || ph > t.h) ? 1.15 : 1;
        const tw = Math.ceil(pw * room / TARGET_STEP) * TARGET_STEP, th = Math.ceil(ph * room / TARGET_STEP) * TARGET_STEP;
        try {
            const tex = Cogl.Texture2D.new_with_size(coglContext(), tw, th);
            tex.set_premultiplied(true);
            const fb = Cogl.Offscreen.new_with_texture(tex);
            fb.allocate();
            const m = new Graphene.Matrix();
            m.init_translate(new Graphene.Point3D({x: -tw / 2, y: -th / 2, z: 0}));
            m.scale(2 / tw, -2 / th, 1);
            fb.set_projection_matrix(m);
            return {tex, fb, w: tw, h: th, s, painted: false};
        } catch (e) {
            this._warnOnce(`Fedora Glass: no picture for the glass (${e.message})`);
            return null;
        }
    }

    /**
     * Keep the finished glass (an app window's): a window that repaints (an app
     * streaming text, a workspace switch) then shows the kept glass instead of
     * running the lens again. Kept at the screen's own px, where up to 1.5.18 a
     * holder actor kept it at twice the size under fractional scaling.
     */
    set keep(on) {
        on = Boolean(on);
        if (on === this._keep)
            return;
        this._keep = on;
        if (!on) {
            retire(this._out);
            this._out = null;
        }
        this.queue_repaint();
    }

    get keep() {
        return this._keep;
    }

    _warnOnce(message) {
        if (this._warned)
            return;
        this._warned = true;
        console.warn(message);
    }

    /** Copy (and blur) what is behind the pane into its picture. */
    _render(node, a, t) {
        const w = Math.ceil(a.width), h = Math.ceil(a.height);
        const layer = Clutter.LayerNode.new_to_framebuffer(t.fb, plainPipeline());
        layer.set_static_name?.('Fedora Glass (picture)');
        node.add_child(layer);
        let into = layer;
        if (this._radius > 0) {
            const bw = Math.max(1, Math.ceil(w * t.s)), bh = Math.max(1, Math.ceil(h * t.s));
            const blur = Clutter.BlurNode.new(bw, bh, this._radius * t.s);
            blur.set_static_name?.('Fedora Glass (blur)');
            layer.add_child(blur);
            blur.add_rectangle(new Clutter.ActorBox({x1: 0, y1: 0, x2: bw, y2: bh}));
            into = blur;
        }
        const m = new Graphene.Matrix();
        m.init_scale(t.s, t.s, 1);
        const scale = Clutter.TransformNode.new(m);
        into.add_child(scale);
        scale.add_child(Clutter.ActorNode.new(a, 255));
    }

    /** Draw the glass: render its picture first when asked, then the lens over it. */
    _draw(node, a, render) {
        const t = this._ensureTarget(a);
        if (!t) {
            node.add_child(Clutter.ActorNode.new(a, -1));
            return;
        }
        if (render || !t.painted) {
            this._render(node, a, t);
            t.painted = true;
            this._lensDirty = true;
        }
        const [w, h] = [a.width, a.height];
        // The lens reads the picture in the pane's own px: tex_* is how much of the
        // pane the whole picture would cover, and the pane starts at its top left.
        const key = `${t.w}x${t.h}@${t.s}`;
        if (key !== this._frame) {
            this._frame = key;
            this._set({tex_w: t.w / t.s, tex_h: t.h / t.s, org_x: 0, org_y: 0});
        }
        const o = a.get_paint_opacity();
        const box = new Clutter.ActorBox({x1: 0, y1: 0, x2: w, y2: h});
        if (this._keep) {
            const out = this._keepLens(node, a, t, w, h);
            if (out) {
                this._blit ??= plainPipeline().copy();
                if (this._blitTex !== out.tex) {
                    this._blitTex = out.tex;
                    this._blit.set_layer_texture(0, out.tex);
                    this._blit.set_layer_filters(0, Cogl.PipelineFilter.LINEAR, Cogl.PipelineFilter.LINEAR);
                }
                this._blit.set_color(new Cogl.Color({red: o, green: o, blue: o, alpha: o}));
                const kept = Clutter.PipelineNode.new(this._blit);
                kept.set_static_name?.('Fedora Glass (kept)');
                node.add_child(kept);
                kept.add_texture_rectangle(box, 0, 0, w * out.s / out.w, h * out.s / out.h);
                return;
            }
        }
        this._lens(node, t, box, w, h, o);
    }

    _lens(node, t, box, w, h, o) {
        if (o !== this._opacity) {
            this._opacity = o;
            this._pipeline.set_color(new Cogl.Color({red: o, green: o, blue: o, alpha: o}));
        }
        const lens = Clutter.PipelineNode.new(this._pipeline);
        lens.set_static_name?.('Fedora Glass (lens)');
        node.add_child(lens);
        lens.add_texture_rectangle(box, 0, 0, w * t.s / t.w, h * t.s / t.h);
    }

    /** Run the lens into the kept picture when anything changed; returns that picture. */
    _keepLens(node, a, t, w, h) {
        const s = screenScale(a);
        const out = this._fit(this._out, w, h, s);
        if (!out)
            return null;
        if (out !== this._out) {
            retire(this._out);
            this._out = out;
            this._lensDirty = true;
        }
        if (this._lensDirty || !out.painted) {
            const layer = Clutter.LayerNode.new_to_framebuffer(out.fb, plainPipeline());
            layer.set_static_name?.('Fedora Glass (keep)');
            node.add_child(layer);
            const m = new Graphene.Matrix();
            m.init_scale(s, s, 1);
            const scale = Clutter.TransformNode.new(m);
            layer.add_child(scale);
            this._lens(scale, t, new Clutter.ActorBox({x1: 0, y1: 0, x2: w, y2: h}), w, h, 255);
            out.painted = true;
            this._lensDirty = false;
            this.keptLens = (this.keptLens ?? 0) + 1;    // read by the QA tools
        }
        return out;
    }

    vfunc_paint_node(node, paintContext, flags) {
        const a = this.get_actor();
        if (!a)
            return;
        if (flags & Clutter.EffectPaintFlags.BYPASS_EFFECT) {
            node.add_child(Clutter.ActorNode.new(a, -1));
            return;
        }
        // No picture yet (new, resized, or let go of while hidden): render now.
        if (!this._target || this._targetFor !== this._wants(a))
            flags |= Clutter.EffectPaintFlags.ACTOR_DIRTY;
        const dirty = Clutter.EffectPaintFlags.ACTOR_DIRTY;
        const size = a ? `${a.width}x${a.height}` : '';
        // While a window animates (see holdPanes), a pane that has a picture of
        // the right size shows it again instead of re-rendering: what changed
        // behind it is caught up in one render when the animation lands. The lens
        // still runs on the kept picture, so the pointer light and press stay live.
        if ((flags & dirty) && hold.held && !a?._free && this._picture === size) {
            this._stale = true;
            this.held = (this.held ?? 0) + 1;    // read by the QA tools
            this._draw(node, a, false);
            return;
        }
        // A window behind that repaints all the time (a chat app streaming text, a
        // video) would re-render this glass for every one of its frames. While the
        // pane itself stays put, show the kept picture and catch up a little later:
        // at most RERENDER_HZ renders a second for changes behind it.
        if ((flags & dirty) && !this._full && !a?._free && this._picture === size &&
            this._placedAt === (a?._placed ?? '')) {
            const wait = this._rerenderWait();
            if (wait > 0) {
                this.throttled = (this.throttled ?? 0) + 1;    // read by the QA tools
                this._catchUpIn(wait);
                this._draw(node, a, false);
                return;
            }
            // Time to catch up, but this frame redraws only part of the screen (the
            // window behind that changed). Rendered now, the glass would copy only that
            // part of what is behind it and show the rest wrong for a frame (another
            // window's glow came and went behind Slack's title bar on 1.5.13). Keep the
            // picture and render it whole next frame instead.
            this._stale = true;
            this.deferred = (this.deferred ?? 0) + 1;    // read by the QA tools
            a?.queueFull?.();
            this._draw(node, a, false);
            return;
        }
        // Painted along with the other screen, the glass would copy only that
        // screen's part of what is behind it (see homeScreen). Keep the picture and
        // render it while its own screen paints. Three times in a row at most, so
        // a pane that can't tell its screen apart still renders.
        const home = (flags & dirty) && this._picture === size && (this._offHome ?? 0) < 3 ? homeScreen(a) : null;
        if (home) {
            this._offHome = (this._offHome ?? 0) + 1;
            this._stale = true;
            this.offScreen = (this.offScreen ?? 0) + 1;    // read by the QA tools
            a?.queueFull?.(home);
            this._draw(node, a, false);
            return;
        }
        if (flags & dirty)
            this._offHome = 0;
        // A pane that moved this frame is inside Mutter's redraw area as a whole.
        const moved = (flags & dirty) && this._placedAt !== (a?._placed ?? '');
        if (flags & dirty) {
            this._picture = size;
            this._placedAt = a?._placed ?? '';
            const t = GLib.get_monotonic_time();
            // Renders close after each other: the source behind keeps changing.
            if (!this._busySince || t - this._renderedAt > BUSY_GAP_US)
                this._busySince = t;
            this._renderedAt = t;
            this._stale = false;
        }
        // Re-rendered for a change in part of it, the pane only gets that part's
        // wallpaper (Mutter paints the wallpaper only inside the frame's redraw
        // area). Its blur and rim reach past that part, and the copy is kept and
        // shown again later, so re-render all of it once more, in full.
        if (flags & dirty) {
            this.renders = (this.renders ?? 0) + 1;    // read by the QA tools
            renderTotal++;    // read by speed.js
            // This frame redraws all of the pane: it gets everything behind it now, so a
            // full render asked for before it (the copies moved as the pane was placed)
            // would only draw the same picture again next frame.
            const whole = drawnWhole(paintContext, a);
            if (whole)
                a?.dropQueuedFull?.();
            if (this._full)
                this._full = false;
            else if (dragging && moved)
                fullAfterDrag.add(this);    // it renders again next frame anyway; one full render when the drag ends
            else if (!whole)
                this.get_actor()?.queueFull?.();
        }
        this._draw(node, a, Boolean(flags & dirty));
    }

    _set(values) {
        GLASS.setOn(this._pipeline, this._uniformAt, values);
    }

    setFloats(values) {
        this._set(values);
        this._lensDirty = true;
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
    floor: 0,           // 0 = off; light glass: the darkest it may get (linear Y, 0..0.9)
    haze: 0,            // 0..0.7, dark glass: grey smoke in the glass, so it shows over black
    solid: 0,           // 1: fill the pane fully, for a full-screen sheet
    pointerLight: 0.5,  // 0..1, how far the light turns towards the pointer
    motion: 1,          // 0 or 1: press and open springs
    liquid: 1,          // 0.25..2.5, how far the glass gives under a press (1: the original feel)
    adapt: 0.35,        // 0..1, how much the glass adjusts to what's behind it
    lift: 0,            // 0..1, light glass: its milk thickens over a dark backdrop
    milk: [0.96, 0.965, 0.98], // the light glass's own body colour, rgb 0..1
    hairline: 0,        // 0..0.3, light glass: a thin dark line at its edge
    shadow: 0,          // 0..1, drawn by the pane itself
    rim: 0.85,          // 0..1, the thin bright line along the very edge
    veil: [0, 0, 0, 0], // straight rgba: the theme's veil over this glass, so the line reads through it
    textShade: 0,       // 0..1, a soft shade right behind bright text (clear glass)
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

// The theme's veil over a pane, as uniforms; anything malformed counts as no veil.
function veilOf(v) {
    const ok = Array.isArray(v) && v.length === 4 && v.every(Number.isFinite);
    const [r, g, b, a] = ok ? v.map(x => Math.max(0, Math.min(1, x))) : [0, 0, 0, 0];
    return [r, g, b, Math.min(a, 0.9)];
}
const ENV_REACH = 32;
// Room around a pane for its soft shadow. Every px of it is blurred and shaded on
// every render, so it is only as wide as the shadow reaches (offset 6 + about 2.5
// sigma), and the reflections pane on top has none: 1.5.0 gave both 40 px, which
// made the panel's glass half again as costly on each frame.
const SHADOW_PAD = 26;   // px the rim sees beyond the edge
// How often a pane that stays put re-renders for changes behind it, at each
// quality level (see setQuality): full, lighter, lightest.
const RERENDER_HZ = [20, 10, 5];
let RERENDER_US = 1e6 / RERENDER_HZ[0];
// While a window is dragged or resized, glass that stays put catches up with changes
// behind it at the next lighter level's rate (eyes follow the window), and glass that
// moves renders once a frame instead of twice; everything renders in full once it ends.
let dragging = false;
let DRAG_RERENDER_US = 1e6 / RERENDER_HZ[1];
// A pane that has re-rendered for changes behind it without a pause (renders less
// than BUSY_GAP_US apart) for BUSY_AFTER_US catches up at most every BUSY_RERENDER_US.
const BUSY_AFTER_US = 3e6;
const BUSY_GAP_US = 400e3;
let BUSY_RERENDER_US = 2 * RERENDER_US;
const fullAfterDrag = new Set();

const GLOW_BLUR = 30;   // px the content's light spreads

// While a window is dragged or resized, every pane re-renders each frame, so they
// all drop to fewer taps until shortly after it settles. A still frame looks the same.
const panes = new Set();
let cheapTimer = 0;

// How much the glass draws (speed.js picks it): 0 full, 1 lighter (fewer taps and
// fewer re-renders for changes behind), 2 lightest (as lighter, and the owners
// show only the wallpaper behind the glass).
let quality = 0;
let renderTotal = 0;

export function setQuality(level) {
    const q = Math.max(0, Math.min(2, Math.round(Number(level) || 0)));
    if (q === quality)
        return;
    quality = q;
    RERENDER_US = 1e6 / RERENDER_HZ[q];
    DRAG_RERENDER_US = 1e6 / RERENDER_HZ[Math.min(2, q + 1)];
    BUSY_RERENDER_US = 2 * RERENDER_US;
    panes.forEach(p => p._setCheap(p._moving));
}

export function getQuality() {
    return quality;
}

// Weather frost (frost.js): how frosty all the glass is now, 0..1, and how far it has
// iced over from its edges. Both 0 unless weather frost is on and it is cool out. A change sets two numbers on each
// pane, so it is drawn again from the copy it already has; only when the extra blur
// steps (frostBlur) is the backdrop blurred again.
let frostNow = {frost: 0, flakes: 0, blur: 0};

export function setFrost(frost, flakes) {
    const f = Math.max(0, Math.min(1, Number(frost) || 0));
    const k = Math.max(0, Math.min(1, Number(flakes) || 0));
    const blur = frostBlur(f);
    if (f === frostNow.frost && k === frostNow.flakes)
        return;
    const reblur = blur !== frostNow.blur;
    frostNow = {frost: f, flakes: k, blur};
    panes.forEach(p => (reblur ? p._applyLook() : p._applyFrost()));
}

export function getFrost() {
    return {...frostNow};
}

/** How many times any pane has rendered since the Shell started. */
export function glassRenders() {
    return renderTotal;
}

/** How many panes are on screen. */
export function shownPanes() {
    let n = 0;
    for (const p of panes)
        n += p.mapped && p.visible ? 1 : 0;
    return n;
}

/** For the speed check: render every pane on screen again, in full, next frame. */
export function redrawAllPanes() {
    for (const p of panes) {
        if (p.mapped)
            p.queueFull();
    }
}

function endDrag() {
    dragging = false;
    const owed = [...fullAfterDrag];
    fullAfterDrag.clear();
    for (const effect of owed) {
        try {
            effect.get_actor()?.queueFull?.();
        } catch {}    // its pane went away during the drag
    }
}

/** For tests and the QA tools: whether a drag is going on. */
export function isDragging() {
    return dragging;
}

export function moving(on) {
    if (cheapTimer) {
        GLib.source_remove(cheapTimer);
        cheapTimer = 0;
    }
    if (on) {
        dragging = true;
        panes.forEach(p => p._setCheap(true));
        return;
    }
    cheapTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 150, () => {
        cheapTimer = 0;
        endDrag();
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

// Our own window animations (animations.js) call these at their start and end, so
// they also hold the glass (see holdPanes): Mutter may already count an opening
// window as shown while ours still plays.
export function freezeSource(actor) {
    holdPanes(actor);
    if (!freezing || frozen.has(actor))
        return;
    frozen.add(actor);
    panes.forEach(p => p._clones.has(actor) && p._syncClones());
}

export function thawSource(actor) {
    releasePanes(actor);
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

// While a window animates (opening, minimizing, restoring, closing; GNOME's own
// animations or ours), no pane re-renders: each keeps its last picture, and one that went stale renders once
// when the last of them ends. On software GL a window-sized pane takes 40-150 ms
// to render, so re-rendering during the animation turned each such frame into a
// stall. The hold has a hard time limit (holdstate.js), so the glass never stays
// behind for long, however many animations follow each other.
const hold = new GlassHold({
    panes: () => panes,
    alive: p => panes.has(p),
    isStale: p => Boolean(p._glass._stale),
    // Bottom window first; Shell surfaces (the panel, menus) sit above all windows.
    rank: p => {
        const order = global.get_window_actors();
        let a = p;
        while (a && !a.meta_window)
            a = a.get_parent();
        const i = a ? order.indexOf(a) : -1;
        return i < 0 ? order.length : i;
    },
    keep: p => {
        p._free = false;
        p._syncClones();    // hides the copies of windows behind
    },
    free: p => {
        p._free = true;
        p._glass._stale = false;
        p._syncClones();    // shows them again
        p.queueFull();
    },
    renders: p => p._glass.renders ?? 0,
    afterFrame: fn => global.stage.connect('after-paint', fn),
    cancelFrame: id => global.stage.disconnect(id),
    endAll: () => {
        for (const p of panes) {
            p._free = false;
            p._syncClones();
            if (p._glass._stale) {
                p._glass._stale = false;
                p.queueFull();
            }
        }
    },
});

// For QA: compare with and without the hold in one session.
export function qaHold(on) {
    hold.enabled = Boolean(on);
    if (!hold.enabled)
        releaseAllPanes(true);
}

// For QA frame strips: with steps on, the catch-up waits for qaCatchUpStep()
// before each pane (the first included), so each step can be captured.
export function qaCatchUp(steps) {
    hold.manual = Boolean(steps);
}

export function qaCatchUpStep() {
    return hold.step()?.name ?? 'done';
}

/** Hold the glass for `key` (a window actor) until releasePanes(key), at most HOLD_LIMIT_MS. */
export function holdPanes(key) {
    hold.hold(key);
}

export function releasePanes(key) {
    hold.release(key);
}

/** Let the glass go; with `now` (turning off), at once, without the one-per-frame catch-up. */
export function releaseAllPanes(now = false) {
    hold.releaseAll(now);
}

export function panesHeld() {
    return hold.held;
}




export function stopMoving() {
    stopCollecting();
    if (cheapTimer)
        GLib.source_remove(cheapTimer);
    cheapTimer = 0;
    dragging = false;
    fullAfterDrag.clear();
}

// The screen that holds the middle of a stage rectangle.
export function monitorFor(x, y, w, h) {
    const d = global.display;
    const n = d?.get_n_monitors?.() ?? 0;
    const cx = x + w / 2, cy = y + h / 2;
    let best = null, bestD = Infinity;
    for (let i = 0; i < n; i++) {
        const g = d.get_monitor_geometry(i);
        const dx = Math.max(g.x - cx, 0, cx - (g.x + g.width));
        const dy = Math.max(g.y - cy, 0, cy - (g.y + g.height));
        if (dx + dy < bestD) {
            bestD = dx + dy;
            best = g;
        }
    }
    return best;
}

/**
 * A copy of what lies behind a pane (the wallpaper, a window). It tells Clutter it
 * paints only inside its clip, the pane's own spot (see GlassPane._clipClone); a plain
 * Clutter.Clone reports the size of what it copies, whatever its clip. Clutter redraws
 * all of that each time a copy moves, and a moving pane moves all of its copies on
 * every frame: dragging a window repainted the whole wallpaper copy (both screens) and
 * every window behind, on every frame (1.5.18).
 */
const GlassClone = GObject.registerClass({GTypeName: 'FedoraGlassClone'},
class FedoraGlassClone extends Clutter.Clone {
    vfunc_get_paint_volume(volume) {
        if (!this.has_clip)
            return super.vfunc_get_paint_volume(volume);
        const [x, y, w, h] = this.get_clip();
        volume.set_origin(new Graphene.Point3D({x, y, z: 0}));
        volume.set_width(Math.max(0, w));
        volume.set_height(Math.max(0, h));
        return true;
    }

});

export const GlassPane = GObject.registerClass(
class FedoraGlassPane extends Clutter.Actor {
    _init(layer = 'full') {
        // Hidden until placed: an effect on an empty actor asks Cogl for a 0×0 texture.
        super._init({name: `fedora-glass-${layer}`, clip_to_allocation: true, reactive: false, visible: false});
        this._layer = LAYERS[layer] ?? 0;
        if (this._layer === LAYERS.reflections) {
            // Its source is the surface's own content; a black background keeps it
            // painted (an empty actor gets no offscreen) and adds no light.
            this.background_color = new Cogl.Color({red: 0, green: 0, blue: 0, alpha: 255});
        }
        // One effect copies and blurs what is behind and draws the lens over it.
        this._glass = new GlassEffect();
        this.add_effect_with_name('fedora-glass-lens', this._glass);
        this._look = {...DEFAULT_LOOK};
        this._radii = [0, 0, 0, 0];
        this._pad = 0;
        this._stage = [0, 0];
        this._size = [1, 1];
        this._whole = [1, 1];       // the whole glass, padding included (see setPart)
        this._at = [0, 0];          // where this pane starts in it
        this._part = null;
        this._inner = null;         // [x, y, w, h] of the glass inside the pane, when smaller (see place)
        this._innerKey = '';
        this._clones = new Map();   // source actor -> clone
        this._placed = '';
        this._edges = '';
        this.setEdges([false, false, false, false]);
        this._cheap = false;
        this._lite = false;
        this._moving = false;
        this._motion = {sx: 0, sy: 0, k: 0, press: 0, open: 1, pullX: 0, pullY: 0};
        this._applyLook();
        panes.add(this);
        followPainting(true);
        this._fullLater = 0;
        // Hidden (a menu closed, the panel's screen gone): let go of the picture after
        // a little while, so a closed menu keeps no copy of what was behind it.
        this._dropLater = 0;
        this.connect('notify::mapped', () => {
            if (this._dropLater)
                GLib.source_remove(this._dropLater);
            this._dropLater = 0;
            if (!this.mapped) {
                this._dropLater = GLib.timeout_add(GLib.PRIORITY_LOW, DROP_HIDDEN_MS, () => {
                    this._dropLater = 0;
                    if (!this.mapped)
                        this._glass.drop();
                    return GLib.SOURCE_REMOVE;
                });
            }
        });
        this.connect('destroy', () => {
            if (this._fullLater)
                global.compositor.get_laters().remove(this._fullLater);
            this._fullLater = 0;
            if (this._dropLater)
                GLib.source_remove(this._dropLater);
            this._dropLater = 0;
            this._glass.stopCatchUp();
            panes.delete(this);
            this._glass.drop();
            followPainting(panes.size > 0);
            this._clones.clear();
        });
    }

    get pad() {
        return this._pad;
    }

    vfunc_paint(ctx) {
        const was = copying.pane;
        copying.pane = this;
        try {
            super.vfunc_paint(ctx);
        } finally {
            copying.pane = was;
        }
    }

    /**
     * Redraw all of the pane (see FedoraGlassEffect.vfunc_paint), before the next
     * frame. With `only` (a stage rect), redraw just its part on that screen.
     */
    queueFull(only = null) {
        // Held (see holdPanes): render once when the hold ends.
        if (this._kept()) {
            this._glass._stale = true;
            return;
        }
        // A whole redraw asked for since wins over one for a single screen.
        this._fullOnly = this._fullLater ? (only && this._fullOnly) : only;
        if (this._fullLater)
            return;
        this._fullLater = global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
            this._fullLater = 0;
            const r = this._fullOnly;
            this._fullOnly = null;
            this._glass._full = true;
            const [ok, x, y] = r ? this.transform_stage_point(r.x, r.y) : [false];
            if (ok)
                this.queue_redraw_with_clip(new Mtk.Rectangle({x: Math.floor(x), y: Math.floor(y), width: r.width, height: r.height}));
            else
                this.queue_redraw();
            return GLib.SOURCE_REMOVE;
        });
    }

    /** A whole render is being drawn now (see drawnWhole): drop the one queued before it. */
    dropQueuedFull() {
        if (!this._fullLater)
            return;
        global.compositor.get_laters().remove(this._fullLater);
        this._fullLater = 0;
        this._fullOnly = null;
        this.dropped = (this.dropped ?? 0) + 1;    // read by the QA tools
    }

    /**
     * restack: put the copies in order even when the order is the same. The relayout
     * that queues is what redraws all of a pane whose owner just moved or changed size,
     * so owners pass false when theirs didn't (see WindowGlass._place).
     */
    setSources(actors, restack = true) {
        const keep = new Set(actors);
        for (const [src, clone] of this._clones) {
            if (!keep.has(src)) {
                this._clones.delete(src);
                clone.destroy();
            }
        }
        let below = null;
        const order = this._order ?? [];
        if (!restack && (order.length !== actors.length || actors.some((a, i) => order[i] !== a)))
            restack = true;
        this._order = [...actors];
        for (const src of actors) {
            let clone = this._clones.get(src);
            if (!clone) {
                restack = true;
                clone = src.meta_window && QUIET_COPIES ? new WindowCopy({source: src}) : new GlassClone({source: src});
                // A clone outlives its source, so a source that goes away takes its copy with it.
                const ids = [src.connect('destroy', () => {
                    if (this._clones.get(src) === clone) {
                        this._clones.delete(src);
                        clone.destroy();
                    }
                })];
                // GNOME 50 redraws the whole pane for any redraw of a copy inside it, so
                // there a window behind changing still re-renders each pane that copies it,
                // in full (the wallpaper paints only inside the frame's redraw area: a
                // part-redrawn pane would lose it around the change, and its blur and rim
                // read black), at most as often as the re-render limit allows.
                if (!QUIET_COPIES && GObject.signal_lookup('damaged', src.constructor.$gtype))
                    ids.push(src.connect('damaged', () => frozen.has(src) || this._glass.behindChanged()));
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
            // Restacked even in the same order unless the owner says it stayed put: the
            // relayout it queues is what redraws the whole pane when a window grows under
            // a corner drag (skipping it left a black patch below a growing terminal in
            // the release checks).
            if (restack) {
                if (below)
                    this.set_child_above_sibling(clone, below);
                else
                    this.set_child_below_sibling(clone, null);
            }
            below = clone;
        }
        this._syncClones();
    }

    /** Keep the finished glass (see FedoraGlassEffect.keep). */
    setKeep(on) {
        this._glass.keep = on;
    }

    /** Which sides touch the screen edge ([left, top, right, bottom], booleans): those get no rim. */
    setEdges(edges) {
        const key = edges.map(Number).join();
        if (key === this._edges)
            return;
        this._edges = key;
        const [l, t, r, b] = edges.map(e => (e ? 1 : 0));
        this._glass.setFloats({edge_l: l, edge_t: t, edge_r: r, edge_b: b});
        this._applyClip();
    }

    /**
     * A side on the screen edge carries its glass on out to the edge of the pane.
     * Where that edge is the seam with a second screen, the glass would show on the
     * other screen as a strip beside the window or panel: cut it at the seam.
     *
     * A panel's or menu's glass that sits on one screen stops at that screen's edge
     * on every side: its room for the blur, rim and shadow reached 27 px over the seam,
     * so each step of the pointer light on a panel redrew the other screen as well.
     */
    _applyClip() {
        const sides = (this._edges ?? '').split(',').map(Number);
        const onOne = this._layer === LAYERS.glass || this._layer === LAYERS.reflections;
        if (!this._stage || !this._size || !(onOne || sides.some(Boolean))) {
            if (this.has_clip)
                this.remove_clip();
            return;
        }
        const [px, py] = this._stage, [pw, ph] = this._size, p = this._pad;
        const m = monitorFor(px + p, py + p, pw - 2 * p, ph - 2 * p);
        if (!m) {
            if (this.has_clip)
                this.remove_clip();
            return;
        }
        // The surface itself lies on that one screen (a px of slack for rounding).
        const inside = onOne && px + p >= m.x - 1 && py + p >= m.y - 1 &&
            px + pw - p <= m.x + m.width + 1 && py + ph - p <= m.y + m.height + 1;
        const cut = i => inside || sides[i];
        const x0 = cut(0) ? Math.max(0, m.x - px) : 0;
        const y0 = cut(1) ? Math.max(0, m.y - py) : 0;
        const x1 = cut(2) ? Math.min(pw, m.x + m.width - px) : pw;
        const y1 = cut(3) ? Math.min(ph, m.y + m.height - py) : ph;
        if (x0 <= 0 && y0 <= 0 && x1 >= pw && y1 >= ph) {
            if (this.has_clip)
                this.remove_clip();
            return;
        }
        this.set_clip(x0, y0, Math.max(0, x1 - x0), Math.max(0, y1 - y0));
    }

    // Fewer taps while something moves behind (moving()); lighter glass (setQuality) has its own.
    _setCheap(movingNow) {
        this._moving = Boolean(movingNow);
        const on = this._moving;
        const lite = quality >= 1;
        if (on === this._cheap && lite === this._lite)
            return;
        this._cheap = on;
        this._lite = lite;
        this._glass.setFloats({cheap: on ? 1 : 0, lite: lite ? 1 : 0});
    }

    setLook(look) {
        this._look = {...DEFAULT_LOOK, ...look};
        this._applyLook();
    }

    /**
     * Draw only part of the glass: [x, y, w, h] in the whole pane's px (its padding
     * included), or null for all of it. The rim over an app window is four thin
     * strips: each re-renders and repaints only its strip, where one pane the size
     * of the window made the whole window repaint every time the rim changed.
     */
    setPart(part) {
        this._part = part ? part.map(v => Math.round(v)) : null;
    }

    /**
     * x, y, w, h: the surface in parent coordinates; sx, sy: its stage position.
     * inner: [sx, sy, w, h] on the stage when the glass is smaller than that and lies
     * inside it: a menu growing out of its button. The pane keeps its place and its
     * picture of what is behind, and only the shape drawn over that picture changes,
     * so each frame of the animation is a lens repaint instead of a new copy and
     * blur of the backdrop at a new size.
     */
    place(x, y, w, h, radii, sx, sy, inner = null) {
        const p = this._pad;
        const part = this._part ?? [];
        const key = [x, y, w, h, sx, sy, p, ...radii, ...part].map(v => Math.round(v * 4)).join();
        const innerKey = inner ? inner.map(v => Math.round(v * 4)).join() : '';
        const innerChanged = innerKey !== this._innerKey;
        this._innerKey = innerKey;
        this._inner = inner ? [inner[0] - sx, inner[1] - sy, inner[2], inner[3]] : null;
        if (key === this._placed) {
            if (innerChanged) {
                this._radii = radii.map(r => Math.max(0, Math.min(r, (inner?.[2] ?? w) / 2, (inner?.[3] ?? h) / 2)));
                this._applyShape();
            }
            this._syncClones();   // windows behind may still have moved
            return;
        }
        this._placed = key;
        this._radii = radii.map(r => Math.max(0, Math.min(r, (inner?.[2] ?? w) / 2, (inner?.[3] ?? h) / 2)));
        this._whole = [Math.max(1, Math.round(w + 2 * p)), Math.max(1, Math.round(h + 2 * p))];
        let [ax, ay, aw, ah] = [0, 0, ...this._whole];
        if (this._part) {
            const [qx, qy, qw, qh] = this._part;
            ax = Math.max(0, Math.min(qx, this._whole[0] - 1));
            ay = Math.max(0, Math.min(qy, this._whole[1] - 1));
            aw = Math.max(1, Math.min(qw, this._whole[0] - ax));
            ah = Math.max(1, Math.min(qh, this._whole[1] - ay));
        }
        this._at = [ax, ay];
        this.set_position(Math.round(x - p) + ax, Math.round(y - p) + ay);
        this._size = [aw, ah];
        this.set_size(...this._size);
        this._stage = [Math.round(sx - p) + ax, Math.round(sy - p) + ay];
        const [W, H] = global.stage.get_size();
        this._glass.setFloats({
            valid_x0: Math.max(0, -this._stage[0]), valid_y0: Math.max(0, -this._stage[1]),
            valid_x1: Math.min(this._size[0], W - this._stage[0]), valid_y1: Math.min(this._size[1], H - this._stage[1]),
        });
        this._syncClones();
        this._applyShape();
        this._applyClip();
        if (this._motion.k > 0)
            this._applyMotion();   // the pointer is held in this pane's own px
    }

    /** Whether the pane is held and has a picture of its size to keep showing. */
    _kept() {
        return hold.held && !this._free && this._glass._picture === `${this.width}x${this.height}`;
    }

    _syncClones() {
        const kept = this._kept();
        for (const [src, clone] of this._clones) {
            // Held, the copies of windows behind are hidden: a hidden copy does not
            // pass its window's redraws on, so the pane is not even asked to show its
            // kept picture again each time a window behind repaints.
            if (kept && src.meta_window) {
                if (clone.visible)
                    this._glass._stale = true;
                clone.hide();
                continue;
            }
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
            // Moved behind the pane: redraw all of it (the wallpaper paints only inside
            // the frame's redraw area, so a part-redrawn pane would read black around it).
            const moved = clone.x !== cx || clone.y !== cy || clone.width !== cw || clone.height !== ch || !clone.visible;
            clone.set_position(cx, cy);
            clone.set_size(cw, ch);
            this._clipClone(clone, cx, cy, cw, ch);
            clone.show();
            if (moved)
                this.queueFull();
        }
    }

    /**
     * A copy draws, and asks Clutter to redraw, only the part of it inside the pane
     * (see GlassClone).
     */
    _clipClone(clone, cx, cy, cw, ch) {
        const [pw, ph] = this._size;
        const x0 = Math.max(0, -cx), y0 = Math.max(0, -cy);
        const x1 = Math.min(cw, pw - cx), y1 = Math.min(ch, ph - cy);
        const [w, h] = [Math.max(0, x1 - x0), Math.max(0, y1 - y0)];
        const key = `${x0},${y0},${w},${h}`;
        if (clone._clipKey === key && clone.has_clip)
            return;
        clone._clipKey = key;
        clone._clipBox = [x0, y0, w, h];    // read while the copy draws (see Holder in windows.js)
        clone.set_clip(x0, y0, w, h);
    }

    _applyLook() {
        const L = this._look;
        const top = this._layer === LAYERS.reflections;
        // The reflections layer blurs a copy of the content into a glow map.
        // The rim over a window mirrors the backdrop sharp: it needs no blur of its own.
        const blur = top ? GLOW_BLUR : this._layer === LAYERS.rim ? 0
            : Math.max(0, Math.min(100, L.blur + (this._frosts() ? frostNow.blur : 0)));
        this._glass.radius = blur;
        // Room around the surface for the blur and the edge reflections to see past
        // the edge, and for the shadow.
        this._pad = Math.ceil(Math.min(64, Math.max(blur, top ? 0 : blur * 0.5 + ENV_REACH, !top && L.shadow > 0 ? SHADOW_PAD : 0, 2)));
        const a = L.lightAngle * Math.PI / 180;
        const [tr, tg, tb, ta] = L.tint;
        const veil = veilOf(L.veil);
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
            floor_y: this._layer >= LAYERS.reflections ? 0 : Math.max(0, Math.min(0.9, L.floor ?? 0)),
            haze: this._layer >= LAYERS.reflections ? 0 : Math.max(0, Math.min(0.7, L.haze)),
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
            rim: this._layer === LAYERS.reflections ? 0 : Math.max(0, Math.min(1, L.rim ?? DEFAULT_LOOK.rim)),
            veil_r: veil[0], veil_g: veil[1], veil_b: veil[2], veil_a: veil[3],
            lens_share: this._layer === LAYERS.glass || this._layer === LAYERS.reflections ? 1 : 0,
            text_shade: this._layer === LAYERS.reflections ? Math.max(0, Math.min(0.6, L.textShade ?? 0)) : 0,
            mode: this._layer,
            cheap: this._cheap ? 1 : 0,
            lite: quality >= 1 ? 1 : 0,
        });
        this._applyFrost();
        this._applyMotion();
        this._applyShape();
    }

    // Weather frost: the glass itself (not the content's light over a menu, not the rim over
    // a window, not a full-screen sheet like the lock screen's).
    _frosts() {
        return (this._layer === LAYERS.full || this._layer === LAYERS.glass) && !(this._look.solid > 0.5);
    }

    _applyFrost() {
        const on = this._frosts();
        this._glass.setFloats({frost: on ? frostNow.frost : 0, flakes: on ? frostNow.flakes : 0});
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
        const lq = Math.max(0.25, Math.min(2.5, L.liquid ?? 1));
        const deep = Math.min(lq, 1) + 0.35 * Math.max(lq - 1, 0);   // as in the shader
        this._glass.setFloats({
            ptr_x: m.sx - ox, ptr_y: m.sy - oy, ptr_k: Math.max(0, Math.min(1, m.k)),
            press: Math.max(0, Math.min(1, m.press)),
            liquid: lq,
            pull_x: m.pullX ?? 0, pull_y: m.pullY ?? 0,
            refr_h: Math.max(0, L.refraction) * Math.max(0, m.open),
            // Pressed, the slab gives: a deeper bend and a fuller dome you can see.
            refr_amt: Math.max(0, L.bend) * (1 + 0.3 * deep * m.press),
            depth: Math.max(0, Math.min(1, L.depth + 0.25 * deep * m.press)),
        });
        // setFloats queued a repaint of the lens over all of the pane, so it shows the
        // new shape in one frame. Never queue_redraw() the pane here: that marks it
        // dirty, and the backdrop is copied and blurred again for every pointer step
        // (1.5.3 did, so a pointer near the panel kept re-rendering its glass).
    }

    _applyShape() {
        const [tl, tr, br, bl] = this._radii;
        // The glass inside a bigger pane (see place): its own size, padding included,
        // and where the pane starts relative to it.
        const p = this._pad, i = this._inner;
        const [ww, wh] = i ? [Math.max(1, i[2] + 2 * p), Math.max(1, i[3] + 2 * p)] : this._whole;
        const [ax, ay] = i ? [-i[0], -i[1]] : this._at;
        this._glass.setFloats({
            width: this._size[0], height: this._size[1], pad: this._pad,
            shape_w: ww, shape_h: wh, shape_x: ax, shape_y: ay,
            r_tl: tl, r_tr: tr, r_br: br, r_bl: bl,
        });
    }
});
