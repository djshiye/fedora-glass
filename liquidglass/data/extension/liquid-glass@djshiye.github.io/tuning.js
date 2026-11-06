// When the glass should get lighter, and how a speed check is scored. Plain
// maths with no GNOME imports, so the unit tests run it under Node.
//
// Levels: 0 full, 1 lighter, 2 lightest.

export const LEVELS = ['full', 'lighter', 'lightest'];
export const QUALITIES = ['auto', ...LEVELS];

// Auto looks back over the frames of the last WINDOW_US in which glass was drawn.
export const WINDOW_US = 5e6;
export const MIN_FRAMES = 20;      // fewer than this says nothing
export const LATE_SHARE = 0.4;     // this share of them late: step down
export const SETTLE_US = 5e6;      // after a change, give the new level this long
export const RETRY_US = 180e6;     // a while after stepping down, try one level up
export const RELAPSE_US = 60e6;
export const FRAME_60HZ_US = 1e6 / 60;    // slow again this soon after a try: stay down

/** The setting as the extension uses it: unknown values mean 'auto'. */
export function cleanQuality(raw) {
    const q = raw && typeof raw === 'object' ? raw.quality : raw;
    return QUALITIES.includes(q) ? q : 'auto';
}

/**
 * Whether a frame came late. gapUs: time since this screen's last frame;
 * paintUs: how long the frame took to draw; intervalUs: one refresh.
 * A frame that follows a pause (the screen had nothing to show) only counts
 * if drawing it took longer than a refresh, so typing or a blinking cursor
 * never reads as slow. Returns null for a frame that tells nothing.
 */
export function frameLate(gapUs, paintUs, intervalUs) {
    if (!(intervalUs > 0))
        return null;
    // On a fast screen (120, 144 Hz) glass that keeps 60 frames a second is not slow:
    // judge against a 60 Hz frame at most. 1.5.0 held a 144 Hz screen to 6.9 ms, so a
    // busy moment on a gaming PC stepped the glass down and back up every few minutes.
    intervalUs = Math.max(intervalUs, FRAME_60HZ_US);
    if (paintUs > intervalUs)
        return true;
    if (!(gapUs > 0) || gapUs > 4 * intervalUs)
        return null;
    // A long gap after a quick frame is the content's own pace, not slow glass: an app
    // that redraws 25-30 times a second (streaming text, a spreadsheet, a video), or
    // the glass itself catching up with it, gives a frame every 33-50 ms. 1.5.6 counted
    // all of those as late and stepped a fast PC down to the lightest glass.
    if (paintUs < intervalUs / 2)
        return false;
    return gapUs > 1.5 * intervalUs;
}

/**
 * How far down auto may step, from the last speed check. The lightest
 * level changes the look (the glass shows only the wallpaper behind it), so when
 * the check found full glass smooth on this PC, a busy moment may make the glass
 * lighter but never that. 1.5.6 took a PC whose check ran full glass at 120 fps
 * down to the lightest glass.
 */
export function deepestFor(check) {
    if (!check || check.state !== 'done')
        return LEVELS.length - 1;
    const smooth = (check.phases ?? []).find(p => p?.verdict === 'smooth');
    const best = smooth ? LEVELS.indexOf(smooth.level) : -1;
    return best < 0 ? LEVELS.length - 1 : Math.min(LEVELS.length - 1, best + 1);
}

export class Tuner {
    constructor() {
        this.deepest = LEVELS.length - 1;   // see deepestFor
        this.level = 0;
        this.floor = 0;            // the lowest level auto may go back up to
        this.reason = 'setting';   // 'setting', 'slow' or 'retry'
        this._frames = [];
        this._late = 0;
        this._changedAt = -Infinity;
        this._retryAt = null;
        this._relapseUntil = -Infinity;
    }

    reset() {
        this.level = 0;
        this.floor = 0;
        this.reason = 'setting';
        this._frames = [];
        this._late = 0;
        this._changedAt = -Infinity;
        this._retryAt = null;
        this._relapseUntil = -Infinity;
    }

