"""The glass login screen in the app: what it sends to fedora-glass-login, how it reads the
helper's answers, and the Login screen section of the Lock and login page.

The helper is a fake script that keeps to login-contract.md (status JSON, `on` with the
values as one argument and the picture on stdin, `off`), and pkexec a fake that runs it,
so the flows run for real without root and without a login screen."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtGui = pytest.importorskip("PySide6.QtGui")
pytest.importorskip("PySide6.QtQuick")
from PySide6.QtQuick import QQuickWindow  # noqa: E402,F401 - the window comes back as a QQuickWindow

from fedoraglass.gui import loginlook  # noqa: E402
from fedoraglass.settings import Settings  # noqa: E402
from tests.test_gui_polish import _backend as _qml_backend, _find, _goto, _spin, _window  # noqa: E402

_keep: list = []

# The fake helper: answers `status` from status.json, logs every call (argv and what came
# on stdin), and does what `on` and `off` do to the state. The exit codes can be set.
FAKE_HELPER = r'''#!{python} -I
import hashlib, json, os, sys
d = os.environ["FAKE_GL_DIR"]
def path(n): return os.path.join(d, n)
def read(n, default):
    try:
        with open(path(n)) as f: return json.load(f)
    except OSError: return default
status = read("status.json", {"version": 1, "available": True, "why": "", "state": "off", "stopped": "",
                              "values": None, "picture_sha256": ""})
cmd = sys.argv[1] if len(sys.argv) > 1 else ""
data = b"" if cmd == "status" else sys.stdin.buffer.read()
with open(path("calls.jsonl"), "a") as f:
    f.write(json.dumps({"argv": sys.argv[1:], "stdin": len(data), "sha": hashlib.sha256(data).hexdigest() if data else ""}) + "\n")
if data:
    with open(path("last-stdin.bin"), "wb") as f: f.write(data)
code = read(cmd + "-exit.json", 0)
if cmd == "status":
    print(json.dumps(status)); sys.exit(0)
if code:
    if code == 3: print(read("why.json", "no-gdm"))
    sys.exit(code)
if cmd == "on":
    values = json.loads(sys.argv[2])
    status["state"] = "trial" if status["state"] == "off" else status["state"]
    status["stopped"] = ""
    status["values"] = values
    status["picture_sha256"] = hashlib.sha256(data).hexdigest() if values.get("picture") == "wallpaper" else ""
elif cmd == "off":
    status.update(state="off", values=None, picture_sha256="", stopped="")
with open(path("status.json"), "w") as f: json.dump(status, f)
'''

FAKE_PKEXEC = r'''#!/bin/sh
# Every call is a password prompt: logged, so a test can count them.
echo "$*" >> "$FAKE_GL_DIR/pkexec.log"
# Not given the password: pkexec's own 126, without running anything.
if [ -f "$FAKE_GL_DIR/no-password" ]; then exit 126; fi
exec "$@"
'''


class Helper:
    def __init__(self, d: Path):
        self.dir = d

    def status(self, **kw) -> None:
        st = {"version": 1, "available": True, "why": "", "state": "off", "stopped": "", "values": None,
              "picture_sha256": ""}
        st.update(kw)
        (self.dir / "status.json").write_text(json.dumps(st))

    def exit_code(self, cmd: str, code: int) -> None:
        (self.dir / f"{cmd}-exit.json").write_text(json.dumps(code))

    def calls(self, cmd: str | None = None) -> list[dict]:
        p = self.dir / "calls.jsonl"
        rows = [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []
        return [r for r in rows if cmd is None or r["argv"][:1] == [cmd]]

    def prompts(self) -> int:
        """How many times pkexec was run (each asks for the password)."""
        p = self.dir / "pkexec.log"
        return len(p.read_text().splitlines()) if p.exists() else 0

    def no_password(self, on: bool = True) -> None:
        p = self.dir / "no-password"
        p.write_text("") if on else p.unlink(missing_ok=True)

    @property
    def state(self) -> dict:
        return json.loads((self.dir / "status.json").read_text())


@pytest.fixture
def helper(tmp_path, monkeypatch):
    """A fake fedora-glass-login and pkexec, put where the Backend looks. The owner check is
    the real one where the tests run as root; elsewhere files only have to exist (the real
    check has its own test below)."""
    from fedoraglass.gui.backend import Backend
    d = tmp_path / "gl"
    d.mkdir()
    h = d / "fedora-glass-login"
    h.write_text(FAKE_HELPER.replace("{python}", sys.executable))
    h.chmod(0o755)
    pk = d / "pkexec"
    pk.write_text(FAKE_PKEXEC)
    pk.chmod(0o755)
    monkeypatch.setenv("FAKE_GL_DIR", str(d))
    monkeypatch.setattr(Backend, "GLASS_LOGIN", h)
    monkeypatch.setattr(Backend, "PKEXEC", pk)
    monkeypatch.setattr(Backend, "LOGIN_HELPER", d / "no-old-helper")
    if os.geteuid() != 0:
        monkeypatch.setattr(Backend, "_root_owned", staticmethod(lambda *ps: all(p.exists() for p in ps)))
    out = Helper(d)
    out.status()
    return out


def _wallpaper(path: Path, w: int, h: int, colour: str = "#3366aa") -> Path:
    img = QtGui.QImage(w, h, QtGui.QImage.Format.Format_RGB32)
    img.fill(QtGui.QColor(colour))
    assert img.save(str(path))
    return path


@pytest.fixture
def backend(app_qt, fake_env, tmp_path, helper):
    from fedoraglass.engine import Engine
    from fedoraglass.gui.backend import Backend
    wall = _wallpaper(tmp_path / "wall.png", 640, 360)
    fake_env.gs[("org.gnome.desktop.background", None)] = {"picture-uri": f"'file://{wall}'"}

    def make():
        b = Backend(env=fake_env, engine_factory=lambda: Engine(fake_env, []),
                    settings_path=tmp_path / "cfg/liquid-glass/settings.json", ui_dark=True, start=False)
        _keep.append(b)
        assert b.waitLoginGlass()
        return b
    return make


@pytest.fixture(scope="module")
def app_qt():
    return QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])


def _wait(b) -> None:
    assert b.waitLoginGlass()
    assert b.waitLoginGlass()        # the status read after a step


# ---------------------------------------------------------------- the values

def test_values_match_the_lock_screen_by_default():
    s = Settings(lock_blur=33, lock_dim=0.5, lock_tint=0.7, lock_card=False, lock_clock="thin",
                 lock_widget_battery=False, lock_message="  call\n me ", login_blur=90, login_clock="gnome",
                 tint="#ABC", frost=0.123456)
    v = loginlook.values(s, "#3584E4")
    assert v == {"accent": "#3584e4", "tint": "#aabbcc", "tint_amount": 0.7, "frost": 0.123, "blur": 33,
                 "dim": 0.5, "card": False, "clock": "thin", "picture": "wallpaper", "fit": "zoom",
                 "battery": False, "message": "call me"}
    assert set(v) == set(loginlook.DEFAULTS)


def test_values_take_the_login_screens_own_when_match_is_off():
    s = Settings(login_match_lock=False, lock_blur=33, login_blur=90, login_dim=0.1, login_tint=0.0,
                 login_card=False, login_clock="gnome", login_picture="glow", login_battery=False,
                 login_message="hello")
    v = loginlook.values(s, "#112233")
    assert (v["blur"], v["dim"], v["tint_amount"], v["card"], v["clock"], v["picture"], v["battery"], v["message"]) \
        == (90, 0.1, 0.0, False, "gnome", "glow", False, "hello")


def test_values_stay_inside_the_contracts_bounds():
    s = Settings(login_match_lock=False, login_blur=999, login_dim=0.99, login_tint=-1, login_clock="huge",
                 login_picture="/etc/shadow", login_message="x" * 500 + "\x00\x1b").normalized()
    v = loginlook.values(s, "#000000")
    assert (v["blur"], v["dim"], v["tint_amount"], v["clock"], v["picture"]) == (100, 0.65, 0.0, "bold", "wallpaper")
    assert len(v["message"]) <= 120 and "\x00" not in v["message"]
    low = loginlook.values(Settings(login_match_lock=False, login_blur=0), "#000000")
    assert low["blur"] == 10
    # The settings themselves are kept in range too.
    assert (s.login_blur, s.login_dim, s.login_tint, s.login_clock, s.login_picture) == (100, 0.65, 0.0, "bold", "wallpaper")
    assert Settings(login_match_lock="false").normalized().login_match_lock is False


def test_the_real_helpers_status_answer_is_read():
    """What the real fedora-glass-login prints for `status`, run here without root (it
    answers whatever this machine is): it must parse, available or not."""
    import subprocess
    repo = Path(__file__).resolve().parents[1]
    out = subprocess.run([sys.executable, "-I", "-S", str(repo / "fedoraglass/login_glass.py"), "status"],
                         capture_output=True, text=True, timeout=60, cwd=repo)
    assert out.returncode == 0, out.stderr
    st = loginlook.parse_status(out.stdout)
    assert st is not None, out.stdout
    assert st["state"] in loginlook.STATES and isinstance(st["available"], bool)
    assert st["available"] or st["why"] in (*loginlook.WHY, "error")
    raw = json.loads(out.stdout)
    assert set(raw) >= {"version", "available", "why", "state", "stopped", "values", "picture_sha256"}


def test_the_message_is_compared_as_the_helper_cleans_it():
    sent = loginlook.values(Settings(lock_message="hi\ud800 there\n\x00 you"), "#3584e4")
    assert sent["message"] == "hi there you"
    # What status gives back: the cleaned message, numbers rounded to 3 places.
    kept = {**sent, "message": "hi there you", "frost": round(sent["frost"] + 0.0002, 3)}
    assert loginlook.same_values(sent, kept)
    json.dumps(sent, ensure_ascii=False).encode()       # goes into an argument: no half pairs


@pytest.mark.parametrize("raw, fit", [
    ("'zoom'", "zoom"), ("'spanned'", "spanned"), ("'scaled'", "scaled"), ("'stretched'", "stretched"),
    ("'centered'", "centered"), ("'wallpaper'", "wallpaper"), ("'none'", "zoom"), ("'tiled-ish'", "zoom"),
    ("", "zoom"), (None, "zoom"), ("spanned\n", "spanned"),
])
def test_fit_follows_the_desktops_picture_options(raw, fit):
    assert loginlook.fit_from_options(raw) == fit


def test_a_status_from_before_fit_counts_as_zoom():
    old = {k: v for k, v in loginlook.DEFAULTS.items() if k != "fit"}
    assert loginlook.normalized(old)["fit"] == "zoom"
    assert loginlook.same_values(old, loginlook.DEFAULTS)
    assert not loginlook.same_values(old, {**loginlook.DEFAULTS, "fit": "spanned"})


def test_status_answers_are_checked():
    good = json.dumps({"version": 1, "available": True, "why": "", "state": "trial", "stopped": "",
                       "values": {"blur": 500, "clock": "nope"}, "picture_sha256": "AB" * 32})
    st = loginlook.parse_status(good)
    assert st["state"] == "trial" and st["values"]["blur"] == 100 and st["values"]["clock"] == "bold"
    assert st["picture_sha256"] == "ab" * 32
    assert loginlook.parse_status("not json") is None
    assert loginlook.parse_status(json.dumps({"version": 2})) is None
    assert loginlook.parse_status("x" * (loginlook.STATUS_MAX + 1)) is None
    odd = loginlook.parse_status(json.dumps({"version": 1, "available": False, "state": "weird", "why": "made-up"}))
    assert (odd["state"], odd["why"], odd["available"]) == ("off", "error", False)


# ---------------------------------------------------------------- what the card says

@pytest.mark.parametrize("st, state, words", [
    ({"state": "off"}, "off", "Off"),
    ({"state": "trial", "values": "same"}, "trial", "On trial: log in once and it stays on"),
    ({"state": "on", "values": "same"}, "on", "On"),
    ({"state": "on", "values": {"blur": 11}}, "behind", "Behind: Apply brings it up to date"),
    ({"state": "on", "values": None}, "behind", "Behind: Apply brings it up to date"),
    ({"state": "off", "stopped": "no-login"}, "stopped", "Turned itself off: nobody logged in after it was turned on"),
    ({"state": "off", "stopped": "crash"}, "stopped", "Turned itself off: the login screen had a problem with it"),
    ({"state": "off", "stopped": "silent"}, "stopped", "Turned itself off: the login screen did not show it"),
    ({"state": "off", "stopped": "kernel-arg"}, "stopped", "Turned itself off: it was switched off when the PC started"),
    ({"state": "off", "stopped": "gnome-version"}, "stopped", "Turned itself off: this GNOME version is not supported yet"),
    ({"state": "off", "stopped": "error"}, "stopped", "Turned itself off: something went wrong when the PC started"),
    ({"available": False, "why": "no-gdm"}, "unavailable", "Not available: it needs GDM, GNOME's own login screen"),
    ({"available": False, "why": "not-gdm"}, "unavailable", "Not available: this PC uses a different login screen"),
    ({"available": False, "why": "no-addon"}, "unavailable", "Not available: a part of Fedora Glass is missing"),
    ({"available": False, "why": "no-dconf"}, "unavailable", "Not available: a system part it needs (dconf) is missing"),
    ({"available": False, "why": "gnome-version"}, "unavailable", "Not available: this GNOME version is not supported yet"),
    ({"available": False, "why": "policy"}, "unavailable", "Not available: the permission it needs is missing"),
])
def test_status_line_for_every_code(backend, helper, st, state, words):
    b = backend()
    b._save_at_once(login_picture="glow")       # no wallpaper copy to compare in this test
    if st.get("values") == "same":
        st = {**st, "values": b.glass_login_values(b._saved)}
    elif isinstance(st.get("values"), dict):
        st = {**st, "values": {**b.glass_login_values(b._saved), **st["values"]}}
    helper.status(**st)
    b._read_glass_status()
    _wait(b)
    assert b.property("glassLoginState") == state
    assert b.property("glassLoginStatus").startswith(words)
    assert b.property("loginCardKind") == "new"
    assert b.property("glassLoginOn") is (state in ("on", "trial", "behind"))


def test_the_old_card_shows_only_when_the_new_one_is_not_available(backend, helper, tmp_path, monkeypatch):
    from fedoraglass.gui.backend import Backend
    old = tmp_path / "gl/old-helper"
    old.write_text("#!/bin/sh\n")
    old.chmod(0o755)
    monkeypatch.setattr(Backend, "LOGIN_HELPER", old)
    monkeypatch.setattr(Backend, "_read_login_state", lambda self: "off")
    assert backend().property("loginCardKind") == "new"
    helper.status(available=False, why="no-gdm")
    b = backend()
    assert b.property("loginCardKind") == "old"
    assert b.property("glassLoginWhy") == "The glass login screen that matches your lock screen is not available here: it needs GDM, GNOME's own login screen."
    # Turned on before (a GNOME update since): the new card stays, so it can be turned off.
    helper.status(available=False, why="gnome-version", state="on")
    b = backend()
    assert b.property("loginCardKind") == "new" and b.property("glassLoginOn")
    # No new helper at all: the old card as before, nothing said about the new one.
    monkeypatch.setattr(Backend, "GLASS_LOGIN", tmp_path / "missing")
    b = backend()
    assert b.property("loginCardKind") == "old" and b.property("glassLoginWhy") == ""


def test_a_helper_others_can_change_is_never_run(app_qt, tmp_path):
    from fedoraglass.gui.backend import Backend
    f = tmp_path / "helper"
    f.write_text("#!/bin/sh\n")
    f.chmod(0o777)
    assert not Backend._root_owned(f)
    assert not Backend._root_owned(tmp_path / "missing")
    if os.geteuid() == 0:
        f.chmod(0o755)
        assert Backend._root_owned(f)


# ---------------------------------------------------------------- turning it on and off

def test_turn_on_sends_the_values_and_the_picture_on_stdin(backend, helper):
    b = backend()
    assert b.property("glassLoginState") == "off" and b.property("glassLoginCanTurnOn")
    b.turnOnGlassLogin()
    _wait(b)
    calls = helper.calls("on")
    assert len(calls) == 1
    argv = calls[0]["argv"]
    assert len(argv) == 2, "the values go as one argument, never a path"
    sent = json.loads(argv[1])
    assert sent == b.glass_login_values(b._saved)
    assert calls[0]["stdin"] > 0
    data = (helper.dir / "last-stdin.bin").read_bytes()
    assert data[:3] == b"\xff\xd8\xff", "a JPEG the app encoded itself"
    assert b.property("glassLoginState") == "trial"
    assert "on trial" in b.property("loginGlassNote")
    assert not b.property("loginGlassFailed")
    # Up to date now: nothing behind, nothing for Apply to do.
    assert not b.property("loginGlassStale")


def test_turn_on_without_the_wallpaper_sends_nothing_on_stdin(backend, helper):
    b = backend()
    b._save_at_once(login_picture="system")
    b.turnOnGlassLogin()
    _wait(b)
    call = helper.calls("on")[-1]
    assert call["stdin"] == 0 and json.loads(call["argv"][1])["picture"] == "system"


def test_turn_off(backend, helper):
    helper.status(state="on", values=loginlook.DEFAULTS)
    b = backend()
    assert b.property("glassLoginOn")
    b.turnOffGlassLogin()
    _wait(b)
    assert helper.calls("off") and b.property("glassLoginState") == "off"
    assert b.property("loginGlassNote") == "The normal login screen is back."


def test_password_not_given_is_quiet(backend, helper):
    b = backend()
    helper.no_password()
    b.turnOnGlassLogin()
    _wait(b)
    assert helper.calls("on") == []
    assert b.property("loginGlassNote") == "Not changed: the password wasn't given."
    assert not b.property("loginGlassFailed")
    assert b.property("glassLoginState") == "off"


@pytest.mark.parametrize("code, words", [
    (2, "Nothing was changed: the login screen did not take these settings"),
    (3, "Nothing was changed: it needs GDM, GNOME's own login screen"),
    (4, "Nothing was changed: it could not be set up, so the normal login screen stays"),
    (1, "Nothing was changed: the helper didn't finish"),
])
def test_each_helper_failure_in_plain_words(backend, helper, code, words):
    b = backend()
    helper.exit_code("on", code)
    b.turnOnGlassLogin()
    _wait(b)
    assert b.property("loginGlassFailed")
    assert b.property("loginGlassNote") == words
    assert b.property("glassLoginState") == "off"


def test_turning_on_over_the_painted_glass_asks_once(backend, helper, tmp_path, monkeypatch):
    """The helper's `on` takes the painted glass off itself (after the new glass is in, and
    rolled back if it can't): the app runs only `on`, one password prompt, then reads the
    painted glass's state again so its card and flags are right."""
    from fedoraglass.gui.backend import Backend
    old = tmp_path / "gl/old-helper"
    old.write_text(f"#!/bin/sh\necho \"$@\" >> {tmp_path}/old.log\n")
    old.chmod(0o755)
    monkeypatch.setattr(Backend, "LOGIN_HELPER", old)
    state = {"v": "on"}
    monkeypatch.setattr(Backend, "_read_login_state", lambda self: state["v"])
    b = backend()
    assert b.property("glassLoginReplacesPainted")
    state["v"] = "off"            # what the helper's `on` leaves of the painted glass
    b.turnOnGlassLogin()
    _wait(b)
    assert helper.prompts() == 1, "one password prompt"
    assert not (tmp_path / "old.log").exists(), "the app never runs the old helper's undo itself"
    assert len(helper.calls("on")) == 1 and b.property("glassLoginState") == "trial"
    assert b.property("loginGlass") == "off" and not b.property("glassLoginReplacesPainted")


