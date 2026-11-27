// A fake GNOME window manager and Clutter timelines: enough to run the real animations.js.
// It copies GNOME's windowManager.js *Done functions and Mutter's kill-window-effects.
// A test calls makeFake() first, then imports animations.js (the stubs read globalThis.fake).
export class Emitter {
    constructor() {
        this._h = new Map();
        this._n = 1;
        this._blocked = new Set();
    }
    connect(s, fn) {
        const id = this._n++;
        this._h.set(id, [s, fn]);
        return id;
    }
    disconnect(id) {
        if (!this._h.delete(id))
            throw new Error(`no handler ${id}`);
    }
    emit(s, ...a) {
        let r;
        for (const [id, [n, fn]] of [...this._h]) {
            if (n === s && !this._blocked.has(id) && this._h.has(id))
                r = fn(this, ...a);
        }
        return r;
    }
    count() {
        return this._h.size;
    }
}

export class Transition extends Emitter {
    constructor(p = {}) {
        super();
        Object.assign(this, p);
    }
    set_from(v) { this.from = v; }
    set_to(v) { this.to = v; }
    pause() {}
}

export const timelines = new Set();
export class Timeline extends Emitter {
    constructor({actor, duration}) {
        super();
        this.actor = actor;
        this.duration = duration;
        this.elapsed = 0;
        this.playing = false;
    }
    start() { this.playing = true; timelines.add(this); }
    pause() { this.playing = false; }
    stop() {
        if (!timelines.has(this))
            return;
        timelines.delete(this);
        this.playing = false;
        this.emit('stopped', false);
    }
    get_elapsed_time() { return this.elapsed; }
    // One frame: no frames while the actor is hidden or at opacity 0 (as on GNOME).
    frame(ms) {
        if (!this.playing)
            return;
        const a = this.actor;
        if (a && (!a.visible || a.opacity === 0))
            return;
        this.elapsed = Math.min(this.duration, this.elapsed + ms);
        this.emit('new-frame');
        if (this.elapsed >= this.duration && timelines.has(this)) {
            timelines.delete(this);
            this.playing = false;
            this.emit('stopped', true);
        }
    }
}

export class Actor extends Emitter {
    constructor(p = {}) {
        super();
        Object.assign(this, {x: 0, y: 0, width: 100, height: 100, scale_x: 1, scale_y: 1, translation_x: 0,
            translation_y: 0, opacity: 255, z_position: 0, visible: true, _pivot: [0, 0], _tr: new Map(),
            _children: [], _parent: null}, p);
    }
    set_pivot_point(x, y) { this._pivot = [x, y]; }
    get_pivot_point() { return [...this._pivot]; }
    set_scale(x, y) { this.scale_x = x; this.scale_y = y; }
    set_translation(x, y) { this.translation_x = x; this.translation_y = y; }
    show() { this.visible = true; }
    hide() { this.visible = false; }
    get_stage() { return {}; }
    get_transformed_position() { return [this.x, this.y]; }
    get_texture() { return {}; }
    add_transition(name, t) {
        if (this._tr.has(name))
            throw new Error(`transition ${name} taken`);
        this._tr.set(name, t);
    }
    get_transition(n) { return this._tr.get(n) ?? null; }
    remove_transition(name) {
        const t = this._tr.get(name);
        if (!t)
            return;
        this._tr.delete(name);
        t.emit('stopped', false);
    }
    remove_all_transitions() {
        for (const n of [...this._tr.keys()])
            this.remove_transition(n);
    }
    add_child(c) { c._parent = this; this._children.push(c); }
    set_child_above_sibling() {}
    get_parent() { return this._parent; }
    add_effect_with_name() {}
    remove_effect() {}
    destroy() { this.destroyed = true; this.emit('destroy'); }
}

