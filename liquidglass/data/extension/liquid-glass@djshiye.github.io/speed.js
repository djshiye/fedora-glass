// How smoothly the glass draws on this PC, and lighter glass when it can't keep up.
//
// The glass quality setting is auto, full, lighter or lightest. On auto, the
// frames in which glass was drawn are watched: when too many come late, the glass
// steps down a level, and a few minutes later tries one level up again (tuning.js).
//
// The Fedora Glass app asks for a speed check by writing
// ~/.config/liquid-glass/speed-check.json ({"id": "<16 hex>"}). The check redraws
// all the glass on screen every frame for a few seconds at each level and scores
// the frame rate. What the glass draws now, and the check's result, go to
// ~/.cache/liquid-glass/speed.json (only this user can read it), for the app.
//
// Nothing here runs while the screen is locked: the extension destroys it then.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {setQuality, glassRenders, redrawAllPanes, shownPanes} from './glass.js';
import {LEVELS, Tuner, cleanQuality, deepestFor, frameLate, scorePhase, pickLevel} from './tuning.js';

const REQUEST = 'speed-check.json';
const REQUEST_MAX = 1024;
const ID = /^[0-9a-f]{16}$/;
// The check: a short warm-up, then each level in turn. The first frames of each
// level are left out, while the new level settles.
const WARMUP_MS = 800;
const PHASE_MS = [6000, 5000, 5000];
const SKIP_US = 500e3;
const CHECK_LIMIT_MS = 30000;

function now() {
    return GLib.get_monotonic_time();
}

