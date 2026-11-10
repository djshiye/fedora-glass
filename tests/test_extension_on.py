"""One rule for "this desktop uses that extension", in Apply and in the app: installed,
switched on in GNOME's settings, not switched off, and extensions not off altogether.
Dash to Panel installed but switched off is stock GNOME."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fedoraglass.engine import Engine
from fedoraglass.settings import Settings
from fedoraglass.targets import shell as ts
from fedoraglass.targets.base import WriteFile
from test_shell import install, switch_on

NODE = shutil.which("node")
ROOT = Path(__file__).resolve().parent.parent
DTP = "org.gnome.shell.extensions.dash-to-panel"
SHELL = ("org.gnome.shell", None)


def _desktop_cfg(env, settings=None):
    ctx = Engine(env, ts.TARGETS).context(settings or Settings())
    w = next(a for a in ts.GlassEffects().plan(ctx) if isinstance(a, WriteFile) and a.path.name == "shell-glass.json")
    return json.loads(w.content)["desktop"]


def test_the_rule(fake_env):
    env = fake_env
    assert not env.extension_on(ts.DASH_TO_PANEL)                     # not installed
    env.gs[SHELL] = {"enabled-extensions": f"['{ts.DASH_TO_PANEL}']"}
    assert not env.extension_on(ts.DASH_TO_PANEL)                     # a removed extension's name left on the list
    install(env, ts.DASH_TO_PANEL, on=False)
    assert env.extension_on(ts.DASH_TO_PANEL)
    env.gs[SHELL]["disabled-extensions"] = f"['{ts.DASH_TO_PANEL}']"
    assert not env.extension_on(ts.DASH_TO_PANEL), "GNOME's switched-off list wins"
    env.gs[SHELL]["disabled-extensions"] = "@as []"
    env.gs[SHELL]["disable-user-extensions"] = "true"
    assert not env.extension_on(ts.DASH_TO_PANEL), "extensions switched off altogether"
    env.gs[SHELL] = {"enabled-extensions": "@as []"}
    assert not env.extension_on(ts.DASH_TO_PANEL)                     # installed, switched off


def test_dash_to_panel_installed_but_off_is_stock_gnome(fake_env):
    install(fake_env, ts.USER_THEME, ts.DASH_TO_PANEL, on=False)
    fake_env.gs[(DTP, None)] = {"hide-overview-on-startup": "false", "trans-use-custom-bg": "false"}
    assert _desktop_cfg(fake_env)["startOnDesktop"] is False, "the overview opens at login, as on stock GNOME"
    got = {r.target: r for r in Engine(fake_env, ts.TARGETS).apply(Settings())}
    assert got["dash-to-panel"].status == "skipped"
    assert got["dash-to-panel"].message == "Dash to Panel is installed but switched off"
    assert fake_env.gs[(DTP, None)] == {"hide-overview-on-startup": "false", "trans-use-custom-bg": "false"}, \
        "Dash to Panel's settings were changed while it is off"


def test_dash_to_panel_on_behaves_as_before(fake_env):
    """Dino's desktop: Dash to Panel on, so GNOME starts on the desktop and its option follows."""
    install(fake_env, ts.USER_THEME, ts.DASH_TO_PANEL)
    fake_env.gs[(DTP, None)] = {"hide-overview-on-startup": "false", "trans-use-custom-bg": "false"}
    assert _desktop_cfg(fake_env)["startOnDesktop"] is True
    got = {r.target: r for r in Engine(fake_env, ts.TARGETS).apply(Settings())}
    assert got["dash-to-panel"].status == "applied"
    assert fake_env.gs[(DTP, None)]["hide-overview-on-startup"] == "true"
    assert fake_env.gs[(DTP, None)]["trans-use-custom-bg"] == "true"


def test_dash_to_panel_restarting_still_counts(fake_env):
    """While GNOME Shell restarts its extensions Dash to Panel is briefly not running; its
    settings still say on, so nothing changes."""
    install(fake_env, ts.USER_THEME, ts.DASH_TO_PANEL)
    fake_env.ext_info[ts.DASH_TO_PANEL] = ("7.0", "")      # switching off for the restart
    assert _desktop_cfg(fake_env)["startOnDesktop"] is True
    assert ts.DashToPanel().detect(fake_env).available


@pytest.mark.parametrize("target, uuid, label", [(ts.ArcMenu(), ts.ARCMENU, "ArcMenu"), (ts.Spawn(), ts.SPAWN, "Spawn")])
def test_start_menus_follow_the_same_rule(fake_env, target, uuid, label):
    install(fake_env, uuid, on=False)
    d = target.detect(fake_env)
    assert not d.available and d.detail == f"{label} is installed but switched off"
    switch_on(fake_env, uuid)
    assert target.detect(fake_env).available


def test_just_perfection_installed_but_off_is_left_alone(fake_env):
    jp = "org.gnome.shell.extensions.just-perfection"
    install(fake_env, ts.JUST_PERFECTION, on=False)
    fake_env.gs[(jp, None)] = {"startup-status": "1"}
    Engine(fake_env, [ts.GlassEffects()]).apply(Settings(start_on_desktop=True))
    assert fake_env.gs[(jp, None)]["startup-status"] == "1"


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_the_extension_does_not_trust_a_removed_extensions_name():
    r = subprocess.run([NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/desktop-stale-extension.test.mjs"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
