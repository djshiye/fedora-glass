"""Shell features in the app: lighter glass on battery (Speed card), apps without glass
(Panel and windows page, with the app picker), the Glass switch in Quick Settings
(Glass page). Backend first, then the QML controls."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtGui")
from test_gui_backend import app, home, make_backend  # noqa: E402,F401
from test_gui_reliability import _find, _js, _spin, _window  # noqa: E402


def desktop(d: Path, did: str, name: str, icon: str = "", wm: str = "", extra: str = "") -> None:
    d.mkdir(parents=True, exist_ok=True)
    text = f"[Desktop Entry]\nType=Application\nName={name}\nExec=true\n"
    text += f"Icon={icon}\n" if icon else ""
    text += f"StartupWMClass={wm}\n" if wm else ""
    (d / did).write_text(text + extra)


@pytest.fixture
def apps_dirs(tmp_path, monkeypatch):
    """Two app folders: the user's own (XDG_DATA_HOME, set by `home`) and a system one."""
    system = tmp_path / "sys"
    monkeypatch.setenv("XDG_DATA_DIRS", str(system))
    user = Path(tmp_path / "data/applications")
    desktop(user, "org.gnome.Nautilus.desktop", "Files", icon="org.gnome.Nautilus")
    desktop(user, "code.desktop", "Visual Studio Code", wm="Code")
    desktop(user, "org.gimp.GIMP.desktop", "GNU Image Manipulation Program", icon=str(tmp_path / "gimp.png"))
    desktop(user, "hidden.desktop", "Hidden", extra="NoDisplay=true\n")
    desktop(system / "applications", "org.gnome.Nautilus.desktop", "Files (system copy)")
    desktop(system / "applications", "mpv.desktop", "mpv Media Player")
    desktop(system / "applications", "broken.desktop", "x", extra="\x00\x01[[[")
    (system / "applications/notes.txt").write_text("not an app")
    return user, system


def _wait(cond, ms=5000):
    from PySide6.QtCore import QCoreApplication, QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while not cond() and t.elapsed() < ms:
        QCoreApplication.processEvents()
    return cond()


def _loaded(b):
    b.refreshInstalledApps()
    assert _wait(lambda: b.property("installedAppsReady"))


# ---- lighter glass on battery: backend ----------------------------------------------------
def test_battery_switch_is_a_setting_with_a_default(make_backend):
    b = make_backend()
    assert b.property("lighterOnBattery") is True
    assert b.property("defaults")["lighter_on_battery"] is True
    b.setProperty("lighterOnBattery", False)
    assert b.settings().lighter_on_battery is False and b.property("dirty")
    assert "lighter_on_battery" in b.property("changedFromDefault")


def test_speed_status_says_battery_or_power_saver(make_backend, home, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / "cache"))
    b = make_backend()
    p = home / "cache/liquid-glass/speed.json"
    p.parent.mkdir(parents=True)
    for power, want in (("battery", "battery"), ("saver", "saver"), ("warp", ""), (None, "")):
        p.write_text(json.dumps({"level": "lighter", "reason": "battery", "power": power}))
        b._on_speed_file()
        assert (b.property("speedLevel"), b.property("speedReason"), b.property("speedPower")) == \
            ("lighter", "battery", want)
    p.write_text(json.dumps({"level": "lighter", "reason": "slow", "power": "battery"}))
    b._on_speed_file()
    assert b.property("speedPower") == "", "only when the battery is the reason"


# ---- apps without glass: backend ---------------------------------------------------------
def test_installed_apps_are_read_off_the_ui_thread(make_backend, apps_dirs, monkeypatch):
    from PySide6.QtCore import QThread

    from fedoraglass.gui import backend as bmod
    threads = []
    real = bmod.installed_apps
    monkeypatch.setattr(bmod, "installed_apps", lambda env: (threads.append(QThread.currentThread()), real(env))[1])
    b = make_backend()
    assert not b.property("installedAppsReady")
    _loaded(b)
    assert threads and threads[0] is not QThread.currentThread()
    apps = {a["id"]: a for a in _js(b.property("installedApps"))}
    assert set(apps) == {"org.gnome.Nautilus.desktop", "code.desktop", "org.gimp.GIMP.desktop", "mpv.desktop"}
    assert apps["org.gnome.Nautilus.desktop"]["name"] == "Files", "the user's own copy wins"
    assert apps["mpv.desktop"]["builtIn"] is True and apps["code.desktop"]["builtIn"] is True
    assert apps["org.gnome.Nautilus.desktop"]["builtIn"] is False
    assert [a["name"] for a in _js(b.property("installedApps"))] == sorted((a["name"] for a in apps.values()), key=str.casefold)


