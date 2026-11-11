"""App redesign: a sidebar of pages built when first shown, one shared preview,
settings search, cards that carry their own captions, and a first-launch welcome
that is shown only once."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtGui")
pytest.importorskip("PySide6.QtQuick")
from PySide6.QtQuick import QQuickWindow  # noqa: F401 - the window comes back as a QQuickWindow

from fedoraglass.engine import Engine

PAGES = ["home", "colour", "glass", "windows", "motion", "pointer", "lock", "apps", "advanced", "about"]
_keep: list = []


def _backend_at(fake_env, settings: Path):
    from fedoraglass.gui.backend import Backend
    return Backend(env=fake_env, engine_factory=lambda: Engine(fake_env, []),
                   settings_path=settings, ui_dark=True, start=False)


# ---------------------------------------------------------------- first run

def test_first_run_only_until_the_welcome_is_dismissed(qml, fake_env, tmp_path):
    settings = tmp_path / "cfg/liquid-glass/settings.json"
    b = _backend_at(fake_env, settings)
    assert b.property("firstRun") is True
    b.dismissWelcome()
    assert (settings.parent / "welcome-seen").exists()
    assert _backend_at(fake_env, settings).property("firstRun") is False


def test_no_welcome_for_someone_who_already_saved_settings(qml, fake_env, tmp_path):
    settings = tmp_path / "cfg/liquid-glass/settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{}\n")
    assert _backend_at(fake_env, settings).property("firstRun") is False


def test_dismissing_never_writes_through_a_planted_symlink(qml, fake_env, tmp_path):
    settings = tmp_path / "cfg/liquid-glass/settings.json"
    settings.parent.mkdir(parents=True)
    victim = tmp_path / "victim"
    (settings.parent / "welcome-seen").symlink_to(victim)     # dangling: points nowhere yet
    b = _backend_at(fake_env, settings)
    b.dismissWelcome()
    assert not victim.exists()


# ---------------------------------------------------------------- the window

def _window(qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    from fedoraglass.gui import app as gui_app
    comp = QQmlComponent(qml, QUrl.fromLocalFile(str(Path(gui_app.QML_DIR) / "Main.qml")))
    win = comp.create()
    assert win is not None, comp.errorString()
    _keep.append(comp)
    return win


def _find(win, name):
    from PySide6.QtCore import QObject
    hit = win.findChild(QObject, name)
    todo = [win.contentItem()]
    while hit is None and todo:
        it = todo.pop()
        if it.objectName() == name:
            hit = it
        todo.extend(it.childItems())
    return hit


def _spin(ms=60):
    from PySide6.QtCore import QCoreApplication, QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QCoreApplication.processEvents()


def test_sidebar_and_ctrl_numbers_open_each_page(qml):
    """Every sidebar item opens its page, built the first time it shows, and Ctrl+1 to
    Ctrl+9 follow the sidebar's order."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    win = _window(qml)
    try:
        win.setWidth(1316)
        win.setHeight(856)
        win.show()
        win.requestActivate()
        _spin(300)
        ids = [p["id"] for p in win.property("pageList").toVariant()]
        assert ids == PAGES
        assert win.property("page") == "home"
        assert _find(win, "glassPage") is None, "pages are built only when first shown"
        for pid in ids:
            _find(win, "nav_" + pid).clicked.emit()
            _spin(80)
            assert win.property("page") == pid
            page = _find(win, pid + "Page")
            assert page is not None and page.property("visible"), pid
        for n, pid in enumerate(ids[:9], start=1):
            QTest.keyClick(win, Qt.Key(Qt.Key_0 + n), Qt.ControlModifier)
            _spin(40)
            assert win.property("page") == pid
    finally:
        win.close()