# ---------------------------------------------------------------- behind, and Apply

def _apply(b):
    b.apply()
    assert b.waitIdle()
    assert b.waitIdle()
    _wait(b)


def test_behind_when_the_applied_values_differ(backend, helper):
    b = backend()
    b.turnOnGlassLogin()
    _wait(b)
    assert b.property("glassLoginState") == "trial"
    b.setProperty("lockBlur", 20)
    assert b.property("loginGlassBehind"), "unapplied changes would change it: the card says so"
    assert b.property("glassLoginState") == "trial", "not behind until the change is applied"
    _apply(b)
    on = helper.calls("on")
    assert len(on) == 2, "Apply brought it up to date (one password prompt)"
    assert json.loads(on[-1]["argv"][1])["blur"] == 20
    assert b.property("glassLoginState") == "trial" and not b.property("loginGlassStale")
    assert helper.prompts() == 2, "one for turning it on, one for this Apply"
    _apply(b)
    assert len(helper.calls("on")) == 2 and helper.prompts() == 2, "nothing behind: no password asked"


def test_password_declined_on_apply_keeps_the_rest_and_says_behind(backend, helper):
    b = backend()
    b.turnOnGlassLogin()
    _wait(b)
    b.setProperty("lockBlur", 20)
    helper.no_password()
    _apply(b)
    assert helper.prompts() == 2 and len(helper.calls("on")) == 1, "asked once, nothing ran"
    assert not b.property("dirty") and b.settings().lock_blur == 20, "the rest of Apply is done"
    assert b.property("glassLoginState") == "behind"
    assert b.property("loginGlassStale")
    assert b.property("loginGlassNote") == "Not changed: the password wasn't given."
    assert not b.property("loginGlassFailed")


