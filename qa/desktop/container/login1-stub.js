// Minimal logind stand-in so GNOME Shell can start in a container.
// With LOCK=1 the container also makes /run/systemd/seats, so the Shell talks to this
// stub as if it were logind and builds its lock screen; the session object and the
// display manager version below are only for that.
const {Gio, GLib} = imports.gi;
const xml = `<node><interface name="org.freedesktop.login1.Manager">
<method name="Inhibit"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="h" direction="out"/></method>
<method name="CanSuspend"><arg type="s" direction="out"/></method>
<method name="CanReboot"><arg type="s" direction="out"/></method>
<method name="CanPowerOff"><arg type="s" direction="out"/></method>
<method name="CanRebootToBootLoaderMenu"><arg type="s" direction="out"/></method>
<method name="ListSessions"><arg type="a(susso)" direction="out"/></method>
<method name="GetSession"><arg type="s" direction="in"/><arg type="o" direction="out"/></method>
<method name="GetSessionByPID"><arg type="u" direction="in"/><arg type="o" direction="out"/></method>
<method name="GetUser"><arg type="u" direction="in"/><arg type="o" direction="out"/></method>
<signal name="PrepareForSleep"><arg type="b"/></signal>
<signal name="SessionRemoved"><arg type="s"/><arg type="o"/></signal>
</interface></node>`;
const impl = {
  CanSuspend: () => 'no', CanReboot: () => 'no', CanPowerOff: () => 'no', CanRebootToBootLoaderMenu: () => 'no',
  ListSessions: () => [], GetSession: () => '/org/freedesktop/login1/session/self',
  GetSessionByPID: () => '/org/freedesktop/login1/session/self',
  GetUser: () => '/org/freedesktop/login1/user/self',
};
const sessionXml = `<node><interface name="org.freedesktop.login1.Session">
<method name="SetLockedHint"><arg type="b" direction="in"/></method>
<method name="Activate"/><method name="Lock"/><method name="Unlock"/>
<signal name="Lock"/><signal name="Unlock"/>
<property name="Id" type="s" access="read"/><property name="Active" type="b" access="read"/>
<property name="LockedHint" type="b" access="read"/><property name="Remote" type="b" access="read"/>
<property name="Class" type="s" access="read"/><property name="Type" type="s" access="read"/>
<property name="State" type="s" access="read"/>
</interface></node>`;
let locked = false;
const session = {
  Id: 'self', Active: true, Remote: false, Class: 'user', Type: 'wayland', State: 'active',
  get LockedHint() { return locked; },
  SetLockedHint(v) { locked = v; },
  Activate() {}, Lock() {}, Unlock() {},
};
const userXml = `<node><interface name="org.freedesktop.login1.User">
<property name="Name" type="s" access="read"/><property name="UID" type="u" access="read"/>
</interface></node>`;
const dmXml = `<node><interface name="org.gnome.DisplayManager.Manager">
<property name="Version" type="s" access="read"/>
</interface></node>`;
const objs = [
  [xml, impl, '/org/freedesktop/login1'],
  [sessionXml, session, '/org/freedesktop/login1/session/self'],
  [sessionXml, session, '/org/freedesktop/login1/session/auto'],
  [userXml, {Name: 'dino', UID: 1000}, '/org/freedesktop/login1/user/self'],
].map(([x, o, p]) => [Gio.DBusExportedObject.wrapJSObject(x, o), p]);
Gio.bus_own_name(Gio.BusType.SYSTEM, 'org.freedesktop.login1', 0,
  c => objs.forEach(([o, p]) => o.export(c, p)), null, () => print('lost login1'));
const dm = Gio.DBusExportedObject.wrapJSObject(dmXml, {Version: '50.0'});
Gio.bus_own_name(Gio.BusType.SYSTEM, 'org.gnome.DisplayManager', 0,
  c => dm.export(c, '/org/gnome/DisplayManager/Manager'), null, () => print('lost gdm'));
new GLib.MainLoop(null, false).run();
