"""The reliability release, app side: "applied" means applied, nothing runs over a package
removal or the login screen step, one source for the presets, search that only finds what
is there, a window that fits a 1280x720 screen, and the slow parts off the UI thread."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtGui")
pytest.importorskip("PySide6.QtQuick")

from fedoraglass import settings as settings_mod  # noqa: E402
from fedoraglass.engine import Engine  # noqa: E402
from fedoraglass.targets.base import Detection, Target, WriteFile  # noqa: E402

_keep: list = []


class _Part(Target):
    """A themed app: one file. `fail` makes its part of Apply fail."""

    def __init__(self, tid, home, fail=False):
        super().__init__(id=tid, name=tid.title(), group="Apps", summary=f"{tid} summary")
        self._home, self.fail = home, fail

    def detect(self, env):
        return Detection(True, "")

    def plan(self, ctx):
        if self.fail:
            raise RuntimeError("broken on purpose")
        return [WriteFile(self._home / f"out/{self.id}.css", f"chrome {ctx.tokens.chrome.css}\n")]


class _Engine(Engine):
    """An Engine that can stop dead in the middle of Apply (a crash, not a failed part)."""

    crash = False

    def apply(self, s, *a, **k):
        if self.crash:
            raise OSError("disk full")
        return super().apply(s, *a, **k)


def _backend(fake_env, tmp_path, targets=None):
    from fedoraglass.gui.backend import Backend
    targets = targets if targets is not None else [_Part("alpha", fake_env.home), _Part("beta", fake_env.home)]
    eng = _Engine(fake_env, targets)
    b = Backend(env=fake_env, engine_factory=lambda: eng,
                settings_path=tmp_path / "cfg/liquid-glass/settings.json", ui_dark=True, start=False)
    b._test_engine = eng
    _keep.append(b)
    return b


def _apply(b) -> list | None:
    got: list = []
    b.applyFinished.connect(lambda rs: got.append(rs))
    b.apply()
    assert b.waitIdle()
    assert b.waitIdle()        # the re-check Apply starts afterwards
    return got[-1] if got else None


def _on_disk(tmp_path) -> dict:
    return json.loads((tmp_path / "cfg/liquid-glass/settings.json").read_text())


# ---------------------------------------------------------------- 1. applied means applied

def test_apply_that_stops_keeps_the_changes_unapplied_and_the_file_on_the_applied_look(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    b.setProperty("frost", 0.3)
    assert _apply(b) is not None
    assert _on_disk(tmp_path)["frost"] == 0.3
    b.setProperty("frost", 0.9)
    b.setProperty("radius", 30)
    assert b.property("changeCount") == 2
    errors: list = []
    b.failed.connect(errors.append)
    b._test_engine.crash = True
    assert _apply(b) is None
    assert errors and "Apply stopped" in errors[0]
    # The watcher re-applies settings.json on a dark/light flip: it must hold the look applied.
    assert _on_disk(tmp_path)["frost"] == 0.3 and _on_disk(tmp_path)["radius"] != 30
    assert b.property("dirty") and b.property("changeCount") == 2
    assert b.property("partlyApplied") == 0
    b.discardChanges()
    assert b.settings().frost == 0.3 and not b.property("dirty")


def test_apply_with_failed_parts_says_so_and_undo_goes_to_the_last_full_look(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    b.setProperty("frost", 0.3)
    _apply(b)
    assert b.property("partlyApplied") == 0
    b._test_engine.targets[1].fail = True
    b.setProperty("frost", 0.7)
    rows = _apply(b)
    assert [r["status"] for r in rows].count("failed") == 1
    # What did apply is the applied look, and settings.json says so (the watcher keeps it).
    assert not b.property("dirty")
    assert _on_disk(tmp_path)["frost"] == 0.7
    assert b.property("partlyApplied") == 1
    assert [r["status"] for r in b.property("partialResults")] == [r["status"] for r in rows]
    # Undo: back to the last look that applied fully, to apply again.
    b.discardChanges()
    assert b.settings().frost == 0.3 and b.property("dirty")
    b._test_engine.targets[1].fail = False
    _apply(b)
    assert b.property("partlyApplied") == 0 and not b.property("dirty")
    assert _on_disk(tmp_path)["frost"] == 0.3


def test_remove_only_switch_during_apply_survives_both_endings(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    b.setProperty("frost", 0.6)
    b._test_engine.crash = True
    b.apply()
    b.setProperty("undoOnRemove", False)          # saved at once, while Apply runs
    assert _on_disk(tmp_path)["frost"] == 0.6     # the file still holds the look being applied
    assert b.waitIdle()
    assert _on_disk(tmp_path)["undo_on_remove"] is False
    assert _on_disk(tmp_path)["frost"] != 0.6
    b._test_engine.crash = False
    b.apply()
    b.setProperty("undoOnRemove", True)
    assert b.waitIdle() and b.waitIdle()
    assert _on_disk(tmp_path)["undo_on_remove"] is True and _on_disk(tmp_path)["frost"] == 0.6


def _probe(qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent
    comp = QQmlComponent(qml)
    comp.setData(b"import QtQuick\nimport FedoraGlass.Core\nQtObject { property var b: Backend }", QUrl())
    obj = comp.create()
    _keep.append((comp, obj))
    return obj.property("b")


def _window(qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    from fedoraglass.gui import app as gui_app
    comp = QQmlComponent(qml, QUrl.fromLocalFile(str(Path(gui_app.QML_DIR) / "Main.qml")))
    win = comp.create()
    assert win is not None, comp.errorString()
    _keep.append(comp)
    return win


def _items(root):
    todo, out = [root], []
    while todo:
        it = todo.pop()
        out.append(it)
        todo.extend(it.childItems())
    return out


def _find(win, name):
    from PySide6.QtCore import QObject
    hit = win.findChild(QObject, name)
    if hit is None:
        hit = next((it for it in _items(win.contentItem()) if it.objectName() == name), None)
    return hit


def _js(v):
    return v.toVariant() if hasattr(v, "toVariant") else v


def _spin(ms=60):
    from PySide6.QtCore import QCoreApplication, QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QCoreApplication.processEvents()


def test_footer_says_partly_applied_and_opens_the_results(qml):
    b = _probe(qml)
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        rows = [{"id": "a", "name": "A", "status": "applied", "message": ""},
                {"id": "b", "name": "B", "status": "failed", "message": "no room"},
                {"id": "c", "name": "C", "status": "failed", "message": "no room"}]
        b._set_partial(rows)
        _spin()
        assert _find(win, "statusText").property("text") == "2 parts didn't change."
        see = _find(win, "partialButton")
        assert see.property("visible") and see.property("text") == "See what happened"
        assert _find(win, "discardButton").property("visible")
        see.clicked.emit()
        _spin(400)
        sheet = _find(win, "resultsSheet")
        assert sheet.property("opened")
        assert sheet.property("failedCount") == 2
        sheet.close()
    finally:
        b._set_partial([])
        win.close()


# ---------------------------------------------------------------- 2. nothing runs over a removal

def test_removing_counts_as_busy_and_blocks_apply_restore_and_plan(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    seen: list = []
    b.busyChanged.connect(lambda: seen.append(b.property("busy")))
    b._set_removing(True)
    try:
        assert b.property("busy") and b.property("busyKind") == "remove" and seen == [True]
        b.setProperty("frost", 0.2)
        b.apply()
        b.revert()
        b.requestPlan()
        assert b._task is None and b._pending_action is None
        assert not (tmp_path / "cfg/liquid-glass/settings.json").exists()
    finally:
        b._set_removing(False)
    assert not b.property("busy")


def test_window_does_not_close_while_the_app_is_being_removed(qml):
    b = _probe(qml)
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        b._set_removing(True)
        _spin()
        assert _find(win, "applyButton").property("enabled") is False
        win.close()
        _spin(400)
        assert win.isVisible()
        sheet = _find(win, "waitSheet")
        assert sheet.property("opened") and sheet.property("title") == "Fedora Glass is being removed"
        assert not _find(win, "closeWhenDone").property("visible")
        sheet.close()
    finally:
        b._set_removing(False)
        win.close()


def test_apply_starts_the_login_screen_step_before_it_reports(qml, fake_env, tmp_path, monkeypatch):
    from fedoraglass.gui.backend import Backend
    pkexec = tmp_path / "pkexec"
    pkexec.write_text("#!/bin/sh\nsleep 0.3\nexit 0\n")
    pkexec.chmod(0o755)
    monkeypatch.setattr(Backend, "PKEXEC", pkexec)
    b = _backend(fake_env, tmp_path)
    b._login_available = lambda: True
    b._read_login_state = lambda: "on"
    b._login_stale = lambda s=None: True
    states: list = []
    b.applyFinished.connect(lambda rs: states.append(b.property("loginGlass")))
    _apply(b)
    assert states == ["busy"]
    from PySide6.QtCore import QCoreApplication, QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while b.property("loginGlass") == "busy" and t.elapsed() < 5000:
        QCoreApplication.processEvents()
    assert b.property("loginGlass") == "on" and not b.property("loginGlassFailed")


def test_apply_and_close_waits_for_the_login_screen_step(qml):
    b = _probe(qml)
    b.discardChanges()
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        win.setProperty("closeAfterApply", True)
        b._login_proc = object()           # the login screen step asks for the password
        b.loginGlassChanged.emit()
        b.applyFinished.emit([])
        _spin(200)
        assert win.isVisible() and win.property("closeAfterLogin")
        win.close()                        # pressing close meanwhile asks to wait too
        _spin(300)
        assert win.isVisible() and _find(win, "waitSheet").property("what") == "login"
        _find(win, "waitSheet").close()
        b._login_proc = None
        b.loginGlassChanged.emit()
        _spin(200)
        assert not win.isVisible()
    finally:
        b._login_proc = None
        win.setProperty("closeAfterLogin", False)
        win.close()


# ---------------------------------------------------------------- 3. the login screen gets the applied look

def test_login_glass_button_uses_the_applied_look_not_the_sliders(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    b.setProperty("frost", 0.3)
    _apply(b)
    assert not b.property("loginGlassBehind")
    b.setProperty("frost", 0.95)
    assert b.property("loginGlassBehind")
    b.setProperty("glassQuality", "lightest")       # not on the login screen: no note for it
    ran: list = []
    b._run_login = lambda args, done: ran.append(args)
    b.turnOnLoginGlass()
    assert ran and ran[0][0] == "apply" and ran[0][-1] == "0.300"
    b.setProperty("frost", 0.3)
    assert not b.property("loginGlassBehind")


# ---------------------------------------------------------------- 4. one source for the presets

def test_preset_tile_tick_and_name_agree_with_the_settings(qml, fake_env, tmp_path):
    from fedoraglass.settings import PRESETS
    b = _backend(fake_env, tmp_path)
    ticks = [t["value"] for t in b.property("frostTicks")]
    assert ticks == pytest.approx([v["frost"] for v in PRESETS.values()])
    for name in PRESETS:
        b.applyPreset(name)
        assert b.property("activePreset") == name
        assert b.frostName(b.property("frost")) == name, name
        assert b.property("presetFrost")[name] == pytest.approx(PRESETS[name]["frost"])
    assert b.frostName(0.1) == "Clear" and b.frostName(0.02) == "Liquid"


def test_home_and_glass_pages_take_the_presets_from_the_backend(qml):
    from fedoraglass.settings import PRESETS
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        win.setProperty("page", "glass")
        _spin(200)
        home = _find(win, "homePage")
        assert home.property("presetFrost")["Clear"] == pytest.approx(PRESETS["Clear"]["frost"])
        for slider in ("homeFrost", "glassFrost"):
            ticks = [t["value"] for t in _find(win, slider).property("ticks")]
            assert ticks == pytest.approx([v["frost"] for v in PRESETS.values()]), slider
    finally:
        win.close()


# ---------------------------------------------------------------- 5. search finds only what is there

def test_search_leaves_out_controls_this_pc_does_not_show(qml):
    b = _probe(qml)
    win = _window(qml)
    side = _find(win, "sidebar")
    field = _find(win, "searchField")

    def found(text):
        field.setProperty("text", text)
        _spin(30)
        return [e["name"] for e in _js(side.property("allResults"))]
    try:
        win.show()
        _spin(200)
        b._targets_ready, b._has_dtp = True, False
        b.targetsChanged.emit()
        _spin()
        assert "panelStyle" not in found("panel") and "panelMargin" not in found("panel margin")
        assert "motionGlide" not in found("glide")
        assert "motionDtpNote" not in found("dash to panel hover")
        b._has_dtp = True
        b.targetsChanged.emit()
        assert "panelStyle" in found("panel") and "motionGlide" in found("glide")
        assert b.property("canRemoveApp") is False
        assert "removeApp" not in found("uninstall") and "undoOnRemove" in found("uninstall")
        assert b.property("loginGlass") == "unavailable"
        assert "loginCard" not in found("login")
        for text, name in (("widget look", "lockWidgetStyle"), ("weather place", "lockWeatherPlace"),
                           ("slide time", "lockSlideMs"), ("bounce", "lockBounce")):
            assert name in found(text), text
    finally:
        field.setProperty("text", "")
        b._targets_ready = False
        win.close()


def test_search_says_when_more_match_than_it_shows(qml):
    win = _window(qml)
    side = _find(win, "sidebar")
    field = _find(win, "searchField")
    try:
        win.show()
        _spin(200)
        field.forceActiveFocus()
        field.setProperty("text", "lock")
        _spin(60)
        total = len(_js(side.property("allResults")))
        assert total > 7 and len(_js(side.property("results"))) == 7
        more = _find(win, "searchMore")
        assert more.property("visible")
        assert more.property("text").startswith(f"{total - 7} more settings match.")
        field.setProperty("text", "corner")
        _spin(60)
        assert not more.property("visible")
    finally:
        field.setProperty("text", "")
        win.close()


# ---------------------------------------------------------------- 6. fits a 1280x720 screen

def test_window_fits_1280x720_with_apply_in_view(qml):
    """1080p at 150 % leaves about 688 px under GNOME's top bar."""
    from fedoraglass.gui.app import fit_size
    win = _window(qml)
    try:
        margin = win.property("margin")
        assert win.minimumHeight() <= 688
        _, h = fit_size(type("R", (), {"width": lambda s: 1280, "height": lambda s: 720})(), margin)
        assert h + 2 * margin <= 688
        win.setWidth(1280)
        win.setHeight(688)
        win.show()
        _spin(300)
        for page in ("home", "glass", "lock", "apps", "about"):
            win.setProperty("page", page)
            _spin(200)
            apply = _find(win, "applyButton")
            pos = apply.mapToScene(apply.boundingRect().bottomRight())
            assert apply.isVisible() and pos.y() <= win.height() - margin, page
    finally:
        win.close()


