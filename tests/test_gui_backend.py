"""The customizer's backend: property round-trips, live tokens and the worker flows.

Runs headless (QT_QPA_PLATFORM=offscreen) against fake targets and a temp home,
so nothing on the machine is touched.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtGui = pytest.importorskip("PySide6.QtGui")

from liquidglass import settings as settings_mod  # noqa: E402
from liquidglass.env import Env, RunResult  # noqa: E402
from liquidglass.settings import PRESETS  # noqa: E402
from liquidglass.targets.base import Detection, Target, WriteFile  # noqa: E402


@pytest.fixture(scope="module")
def app():
    inst = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])
    yield inst


class FakeEnv(Env):
    """No gsettings, no commands: a dark desktop with a blue accent."""

    def run(self, argv, timeout=30):
        if argv[:1] == ["gsettings"] and "get" in argv:
            key = argv[-1]
            return RunResult(0, {"color-scheme": "'prefer-dark'", "accent-color": "'blue'"}.get(key, ""), "")
        return RunResult(1, "", "not available in tests")

    def which(self, name):
        return None


class FakeTarget(Target):
    def __init__(self, tid, group, available=True, path=None):
        super().__init__(id=tid, name=tid.title(), group=group, summary=f"{tid} summary",
                         notes=[f"{tid} note"])
        self._available = available
        self._path = path

    def detect(self, env):
        return Detection(self._available, "" if self._available else f"{self.name} is not installed")

    def plan(self, ctx):
        return [WriteFile(self._path, f"chrome {ctx.tokens.chrome.css}\n")]


class FakeEngine:
    def __init__(self, env, targets):
        from liquidglass.engine import Engine
        self._real = Engine(env, targets)
        self.env = env
        self.targets = targets

    def __getattr__(self, name):
        return getattr(self._real, name)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    return tmp_path


@pytest.fixture
def make_backend(app, home):
    from liquidglass.gui.backend import Backend

    def make(targets=None, start=False):
        env = FakeEnv(home=home)
        targets = targets if targets is not None else [
            FakeTarget("alpha", "Desktop", path=home / "out/alpha.css"),
            FakeTarget("beta", "Apps", path=home / "out/beta.css"),
            FakeTarget("gamma", "Apps", available=False, path=home / "out/gamma.css"),
        ]
        b = Backend(env=env, engine_factory=lambda: FakeEngine(env, targets),
                    settings_path=home / "config/liquid-glass/settings.json", ui_dark=True, start=start)
        return b
    return make


def test_property_round_trips(make_backend):
    b = make_backend()
    cases = {"frost": 0.8, "scheme": "light", "accent": "purple", "tint": "#112233",
             "tintStrength": 0.4, "radius": 24, "highlight": 0.2, "opacity": 0.6, "blur": 30,
             "reduceTransparency": True, "panelStyle": "docked", "panelMargin": 12,
             "blurAppWindows": False, "terminalOpacity": 0.5, "refraction": 0.2, "dispersion": 0.9,
             "vibrancy": 0.1, "glassPanel": False, "glassMenus": False, "glassOverview": False,
             "glassSeeWindows": False}
    for name, value in cases.items():
        b.setProperty(name, value)
        got = b.property(name)
        assert got == pytest.approx(value) if isinstance(value, float) else got == value, name
    s = b.settings()
    assert (s.frost, s.scheme, s.accent, s.radius, s.panel_style) == (0.8, "light", "purple", 24, "docked")


def test_overrides_use_minus_one_for_auto(make_backend):
    b = make_backend()
    assert b.property("opacity") == -1 and b.property("blur") == -1 and b.property("terminalOpacity") == -1
    b.setProperty("opacity", 0.5)
    assert b.settings().opacity == 0.5
    b.setProperty("opacity", -1)
    assert b.settings().opacity is None
    auto = b.property("autoValues")
    assert 0 < auto["opacity"] < 1 and auto["blur"] > 0


def test_invalid_values_are_normalized(make_backend):
    b = make_backend()
    b.setProperty("frost", 3.0)
    assert b.property("frost") == 1.0
    b.setProperty("radius", 99)
    assert b.property("radius") == 32
    b.setProperty("accent", "not-a-colour")
    assert b.property("accent") == "system"


def test_tokens_follow_frost(make_backend):
    b = make_backend()
    seen = []
    b.tokensChanged.connect(lambda: seen.append(True))
    b.setProperty("frost", 0.0)
    liquid = b.property("tokens")
    b.setProperty("frost", 1.0)
    frosted = b.property("tokens")
    assert seen, "tokensChanged must fire while the slider moves"
    assert isinstance(liquid["chrome"], QtGui.QColor)
    assert frosted["chrome"].alphaF() > liquid["chrome"].alphaF()
    assert frosted["blur_radius"] > liquid["blur_radius"]
    assert frosted["highlight"].alphaF() < liquid["highlight"].alphaF()
    assert frosted["frost"] == 1.0


def test_preview_scheme_switch(make_backend):
    b = make_backend()
    assert b.property("previewDark") is True
    assert b.property("tokens")["dark"] is True
    b.setProperty("previewDark", False)
    assert b.property("tokens")["dark"] is False
    assert b.property("lightTokens")["fg"] == b.property("tokens")["fg"]
    b.setProperty("scheme", "dark")          # choosing a style moves the preview with it
    assert b.property("previewDark") is True


def test_presets_and_dirty(make_backend):
    b = make_backend()
    assert b.property("dirty") is False
    assert b.property("activePreset") == "Balanced"
    for name in PRESETS:
        b.applyPreset(name)
        assert b.property("activePreset") == name
    assert b.property("dirty") is True
    b.discardChanges()
    assert b.property("dirty") is False


def test_targets_grouped_with_honest_state(make_backend):
    b = make_backend(start=True)
    assert b.waitIdle()
    assert b.property("targetsReady") is True
    groups = b.property("targets")
    assert [g["group"] for g in groups] == ["Desktop", "Apps"]
    items = {t["id"]: t for g in groups for t in g["items"]}
    assert items["gamma"]["available"] is False and "not installed" in items["gamma"]["detail"]
    assert items["alpha"]["notes"] == ["alpha note"]
    assert b.property("activeTargetCount") == 2
    b.setTargetEnabled("beta", False)
    assert b.settings().targets["beta"] is False
    assert b.property("activeTargetCount") == 1


def test_plan_apply_revert(make_backend, home):
    b = make_backend(start=True)
    assert b.waitIdle()
    b.setProperty("frost", 0.9)

    plans = []
    b.planReady.connect(plans.append)
    b.requestPlan()
    assert b.waitIdle()
    assert plans and {p["id"] for p in plans[0]} == {"alpha", "beta"}
    assert plans[0][0]["actions"][0]["text"].startswith("write ~/out/")
    assert not (home / "out/alpha.css").exists(), "Show changes must not change anything"

    results = []
    b.applyFinished.connect(results.append)
    b.apply()
    assert b.property("busy") is True
    assert b.waitIdle()
    assert b.property("busy") is False
    status = {r["id"]: r["status"] for r in results[0]}
    assert status == {"alpha": "applied", "beta": "applied", "gamma": "skipped"}
    assert (home / "out/alpha.css").is_file()
    saved = settings_mod.load(home / "config/liquid-glass/settings.json")
    assert saved.frost == pytest.approx(0.9)
    assert b.property("dirty") is False
    assert b.property("hasBackup") is True

    problems = []
    b.revertFinished.connect(problems.append)
    b.revert()
    assert b.waitIdle()
    assert problems == [[]]
    assert not (home / "out/alpha.css").exists()
    assert b.property("hasBackup") is False


def test_qml_loads(make_backend, home):
    """The whole window compiles and every component resolves."""
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent, QQmlEngine, qmlRegisterSingletonInstance

    from liquidglass.gui import app as gui_app
    from liquidglass.gui.backend import Backend
    b = make_backend()
    qmlRegisterSingletonInstance(Backend, "LiquidGlass.Core", 1, 0, "Backend", b)
    engine = QQmlEngine()
    engine.addImportPath(str(gui_app.QML_DIR))
    engine.rootContext().setContextProperty("appIconUrl", QUrl())
    comp = QQmlComponent(engine, QUrl.fromLocalFile(str(Path(gui_app.QML_DIR) / "Main.qml")))
    assert comp.status() == QQmlComponent.Status.Ready, comp.errorString()


def test_popups_compile_on_glass(make_backend, home):
    """A tooltip, a dropdown and the colour picker (all on PopupGlass) compile."""
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent, QQmlEngine, qmlRegisterSingletonInstance

    from liquidglass.gui import app as gui_app
    from liquidglass.gui.backend import Backend
    b = make_backend()
    qmlRegisterSingletonInstance(Backend, "LiquidGlass.Core", 1, 0, "Backend", b)
    engine = QQmlEngine()
    engine.addImportPath(str(gui_app.QML_DIR))
    comp = QQmlComponent(engine)
    comp.setData(b"""