def test_behind_when_the_wallpaper_changed(backend, helper, fake_env, tmp_path):
    b = backend()
    b.turnOnGlassLogin()
    _wait(b)
    assert not b.property("loginGlassStale")
    new = _wallpaper(tmp_path / "wall2.png", 320, 200, "#aa3300")
    b._wallpapers = {"light": f"file://{new}", "dark": ""}
    b.loginGlassChanged.emit()
    b.property("glassLoginState")       # starts the copy of the new picture
    _wait(b)
    assert b.property("glassLoginState") == "behind"
    assert b.property("loginGlassStale"), "the footer says the login screen needs Apply"
    _apply(b)
    assert helper.calls("on")[-1]["sha"] == hashlib.sha256((helper.dir / "last-stdin.bin").read_bytes()).hexdigest()
    assert b.property("glassLoginState") == "trial"


def test_turn_off_that_fails_does_not_claim_nothing_changed(backend, helper):
    helper.status(state="on", values=loginlook.DEFAULTS)
    helper.exit_code("off", 4)
    b = backend()
    b.turnOffGlassLogin()
    _wait(b)
    assert b.property("loginGlassFailed")
    assert b.property("loginGlassNote").startswith("The glass login screen could not be turned off completely.")


def test_the_desktops_fit_goes_along_and_a_change_is_behind(backend, helper, fake_env):
    fake_env.gs[("org.gnome.desktop.background", None)]["picture-options"] = "'spanned'"
    b = backend()
    b.turnOnGlassLogin()
    _wait(b)
    assert json.loads(helper.calls("on")[-1]["argv"][1])["fit"] == "spanned"
    assert b.property("glassLoginState") == "trial"
    b._wallpaper_lines("picture-options: 'none'\n")      # changed in GNOME's settings
    _wait(b)
    assert b.property("glassLoginState") == "behind" and not b.property("dirty")
    _apply(b)
    assert json.loads(helper.calls("on")[-1]["argv"][1])["fit"] == "zoom"
    assert b.property("glassLoginState") == "trial"