# ---------------------------------------------------------------- 7. the Apps page keeps its rows

def test_flipping_one_app_keeps_every_row_and_its_open_notes(qml):
    b = _probe(qml)
    win = _window(qml)
    saved = (b._targets, b._targets_ready)
    try:
        b._targets = [{"id": i, "name": i.title(), "group": "Apps", "summary": "", "notes": ["a note"],
                       "available": True, "detail": "", "hideWhenMissing": False} for i in ("one", "two")]
        b._targets_ready = True
        b.targetsChanged.emit()
        win.show()
        _spin(200)
        win.setProperty("page", "apps")
        _spin(300)
        rows = [it for it in _items(_find(win, "appsPage")) if it.metaObject().indexOfProperty("notesOpen") >= 0]
        assert sorted(r.property("item")["id"] for r in rows) == ["one", "two"]
        first = next(r for r in rows if r.property("item")["id"] == "one")
        second = next(r for r in rows if r.property("item")["id"] == "two")
        first.setProperty("notesOpen", True)
        rebuilt: list = []
        first.destroyed.connect(lambda *_: rebuilt.append(1))
        b.setTargetEnabled("two", False)
        _spin(100)
        assert not rebuilt
        assert first.property("notesOpen") is True
        assert second.property("on") is False and first.property("on") is True
        assert b.property("activeTargetCount") == 1
        b.discardChanges()
        _spin(60)
        assert second.property("on") is True
    finally:
        b.discardChanges()
        b._targets, b._targets_ready = saved
        b.targetsChanged.emit()
        win.close()