export function makeFake({killUnminimize = false} = {}) {
    const shellwm = new Emitter();
    const log = [];
    shellwm.completed_map = a => log.push(['completed_map', a]);
    shellwm.completed_minimize = a => { log.push(['completed_minimize', a]); a.visible = false; };
    shellwm.completed_unminimize = a => log.push(['completed_unminimize', a]);
    shellwm.completed_destroy = a => log.push(['completed_destroy', a]);
    const wm = {
        _mapping: new Set(), _minimizing: new Set(), _unminimizing: new Set(), _destroying: new Set(),
        _skippedActors: new Set(),
        _shouldAnimate: () => true,
        _getAnimationWindowType: () => 0,
        _mapWindow(sw, a) {
            if (this._skippedActors.delete(a)) return sw.completed_map(a);
            log.push(['gnome-map', a]); sw.completed_map(a);
        },
        _mapWindowDone(sw, a) { if (this._mapping.delete(a)) { a.remove_all_transitions(); sw.completed_map(a); } },
        _minimizeWindow(sw, a) {
            if (this._skippedActors.delete(a)) return sw.completed_minimize(a);
            log.push(['gnome-minimize', a]); sw.completed_minimize(a);
        },
        _minimizeWindowDone(sw, a) {
            if (this._minimizing.delete(a)) {
                a.remove_all_transitions(); a.set_scale(1, 1); a.opacity = 255; a.set_pivot_point(0, 0);
                sw.completed_minimize(a);
            }
        },
        _unminimizeWindow(sw, a) {
            if (this._skippedActors.delete(a)) return sw.completed_unminimize(a);
            log.push(['gnome-unminimize', a]); sw.completed_unminimize(a);
        },
        _unminimizeWindowDone(sw, a) {
            if (this._unminimizing.delete(a)) {
                a.remove_all_transitions(); a.set_scale(1, 1); a.opacity = 255; a.set_pivot_point(0, 0);
                sw.completed_unminimize(a);
            }
        },
        _destroyWindow(sw, a) {
            if (this._skippedActors.delete(a)) return sw.completed_destroy(a);
            log.push(['gnome-destroy', a]); sw.completed_destroy(a);
        },
        _destroyWindowDone(sw, a) { if (this._destroying.delete(a)) sw.completed_destroy(a); },
    };
    // GNOME's own handlers, connected first (they get blocked).
    const gnomeIds = {};
    for (const s of ['map', 'minimize', 'unminimize', 'destroy'])
        gnomeIds[s] = shellwm.connect(s, () => log.push(['GNOME-HANDLER-RAN', s]));
    // GNOME's kill-window-effects handler (never blocked).
    shellwm.connect('kill-window-effects', (sw, a) => {
        wm._minimizeWindowDone(sw, a);
        wm._mapWindowDone(sw, a);
        wm._destroyWindowDone(sw, a);
        if (fake.killUnminimize)
            wm._unminimizeWindowDone(sw, a);
    });
    const timeouts = {
        _m: new Map(), _n: 1,
        add(ms, fn) { const id = this._n++; this._m.set(id, {ms, fn}); return id; },
        remove(id) { this._m.delete(id); },
        fire(minMs = 0) {
            for (const [id, {ms, fn}] of [...this._m]) {
                if (ms >= minMs && this._m.has(id)) { this._m.delete(id); fn(); }
            }
        },
    };
    const stSettings = Object.assign(new Emitter(), {enable_animations: true});
    let clock = 0;
    const fake = {
        Actor, Clone: Actor, Widget: Actor, Timeline, PropertyTransition: Transition, wm, timeouts,
        now: () => clock, stSettings,
        appSystem: new Emitter(), windowTracker: Object.assign(new Emitter(), {get_window_app: () => null}),
        extensionManager: new Emitter(),
        layoutManager: {monitors: [{x: 0, y: 0, width: 2048, height: 1152}],
            primaryMonitor: {x: 0, y: 0, width: 2048, height: 1152},
            getWorkAreaForMonitor: () => ({x: 0, y: 0, width: 2048, height: 1100}), uiGroup: new Actor()},
        gobject: {
            find: (obj, m) => gnomeIds[m.signalId],
            block: (obj, id) => obj._blocked.add(id),
            unblock: (obj, id) => obj._blocked.delete(id),
        },
        filters: {add: () => 1, remove: () => {}},
        // Does Mutter's kill-window-effects end a restore too? (A test may flip it.)
        killUnminimize,
    };
    globalThis.fake = fake;
    globalThis.log = msg => fake.logs?.push(msg);
    globalThis.logError = (e, m) => { (fake.errors ??= []).push([m, e]); };
    globalThis.global = {
        window_manager: shellwm, stage: Object.assign(new Emitter(), {get_size: () => [2048, 1152], is_grabbed: false}),
        get_window_actors: () => [], compositor: {get_laters: () => ({add: () => 1, remove() {}})},
        window_group: null,
    };
    return {fake, shellwm, wm, log, advance: ms => { clock += ms * 1000; for (const t of [...timelines]) t.frame(ms); }};
}

export function windowActor(fake) {
    const win = {
        get_monitor: () => 0, is_monitor_sized: () => false, get_maximized: () => false,
        get_frame_rect: () => ({x: 400, y: 200, width: 1000, height: 700}),
        get_icon_geometry: () => [true, {x: 1000, y: 1110, width: 40, height: 40}],
        disconnectObject() {},
    };
    return new Actor({x: 400, y: 200, width: 1000, height: 700, meta_window: win});
}