def test_apply_leaves_it_alone_while_it_is_off(backend, helper):
    b = backend()
    b.setProperty("lockBlur", 20)
    _apply(b)
    assert helper.calls("on") == [] and helper.calls("off") == []


# ---------------------------------------------------------------- Restore and Remove

def test_restore_turns_it_off_only_when_it_is_on(backend, helper):
    b = backend()
    b.revert()
    assert b.waitIdle()
    _wait(b)
    assert helper.calls("off") == [], "nothing on: no password asked"
    helper.status(state="trial", values=loginlook.DEFAULTS)
    b = backend()
    b.revert()
    assert b.waitIdle()
    _wait(b)
    assert len(helper.calls("off")) == 1 and b.property("glassLoginState") == "off"


def test_remove_leaves_it_to_the_package(backend, helper, monkeypatch):
    """Removing the app runs Restore's engine part, then the package manager through pkexec:
    the package's own removal script turns the login screen off as root, so no second
    password prompt comes from here."""
    helper.status(state="on", values=loginlook.DEFAULTS)
    b = backend()
    ran: list = []
    monkeypatch.setattr(b, "_run_login_steps", lambda steps: ran.append(steps) or True)
    b._remove_package = "fedora-glass"
    b.removeApp()
    assert b.waitIdle()
    assert ran == []