# ---------------------------------------------------------------- 8. the preview follows the wallpaper

def test_preview_wallpaper_follows_light_dark_and_a_new_wallpaper(qml, fake_env, tmp_path):
    from PySide6.QtCore import QCoreApplication, QElapsedTimer, QUrl
    from PySide6.QtGui import QColor, QImage
    pics = {}
    for name, colour in (("day", "#f0f0f0"), ("night", "#101018"), ("new", "#808080")):
        img = QImage(32, 18, QImage.Format_RGB32)
        img.fill(QColor(colour))
        pics[name] = tmp_path / f"{name}.png"
        img.save(str(pics[name]))
    bg = fake_env.gs.setdefault(("org.gnome.desktop.background", None), {})
    bg["picture-uri"] = f"'file://{pics['day']}'"
    bg["picture-uri-dark"] = f"'file://{pics['night']}'"
    b = _backend(fake_env, tmp_path)
    url = lambda p: QUrl.fromLocalFile(str(p)).toString()   # noqa: E731
    seen: list = []
    b.wallpaperChanged.connect(lambda: seen.append(b.property("wallpaper")))
    assert b.property("previewDark") is True
    assert b.property("wallpaper") == url(pics["night"]) == b.property("appWallpaper")
    b.setProperty("previewDark", False)              # the preview's Light/Dark pill
    assert b.property("wallpaper") == url(pics["day"])
    assert b.property("appWallpaper") == url(pics["night"])     # the window follows GNOME, not the pill
    b._wallpaper_lines(f"picture-uri: 'file://{pics['new']}'\n")
    assert b.property("wallpaper") == url(pics["new"]) and seen[-1] == url(pics["new"])
    # Its brightness is decoded on a worker thread, then announced.
    first = b.property("wallpaperLuma")
    t = QElapsedTimer()
    t.start()
    while url(pics["new"]) not in b._lumas and t.elapsed() < 5000:
        QCoreApplication.processEvents()
    assert first == 0.2 and 0.1 < b.property("wallpaperLuma") < 0.4
    b.setProperty("previewDark", True)
    assert b.property("wallpaper") == url(pics["night"])
    # Without a dark picture GNOME shows the light one in dark style too.
    b._wallpaper_lines("picture-uri-dark: ''\n")
    assert b.property("wallpaper") == url(pics["new"])


