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
// So does how smoothly the last window drag drew (see _dragEnd), the real thing on
// this PC rather than the check's redraw-everything test.
//
// On battery or in Power Saver (power.js), and with the app's "use lighter glass" switch
// on, the glass draws at most at the lighter level: never heavier than the setting or
// auto picked, and back to that once the PC is on mains again. The status then says
// why ("battery"), so the app can tell the user.
//
// Nothing here runs while the screen is locked: the extension destroys it then.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {setQuality, glassRenders, redrawAllPanes, shownPanes} from './glass.js';
import {GrabMove} from './grabmove.js';
import {PowerWatch} from './power.js';
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
// A drag shorter than this many frames (a click on a title bar) is not worth keeping.
const DRAG_MIN_FRAMES = 10;
// Frame times kept per screen during a drag (a minute at 120 Hz); longer drags keep counting.
const DRAG_KEEP = 7200;
// A longer wait between two frames of a drag is the pointer held still (nothing to draw),
// not a frame that came late.
const DRAG_IDLE_US = 250e3;
// The level the glass draws at most on battery or in Power Saver.
const BATTERY_LEVEL = LEVELS.indexOf('lighter');

function now() {
    return GLib.get_monotonic_time();
}

export class Speed {
    /** onLevel(level) is called when the glass should redraw at another level. */
    constructor(cfg, onLevel) {
        this._onLevel = onLevel;
        this._tuner = new Tuner();
        this._quality = cleanQuality(cfg?.speed);
        this._lighterOnBattery = cfg?.speed?.lighterOnBattery !== false;
        this._power = {battery: false, saver: false};
        this._powerWatch = null;
        this._level = this._fixedLevel();
        this._since = Math.floor(Date.now() / 1000);
        this._views = new Map();   // view -> {start, last}
        this._renders = glassRenders();
        this._retry = 0;
        this._check = null;        // the running check
        this._drag = null;         // the window drag going on: {start, windows, views}
        this._writeId = 0;         // the status write waiting for a quiet moment
        this._writeReason = undefined;
        setQuality(this._level);

        this._cacheDir = GLib.build_filenamev([GLib.get_user_cache_dir(), 'liquid-glass']);
        // The last finished check, kept apart from the last check (which may have
        // stopped short: locked, busy, no glass) so that an aborted one never loses it.
        // One from before a restart stays.
        this._done = this._lastResult();
        this._result = this._done;
        this._lastDrag = this._lastDragOf(this._lastStatus);
        this._lastStatus = null;
        // A PC the check found smooth never drops to the lightest glass (tuning.js).
        this._tuner.deepest = deepestFor(this._done);
        this._configDir = Gio.File.new_for_path(GLib.build_filenamev([GLib.get_user_config_dir(), 'liquid-glass']));
        // A request left over from before (the app asked, then the PC restarted) does not run.
        this._seenId = this._readRequest();

        this._before = global.stage.connect('before-paint', (_s, view) => this._beforePaint(view));
        this._after = global.stage.connect('after-paint', (_s, view) => this._afterPaint(view));
        // Mutter makes new views when screens change (plugged in, unplugged, a new
        // refresh rate): forget the old ones, and read the new refresh rates.
        this._monitorsId = Main.layoutManager.connect('monitors-changed', () => this._views.clear());
        // A window dragged or resized with the pointer or the keyboard (see surfaces.js),
        // from its first real move: a window only held (a press on the taskbar) is no drag.
        this._grabMove = new GrabMove(global.display, on => on ? this._dragBegin() : this._dragEnd());
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
        this._watchPower();
        this._writeStatus();
    }

    /** The level the glass draws at right now (0 full .. 2 lightest). */
    get level() {
        return this._level;
    }

    _fixedLevel() {
        return this._quality === 'auto' ? this._tuner.level : LEVELS.indexOf(this._quality);
    }

    // ---- battery and Power Saver ---------------------------------------------------------
    /** The lightest the glass must be now for the power state: 0 (no limit) or BATTERY_LEVEL. */
    _powerLevel() {
        return this._lighterOnBattery && (this._power.battery || this._power.saver) ? BATTERY_LEVEL : 0;
    }

    /** What the glass draws at: the setting's (or auto's) level, lighter on battery. */
    _wanted() {
        return Math.max(this._fixedLevel(), this._powerLevel());
    }

    _watchPower() {
        if (this._lighterOnBattery && !this._powerWatch) {
            try {
                this._powerWatch = new PowerWatch(state => this._powerChanged(state));
            } catch (e) {
                console.warn(`Fedora Glass: no lighter glass on battery: ${e}`);
                this._powerWatch = null;
            }
        } else if (!this._lighterOnBattery && this._powerWatch) {
            this._powerWatch.destroy();
            this._powerWatch = null;
            this._power = {battery: false, saver: false};
        }
    }

    _powerChanged(state) {
        this._power = {battery: !!state?.battery, saver: !!state?.saver};
        if (!this._check)
            this._setLevel(this._wanted());
        this._writeStatus();
    }

