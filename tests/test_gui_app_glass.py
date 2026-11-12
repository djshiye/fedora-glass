"""Per-app glass strength in the app: the "Apps with their own glass" card on the Panel and
windows page, one row per app with its choice (No glass, More solid, Clearer). Settings
older than this keep their no-glass apps as rows set to No glass. Backend first, then
the QML controls (mouse and keyboard)."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtGui")
from test_gui_backend import app, home, make_backend  # noqa: E402,F401
from test_gui_reliability import _find, _js, _spin, _window  # noqa: E402
from test_gui_shell_features import _items, _loaded, _page, _probe, _wait, apps_dirs, desktop  # noqa: E402,F401


def _rows(b):
    return [(r["key"], r["glass"]) for r in _js(b.property("noGlassApps"))]


def test_old_no_glass_settings_are_rows_set_to_no_glass(make_backend, apps_dirs):
    b = make_backend()
    b._set("no_glass_apps", ["org.gnome.Nautilus", "Code", "code"])
    _loaded(b)
    assert _rows(b) == [("org.gnome.Nautilus.desktop", "none"), ("code.desktop", "none")]


def test_a_row_choice_moves_all_its_ids_between_the_lists_and_keeps_its_place(make_backend, apps_dirs):
    b = make_backend()
    _loaded(b)
    b.addNoGlassApp("org.gnome.Nautilus.desktop")
    b.addNoGlassApp("code.desktop")
    b.addNoGlassApp("org.gimp.GIMP.desktop")
    b.setAppGlass("code.desktop", "solid")
    s = b.settings()
    assert s.no_glass_apps == ["org.gnome.Nautilus", "org.gimp.GIMP"]
    assert s.app_glass == {"code": "solid", "Code": "solid"}
    assert _rows(b) == [("org.gnome.Nautilus.desktop", "none"), ("code.desktop", "solid"),
                        ("org.gimp.GIMP.desktop", "none")], "the row stays where it was"
    b.setAppGlass("org.gnome.Nautilus.desktop", "clearer")
    b.setAppGlass("code.desktop", "clearer")
    assert b.settings().app_glass == {"org.gnome.Nautilus": "clearer", "code": "clearer", "Code": "clearer"}
    b.setAppGlass("code.desktop", "none")
    assert b.settings().no_glass_apps == ["org.gimp.GIMP", "code", "Code"]
    assert b.settings().app_glass == {"org.gnome.Nautilus": "clearer"}
    assert [k for k, _g in _rows(b)] == ["org.gnome.Nautilus.desktop", "code.desktop", "org.gimp.GIMP.desktop"]
    # Unknown choices and rows do nothing.
    before = b.settings()
    b.setAppGlass("code.desktop", "normal")
    b.setAppGlass("nothing.desktop", "solid")
    assert b.settings() == before
    assert b.property("dirty"), "the desktop changes on Apply"


def test_remove_and_the_picker_take_an_app_off_whatever_its_choice(make_backend, apps_dirs):
    b = make_backend()
    _loaded(b)
    b.addNoGlassApp("code.desktop")
    b.setAppGlass("code.desktop", "solid")
    b.addNoGlassApp("code.desktop")
    assert b.settings().no_glass_apps == [] and b.settings().app_glass == {"code": "solid", "Code": "solid"}, \
        "already on the list: adding again leaves its choice"
    b.toggleNoGlassApp("code.desktop")
    assert b.settings().app_glass == {} and _rows(b) == []
    b.addNoGlassApp("org.gimp.GIMP.desktop")
    b.setAppGlass("org.gimp.GIMP.desktop", "clearer")
    b.removeNoGlassApp("org.gimp.GIMP.desktop")
    assert b.settings().app_glass == {} and b.settings().no_glass_apps == []
    # An id no installed app has is a row of its own, with its choice.
    b._set("app_glass", {"com.example.Gone": "solid"})
    assert _rows(b) == [("com.example.Gone", "solid")]
    b.removeNoGlassApp("com.example.Gone")
    assert b.settings().app_glass == {}


def test_see_changes_reset_and_apply(make_backend, apps_dirs):
    from fedoraglass import palette
    from fedoraglass.render import glass as rg
    b = make_backend()
    _loaded(b)
    b.addNoGlassApp("org.gnome.Nautilus.desktop")
    b.setAppGlass("org.gnome.Nautilus.desktop", "solid")
    rows = {r["key"]: r for r in _js(b.property("changeList"))}
    assert rows["app_glass"]["label"] == "Glass strength for apps"
    assert rows["app_glass"]["after"] == "More solid: org.gnome.Nautilus"
    assert "app_glass" in b.property("changedFromDefault")
    s = b.settings()
    w = rg.config(s, palette.build(s, dark=True))["windows"]
    assert w["appGlass"] == {"org.gnome.nautilus": "solid"}
    # Reset all keeps the apps picked on this PC, like the no-glass list; the card's Reset empties both.
    assert b._all_reset().app_glass == {"org.gnome.Nautilus": "solid"}
    b.resetSettings(["no_glass_apps", "app_glass"])
    assert b.settings().app_glass == {} and b.settings().no_glass_apps == []


def _choice(row):
    return next(it for it in _items(row) if it.objectName() == "noGlassChoice")


def test_the_card_rows_choose_with_mouse_and_keyboard(qml, tmp_path, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    b = _probe(qml)
    system = tmp_path / "sys"
    monkeypatch.setenv("XDG_DATA_DIRS", str(system))
    data = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    desktop(data / "applications", "org.gnome.Nautilus.desktop", "Files")
    desktop(data / "applications", "code.desktop", "Visual Studio Code", wm="Code")
    win = _window(qml)
    try:
        win.show()
        _spin(150)
        _page(win, "windows")
        card = _find(win, "noGlassCard")
        b.refreshInstalledApps()
        assert _wait(lambda: b.property("installedAppsReady"))
        title = next(it for it in _items(card) if it.property("text") == "Apps with their own glass")
        assert "colours stay as they are" in title.property("caption")
        b.addNoGlassApp("code.desktop")
        _spin()
        row = _find(win, "noGlassRow_code.desktop")
        seg = _choice(row)
        assert seg.property("value") == "none"
        assert [m["label"] for m in _js(seg.property("model"))] == ["No glass", "More solid", "Clearer"]
        # A click on More solid.
        seg.activated.emit("solid")
        _spin()
        assert b.settings().app_glass == {"code": "solid", "Code": "solid"}
        row = _find(win, "noGlassRow_code.desktop")
        assert _choice(row).property("value") == "solid"
        # The keyboard: the arrow keys move the choice, and the focus stays on the row's
        # choice after the list is made again.
        seg = _choice(row)
        seg.forceActiveFocus()
        _spin()
        QTest.keyClick(win, Qt.Key_Right)
        _spin()
        assert b.settings().app_glass == {"code": "clearer", "Code": "clearer"}
        seg = _choice(_find(win, "noGlassRow_code.desktop"))
        assert seg.property("activeFocus"), "the focus came back to the row's choice"
        QTest.keyClick(win, Qt.Key_Left)
        QTest.keyClick(win, Qt.Key_Left)
        _spin()
        assert b.settings().no_glass_apps == ["code", "Code"] and b.settings().app_glass == {}
        assert _choice(_find(win, "noGlassRow_code.desktop")).property("activeFocus")
    finally:
        b.resetSettings(["no_glass_apps", "app_glass"])
        win.close()