# ---------------------------------------------------------------- damaged settings.json

def test_damaged_settings_note_shows_until_the_next_save(qml, fake_env, tmp_path, monkeypatch):
    notes = ["Your settings file was damaged, so Fedora Glass set it aside and loaded the last good copy."]
    monkeypatch.setattr(settings_mod, "damage_notice", lambda path=None: notes[0], raising=False)
    b = _backend(fake_env, tmp_path)
    assert b.property("damageNote") == notes[0]
    notes[0] = None                       # the next save clears it
    b.setProperty("undoOnRemove", False)
    assert b.property("damageNote") == ""
    monkeypatch.delattr(settings_mod, "damage_notice", raising=False)
    assert _backend(fake_env, tmp_path).property("damageNote") == ""     # an engine without it


def test_damaged_settings_banner(qml):
    b = _probe(qml)
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        assert not _find(win, "damageBanner").property("shown")
        b._damage = "Your settings file was damaged."
        b.damageNoteChanged.emit()
        _spin(400)
        banner = _find(win, "damageBanner")
        assert banner.property("shown") and banner.height() == 48
        assert _find(win, "damageNote").property("text") == "Your settings file was damaged."
    finally:
        b._damage = ""
        b.damageNoteChanged.emit()
        win.close()


# ---------------------------------------------------------------- 9. what counts as a change