import QtQuick
import LiquidGlass
Item {
    width: 400; height: 300
    LgDropdown { model: [{ value: "a", label: "A", tip: "first" }]; value: "a"; tip: "pick" }
    LgToolTip { shown: true; text: "hello" }
    ColorPicker { }
}
""", QUrl.fromLocalFile(str(Path(gui_app.QML_DIR) / "popups.qml")))
    assert comp.status() == QQmlComponent.Status.Ready, comp.errorString()


def test_missing_icon_is_transparent_not_black(app):
    from PySide6.QtCore import QSize
    from liquidglass.gui.icons import IconProvider
    pm = IconProvider().requestPixmap("no-such-icon-xyz", QSize(), QSize(16, 16))
    assert pm.toImage().pixelColor(0, 0).alpha() == 0


def test_apply_waits_for_the_startup_check_instead_of_being_dropped(make_backend, home):
    b = make_backend(start=True)          # the target check is running in the background
    b.setProperty("frost", 0.7)
    results = []
    b.applyFinished.connect(results.append)
    b.apply()
    assert b.waitIdle()
    assert results, "Apply was silently dropped while the target check ran"
    assert settings_mod.load(home / "config/liquid-glass/settings.json").frost == pytest.approx(0.7)


def test_live_glass_follows_sliders_and_falls_back_on_quit(make_backend, home):
    import json
    b = make_backend()
    path = home / "config/liquid-glass/shell-glass.json"
    b.setProperty("refraction", 0.9)
    b._live_timer.stop()
    assert not path.exists(), "nothing is written while the extension isn't running"
    b._glass_live = True
    b.setProperty("refraction", 0.0)
    b._write_live_glass(b.settings())
    assert json.loads(path.read_text())["look"]["bend"] == 0
    b.shutdown()                           # unapplied: the desktop goes back to the saved look
    assert json.loads(path.read_text())["look"]["bend"] > 0


def test_part_overrides(make_backend):
    b = make_backend()
    seen = []
    b.settingsChanged.connect(lambda: seen.append(1))
    assert b.hasPart("panel", "radius") is False
    assert b.partValue("panel", "radius") == b.property("radius")              # follows the global value
    assert b.partValue("panel", "reflections") == pytest.approx(b.property("highlight"))
    b.setPart("panel", "radius", 4)
    b.setPart("panel", "tint", "#ff0000")
    b.setPart("nonsense", "radius", 4)                                          # ignored
    b.setPart("panel", "bogus", 4)                                              # ignored
    assert b.hasPart("panel", "radius") and b.partValue("panel", "radius") == 4
    assert b.property("parts") == {"panel": {"radius": 4, "tint": "#ff0000"}}
    assert len(seen) == 2
    assert b.property("tokens")["panel_radius"] == 4 and b.property("tokens")["menu_radius"] == 18
    assert b.property("tokens")["parts"]["panel"]["radius"] == 4
    assert b.property("dirty") is True
    b.clearPart("panel", "radius")
    assert b.hasPart("panel", "radius") is False and b.hasPart("panel", "tint")
    b.resetPart("panel")
    assert b.property("parts") == {}
    assert b.property("dirty") is False


def test_bleed_property(make_backend):
    b = make_backend()
    assert b.property("bleed") == pytest.approx(0.6)
    b.setProperty("bleed", 0.2)
    assert b.settings().bleed == pytest.approx(0.2)
    assert b.property("tokens")["bleed"] < 0.2 + 1e-9


def test_header_bar_properties(make_backend):
    b = make_backend()
    assert b.property("headerHeight") == 47 and b.property("headerOpacity") == -1
    b.setProperty("headerHeight", 40.6)
    b.setProperty("headerOpacity", 0.3)
    s = b.settings()
    assert (s.header_height, s.header_opacity) == (41, pytest.approx(0.3))
    b.setProperty("headerHeight", 500)
    b.setProperty("headerOpacity", -1)
    s = b.settings()
    assert (s.header_height, s.header_opacity) == (64, None)


def test_restart_files_only_after_header_change_and_only_on_click(make_backend, monkeypatch):
    from liquidglass.gui import backend as be

    started = []
    monkeypatch.setattr(be.QProcess, "startDetached", lambda prog, args: started.append([prog, *args]) or True)
    b = make_backend(start=True)
    assert b.waitIdle()
    b.setProperty("frost", 0.8)
    b.apply()
    assert b.waitIdle()
    assert b.property("headerNote") == ""          # nothing about header bars changed

    b.setProperty("headerHeight", 40)
    b.apply()
    assert b.waitIdle()
    assert b.property("headerNote") == "pending"
    assert started == [], "Apply must never quit Files by itself"

    assert b.restartFiles() is False                # Files isn't installed in the fake env
    monkeypatch.setattr(b._env, "which", lambda name: "/usr/bin/nautilus" if name == "nautilus" else None)
    assert b.restartFiles() is True
    assert started == [["/usr/bin/nautilus", "-q"]]   # fixed command, never Terminal
    assert b.property("headerNote") == "restarted"


def test_terminal_palette_is_reported_not_changed(make_backend, home, monkeypatch):
    from liquidglass.targets.base import Detection
    from liquidglass.targets.terminal import Ptyxis

    gs = {("org.gnome.Ptyxis", None): {"profile-uuids": "['aaaabbbbcccc']", "default-profile-uuid": "'aaaabbbbcccc'"},
          ("org.gnome.Ptyxis.Profile", "/org/gnome/Ptyxis/Profiles/aaaabbbbcccc/"): {"palette": "'gooey'"}}
    monkeypatch.setattr(Ptyxis, "detect", lambda self, env: Detection(True))
    monkeypatch.setattr(FakeEnv, "gsettings_get", lambda self, schema, key, path=None: gs.get((schema, path), {}).get(key))
    b = make_backend(targets=[Ptyxis()], start=True)
    assert b.waitIdle()
    assert b.property("terminalPalette") == "gooey"
    assert b.property("liquidGlassPalette") == "Liquid Glass"
    assert b.property("terminalColors") is False
    b.setProperty("terminalColors", True)
    assert b.settings().terminal_colors is True


def test_motion_picker(make_backend):
    b = make_backend()
    assert b.motionIsDefault and b.motion["open"]["preset"] == "spring"
    assert "genie" in b.motionPresets["minimize"] and "bounce" not in b.motionPresets["close"]
    b.setMotion("open", "preset", "jelly")
    b.setMotion("open", "intensity", 0.8)
    b.setMotion("open", "speed", 5.0)          # clamped
    b.setMotion("close", "preset", "bounce")   # not offered for close: ignored
    b.setMotion("bogus", "preset", "spring")
    assert b.motion["open"] == {"preset": "jelly", "intensity": 0.8, "speed": 2.0}
    assert b.motion["close"]["preset"] == "scalefade"
    assert b.dirty and not b.motionIsDefault
    b.resetMotion()
    assert b.motionIsDefault


def test_replaced_files_show_a_reapply_note(make_backend, home):
    """A theme update relinking a file Apply wrote is reported once, in plain words; the
    app never fights it in the background."""
    b = make_backend(start=True)
    assert b.waitIdle()
    b.apply()
    assert b.waitIdle()
    assert b.property("lostNote") == ""
    out = home / "out/alpha.css"
    out.unlink()
    out.symlink_to(home / "elsewhere.css")
    b.refreshTargets()
    assert b.waitIdle()
    assert b.property("lostNote") == "Another app replaced the Liquid Glass look for Alpha. Apply again to bring it back."
    assert out.is_symlink()                     # only reported, nothing rewritten
    b.apply()
    assert b.waitIdle()
    assert b.property("lostNote") == ""