def test_add_writes_every_id_the_extension_matches_and_remove_takes_them_all(make_backend, apps_dirs):
    b = make_backend()
    _loaded(b)
    b.addNoGlassApp("org.gnome.Nautilus.desktop")
    b.addNoGlassApp("code.desktop")
    assert b.settings().no_glass_apps == ["org.gnome.Nautilus", "code", "Code"]
    rows = _js(b.property("noGlassApps"))
    assert [(r["key"], r["name"]) for r in rows] == [("org.gnome.Nautilus.desktop", "Files"),
                                                     ("code.desktop", "Visual Studio Code")]
    assert rows[1]["ids"] == ["code", "Code"]
    b.addNoGlassApp("code.desktop")
    assert b.settings().no_glass_apps == ["org.gnome.Nautilus", "code", "Code"], "once"
    b.removeNoGlassApp("code.desktop")
    assert b.settings().no_glass_apps == ["org.gnome.Nautilus"]
    b.toggleNoGlassApp("org.gnome.Nautilus.desktop")
    assert b.settings().no_glass_apps == []
    b.toggleNoGlassApp("org.gimp.GIMP.desktop")
    assert b.settings().no_glass_apps == ["org.gimp.GIMP"]
    b.addNoGlassApp("not-installed.desktop")
    assert b.settings().no_glass_apps == ["org.gimp.GIMP"], "only installed apps are added"
    assert b.property("dirty"), "the desktop changes on Apply"


def test_an_id_no_installed_app_has_is_a_row_of_its_own(make_backend, apps_dirs):
    b = make_backend()
    b._set("no_glass_apps", ["Code", "com.example.Gone"])
    rows = _js(b.property("noGlassApps"))
    assert [r["name"] for r in rows] == ["Code", "com.example.Gone"], "names come once the apps are read"
    _loaded(b)
    rows = _js(b.property("noGlassApps"))
    assert [(r["key"], r["name"]) for r in rows] == [("code.desktop", "Visual Studio Code"),
                                                     ("com.example.Gone", "com.example.Gone")]
    b.removeNoGlassApp("code.desktop")
    b.removeNoGlassApp("com.example.Gone")
    assert b.settings().no_glass_apps == []


def test_apply_renders_the_list_into_shell_glass_json(make_backend, apps_dirs):
    from fedoraglass import palette
    from fedoraglass.render import glass as rg
    b = make_backend()
    _loaded(b)
    b.addNoGlassApp("code.desktop")
    b.addNoGlassApp("org.gimp.GIMP.desktop")
    s = b.settings()
    skip = rg.config(s, palette.build(s, dark=True))["windows"]["skip"]
    assert "org.gimp.GIMP" in skip and "Code" in skip and skip.count("Code") == 1


def test_built_in_ones_are_named(make_backend):
    text = make_backend().property("noGlassBuiltIn")
    for word in ("Steam", "video players", "Firefox"):
        assert word in text


def test_quick_toggle_is_a_setting(make_backend):
    b = make_backend()
    assert b.property("quickToggle") is True
    b.setProperty("quickToggle", False)
    assert b.settings().quick_toggle is False and "quick_toggle" in b.property("changedFromDefault")
    b.resetSettings(["quick_toggle"])
    assert b.settings().quick_toggle is True


# ---- the controls ---------------------------------------------------------------------------
def _probe(qml):
    from test_gui_reliability import _probe as probe
    return probe(qml)


def _page(win, page):
    win.setProperty("page", page)
    _spin(150)


def test_speed_card_battery_switch_and_reason(qml):
    b = _probe(qml)
    win = _window(qml)
    saved = (b._speed_status, b._glass_live)
    try:
        win.show()
        _spin(150)
        _page(win, "glass")
        row = _find(win, "lighterOnBattery")
        assert row is not None and row.property("visible")
        assert row.property("checked") is True
        assert "Power Saver" in row.property("caption")
        row.toggled.emit(False)
        assert b.property("lighterOnBattery") is False
        b.resetSettings(["lighter_on_battery"])
        assert row.property("checked") is True
        b._glass_live = True
        b._speed_status = {"level": "lighter", "reason": "battery", "power": "battery"}
        b.speedChanged.emit()
        b.targetsChanged.emit()
        _spin()
        status = _find(win, "speedStatus")
        assert status.property("text") == "Right now: lighter glass, because you're on battery."
        b._speed_status = {"level": "lighter", "reason": "battery", "power": "saver"}
        b.speedChanged.emit()
        _spin()
        assert status.property("text") == "Right now: lighter glass, because Power Saver is on."
    finally:
        b._speed_status, b._glass_live = saved
        b.speedChanged.emit()
        b.targetsChanged.emit()
        b.resetSettings(["lighter_on_battery"])
        win.close()


