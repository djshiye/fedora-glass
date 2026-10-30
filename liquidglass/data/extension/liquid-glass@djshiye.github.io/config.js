// Reads ~/.config/liquid-glass/shell-glass.json, written by the Liquid Glass
// app, and reports changes. Anything missing or malformed falls back to the
// defaults, so a broken file never breaks the Shell.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import {DEFAULT_LOOK} from './glass.js';

const MAX_BYTES = 64 * 1024;
const PARTS = ['panel', 'arcmenu', 'quicksettings', 'calendar'];

export const DEFAULTS = Object.freeze({
    panel: {enabled: true, behind: 'windows', look: {}},
    menus: {enabled: true, behind: 'windows', look: {}},
    windows: {enabled: true, radius: 12, skip: [], look: {refraction: 0, bend: 0, highlight: 0, blur: 30}},
    overview: {enabled: true, blur: 40, brightness: 0.7},
    look: {...DEFAULT_LOOK},
});

function num(v, fallback, min, max) {
    return typeof v === 'number' && Number.isFinite(v) ? Math.min(max, Math.max(min, v)) : fallback;
}

function cleanLook(raw, base) {
    const out = {...base};
    if (!raw || typeof raw !== 'object')
        return out;
    const ranges = {
        blur: [0, 100], refraction: [0, 80], bend: [0, 80], depth: [0, 1], dispersion: [0, 1],
        saturation: [0, 3], brightness: [0, 2], highlight: [0, 1], lightAngle: [-360, 360],
        shadow: [0, 1], bleed: [0, 1], adapt: [0, 1],
    };
    // edgeLight is the newer name for highlight.
    if (typeof raw.highlight !== 'number' && typeof raw.edgeLight === 'number')
        raw = {...raw, highlight: raw.edgeLight};
    for (const [k, [lo, hi]] of Object.entries(ranges))
        out[k] = num(raw[k], base[k], lo, hi);
    if (Array.isArray(raw.tint) && raw.tint.length === 4)
        out.tint = raw.tint.map((v, i) => num(v, base.tint[i], 0, 1));
    return out;
}

function cleanSurface(raw, def) {
    const out = {...def};
    if (!raw || typeof raw !== 'object')
        return out;
    if (typeof raw.enabled === 'boolean')
        out.enabled = raw.enabled;
    if ('behind' in def && (raw.behind === 'windows' || raw.behind === 'wallpaper'))
        out.behind = raw.behind;
    if ('radius' in def)
        out.radius = num(raw.radius, def.radius, 0, 40);
    if ('blur' in def)
        out.blur = num(raw.blur, def.blur, 0, 100);
    if ('brightness' in def)
        out.brightness = num(raw.brightness, def.brightness, 0, 1);
    if ('skip' in def && Array.isArray(raw.skip))
        out.skip = raw.skip.filter(s => typeof s === 'string' && s.length < 200).slice(0, 200);
    if ('look' in def && raw.look && typeof raw.look === 'object')
        out.look = {...def.look, ...raw.look};
    return out;
}

export function parse(text) {
    let raw = {};
    try {
        raw = JSON.parse(text);
    } catch {
        raw = {};
    }
    if (!raw || typeof raw !== 'object')
        raw = {};
    const look = cleanLook(raw.look, DEFAULTS.look);
    const cfg = {look};
    for (const name of ['panel', 'menus', 'windows', 'overview']) {
        cfg[name] = cleanSurface(raw[name], DEFAULTS[name]);
        if (cfg[name].look)
            cfg[name].look = cleanLook(cfg[name].look, look);
    }
    // Each part of the Shell can have its own look; missing parts follow the panel or menus.
    cfg.parts = {};
    const parts = raw.parts && typeof raw.parts === 'object' ? raw.parts : {};
    for (const name of PARTS) {
        const base = name === 'panel' ? cfg.panel : cfg.menus;
        const part = parts[name];
        cfg.parts[name] = part && typeof part === 'object' && part.look && typeof part.look === 'object'
            ? {...base, look: cleanLook(part.look, base.look)} : base;
    }
    return cfg;
}

export class Config {
    constructor(onChange) {
        this._onChange = onChange;
        this._dir = Gio.File.new_for_path(GLib.build_filenamev([GLib.get_user_config_dir(), 'liquid-glass']));
        this._file = this._dir.get_child('shell-glass.json');
        this._timeout = 0;
        this.value = this._read();
        // Watch the folder: the app replaces the file atomically, which a file monitor can miss.
        try {
            this._monitor = this._dir.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, null);
            this._monitorId = this._monitor.connect('changed', (_m, file, other) => {
                if (file?.get_basename() === 'shell-glass.json' || other?.get_basename() === 'shell-glass.json')
                    this._queue();
            });
        } catch {
            this._monitor = null;
        }
    }

    _read() {
        try {
            const info = this._file.query_info('standard::size,standard::type', Gio.FileQueryInfoFlags.NONE, null);
            if (info.get_file_type() !== Gio.FileType.REGULAR || info.get_size() > MAX_BYTES)
                return parse('{}');
            const [, bytes] = this._file.load_contents(null);
            return parse(new TextDecoder().decode(bytes));
        } catch {
            return parse('{}');
        }
    }

    _queue() {
        if (this._timeout)
            return;
        this._timeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 60, () => {
            this._timeout = 0;
            this.value = this._read();
            this._onChange(this.value);
            return GLib.SOURCE_REMOVE;
        });
    }

    destroy() {
        if (this._timeout)
            GLib.source_remove(this._timeout);
        this._timeout = 0;
        if (this._monitor) {
            this._monitor.disconnect(this._monitorId);
            this._monitor.cancel();
            this._monitor = null;
        }
    }
}
