"""Lay out the test screens side by side at one scale (Dino uses two screens at 125 %),
through Mutter's own display settings API."""
import sys

from gi.repository import Gio, GLib

want = float(sys.argv[1]) if len(sys.argv) > 1 else 1.25
bus = Gio.bus_get_sync(Gio.BusType.SESSION)


def call(method, args=None, sig=None):
    return bus.call_sync("org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig",
                         "org.gnome.Mutter.DisplayConfig", method, args, sig and GLib.VariantType(sig),
                         Gio.DBusCallFlags.NONE, 10000, None).unpack()


serial, monitors, _logical, _props = call("GetCurrentState")
layout, x = [], 0
for i, ((conn, *_), modes, _mprops) in enumerate(sorted(monitors, key=lambda m: m[0][0])):
    mode = next(m for m in modes if m[6].get("is-current"))
    scale = min(mode[5], key=lambda s: abs(s - want))
    layout.append((x, 0, scale, 0, i == 0, [(conn, mode[0], {})]))
    print(f"{conn} {mode[1]}x{mode[2]} at x={x} scale {scale:.4f} (asked {want})")
    x += round(mode[1] / scale)
call("ApplyMonitorsConfig", GLib.Variant("(uua(iiduba(ssa{sv}))a{sv})", (serial, 1, layout, {})))