    /** Never deeper than this level (deepestFor); a level already deeper comes back up to it. */
    limit(deepest, t) {
        this.deepest = deepest;
        if (this.level <= deepest)
            return null;
        this.level = deepest;
        this.floor = Math.min(this.floor, deepest);
        this.reason = 'setting';
        this._changedAt = t;
        this._frames = [];
        this._late = 0;
        this._retryAt = this.level > this.floor ? t + RETRY_US : null;
        return this.level;
    }

    /** When the next try at a higher level is due (µs), or null. */
    get retryAt() {
        return this._retryAt;
    }

    /** A frame in which glass was drawn. Returns the new level when it changes, else null. */
    frame(t, late) {
        if (late === null || late === undefined)
            return null;
        const f = this._frames;
        f.push([t, late]);
        // A running count of the late ones: this runs for every frame (up to 288 a
        // second on two 144 Hz screens), so it never walks the whole window.
        this._late = (this._late ?? 0) + (late ? 1 : 0);
        while (f.length && f[0][0] < t - WINDOW_US)
            this._late -= f.shift()[1] ? 1 : 0;
        if (this.level >= this.deepest || t - this._changedAt < SETTLE_US || f.length < MIN_FRAMES)
            return null;
        const share = this._late / f.length;
        if (share < LATE_SHARE)
            return null;
        // Slow again soon after trying a higher level: this level is as high as it goes.
        if (t < this._relapseUntil)
            this.floor = this.level + 1;
        this.level++;
        this.reason = 'slow';
        this._changedAt = t;
        this._frames = [];
        this._late = 0;
        this._relapseUntil = -Infinity;
        this._retryAt = this.level > this.floor ? t + RETRY_US : null;
        return this.level;
    }

    /** Called when the retry time comes. Returns the new level, or null. */
    tick(t) {
        if (this._retryAt === null || t < this._retryAt || this.level <= this.floor)
            return null;
        this.level--;
        this.reason = 'retry';
        this._changedAt = t;
        this._frames = [];
        this._late = 0;
        this._relapseUntil = t + RELAPSE_US;
        this._retryAt = this.level > this.floor ? t + RETRY_US : null;
        return this.level;
    }
}

/**
 * Scores one phase of a speed check. gaps: µs between frames on the busiest
 * screen while every frame was asked for; refreshHz: that screen's rate.
 */
export function scorePhase(level, gaps, refreshHz) {
    // As in frameLate: 60 frames a second is smooth, however fast the screen.
    refreshHz = Math.min(refreshHz, 60);
    const interval = 1e6 / refreshHz;
    const total = gaps.reduce((a, b) => a + b, 0);
    const fps = total > 0 ? gaps.length / (total / 1e6) : 0;
    const late = gaps.length ? gaps.filter(g => g > 1.5 * interval).length / gaps.length : 1;
    let verdict = 'slow';
    if (fps >= 0.9 * refreshHz && late <= 0.05)
        verdict = 'smooth';
    else if (fps >= Math.min(30, 0.5 * refreshHz) && late <= 0.35)
        verdict = 'ok';
    return {level: LEVELS[level], fps: Math.round(fps * 10) / 10, late: Math.round(late * 1000) / 1000, verdict};
}

/** The best level that ran smoothly; else the best that ran fair; else the fastest. */
export function pickLevel(phases) {
    for (const want of ['smooth', 'ok']) {
        const p = phases.find(x => x.verdict === want);
        if (p)
            return p.level;
    }
    let best = phases[0];
    for (const p of phases)
        best = p.fps > best.fps ? p : best;
    return best?.level ?? 'full';
}

/**
 * The config the glass draws with at a level: at lightest, the panel, menus and
 * windows show only the wallpaper behind them, so windows changing behind never
 * re-render them. Everything else stays as the user set it.
 */
export function effectiveConfig(cfg, level) {
    if (level < 2 || !cfg)
        return cfg;
    const wall = s => (s && typeof s === 'object' && 'behind' in s ? {...s, behind: 'wallpaper'} : s);
    const out = {...cfg, panel: wall(cfg.panel), menus: wall(cfg.menus), windows: wall(cfg.windows)};
    if (cfg.parts && typeof cfg.parts === 'object')
        out.parts = Object.fromEntries(Object.entries(cfg.parts).map(([k, v]) => [k, wall(v)]));
    return out;
}
