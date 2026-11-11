// Whether the PC runs on battery or in Power Saver, for lighter glass then (speed.js).
//
// UPower says OnBattery; power-profiles-daemon says the active profile, under its new
// name (org.freedesktop.UPower.PowerProfiles) and its old one (net.hadess.PowerProfiles),
// either of which a GNOME 50 or 51 PC may run. All three are watched through D-Bus
// proxies made without blocking the Shell, and followed by their change signals: no
// polling. A service that isn't there (a desktop PC without UPower or profiles) simply
// reads as "on mains, balanced", and one that starts later is picked up then.

import Gio from 'gi://Gio';

const SERVICES = [
    {key: 'battery', name: 'org.freedesktop.UPower', path: '/org/freedesktop/UPower',
        iface: 'org.freedesktop.UPower', prop: 'OnBattery', test: v => v === true},
    {key: 'saver', name: 'org.freedesktop.UPower.PowerProfiles', path: '/org/freedesktop/UPower/PowerProfiles',
        iface: 'org.freedesktop.UPower.PowerProfiles', prop: 'ActiveProfile', test: v => v === 'power-saver'},
    {key: 'saverOld', name: 'net.hadess.PowerProfiles', path: '/net/hadess/PowerProfiles',
        iface: 'net.hadess.PowerProfiles', prop: 'ActiveProfile', test: v => v === 'power-saver'},
];

function unpack(v) {
    try {
        return v?.unpack?.() ?? null;
    } catch {
        return null;
    }
}

export class PowerWatch {
    /** onChange({battery, saver}) is called when either changes; never before the first answer. */
    constructor(onChange) {
        this._onChange = onChange;
        this._cancel = new Gio.Cancellable();
        this._proxies = [];
        this._state = {battery: false, saver: false};
        for (const s of SERVICES) {
            try {
                // Never start a service from the Shell (DO_NOT_AUTO_START): one that isn't
                // running isn't wanted. The proxy still follows it if it starts later.
                Gio.DBusProxy.new_for_bus(Gio.BusType.SYSTEM, Gio.DBusProxyFlags.DO_NOT_AUTO_START, null,
                    s.name, s.path, s.iface, this._cancel, (_src, res) => this._made(s, res));
            } catch (e) {
                console.warn(`Fedora Glass: no ${s.prop} watch: ${e}`);
            }
        }
    }

    /** {battery, saver} as last read. */
    get state() {
        return {...this._state};
    }

    _made(s, res) {
        let proxy;
        try {
            proxy = Gio.DBusProxy.new_for_bus_finish(res);
        } catch (e) {
            // Cancelled (the screen locked first) or no system bus: nothing to follow.
            if (!this._cancel?.is_cancelled())
                console.warn(`Fedora Glass: no ${s.prop} watch: ${e}`);
            return;
        }
        if (!this._cancel || this._cancel.is_cancelled())
            return;
        const ids = [proxy.connect('g-properties-changed', () => this._read()),
            // The service started or went away: its cached values come or go with it.
            proxy.connect('notify::g-name-owner', () => this._read())];
        this._proxies.push({s, proxy, ids});
        this._read();
    }

    _read() {
        const on = {battery: false, saver: false};
        for (const {s, proxy} of this._proxies) {
            let v = null;
            try {
                v = proxy.get_name_owner() ? unpack(proxy.get_cached_property(s.prop)) : null;
            } catch {}
            if (s.test(v))
                on[s.key === 'battery' ? 'battery' : 'saver'] = true;
        }
        if (on.battery === this._state.battery && on.saver === this._state.saver)
            return;
        this._state = on;
        try {
            this._onChange?.({...on});
        } catch (e) {
            logError(e, 'Fedora Glass: following the power state');
        }
    }

    destroy() {
        this._cancel?.cancel();
        this._cancel = null;
        for (const {proxy, ids} of this._proxies)
            ids.forEach(id => proxy.disconnect(id));
        this._proxies = [];
        this._onChange = null;
    }
}
