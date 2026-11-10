"""The Apps page lists what this PC has first; parts that are not installed fold into one
quiet "Not installed here (N)" card, and the author's own apps only show where installed."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtGui")

from fedoraglass.gui.backend import _missing_text  # noqa: E402
from fedoraglass.targets import myapps  # noqa: E402
from fedoraglass.targets import shell as ts  # noqa: E402

from test_gui_backend import FakeTarget, make_backend, home, app  # noqa: E402,F401


class MyFake(FakeTarget):
    hide_when_missing = True


def _stock(home):
    return [
        FakeTarget("shell", "Desktop", path=home / "a"),
        FakeTarget("flatpak", "Desktop", available=False, path=home / "b"),
        FakeTarget("dtp", "Panel", available=False, path=home / "c"),
        FakeTarget("discord", "Apps", available=False, path=home / "d"),
        FakeTarget("libreoffice", "Apps", path=home / "e"),
        MyFake("clipperino", "My apps", available=False, path=home / "f"),
        MyFake("wheelguard", "My apps", available=True, path=home / "g"),
    ]


def test_my_apps_are_marked_to_hide_when_missing():
    assert all(t.hide_when_missing for t in myapps.TARGETS)
    assert not getattr(ts.DashToPanel(), "hide_when_missing", False)


def test_backend_splits_installed_from_not_installed(make_backend, home):
    b = make_backend(_stock(home), start=True)
    assert b.waitIdle()
    installed = b.property("installedTargets")
    assert [g["group"] for g in installed] == ["Desktop", "Apps", "My apps"]   # no empty Panel group
    assert {t["id"] for g in installed for t in g["items"]} == {"shell", "libreoffice", "wheelguard"}
    assert all(t["available"] for g in installed for t in g["items"])
    missing = b.property("missingTargets")
    assert [t["id"] for t in missing] == ["flatpak", "dtp", "discord"]   # group order, no my-apps
    assert all(t["reason"] == "Not installed" and t["install"] == "" for t in missing)
    # The full list hides a missing own app too, and the count on Apply is unchanged.
    every = {t["id"] for g in b.property("targets") for t in g["items"]}
    assert "clipperino" not in every and "wheelguard" in every
    assert b.property("activeTargetCount") == 3


def test_missing_text_is_calm_and_keeps_one_command_installs():
    def mk(name, detail):
        return _missing_text({"name": name, "available": False, "detail": detail})
    assert mk("Discord", "Discord is not installed") == {"reason": "Not installed", "install": ""}
    assert mk("Dash to Panel", "Dash to Panel is not installed (gnome-shell-extension-dash-to-panel)")["reason"] \
        == "Not installed (gnome-shell-extension-dash-to-panel)"
    assert mk("Brave and Helium", "Brave and Helium are not installed")["reason"] == "Brave and Helium are not installed"
    k = mk("Qt apps (Kvantum)", "Install Kvantum: sudo dnf install kvantum")
    assert k == {"reason": "", "install": "Install Kvantum: sudo dnf install kvantum"}
    assert mk("X", "Install Kvantum (the kvantum package)")["install"] == ""
    assert _missing_text({"name": "X", "available": True, "detail": "found"}) == {"reason": "", "install": ""}


def test_user_themes_missing_gives_the_install_command(tmp_path):
    from fedoraglass.env import Env
    det = ts.GnomeShell().detect(Env(home=tmp_path))
    if det.available:
        pytest.skip("User Themes is installed system-wide here")
    assert det.detail == "Install the User Themes extension: sudo dnf install gnome-shell-extension-user-theme"


def test_glass_summary_names_no_optional_extension():
    s = ts.GlassEffects().summary
    for name in ("ArcMenu", "Spawn", "Dash to Panel", "Dash to Dock"):
        assert name not in s


# ---- QML ------------------------------------------------------------------------------
def _spin(ms=60):
    from PySide6.QtCore import QCoreApplication, QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QCoreApplication.processEvents()


def _find(root, name):
    from PySide6.QtCore import QObject
    return root.findChild(QObject, name)


def _item(t, available, group, hide=False):
    return {"id": t, "name": t.title(), "group": group, "summary": f"{t} summary", "notes": [],
            "available": available, "detail": "" if available else f"{t.title()} is not installed",
            "hideWhenMissing": hide}


@pytest.fixture
def page(qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent
    probe = QQmlComponent(qml)
    probe.setData(b"import QtQuick\nimport FedoraGlass.Core\nQtObject { property var b: Backend }", QUrl())
    holder = probe.create()
    b = holder.property("b")
    saved = (b._targets, b._targets_ready)
    b._targets = [_item("gtk4", True, "Desktop"), _item("flatpak", False, "Desktop"),
                  _item("dtp", False, "Panel"), _item("discord", False, "Apps"),
                  _item("mine", False, "My apps", hide=True)]
    b._targets_ready = True
    b.targetsChanged.emit()
    comp = QQmlComponent(qml)
    comp.setData(b"import QtQuick\nimport FedoraGlass\nAppsPage { width: 900; height: 600 }", QUrl())
    root = comp.create()
    assert root is not None, comp.errorString()
    _spin()
    yield b, root
    b._targets, b._targets_ready = saved
    b.targetsChanged.emit()
    root.deleteLater()


def test_folded_row_counts_and_opens(page):
    b, root = page
    head = _find(root, "notInstalled")
    rows = _find(root, "notInstalledRows")
    assert head is not None and head.property("visible")
    assert _find(root, "notInstalledTitle").property("text") == "Not installed here (3)"
    assert root.property("missingOpen") is False and rows.property("height") == 0
    from PySide6.QtCore import QMetaObject
    QMetaObject.invokeMethod(head, "clicked")
    _spin(700)
    assert root.property("missingOpen") is True and rows.property("height") > 0
    assert not _find(root, "appsEmpty").property("visible")
    # "Check again" keeps the card open.
    b.targetsChanged.emit()
    _spin()
    assert root.property("missingOpen") is True


def test_empty_state_when_nothing_is_installed(page):
    b, root = page
    b._targets = [_item("discord", False, "Apps"), _item("mine", False, "My apps", hide=True)]
    b.targetsChanged.emit()
    _spin()
    assert _find(root, "appsEmpty").property("visible")
    assert _find(root, "notInstalledTitle").property("text") == "Not installed here (1)"
    b._targets = []
    b.targetsChanged.emit()
    _spin()
    assert _find(root, "appsEmpty").property("visible")
    assert not _find(root, "notInstalledCard").property("visible")