def test_the_one_preview_follows_the_page(qml):
    """One preview for the whole app: it moves into the slot of each page that has one."""
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        preview = _find(win, "preview")
        for pid in ("home", "colour", "glass", "lock", "advanced"):
            win.setProperty("page", pid)
            _spin(80)
            if pid == "lock":       # the lock page shows its own lock-screen preview
                continue
            slot = _find(win, pid + "PreviewSlot")
            assert slot is not None, pid
            pane = _find(win, "previewPane")
            assert pane.parentItem() == slot, pid
            assert pane.isAncestorOf(preview), pid
        assert len([1 for _ in _all(win, "preview")]) == 1
    finally:
        win.close()


def _all(win, name):
    todo = [win.contentItem()]
    while todo:
        it = todo.pop()
        if it.objectName() == name:
            yield it
        todo.extend(it.childItems())


def test_every_card_title_carries_its_own_caption(qml):
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        win.setProperty("page", "glass")
        _spin(100)
        status = _find(win, "glassStatus")
        assert status is not None and "Apply" in status.property("text")
    finally:
        win.close()


def test_welcome_sheet_picks_a_look_and_marks_itself_seen(qml):
    win = _window(qml)
    b = _find(win, "welcomeSheet")
    try:
        win.show()
        _spin()
        win.setProperty("startSheet", "welcome")
        _spin(400)
        assert b.property("opened")
        frosted = _find(win, "welcomeLookFrosted")
        assert frosted is not None
        frosted.clicked.emit()
        _spin()
        probe = _probe_backend(qml)
        assert probe.property("activePreset") == "Frosted"
        _find(win, "welcomeStart").clicked.emit()
        _spin(400)
        assert not b.property("opened")
    finally:
        _probe_backend(qml).discardChanges()
        win.close()