# ---------------------------------------------------------------- the picture

def _size(data: bytes) -> tuple[int, int]:
    img = QtGui.QImage.fromData(data)
    return img.width(), img.height()


def test_a_picture_over_two_screens_keeps_its_size(tmp_path):
    """One 5120x1440 picture spanned over two screens goes as it is, re-encoded."""
    data = loginlook.prepare_picture(str(_wallpaper(tmp_path / "wide.png", 5120, 1440)))
    assert data[:3] == b"\xff\xd8\xff" and _size(data) == (5120, 1440)
    assert (loginlook.PICTURE_MAX_SIDE, loginlook.PICTURE_MAX_PIXELS) == (7680, 33_177_600)


def test_a_big_picture_is_scaled_keeping_its_shape(tmp_path, monkeypatch):
    # The limits made small, so the test pictures stay small: the rule is the same.
    monkeypatch.setattr(loginlook, "PICTURE_MAX_SIDE", 800)
    monkeypatch.setattr(loginlook, "PICTURE_MAX_PIXELS", 120_000)
    assert _size(loginlook.prepare_picture(str(_wallpaper(tmp_path / "long.png", 1600, 100)))) == (800, 50), \
        "beyond the long side"
    w, h = _size(loginlook.prepare_picture(str(_wallpaper(tmp_path / "square.png", 500, 500))))
    assert w == h and w * h <= 120_000 and w >= 340, "beyond the pixel count, shape kept"
    assert _size(loginlook.prepare_picture(str(_wallpaper(tmp_path / "ok.png", 400, 300)))) == (400, 300), \
        "within both: never scaled"