def test_quick_settings_switch_on_the_glass_page(qml):
    b = _probe(qml)
    win = _window(qml)
    try:
        win.show()
        _spin(150)
        _page(win, "glass")
        row = _find(win, "quickToggle")
        tile = _find(win, "quickTogglePreview")
        assert row is not None and row.property("visible") and row.property("checked") is True
        assert row.property("label") == "Glass switch in Quick Settings"
        assert tile.property("opacity") == 1
        row.toggled.emit(False)
        _spin(300)
        assert b.property("quickToggle") is False and tile.property("opacity") < 0.5
    finally:
        b.resetSettings(["quick_toggle"])
        win.close()


def test_apps_without_glass_card_add_remove_and_built_in(qml, tmp_path, monkeypatch):
    b = _probe(qml)
    system = tmp_path / "sys"
    monkeypatch.setenv("XDG_DATA_DIRS", str(system))
    data = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    desktop(data / "applications", "org.gnome.Nautilus.desktop", "Files")
    desktop(data / "applications", "code.desktop", "Visual Studio Code", wm="Code")
    desktop(system / "applications", "mpv.desktop", "mpv Media Player")
    win = _window(qml)
    try:
        win.show()
        _spin(150)
        _page(win, "windows")
        card = _find(win, "noGlassCard")
        assert card is not None and card.property("visible")
        assert _wait(lambda: b.property("installedAppsReady"))
        assert _find(win, "noGlassEmpty").property("visible")
        builtin = _find(win, "noGlassBuiltIn")
        assert builtin.property("text").startswith("Always without glass: Steam")
        # Add: the picker lists the installed apps, searchable; built-in ones can't be picked.
        _find(win, "noGlassAdd").clicked.emit()
        _spin(400)
        picker = card.property("picker")
        assert picker.property("opened")
        assert _wait(lambda: len(_js(picker.property("shown"))) == 3)
        _find(win, "appPickerSearch").setProperty("text", "visual")
        _spin()
        assert [a["id"] for a in _js(picker.property("shown"))] == ["code.desktop"]
        _find(win, "appPickerSearch").setProperty("text", "k")
        _spin()
        assert _js(picker.property("shown")) == [], "never matched by the .desktop on every id"
        _find(win, "appPickerSearch").setProperty("text", "")
        _spin()
        mpv = _find(win, "appPick_mpv.desktop")
        assert mpv is not None and mpv.property("enabled") is False
        pick = _find(win, "appPick_code.desktop")
        pick.clicked.emit()
        _spin()
        assert b.settings().no_glass_apps == ["code", "Code"]
        assert pick.property("added") is True
        _find(win, "appPickerDone").clicked.emit()
        _spin(400)
        assert not picker.property("opened")
        # The list shows the app once, by name, with Remove.
        row = _find(win, "noGlassRow_code.desktop")
        assert row is not None and not _find(win, "noGlassEmpty").property("visible")
        assert b.property("changedFromDefault").count("no_glass_apps") == 1
        remove = next(it for it in _items(row) if it.objectName() == "noGlassRemove")
        remove.clicked.emit()
        _spin()
        assert b.settings().no_glass_apps == []
        # Glass behind app windows off: the card says why no app gets it.
        assert not _find(win, "noGlassAppWindowsOff").property("visible")
        b.setProperty("blurAppWindows", False)
        _spin()
        assert _find(win, "noGlassAppWindowsOff").property("visible")
    finally:
        b.resetSettings(["no_glass_apps", "blur_app_windows"])
        card = _find(win, "noGlassCard")
        if card is not None:
            card.property("picker").close()
        win.close()


def _items(root):
    from test_gui_reliability import _items as items
    return items(root)


def test_search_finds_the_new_controls(qml):
    win = _window(qml)
    side = _find(win, "sidebar")
    field = _find(win, "searchField")

    def found(text):
        field.setProperty("text", text)
        _spin(30)
        return [e["name"] for e in _js(side.property("allResults"))]
    try:
        win.show()
        _spin(150)
        assert "lighterOnBattery" in found("battery")
        assert "lighterOnBattery" in found("power saver")
        assert "noGlassCard" in found("apps without glass")
        assert "quickToggle" in found("quick settings")
        assert "quickToggle" in found("pause")
    finally:
        field.setProperty("text", "")
        win.close()