@pytest.mark.parametrize("dtp", [True, False])
def test_start_on_desktop_off_and_on_again_is_no_change(qml, fake_env, tmp_path, dtp):
    b = _backend(fake_env, tmp_path)
    b._targets_ready, b._has_dtp = True, dtp
    assert b.settings().start_on_desktop is None
    assert b.property("startOnDesktop") is dtp
    b.setProperty("startOnDesktop", not dtp)
    assert b.property("dirty") and b.property("changeCount") == 1
    b.setProperty("startOnDesktop", dtp)           # back to what Apply decides here anyway
    assert not b.property("dirty") and b.property("changeCount") == 0
    assert "start_on_desktop" not in b.property("changedFromDefault")


def test_remove_switch_is_never_an_unapplied_change(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    b.setProperty("undoOnRemove", False)
    assert not b.property("dirty") and b.property("changeCount") == 0
    assert "undo_on_remove" not in b.property("changedFromDefault")
    b.setProperty("frost", 0.9)
    b.resetDefaults()                              # Reset all leaves the saved switch alone
    assert b.property("undoOnRemove") is False
    b.resetSettings(["undo_on_remove", "frost"])
    assert b.property("undoOnRemove") is False and not b.property("dirty")


# ---------------------------------------------------------------- 10. nothing slow on the UI thread

def _settle(cond, ms=5000):
    from PySide6.QtCore import QCoreApplication, QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while not cond() and t.elapsed() < ms:
        QCoreApplication.processEvents()
    return cond()


def test_package_query_waits_for_the_first_check_and_runs_off_the_ui_thread(qml, fake_env, tmp_path, monkeypatch):
    import threading
    from fedoraglass.gui.backend import Backend
    calls: list = []
    monkeypatch.setattr(Backend, "_installed_package",
                        lambda self: calls.append(threading.current_thread()) or "fedora-glass")
    b = _backend(fake_env, tmp_path)
    assert calls == [] and b.property("canRemoveApp") is False
    b.refreshTargets()
    assert b.waitIdle()
    assert len(calls) == 1 and calls[0] is not threading.main_thread()
    assert b.property("canRemoveApp") is True
    b.refreshTargets()
    assert b.waitIdle() and len(calls) == 1          # asked once


def test_old_copy_clean_up_runs_off_the_ui_thread(qml, fake_env, tmp_path, monkeypatch):
    import threading

    from fedoraglass import leftovers
    ran: list = []
    monkeypatch.setattr(leftovers, "clean_up", lambda env: ran.append(threading.current_thread()) or [])
    b = _backend(fake_env, tmp_path)
    b._leftovers = [tmp_path / "old"]
    said: list = []
    b.noticed.connect(said.append)
    b.cleanUpOldCopy()
    assert b.property("busyKind") == "cleanup"
    assert b.waitIdle()
    assert ran and ran[0] is not threading.main_thread() and said


def test_weather_is_looked_at_off_the_ui_thread_and_not_on_every_focus(qml, fake_env, tmp_path, monkeypatch):
    import threading

    from fedoraglass.gui import backend as bmod
    looks: list = []
    monkeypatch.setattr(bmod, "_weather_state", lambda env: looks.append(threading.current_thread()) or "no-app")
    b = _backend(fake_env, tmp_path)
    for _ in range(5):                    # the window gains focus again and again
        b.refreshWeather()
        assert _settle(lambda: b._weather_task is None)
    assert len(looks) == 1 and looks[0] is not threading.main_thread()
    assert b.property("weatherState") == "no-app"
    b._weather_at -= b.WEATHER_EVERY
    b.refreshWeather()
    assert _settle(lambda: b._weather_task is None) and len(looks) == 2


def test_settings_that_do_not_touch_the_colours_leave_the_tokens_alone(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    seen: list = []
    b.tokensChanged.connect(lambda: seen.append(1))
    for name, value in (("lockSlideMs", 900), ("lockClock", "thin"), ("cursorSize", 48), ("menuGrow", False)):
        b.setProperty(name, value)
    assert seen == [] and b.property("dirty")
    b.setProperty("frost", 0.9)
    assert len(seen) == 1
    b.setProperty("previewDark", not b.property("previewDark"))     # other tokens show now
    assert len(seen) == 2


# ---------------------------------------------------------------- 11. screen readers

def test_segmented_and_dropdowns_tell_screen_readers_what_they_are(qml):
    from PySide6.QtGui import QAccessible
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        for page in ("home", "colour", "windows", "pointer", "lock", "glass", "motion"):
            win.setProperty("page", page)
            _spin(150)
        segs = [it for it in _items(win.contentItem()) if it.metaObject().indexOfProperty("segWidths") >= 0]
        drops = [it for it in _items(win.contentItem()) if it.metaObject().indexOfProperty("glyphs") >= 0]
        assert len(segs) >= 8 and len(drops) >= 1
        unnamed = []
        for seg in segs:
            a = QAccessible.queryAccessibleInterface(seg)
            assert a.role() == QAccessible.Grouping
            if not a.text(QAccessible.Name):
                unnamed.append(seg.objectName() or str(_js(seg.property("model"))))
            if seg.property("currentIndex") >= 0:
                assert a.text(QAccessible.Description).endswith(", selected")
            radios = [QAccessible.queryAccessibleInterface(c) for c in _items(seg)
                      if c is not seg and QAccessible.queryAccessibleInterface(c) is not None
                      and QAccessible.queryAccessibleInterface(c).role() == QAccessible.RadioButton]
            assert len(radios) == len(_js(seg.property("model")))
            assert sum(1 for r in radios if r.state().checked) == (1 if seg.property("currentIndex") >= 0 else 0)
            assert all(r.text(QAccessible.Name) for r in radios)
        assert not unnamed, unnamed
        for d in drops:
            a = QAccessible.queryAccessibleInterface(d)
            assert a.role() == QAccessible.ComboBox and a.text(QAccessible.Name)
            assert a.text(QAccessible.Description) == _js(d.property("model"))[d.property("currentIndex")]["label"]
        swatches = [it for it in _items(win.contentItem()) if it.metaObject().indexOfProperty("rainbow") >= 0]
        assert swatches
        for s in swatches:
            a = QAccessible.queryAccessibleInterface(s)
            assert a.role() == QAccessible.RadioButton and a.text(QAccessible.Name)
            assert bool(a.state().checked) == bool(s.property("selected"))
    finally:
        win.close()


# ---------------------------------------------------------------- 12. the preview clock keeps time

def test_preview_clock_ticks_each_minute_only_while_the_window_shows(qml):
    from PySide6.QtCore import QDateTime, QObject
    win = _window(qml)
    try:
        win.show()
        _spin(300)
        preview = _find(win, "preview")
        tick = next(c for c in preview.findChildren(QObject) if c.objectName() == "previewClockTick")
        assert tick.property("running") and tick.property("repeat")
        old = QDateTime.fromString("2024-01-02T03:04:59.500", "yyyy-MM-ddTHH:mm:ss.zzz")
        preview.setProperty("now", old)
        _spin()
        assert "3:04" in preview.property("clock")
        assert tick.property("interval") <= 600          # due at the turn of the minute
        tick.triggered.emit()
        _spin()
        assert "3:04" not in preview.property("clock")
        win.hide()
        _spin()
        assert not tick.property("running")
        preview.setProperty("now", old)
        win.show()
        _spin(200)
        assert tick.property("running") and "3:04" not in preview.property("clock")
    finally:
        win.close()


def test_search_results_float_above_the_page(qml):
    """They were drawn under the preview, which cut the list off at the sidebar's edge."""
    win = _window(qml)
    try:
        assert _find(win, "sidebar").z() > _find(win, "pages").parentItem().z()
    finally:
        win.close()


def _damaged(tmp_path):
    p = tmp_path / "cfg/liquid-glass/settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"frost": 0.9, "scheme": "dark"')     # truncated, and no good copy
    return p


def test_damaged_settings_are_written_only_by_an_apply(qml, fake_env, tmp_path):
    """The defaults that stand in for a damaged file must never land in settings.json by
    anything but Apply: the watcher would then take them for the user's own."""
    p = _damaged(tmp_path)
    b = _backend(fake_env, tmp_path)
    b.setProperty("undoOnRemove", False)
    assert not p.exists()
    got = settings_mod.load_checked(p)
    assert not got.usable and got.settings.undo_on_remove is False, "removing the package still reads it"
    assert _backend(fake_env, tmp_path).property("undoOnRemove") is False, "the app shows it again"
    b.setProperty("frost", 0.5)
    b._test_engine.crash = True
    assert _apply(b) is None
    assert not p.exists() and not p.with_name("settings.json.bak").exists()
    assert not settings_mod.load_checked(p).usable
    b._test_engine.crash = False
    assert _apply(b) is not None
    assert _on_disk(tmp_path)["frost"] == 0.5 and _on_disk(tmp_path)["undo_on_remove"] is False
    assert settings_mod.load_checked(p).usable
    b.setProperty("undoOnRemove", True)                 # usable again: saved as before
    assert _on_disk(tmp_path)["undo_on_remove"] is True


def test_remove_only_during_an_apply_over_a_damaged_file(qml, fake_env, tmp_path):
    p = _damaged(tmp_path)
    b = _backend(fake_env, tmp_path)
    b.setProperty("frost", 0.6)
    b._test_engine.crash = True
    b.apply()
    b.setProperty("undoOnRemove", False)
    assert b.waitIdle()
    assert not p.exists() and settings_mod.load_checked(p).settings.undo_on_remove is False


def test_a_failed_apply_keeps_the_bak_the_last_applied_look(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    b.setProperty("frost", 0.2)
    _apply(b)
    b.setProperty("frost", 0.3)
    _apply(b)
    bak = tmp_path / "cfg/liquid-glass/settings.json.bak"
    assert json.loads(bak.read_text())["frost"] == 0.2
    b.setProperty("frost", 0.9)
    b._test_engine.crash = True
    assert _apply(b) is None
    assert _on_disk(tmp_path)["frost"] == 0.3
    assert json.loads(bak.read_text())["frost"] != 0.9, "the look that failed is no good copy"