def test_the_quality_steps_down_rather_than_send_too_much(tmp_path, monkeypatch):
    import random
    rnd = random.Random(7)
    img = QtGui.QImage(600, 400, QtGui.QImage.Format.Format_RGB32)
    for y in range(400):
        for x in range(0, 600, 3):
            img.setPixel(x, y, rnd.randrange(1 << 24))
    noisy = tmp_path / "noisy.png"
    assert img.save(str(noisy))
    full = loginlook.prepare_picture(str(noisy))
    monkeypatch.setattr(loginlook, "PICTURE_MAX_BYTES", len(full) - 1)
    smaller = loginlook.prepare_picture(str(noisy))
    assert smaller is not None and len(smaller) < len(full) and _size(smaller) == (600, 400)
    monkeypatch.setattr(loginlook, "PICTURE_MAX_BYTES", 1000)
    assert loginlook.prepare_picture(str(noisy)) is None, "never more than the helper takes"


def test_metadata_does_not_go_along(tmp_path):
    img = QtGui.QImage(200, 100, QtGui.QImage.Format.Format_RGB32)
    img.fill(QtGui.QColor("#225588"))
    img.setText("Description", "my secret place")
    p = tmp_path / "meta.png"
    assert img.save(str(p))
    assert b"my secret place" in p.read_bytes()
    assert b"my secret place" not in loginlook.prepare_picture(str(p))