    update(cfg) {
        const q = cleanQuality(cfg?.speed);
        const battery = cfg?.speed?.lighterOnBattery !== false;
        if (q === this._quality && battery === this._lighterOnBattery)
            return;
        if (q !== this._quality) {
            this._quality = q;
            this._tuner.reset();
            this._stopRetry();
        }
        this._lighterOnBattery = battery;
        this._watchPower();
        if (!this._check)
            this._setLevel(this._wanted());
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
        if (this._drag)
            this._dragFrame(v, gap);

        if (this._check) {
            this._checkFrame(v, gap, t);
            return;
        }
        // Auto judges only frames drawn at its own level: held at the lighter level on
        // battery, a full-glass auto would read lighter glass's frames as its own.
        if (this._quality !== 'auto' || !drew || this._tuner.level < this._powerLevel())
            return;
        const level = this._tuner.frame(t, frameLate(gap, paint, v.interval));
        if (level === null)
            return;
        this._setLevel(this._wanted());
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
                this._setLevel(this._wanted());
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

    // ---- window drags ---------------------------------------------------------------------
    _dragBegin() {
        let windows = 0;
        try {
            windows = global.get_window_actors().filter(a => a.visible && a.meta_window && !a.meta_window.minimized).length;
        } catch {}
        this._drag = {start: now(), windows, views: new Map(), check: !!this._check};
    }

    // What counts is the time from one frame to the next, as the eye sees it, not the
    // time the CPU took to ask for the frame: a drag held up by the GPU asks quickly and
    // still shows few frames. A screen's first frame of the drag is left out: its gap
    // reaches back to a frame from before the drag.
    _dragFrame(v, gap) {
        const d = this._drag;
        if (this._check)
            d.check = true;    // the check's frames redraw everything: not a real drag
        let e = d.views.get(v);
        if (!e)
            d.views.set(v, e = {n: 0, ms: []});
        e.n++;
        if (e.n > 1 && gap > 0 && gap <= DRAG_IDLE_US && e.ms.length < DRAG_KEEP)
            e.ms.push(gap / 1000);
    }

    /**
     * The drag ended: the time between its frames on the screen that drew most of them
     * (median and 95th percentile), once per drag, to the status file (read by the app):
     * {at, frames, median_ms, p95_ms, refresh, windows}.
     */
    _dragEnd() {
        const d = this._drag;
        this._drag = null;
        if (!d || d.check)
            return;
        let best = null;
        for (const [v, e] of d.views) {
            if (!best || e.n > best[1].n)
                best = [v, e];
        }
        if (!best || best[1].n < DRAG_MIN_FRAMES || !best[1].ms.length)
            return;
        const [v, e] = best;
        const ms = e.ms.sort((a, b) => a - b);
        const at = q => Math.round(ms[Math.min(ms.length - 1, Math.floor(ms.length * q))] * 10) / 10;
        this._lastDrag = {at: Math.floor(Date.now() / 1000), frames: e.n, median_ms: at(0.5), p95_ms: at(0.95),
            refresh: Math.round(1e7 / (v.interval || 1e6 / 60)) / 10, windows: d.windows};
        this._writeStatus();
    }

    _lastDragOf(status) {
        const d = status?.drag;
        if (!d || typeof d !== 'object')
            return null;
        const num = x => (Number.isFinite(x) && x >= 0 ? x : 0);
        return {at: Math.floor(num(d.at)), frames: Math.floor(num(d.frames)), median_ms: num(d.median_ms),
            p95_ms: num(d.p95_ms), refresh: num(d.refresh), windows: Math.floor(num(d.windows))};
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
        if (state === 'done') {
            this._done = this._result;
            this._tuner.limit(deepestFor(this._done), now());
        }
        this._setLevel(Math.max(this._powerLevel(),
            this._quality === 'auto' ? Math.min(c.back, this._tuner.level) : this._fixedLevel()));
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
            const status = JSON.parse(new TextDecoder().decode(bytes));
            this._lastStatus = status;
            // 'lastDone'; an older status file has only 'check', which an aborted check replaced.
            const c = status?.lastDone?.state === 'done' ? status.lastDone : status?.check;
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
    /**
     * Written when the Shell has a quiet moment, not right away: it is asked for just as
     * frames come late (the glass steps down, a drag ends), and writing takes a while on a
     * slow disk. Several asked for before then make one write.
     */
    _writeStatus(reason) {
        this._writeReason = reason;
        if (this._writeId)
            return;
        this._writeId = GLib.idle_add(GLib.PRIORITY_LOW, () => {
            this._writeId = 0;
            this._writeNow();
            return GLib.SOURCE_REMOVE;
        });
    }

    _writeNow() {
        const reason = this._writeReason;
        this._writeReason = undefined;
        // Lighter than the setting or auto would draw, because of the battery or Power Saver.
        const power = !this._check && this._level > this._fixedLevel() && this._powerLevel() > this._fixedLevel()
            ? (this._power.battery ? 'battery' : 'saver') : '';
        const status = {
            version: 1,
            quality: this._quality,
            level: LEVELS[this._level],
            reason: reason ?? (power ? 'battery' : this._quality === 'auto' ? this._tuner.reason : 'setting'),
            power,
            since: this._since,
            check: this._result,
            lastDone: this._done,
            drag: this._lastDrag,
        };
        try {
            GLib.mkdir_with_parents(this._cacheDir, 0o700);
            // A status the app reads again on the next change: no need to wait for the disk
            // (fsync) as safe mode's state does. Written beside it and moved over it, so the
            // app never reads half of it.
            const path = GLib.build_filenamev([this._cacheDir, 'speed.json']);
            const tmp = `${path}.new`;
            GLib.file_set_contents_full(tmp, new TextEncoder().encode(JSON.stringify(status)),
                GLib.FileSetContentsFlags.NONE, 0o600);
            Gio.File.new_for_path(tmp).move(Gio.File.new_for_path(path), Gio.FileCopyFlags.OVERWRITE, null, null);
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
        // Going away (the screen locks): what is waiting is written now.
        if (this._writeId) {
            GLib.source_remove(this._writeId);
            this._writeId = 0;
            this._writeNow();
        }
        this._drag = null;
        this._grabMove?.destroy();
        this._grabMove = null;
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
        this._powerWatch?.destroy();
        this._powerWatch = null;
        this._views.clear();
        setQuality(0);
        this._onLevel = null;
    }
}