export class Speed {
    /** onLevel(level) is called when the glass should redraw at another level. */
    constructor(cfg, onLevel) {
        this._onLevel = onLevel;
        this._tuner = new Tuner();
        this._quality = cleanQuality(cfg?.speed);
        this._level = this._fixedLevel();
        this._since = Math.floor(Date.now() / 1000);
        this._views = new Map();   // view -> {start, last}
        this._renders = glassRenders();
        this._retry = 0;
        this._check = null;        // the running check
        setQuality(this._level);

        this._cacheDir = GLib.build_filenamev([GLib.get_user_cache_dir(), 'liquid-glass']);
        // The last check's result, for the status file. One from before a restart stays.
        this._result = this._lastResult();
        // A PC the check found smooth never drops to the lightest glass (tuning.js).
        this._tuner.deepest = deepestFor(this._result);
        this._configDir = Gio.File.new_for_path(GLib.build_filenamev([GLib.get_user_config_dir(), 'liquid-glass']));
        // A request left over from before (the app asked, then the PC restarted) does not run.
        this._seenId = this._readRequest();

        this._before = global.stage.connect('before-paint', (_s, view) => this._beforePaint(view));
        this._after = global.stage.connect('after-paint', (_s, view) => this._afterPaint(view));
        // Mutter makes new views when screens change (plugged in, unplugged, a new
        // refresh rate): forget the old ones, and read the new refresh rates.
        this._monitorsId = Main.layoutManager.connect('monitors-changed', () => this._views.clear());
        try {
            this._monitor = this._configDir.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, null);
            this._monitorId = this._monitor.connect('changed', (_m, file, other) => {
                if (file?.get_basename() === REQUEST || other?.get_basename() === REQUEST)
                    this._onRequest();
            });
        } catch (e) {
            console.warn(`Fedora Glass: no speed check: ${e}`);
            this._monitor = null;
        }
        this._writeStatus();
    }

    /** The level the glass draws at right now (0 full .. 2 lightest). */
    get level() {
        return this._level;
    }

    _fixedLevel() {
        return this._quality === 'auto' ? this._tuner.level : LEVELS.indexOf(this._quality);
    }

    update(cfg) {
        const q = cleanQuality(cfg?.speed);
        if (q === this._quality)
            return;
        this._quality = q;
        this._tuner.reset();
        this._stopRetry();
        if (!this._check)
            this._setLevel(this._fixedLevel());
        this._writeStatus();
    }

    _setLevel(level) {
        if (level === this._level)
            return;
        this._level = level;
        this._since = Math.floor(Date.now() / 1000);
        setQuality(level);
        try {
            this._onLevel?.(level);
        } catch (e) {
            logError(e, 'Fedora Glass: changing the glass level');
        }
    }

    // ---- frames ------------------------------------------------------------------------
    _key(view) {
        return view ?? 'stage';
    }

    _beforePaint(view) {
        const k = this._key(view);
        let v = this._views.get(k);
        if (!v) {
            v = {start: 0, last: 0, interval: 0};
            this._views.set(k, v);
        }
        v.start = now();
    }

    _afterPaint(view) {
        const t = now();
        const v = this._views.get(this._key(view));
        if (!v || !v.start)
            return;
        if (!v.interval) {
            let hz = 0;
            try {
                hz = view?.get_refresh_rate?.() ?? 0;
            } catch {}
            v.interval = 1e6 / (hz > 1 ? hz : 60);
        }
        const gap = v.last ? t - v.last : 0;
        const paint = t - v.start;
        v.last = t;
        v.start = 0;
        const renders = glassRenders();
        const drew = renders !== this._renders;
        this._renders = renders;

        if (this._check) {
            this._checkFrame(v, gap, t);
            return;
        }
        if (this._quality !== 'auto' || !drew)
            return;
        const level = this._tuner.frame(t, frameLate(gap, paint, v.interval));
        if (level === null)
            return;
        this._setLevel(level);
        this._scheduleRetry();
        this._writeStatus();
    }

    _scheduleRetry() {
        this._stopRetry();
        const at = this._tuner.retryAt;
        if (at === null)
            return;
        const s = Math.max(1, Math.ceil((at - now()) / 1e6));
        this._retry = GLib.timeout_add_seconds(GLib.PRIORITY_LOW, s, () => {
            this._retry = 0;
            if (this._check) {
                this._scheduleRetry();   // after the check
                return GLib.SOURCE_REMOVE;
            }
            const level = this._tuner.tick(now());
            if (level !== null) {
                this._setLevel(level);
                this._writeStatus();
            }
            this._scheduleRetry();
            return GLib.SOURCE_REMOVE;
        });
    }

    _stopRetry() {
        if (this._retry)
            GLib.source_remove(this._retry);
        this._retry = 0;
    }

    // ---- the speed check -----------------------------------------------------------------
    _readRequest() {
        try {
            const f = this._configDir.get_child(REQUEST);
            const info = f.query_info('standard::size,standard::type', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, null);
            if (info.get_file_type() !== Gio.FileType.REGULAR || info.get_size() > REQUEST_MAX)
                return null;
            const [, bytes] = f.load_contents(null);
            const id = JSON.parse(new TextDecoder().decode(bytes))?.id;
            return typeof id === 'string' && ID.test(id) ? id : null;
        } catch {
            return null;
        }
    }

    _onRequest() {
        const id = this._readRequest();
        if (!id || id === this._seenId || this._check)
            return;
        this._seenId = id;
        this._startCheck(id);
    }

    _startCheck(id) {
        if (shownPanes() === 0) {
            this._result = {id, state: 'failed', error: 'noglass', refresh: 0, phases: [], pick: ''};
            this._writeStatus();
            return;
        }
        this._stopRetry();
        this._check = {id, phase: -1, phaseStart: now(), gaps: new Map(), phases: [], back: this._level, timer: 0, limit: 0};
        this._result = {id, state: 'running', error: '', refresh: 0, phases: [], pick: ''};
        this._setLevel(0);
        this._writeStatus('check');
        this._check.timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, WARMUP_MS, () => this._nextPhase());
        // Never longer than this, whatever happens to the frames.
        this._check.limit = GLib.timeout_add(GLib.PRIORITY_DEFAULT, CHECK_LIMIT_MS, () => {
            this._check.limit = 0;
            this._endCheck('failed', 'busy');
            return GLib.SOURCE_REMOVE;
        });
        redrawAllPanes();
    }

    _checkFrame(v, gap, t) {
        const c = this._check;
        if (c.phase >= 0 && gap > 0 && t - c.phaseStart > SKIP_US) {
            let g = c.gaps.get(v);
            if (!g)
                c.gaps.set(v, g = []);
            g.push(gap);
        }
        // Ask for the next frame at once: all the glass, drawn again in full.
        redrawAllPanes();
    }

    _scoreCurrent() {
        const c = this._check;
        // The busiest screen: the one that drew most frames.
        let best = null, bestN = -1;
        for (const [v, g] of c.gaps) {
            if (g.length > bestN) {
                best = [v, g];
                bestN = g.length;
            }
        }
        const interval = best?.[0].interval || 1e6 / 60;
        const hz = 1e6 / interval;
        c.refresh = Math.max(c.refresh ?? 0, hz);
        c.phases.push(scorePhase(c.phase, best?.[1] ?? [], hz));
    }

    _nextPhase() {
        const c = this._check;
        if (!c)
            return GLib.SOURCE_REMOVE;
        c.timer = 0;
        if (c.phase >= 0)
            this._scoreCurrent();
        c.phase++;
        if (c.phase >= PHASE_MS.length) {
            this._endCheck('done', '');
            return GLib.SOURCE_REMOVE;
        }
        c.gaps = new Map();
        c.phaseStart = now();
        this._setLevel(c.phase);
        redrawAllPanes();
        c.timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, PHASE_MS[c.phase], () => this._nextPhase());
        return GLib.SOURCE_REMOVE;
    }

    _endCheck(state, error) {
        const c = this._check;
        if (!c)
            return;
        if (c.timer)
            GLib.source_remove(c.timer);
        if (c.limit)
            GLib.source_remove(c.limit);
        this._check = null;
        const phases = c.phases;
        this._result = {id: c.id, state, error, refresh: Math.round((c.refresh ?? 0) * 10) / 10, phases,
            pick: state === 'done' ? pickLevel(phases) : ''};
        // Back to what the setting (or auto) had; auto no deeper than this check allows.
        if (state === 'done')
            this._tuner.limit(deepestFor(this._result), now());
        this._setLevel(this._quality === 'auto' ? Math.min(c.back, this._tuner.level) : this._fixedLevel());
        this._scheduleRetry();
        this._writeStatus();
    }

    _lastResult() {
        try {
            const f = Gio.File.new_for_path(GLib.build_filenamev([this._cacheDir, 'speed.json']));
            const info = f.query_info('standard::size,standard::type', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, null);
            if (info.get_file_type() !== Gio.FileType.REGULAR || info.get_size() > 16 * 1024)
                return null;
            const [, bytes] = f.load_contents(null);
            const c = JSON.parse(new TextDecoder().decode(bytes))?.check;
            if (!c || c.state !== 'done' || typeof c.id !== 'string' || !ID.test(c.id) || !Array.isArray(c.phases))
                return null;
            const phases = c.phases.slice(0, LEVELS.length).filter(x => x && LEVELS.includes(x.level)).map(x => ({
                level: x.level, fps: Number(x.fps) || 0, late: Number(x.late) || 0,
                verdict: ['smooth', 'ok', 'slow'].includes(x.verdict) ? x.verdict : 'slow'}));
            return {id: c.id, state: 'done', error: '', refresh: Number(c.refresh) || 0, phases,
                pick: LEVELS.includes(c.pick) ? c.pick : ''};
        } catch {
            return null;
        }
    }

    // ---- status for the app -------------------------------------------------------------------
    _writeStatus(reason) {
        const status = {
            version: 1,
            quality: this._quality,
            level: LEVELS[this._level],
            reason: reason ?? (this._quality === 'auto' ? this._tuner.reason : 'setting'),
            since: this._since,
            check: this._result,
        };
        try {
            GLib.mkdir_with_parents(this._cacheDir, 0o700);
            const path = GLib.build_filenamev([this._cacheDir, 'speed.json']);
            GLib.file_set_contents_full(path, new TextEncoder().encode(JSON.stringify(status)),
                GLib.FileSetContentsFlags.CONSISTENT, 0o600);
        } catch (e) {
            console.warn(`Fedora Glass: could not write the speed status: ${e}`);
        }
    }

    destroy() {
        if (this._check) {
            const c = this._check;
            if (c.timer)
                GLib.source_remove(c.timer);
            if (c.limit)
                GLib.source_remove(c.limit);
            this._check = null;
            this._result = {id: c.id, state: 'failed', error: 'locked', refresh: 0, phases: [], pick: ''};
            this._writeStatus();
        }
        this._stopRetry();
        if (this._before)
            global.stage.disconnect(this._before);
        if (this._after)
            global.stage.disconnect(this._after);
        this._before = this._after = 0;
        if (this._monitorsId)
            Main.layoutManager.disconnect(this._monitorsId);
        this._monitorsId = 0;
        if (this._monitor) {
            this._monitor.disconnect(this._monitorId);
            this._monitor.cancel();
            this._monitor = null;
        }
        this._views.clear();
        setQuality(0);
        this._onLevel = null;
    }
}