def test_an_unreadable_wallpaper_offers_glow(backend, helper, tmp_path):
    b = backend()
    bad = tmp_path / "broken.jpg"
    bad.write_bytes(b"\xff\xd8\xff not really a picture")
    assert loginlook.prepare_picture(str(bad)) is None
    b._wallpapers = {"light": f"file://{bad}", "dark": ""}
    b.turnOnGlassLogin()
    _wait(b)
    assert helper.calls("on") == [], "nothing goes to root"
    assert b.property("glassLoginPictureFailed") and b.property("loginGlassFailed")
    assert "could not be read" in b.property("loginGlassNote")
    b.useGlowForLogin()
    _wait(b)
    call = helper.calls("on")[-1]
    assert json.loads(call["argv"][1])["picture"] == "glow" and call["stdin"] == 0
    assert b.settings().login_picture == "glow" and not b.property("dirty")
    assert not b.property("glassLoginPictureFailed")


def test_the_picture_is_kept_until_the_wallpaper_changes(backend, helper, monkeypatch):
    b = backend()
    made: list = []
    real = loginlook.prepare_picture
    monkeypatch.setattr(loginlook, "prepare_picture", lambda p: made.append(p) or real(p))
    b.turnOnGlassLogin()
    _wait(b)
    for _ in range(5):
        b.property("glassLoginState")
        b.property("loginGlassStale")
    assert len(made) == 1


def test_the_dark_wallpaper_is_the_one_copied(backend, helper, tmp_path):
    b = backend()
    dark = _wallpaper(tmp_path / "dark.png", 100, 50, "#000000")
    b._wallpapers = {"light": "file:///nowhere.png", "dark": f"file://{dark}"}
    assert b._login_picture_path() == str(dark)


# ---------------------------------------------------------------- See it now

def test_see_it_now_locks_then_asks_gdm(backend, helper, tmp_path, monkeypatch, fake_env):
    log = tmp_path / "gdbus.log"
    gdbus = tmp_path / "gdbus"
    gdbus.write_text(f"#!/bin/sh\necho \"$@\" >> {log}\ncase \"$*\" in *CreateTransientDisplay*) exit ${{GDM_EXIT:-0}};; esac\n")
    gdbus.chmod(0o755)
    monkeypatch.setattr(fake_env, "which", lambda name: str(gdbus) if name == "gdbus" else None)
    b = backend()
    b.seeLoginScreen()
    _spin(1500)
    lines = log.read_text().splitlines()
    assert "org.gnome.ScreenSaver.Lock" in lines[0] and "--session" in lines[0]
    assert "CreateTransientDisplay" in lines[1] and "--system" in lines[1]
    assert "/org/gnome/DisplayManager/LocalDisplayFactory" in lines[1]
    assert b.property("glassLoginSeeNote") == ""
    monkeypatch.setenv("GDM_EXIT", "1")
    b.seeLoginScreen()
    _spin(1500)
    assert "Restart or log out to see it" in b.property("glassLoginSeeNote")
    # Switching users is off here: GDM would refuse, so the screen isn't even locked.
    fake_env.gs[("org.gnome.desktop.lockdown", None)] = {"disable-user-switching": "true"}
    log.unlink()
    b.seeLoginScreen()
    assert not log.exists() and "Restart or log out" in b.property("glassLoginSeeNote")


# ---------------------------------------------------------------- the section on the page

def _card_state(qml, helper, **status):
    b = _qml_backend(qml)
    helper.status(**status)
    b._read_glass_status()
    assert b.waitLoginGlass()
    return b