def _probe_backend(qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent
    probe = QQmlComponent(qml)
    probe.setData(b"import QtQuick\nimport FedoraGlass.Core\nQtObject { property var b: Backend }", QUrl())
    obj = probe.create()
    _keep.append((probe, obj))
    return obj.property("b")


def test_every_search_result_lands_on_a_real_control(qml):
    """Each entry in the search index names a control that exists on its page, so a
    search never opens a page and then finds nothing to light up."""
    import re
    from fedoraglass.gui import app as gui_app
    index = (Path(gui_app.QML_DIR) / "FedoraGlass" / "searchindex.js").read_text()
    entries = re.findall(r'page: "(\w+)", name: "(\w+)"', index)
    assert len(entries) >= 50
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        for page in PAGES:
            win.setProperty("page", page)
            _spin(60)
        missing = []
        for page, name in entries:
            root = _find(win, page + "Page")
            hit = None
            todo = [root] if root is not None else []
            while todo and hit is None:
                it = todo.pop()
                if it.objectName() == name:
                    hit = it
                todo.extend(it.childItems())
            if hit is None:
                missing.append(f"{page}/{name}")
        assert not missing, f"search names with no control on their page: {missing}"
    finally:
        win.close()


# ---------------------------------------------------------------- a preview big enough to judge

def _open_page(win, pid, w, h):
    win.setWidth(w)
    win.setHeight(h)
    win.show()
    _spin(150)
    win.setProperty("page", pid)
    _spin(400)
    return _find(win, "previewPane"), _find(win, "preview")


def _settings_page(item):
    """The SettingsPage an item sits in (the side column scrolls, so a few levels up)."""
    while item is not None and item.property("stacked") is None:
        item = item.parentItem()
    assert item is not None
    return item


def test_the_preview_takes_half_the_page_and_shows_glass_close_up(qml):
    """Beside the cards the preview gets about half the page, and close up it draws the
    desktop at about half real size (it was a fifth), so blur, corners and rims read."""
    win = _window(qml)
    try:
        pane, preview = _open_page(win, "glass", 1316, 856)
        assert _settings_page(_find(win, "glassPreviewSlot")).property("stacked") is False
        assert pane.width() >= 440 and pane.property("viewH") >= 360
        assert pane.property("closeUp") is True
        assert preview.property("s") >= 0.5
        assert preview.width() > pane.width()          # a crop of the desktop, not all of it
        # Whole screen: back to fitting the pane, nothing to pan along the long side.
        pane.setProperty("closeUp", False)
        _spin(60)
        assert preview.property("s") < 0.5
    finally:
        win.close()


def test_a_small_window_puts_the_preview_above_the_cards(qml):
    win = _window(qml)
    try:
        pane, preview = _open_page(win, "glass", 1036, 716)
        slot = _find(win, "glassPreviewSlot")
        page = _settings_page(slot)
        assert page.property("stacked") is True
        assert pane.width() >= 560                    # the full page width, not a side column
        scroller = _find(win, "glassScroller")
        top = pane.mapToItem(page, 0, 0).y() + pane.height()
        assert scroller.y() >= top                    # the cards start under it
        assert scroller.height() >= 200               # and keep room to work in
        assert preview.property("s") >= 0.3
    finally:
        win.close()


def test_the_view_follows_the_scene_and_stays_on_the_desktop(qml):
    win = _window(qml)
    try:
        pane, preview = _open_page(win, "glass", 1316, 856)
        # With Dash to Panel at the bottom the close-up sits on the bottom edge.
        if not preview.property("topBar"):
            assert abs(pane.property("camY") - (preview.height() - pane.property("viewH"))) < 1.5
        # Dragging far past an edge stops at the edge.
        pane.setProperty("panX", -100000)
        pane.setProperty("panY", 100000)
        _spin(30)
        assert pane.property("camX") == 0
        assert abs(pane.property("camY") - (preview.height() - pane.property("viewH"))) < 1.5
        # A new scene re-centres on what it shows; the overview always shows all of it.
        preview.setProperty("scene", "overview")
        _spin(60)
        assert pane.property("panX") == 0
        assert pane.property("zoomed") is False
    finally:
        win.close()


def test_clicking_a_part_on_the_zoomed_preview_picks_that_part(qml):
    """The Advanced page picks the part under the pointer: through the close-up's
    offset, not as if the preview still started at the pane's corner."""
    from PySide6.QtCore import Q_ARG, Q_RETURN_ARG, QMetaObject, QPoint, Qt
    from PySide6.QtTest import QTest
    win = _window(qml)
    try:
        pane, preview = _open_page(win, "advanced", 1316, 856)
        _spin(500)
        assert pane.property("outlinedPart") == "panel"
        term = QMetaObject.invokeMethod(preview, "partItem", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", "terminal"))
        k = preview.property("s")
        # Pan so the terminal's middle sits in the middle of the view, well off the corner.
        want = term.x() + 100 * k - pane.property("viewW") / 2
        pane.setProperty("panX", want - (pane.property("lookAt").x() * k - pane.property("viewW") / 2))
        _spin(900)                                   # past the glide
        assert pane.property("camX") > 100           # the view is really shifted
        assert term is not None and term.isVisible()
        p = term.mapToItem(win.contentItem(), 100 * k, 270 * k)
        inside = term.mapToItem(pane, 100 * k, 270 * k)
        assert 0 < inside.x() < pane.width() and 0 < inside.y() < pane.property("viewH")
        QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, QPoint(int(p.x()), int(p.y())))
        _spin(100)
        assert pane.property("outlinedPart") == "terminal"
    finally:
        win.close()


def test_a_short_window_scrolls_the_home_side_cards_instead_of_spilling(qml):
    """At the smallest window size (and more so with a notice at the bottom, such as
    "Glass is paused") Home's right-hand cards scroll in their own room instead of
    running under the notice and the Apply bar."""
    win = _window(qml)
    try:
        _open_page(win, "home", 1036, 560)
        side = _find(win, "homeSideScroller")
        page = _settings_page(side)
        assert side.property("overflows") is True
        assert side.y() + side.height() <= page.height() + 0.5
        assert side.property("contentHeight") > side.height()
        # A tall window: no scrolling, nothing clipped.
        _open_page(win, "home", 1316, 1000)
        assert side.property("overflows") is False and side.clip() is False
    finally:
        win.close()