def test_the_section_on_the_lock_and_login_page(qml, helper):
    b = _card_state(qml, helper)
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        _goto(win, "lock", 400)
        card = _find(win, "loginGlassCard")
        assert card is not None and card.property("visible")
        assert not _find(win, "loginCard").property("visible"), "the painted glass card stays hidden"
        assert _find(win, "loginGlassStatus").property("text") == "Off"
        toggle = _find(win, "loginGlassToggle")
        assert toggle.property("text") == "Turn on glass login screen" and toggle.property("enabled")
        assert not _find(win, "loginSeeNow").property("visible")
        assert _find(win, "loginPictureNote").property("visible")
        own = _find(win, "loginOwn")
        assert not own.property("visible"), "Match my lock screen hides the login screen's own settings"
        b.setProperty("loginMatchLock", False)
        _spin(100)
        assert own.property("visible")
        assert b.property("loginBlur") == b.property("lockBlur"), "starts from the lock screen's values"
        # Its Reset pill puts the section back.
        title = _find(win, "loginGlassTitle")
        _spin(100)
        reset = next(it for it in [title, *title.childItems()[0].childItems()] if it.objectName() == "cardReset")
        assert reset.property("visible")
        reset.clicked.emit()
        _spin(100)
        assert b.property("loginMatchLock") is True and not own.property("visible")
        # On: Turn off and See it now.
        b2 = _card_state(qml, helper, state="on", values=b.glass_login_values(b._saved))
        _spin(100)
        assert b2 is b
        assert toggle.property("text") == "Turn off"
        assert _find(win, "loginSeeNow").property("visible")
        # Not available: only the title and why, no buttons.
        _card_state(qml, helper, available=False, why="no-gdm")
        _spin(100)
        assert card.property("visible") and not toggle.property("visible")
        assert "Not available" in _find(win, "loginGlassStatus").property("text")
        assert not _find(win, "loginSafe").property("visible")
    finally:
        _card_state(qml, helper)
        b.discardChanges()
        win.close()


def test_behind_with_nothing_else_to_apply_has_a_way_forward(qml, helper):
    """The login screen is behind (here: turned on with older values) and nothing else is
    unapplied: Apply can be pressed, the footer says why, See changes lists it."""
    b = _card_state(qml, helper)
    b._save_at_once(login_picture="glow")
    b = _card_state(qml, helper, state="on", values={**b.glass_login_values(b._saved), "blur": 11})
    win = _window(qml)
    sheet = None
    try:
        win.show()
        _spin(200)
        assert not b.property("dirty") and b.property("glassLoginState") == "behind"
        assert _find(win, "applyButton").property("enabled")
        assert _find(win, "statusText").property("text") == "Login screen needs Apply"
        sheet = _find(win, "changesSheet")
        sheet.open()
        _spin(300)
        row = _find(win, "change_login_refresh")
        assert row is not None and row.property("visible")
        assert "1 change" in sheet.property("subtitle")
        sheet.close()
        _spin(200)
        before = helper.prompts()
        _find(win, "applyButton").clicked.emit()
        assert b.waitIdle() and b.waitIdle()
        _wait(b)
        assert helper.prompts() == before + 1, "Apply asked once and brought it up to date"
        assert b.property("glassLoginState") == "on" and not b.property("loginGlassStale")
        assert _find(win, "statusText").property("text") != "Login screen needs Apply"
    finally:
        if sheet is not None:
            sheet.close()
        _card_state(qml, helper)
        b._save_at_once(login_picture="wallpaper")
        b.discardChanges()
        win.close()


def test_the_preview_shows_the_login_screen(qml, helper):
    b = _card_state(qml, helper)
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        _goto(win, "lock", 400)
        seg = _find(win, "lockPreviewScreen")
        assert seg is not None and seg.property("visible")
        page = _find(win, "lockPage")
        page.setProperty("previewScreen", "login")
        _spin(200)
        login = _find(win, "loginPreview")
        assert login.property("visible")
        assert not _find(win, "lockPreviewMode").property("visible"), "Clock | Password is for the lock screen"
        b.setProperty("loginMatchLock", False)
        b.setProperty("loginCard", False)
        b.setProperty("loginMessage", "If found, call 555 0100")
        _spin(100)
        assert not _find(win, "loginPreviewCard").property("visible"), "follows the switch live"
        assert _find(win, "loginPreviewMessage").property("visible")
        b.setProperty("loginClock", "gnome")
        _spin(100)
        assert _find(win, "loginPreviewPanelClock").property("visible")
        assert b.property("glassLoginLook")["clock"] == "gnome"
    finally:
        page.setProperty("previewScreen", "lock")
        b.discardChanges()
        win.close()
