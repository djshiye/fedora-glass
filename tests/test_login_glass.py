"""The glass login screen's root helper (fedoraglass/login_glass.py).

Every test builds a small system in a temporary folder (Fedora, Ubuntu or Arch shaped: the
dconf profile, dbs, the add-on, GDM's working folder) and points the helper at it with
Paths(root). The switch is compiled and read back with the real `dconf`, so these run in the
desktop test image (and in CI where dconf is installed); nothing outside the folder is touched.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import signal
import stat
import subprocess
from pathlib import Path

import pytest

from fedoraglass import login_glass as lg
from tests.ci_guard import required

DCONF = "/usr/bin/dconf"
needs_dconf = pytest.mark.skipif(not os.access(DCONF, os.X_OK), reason="needs dconf")
UUID = lg.UUID
BOOT_A = "0d4f3a52-1c7e-4b8e-9a41-3e1b2c4d5e6f"
BOOT_B = "7a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64


def test_ci_has_dconf_so_the_tests_below_do_not_skip():
    """Where CI says dconf is installed (FEDORAGLASS_REQUIRE=dconf), its absence is a failure."""
    if not required("dconf"):
        pytest.skip("not a CI run that installs dconf")
    assert os.access(DCONF, os.X_OK), "dconf is missing: install dconf-cli / dconf"


# ---- a small system ---------------------------------------------------------------------

def compile_db(out: Path, keyfile: str = "", locks: str = "") -> None:
    src = out.parent / (out.name + ".src")
    (src / "locks").mkdir(parents=True, exist_ok=True)
    if keyfile:
        (src / "00-test").write_text(keyfile)
    if locks:
        (src / "locks" / "00-test").write_text(locks)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([DCONF, "compile", str(out), str(src)], check=True)
    shutil.rmtree(src)


def script(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)


PROFILES = {
    # Fedora's gdm package patches the profile to read the system db "gdm" (c10s.spec).
    "fedora": "user-db:user\nsystem-db:gdm\nfile-db:/usr/share/gdm/greeter-dconf-defaults\n",
    # Ubuntu's gdm3 (26.04 and 26.10): the defaults compiled into /var/lib/gdm3 at install.
    "ubuntu": "user-db:user\nfile-db:/var/lib/gdm3/greeter-dconf-defaults\n",
    # Arch and upstream GDM.
    "arch": "user-db:user\nfile-db:/usr/share/gdm/greeter-dconf-defaults\n",
}
FILE_DB = {"fedora": "usr/share/gdm/greeter-dconf-defaults", "ubuntu": "var/lib/gdm3/greeter-dconf-defaults",
           "arch": "usr/share/gdm/greeter-dconf-defaults"}


def make_system(root: Path, kind: str = "fedora", base_exts: str | None = None, gdm_db: bool = True,
                shell: str = "51.0") -> lg.Paths:
    """A system like `kind`. base_exts: an enabled-extensions value set at system level."""
    if not os.access(DCONF, os.X_OK):
        pytest.skip("needs dconf")              # in CI, test_ci_has_dconf_... fails instead
    addon = root / "usr/share/gdm/greeter/gnome-shell/extensions" / UUID
    addon.mkdir(parents=True)
    (addon / "metadata.json").write_text(json.dumps({"uuid": UUID, "name": "Fedora Glass login",
                                                     "shell-version": ["50", "51"]}))
    (addon / "extension.js").write_text("export default class {}\n")
    (root / "etc/systemd/system/graphical.target.wants").mkdir(parents=True)
    dm = "gdm3.service" if kind == "ubuntu" else "gdm.service"
    os.symlink(f"/usr/lib/systemd/system/{dm}", root / "etc/systemd/system/display-manager.service")
    os.symlink(f"/usr/lib/systemd/system/{lg.GUARD_UNIT}",
               root / "etc/systemd/system/graphical.target.wants" / lg.GUARD_UNIT)
    (root / "usr/bin").mkdir(parents=True)
    os.symlink(DCONF, root / "usr/bin/dconf")
    script(root / "usr/bin/gnome-shell", f'echo "GNOME Shell {shell}"')
    (root / "proc/sys/kernel/random").mkdir(parents=True)
    (root / "proc/cmdline").write_text("BOOT_IMAGE=/vmlinuz root=UUID=x ro quiet rhgb\n")
    (root / "proc/sys/kernel/random/boot_id").write_text(BOOT_A + "\n")
    (root / "var/lib").mkdir(parents=True, exist_ok=True)
    (root / "usr/share/dconf/profile").mkdir(parents=True)
    (root / "usr/share/dconf/profile/gdm").write_text(PROFILES[kind])
    keyfile = "[org/gnome/login-screen]\nenable-smartcard-authentication=false\n"
    if base_exts is not None and kind != "fedora":
        keyfile += f"[org/gnome/shell]\nenabled-extensions={base_exts}\n"
    compile_db(root / FILE_DB[kind], keyfile)
    (root / "etc/dconf/db").mkdir(parents=True)
    if kind == "fedora" and gdm_db:
        d = root / "etc/dconf/db/gdm.d"
        (d / "locks").mkdir(parents=True)
        if base_exts is not None:
            (d / "00-admin").write_text(f"[org/gnome/shell]\nenabled-extensions={base_exts}\n")
        subprocess.run([DCONF, "compile", str(root / "etc/dconf/db/gdm"), str(d)], check=True)
    return lg.Paths(str(root))


def snapshot(root: Path) -> dict:
    """Every file's bytes and mode, every folder and link, outside root's own state folder
    (its lock file stays, so on/off/guard keep taking turns)."""
    out = {}
    for folder, dirs, files in os.walk(root):
        rel = os.path.relpath(folder, root)
        if rel.startswith("var/lib/fedora-glass"):
            dirs[:] = []
            continue
        for name in dirs + files:
            full = os.path.join(folder, name)
            relname = os.path.normpath(os.path.join(rel, name))
            if relname.startswith("var/lib/fedora-glass"):
                continue
            st = os.lstat(full)
            if stat.S_ISLNK(st.st_mode):
                out[relname] = ("l", os.readlink(full))
            elif stat.S_ISDIR(st.st_mode):
                out[relname] = ("d", stat.S_IMODE(st.st_mode))
            else:
                out[relname] = ("f", stat.S_IMODE(st.st_mode), Path(full).read_bytes())
    return out


def effective(paths: lg.Paths, key: str = "/org/gnome/shell/enabled-extensions", user_keyfile: str = "") -> str:
    """The value the login screen sees: its real profile, its user db (here with whatever
    the greeter's user wrote into it) included, read with the real dconf."""
    root = Path(paths.root)
    text = None
    for p in paths.profile_candidates:
        if os.path.exists(p):
            text = Path(p).read_text()
            break
    assert text is not None
    home = root / "greeter-home"
    (home / "run").mkdir(parents=True, exist_ok=True)
    (home / "run").chmod(0o700)
    if user_keyfile:
        compile_db(home / ".config/dconf/user", user_keyfile)
    lines = []
    for line in text.splitlines():
        kind, _, value = line.partition(":")
        if kind == "user-db":
            lines.append(line)
        elif kind == "system-db" and (root / "etc/dconf/db" / value).exists():
            lines.append(f"file-db:{root}/etc/dconf/db/{value}")
        elif kind == "file-db" and (root / value.lstrip("/")).exists():
            lines.append(f"file-db:{root}{value}")
    prof = home / "profile"
    prof.write_text("\n".join(lines) + "\n")
    r = subprocess.run([DCONF, "read", key], capture_output=True, text=True, check=True,
                       env={"PATH": "/usr/bin", "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
                            "XDG_RUNTIME_DIR": str(home / "run"), "DCONF_PROFILE": str(prof)})
    shutil.rmtree(home)
    return r.stdout.strip()


def values(**kw) -> dict:
    return lg.check_values(kw)


def on(paths: lg.Paths, pic=(JPEG, "jpg"), **kw) -> tuple[int, str]:
    v = values(**kw)
    return lg.turn_on(paths, v, pic if v["picture"] == "wallpaper" else None)


def state(paths: lg.Paths) -> dict:
    return json.loads(Path(paths.state).read_text())


def note(paths: lg.Paths, token: str, phase: str = "ok", boot: str = BOOT_A, verified: str = "",
         gdm: str = "var/lib/gdm", seat: str = "seat0", raw: bytes | None = None) -> Path:
    d = Path(paths.root) / gdm / seat / "state/fedora-glass-login"
    d.mkdir(parents=True, exist_ok=True)
    f = d / "health.json"
    f.write_bytes(raw if raw is not None else json.dumps(
        {"v": 1, "token": token, "boot": boot, "phase": phase, "verified": verified}).encode())
    return f


def reboot(paths: lg.Paths, boot: str) -> None:
    Path(paths.boot_id).write_text(boot + "\n")


@pytest.fixture
def fedora(tmp_path):
    return make_system(tmp_path / "root", "fedora")


@pytest.fixture
def ubuntu(tmp_path):
    return make_system(tmp_path / "root", "ubuntu")


# ---- the values ---------------------------------------------------------------------------

def test_missing_values_take_the_defaults_and_colours_are_lower_case():
    v = lg.parse_values('{"accent": "#AABBCC"}')
    assert v == {**lg.DEFAULTS, "accent": "#aabbcc"}
    assert list(v) == list(lg.DEFAULTS)
    assert lg.parse_values("{}") == lg.DEFAULTS


@pytest.mark.parametrize("text", [
    "[]", '"x"', "null", "1", "true", "", "{", '{"accent": "#3584e4",}', "{'accent': '#3584e4'}",
    '{"frost": NaN}', '{"frost": Infinity}', '{"frost": -Infinity}', '{"frost": 1e999}',
    '{"frost": 0.2, "frost": 0.3}', '{"colour": "#3584e4"}', '{"accent": "#3584e4", "extra": 1}',
    '{"accent": "3584e4"}', '{"accent": "#3584e"}', '{"accent": "#3584e4 "}', '{"accent": "#gggggg"}',
    '{"accent": 3584}', '{"tint": "#1e1e2a; } * {"}', '{"tint_amount": true}', '{"tint_amount": "0.5"}',
    '{"tint_amount": 1.0001}', '{"tint_amount": -0.0001}', '{"frost": false}', '{"frost": null}',
    '{"blur": 60.0}', '{"blur": 9}', '{"blur": 101}', '{"blur": true}', '{"blur": "60"}',
    '{"dim": 0.66}', '{"dim": -1}', '{"card": 1}', '{"card": "true"}', '{"battery": 0}',
    '{"clock": "middle"}', '{"clock": "BOLD"}', '{"clock": 1}', '{"picture": "file:///etc/shadow"}',
    '{"picture": ["wallpaper"]}', '{"message": 5}', '{"message": null}', '{"message": ["a"]}',
    '{"blur": 1' + "0" * 5000 + "}",
    '{"fit": "none"}', '{"fit": "Zoom"}', '{"fit": ""}', '{"fit": null}', '{"fit": 1}', '{"fit": ["zoom"]}',
    '{"fit": "zoom "}', '{"fit": "zoom\'"}',
])
def test_bad_values_are_refused(text):
    with pytest.raises(lg.BadInput):
        lg.parse_values(text)


def test_oversized_or_non_text_arguments_are_refused():
    with pytest.raises(lg.BadInput):
        lg.parse_values('{"message": "' + "a" * 9000 + '"}')
    with pytest.raises(lg.BadInput):
        lg.parse_values(None)
    with pytest.raises(lg.BadInput):
        lg.check_values(["accent"])


@pytest.mark.parametrize("x", [0, 1, 0.5, 0.0])
def test_numbers_at_their_bounds_are_fine(x):
    v = lg.check_values({"tint_amount": x, "frost": x, "dim": min(x, 0.65), "blur": 10 if x < 0.5 else 100})
    assert v["tint_amount"] == float(x) and isinstance(v["frost"], float)


def test_the_message_loses_control_characters_and_is_cut():
    v = lg.check_values({"message": "  Hello\x00\nthere\x1b[31m\u2028world\x7f\u0085 "})
    assert v["message"] == "Hello there [31m world"
    assert len(lg.check_values({"message": "é" * 500})["message"]) == lg.MESSAGE_MAX
    assert lg.check_values({"message": "a\ud800b"})["message"] == "ab"


def test_pictures_are_checked_by_their_first_bytes_and_size():
    assert lg.read_picture(io.BytesIO(JPEG)) == (JPEG, "jpg")
    assert lg.read_picture(io.BytesIO(PNG)) == (PNG, "png")
    for bad in (b"", b"GIF89a" + b"\0" * 20, b"\xff\xd8", b"<svg/>", b"\x89PNG\r\n\x1a"):
        with pytest.raises(lg.BadInput):
            lg.read_picture(io.BytesIO(bad))
    big = JPEG + b"\0" * (lg.MAX_PICTURE - len(JPEG))
    assert lg.read_picture(io.BytesIO(big))[1] == "jpg"
    with pytest.raises(lg.BadInput):
        lg.read_picture(io.BytesIO(big + b"\0"))


def test_look_json_is_the_token_and_the_values():
    v = lg.check_values({})
    look = json.loads(lg.look_json("a" * 32, v))
    assert look == {"version": 1, "token": "a" * 32, **v}


# ---- profiles and routes ------------------------------------------------------------------

def test_profile_lines_are_understood_or_refused():
    assert lg.parse_profile("# c\n\nuser-db:user\n system-db:gdm \nfile-db:/a/b\nservice-db:x\n") == [
        ("user-db", "user"), ("system-db", "gdm"), ("file-db", "/a/b"), ("service-db", "x")]
    for bad in ("user\n", "system-db:../x\n", "file-db:relative\n", "file-db:/a/../b\n", "other-db:x\n",
                "system-db:a b\n", "file-db:/a b\n"):
        with pytest.raises(lg.Unavailable):
            lg.parse_profile(bad)


def test_our_line_goes_right_after_the_last_user_db_line_and_comes_out_exactly():
    for text in ("user-db:user\nfile-db:/x\n", "user-db:user", "file-db:/x\n", "# c\nuser-db:a\nuser-db:b\nfile-db:/x"):
        new = lg.with_our_line(text)
        assert new.count(lg.PROFILE_LINE) == 1
        assert lg.with_our_line(new) == new
    assert lg.with_our_line("user-db:user\nfile-db:/x\n") == "user-db:user\nsystem-db:fedora-glass-login\nfile-db:/x\n"
    assert lg.with_our_line("file-db:/x\n") == "system-db:fedora-glass-login\nfile-db:/x\n"
    assert lg.without_our_line(lg.with_our_line("user-db:user\nfile-db:/x\n")) == "user-db:user\nfile-db:/x\n"


@needs_dconf
@pytest.mark.parametrize("kind,route,db", [("fedora", "a", "gdm"), ("ubuntu", "b", lg.OWN_DB), ("arch", "b", lg.OWN_DB)])
def test_each_distro_gets_its_route_and_the_add_on_is_on_for_the_login_screen(tmp_path, kind, route, db):
    paths = make_system(tmp_path / "root", kind, base_exts="['dock@distro.example']")
    assert on(paths) == (0, "trial")
    s = state(paths)
    assert (s["route"], s["db"]) == (route, db)
    root = Path(paths.root)
    assert (root / f"etc/dconf/db/{db}.d/{lg.OUR_FILE}").is_file()
    assert (root / f"etc/dconf/db/{db}.d/locks/{lg.OUR_FILE}").is_file()
    # Read with the real dconf the way the login screen will, with a greeter user db that
    # tries to switch it off: the locks win, and the distro's own extension stays.
    got = effective(paths, user_keyfile="[org/gnome/shell]\nenabled-extensions=@as []\ndisable-user-extensions=true\n")
    assert got == f"['dock@distro.example', '{UUID}']"
    assert effective(paths, "/org/gnome/shell/disable-user-extensions",
                     user_keyfile="[org/gnome/shell]\ndisable-user-extensions=true\n") == "false"
    assert effective(paths, "/org/gnome/desktop/background/picture-uri") == "'file:///etc/fedora-glass/login/picture.jpg'"
    if route == "b":
        assert (root / "etc/dconf/profile/gdm").read_text() == lg.with_our_line(PROFILES[kind])
    else:
        assert not (root / "etc/dconf/profile/gdm").exists()


@needs_dconf
@pytest.mark.parametrize("kind", ["fedora", "ubuntu"])
def test_on_then_off_leaves_every_file_as_it_was(tmp_path, kind):
    paths = make_system(tmp_path / "root", kind, base_exts="['a@b.c']")
    before = snapshot(Path(paths.root))
    assert on(paths)[0] == 0
    assert on(paths, pic=(PNG, "png"), accent="#ff0000")[0] == 0     # a change of look on top
    assert snapshot(Path(paths.root)) != before
    assert lg.turn_off(paths) == []
    assert snapshot(Path(paths.root)) == before
    assert effective(paths) == "['a@b.c']"
    assert not os.path.exists(paths.state) and not os.path.exists(paths.trial)


@needs_dconf
def test_on_then_off_without_a_gdm_db_takes_away_the_folders_it_made(tmp_path):
    paths = make_system(tmp_path / "root", "fedora", gdm_db=False)
    before = snapshot(Path(paths.root))
    assert on(paths)[0] == 0
    assert state(paths)["db"] == "gdm" and os.path.isfile(Path(paths.root) / "etc/dconf/db/gdm")
    assert lg.turn_off(paths) == []
    assert snapshot(Path(paths.root)) == before


@needs_dconf
def test_an_admins_own_profile_only_gets_one_line_and_gets_it_back_exactly(tmp_path):
    paths = make_system(tmp_path / "root", "ubuntu")
    etc = Path(paths.root) / "etc/dconf/profile"
    etc.mkdir(parents=True)
    admin = "# mine\nuser-db:user\nfile-db:/var/lib/gdm3/greeter-dconf-defaults"      # no final newline
    (etc / "gdm").write_text(admin)
    before = snapshot(Path(paths.root))
    assert on(paths)[0] == 0
    assert (etc / "gdm").read_text() == "# mine\nuser-db:user\nsystem-db:fedora-glass-login\nfile-db:/var/lib/gdm3/greeter-dconf-defaults"
    assert lg.turn_off(paths) == []
    assert snapshot(Path(paths.root)) == before


@needs_dconf
def test_an_admin_edit_after_on_keeps_the_admins_file_and_only_our_line_goes(tmp_path):
    paths = make_system(tmp_path / "root", "ubuntu")
    assert on(paths)[0] == 0
    prof = Path(paths.root) / "etc/dconf/profile/gdm"
    prof.write_text(prof.read_text() + "# admin was here\n")
    assert lg.turn_off(paths) == []
    assert prof.read_text() == PROFILES["ubuntu"] + "# admin was here\n"


@needs_dconf
def test_a_binary_db_without_its_folder_is_left_alone_and_its_list_is_kept(tmp_path):
    paths = make_system(tmp_path / "root", "arch")
    root = Path(paths.root)
    (root / "usr/share/dconf/profile/gdm").write_text("user-db:user\nsystem-db:site\nfile-db:/usr/share/gdm/greeter-dconf-defaults\n")
    compile_db(root / "etc/dconf/db/site", "[org/gnome/shell]\nenabled-extensions=['site@x.y']\n")
    site = (root / "etc/dconf/db/site").read_bytes()
    before = snapshot(root)
    assert on(paths)[0] == 0
    assert state(paths)["route"] == "b"
    assert (root / "etc/dconf/db/site").read_bytes() == site
    assert effective(paths) == f"['site@x.y', '{UUID}']"
    assert lg.turn_off(paths) == []
    assert snapshot(root) == before


@needs_dconf
def test_a_profile_from_the_greeter_data_folder_wins_over_usr_share(tmp_path):
    paths = make_system(tmp_path / "root", "arch")
    root = Path(paths.root)
    (root / "usr/share/gdm/greeter/dconf/profile").mkdir(parents=True)
    (root / "usr/share/gdm/greeter/dconf/profile/gdm").write_text(PROFILES["fedora"])
    (root / "etc/dconf/db/gdm.d/locks").mkdir(parents=True)
    assert on(paths)[0] == 0
    assert state(paths)["route"] == "a"


@needs_dconf
def test_an_admin_who_switched_off_login_screen_extensions_is_obeyed(tmp_path):
    paths = make_system(tmp_path / "root", "fedora")
    root = Path(paths.root)
    (root / "etc/dconf/db/gdm.d/10-admin").write_text("[org/gnome/shell]\ndisable-user-extensions=true\n")
    subprocess.run([DCONF, "compile", str(root / "etc/dconf/db/gdm"), str(root / "etc/dconf/db/gdm.d")], check=True)
    before = snapshot(root)
    assert lg.available(paths) == (False, "policy")
    assert on(paths) == (3, "policy")
    assert snapshot(root) == before


@needs_dconf
def test_a_later_lock_that_would_override_ours_is_found_and_everything_is_undone(tmp_path):
    paths = make_system(tmp_path / "root", "fedora")
    root = Path(paths.root)
    # The distro defaults (read after the gdm db) lock the list: dconf then takes their value.
    compile_db(root / FILE_DB["fedora"], "[org/gnome/shell]\nenabled-extensions=['x@y']\n",
               "/org/gnome/shell/enabled-extensions\n")
    before = snapshot(root)
    assert on(paths) == (3, "policy")
    assert snapshot(root) == before


@pytest.mark.parametrize("value", ["['ok@x', 'it''s']", "['a', \"b\"]", "[1, 2]", "'x'", "['a b']", "['a','b']", "garbage"])
def test_an_extension_list_that_is_not_plain_names_fails_closed(value):
    with pytest.raises(lg.Unavailable):
        lg.parse_strv(value)


def test_plain_extension_lists_are_read():
    assert lg.parse_strv("") == [] and lg.parse_strv("@as []") == []
    assert lg.parse_strv("['a@b.c', 'd-e_f.g', 'a@b.c']") == ["a@b.c", "d-e_f.g"]


@needs_dconf
def test_a_failing_dconf_compile_rolls_everything_back(tmp_path):
    paths = make_system(tmp_path / "root", "ubuntu")
    root = Path(paths.root)
    (root / "usr/bin/dconf").unlink()
    script(root / "usr/bin/dconf", f'[ "$1" = compile ] && exit 1\nexec {DCONF} "$@"')
    before = snapshot(root)
    code, msg = on(paths)
    assert code == 4 and "dconf compile failed" in msg
    assert snapshot(root) == before
    assert not os.path.exists(paths.state)


@needs_dconf
def test_a_failing_compile_on_a_change_puts_the_earlier_look_back(tmp_path):
    paths = make_system(tmp_path / "root", "fedora")
    assert on(paths)[0] == 0
    root = Path(paths.root)
    (root / "usr/bin/dconf").unlink()
    # Compiling the real db fails; the probes still work.
    script(root / "usr/bin/dconf", f'[ "$1" = compile ] && case "$2" in */etc/dconf/db/.fedora-glass-*) exit 1;; esac\nexec {DCONF} "$@"')
    before = snapshot(root)
    st_before = Path(paths.state).read_bytes()
    code, msg = on(paths, picture="glow", tint="#102030")
    assert code == 4 and "dconf compile failed" in msg
    assert snapshot(root) == before
    assert Path(paths.state).read_bytes() == st_before


@needs_dconf
def test_not_available_reasons(tmp_path):
    def fresh(name, **kw):
        return make_system(tmp_path / name, "fedora", **kw)
    p = fresh("ok")
    assert lg.available(p) == (True, "")
    p = fresh("nogdm")
    shutil.rmtree(Path(p.root) / "usr/share/gdm/greeter")
    assert lg.available(p) == (False, "no-gdm")
    p = fresh("noprofile")
    (Path(p.root) / "usr/share/dconf/profile/gdm").unlink()
    assert lg.available(p) == (False, "no-gdm")
    p = fresh("sddm")
    dm = Path(p.root) / "etc/systemd/system/display-manager.service"
    dm.unlink()
    os.symlink("/usr/lib/systemd/system/sddm.service", dm)
    assert lg.available(p) == (False, "not-gdm")
    p = fresh("noaddon")
    (Path(p.addon) / "extension.js").unlink()
    assert lg.available(p) == (False, "no-addon")
    p = fresh("badmeta")
    (Path(p.addon) / "metadata.json").write_text('{"uuid": "other@x", "shell-version": ["51"]}')
    assert lg.available(p) == (False, "no-addon")
    p = fresh("nodconf")
    (Path(p.root) / "usr/bin/dconf").unlink()
    assert lg.available(p) == (False, "no-dconf")
    p = fresh("gnome52", shell="52.alpha")
    assert lg.available(p) == (False, "gnome-version")
    p = fresh("noshell")
    (Path(p.root) / "usr/bin/gnome-shell").unlink()
    assert lg.available(p) == (False, "gnome-version")


@needs_dconf
def test_on_needs_the_boot_guard(fedora):
    (Path(fedora.root) / "etc/systemd/system/graphical.target.wants" / lg.GUARD_UNIT).unlink()
    before = snapshot(Path(fedora.root))
    assert on(fedora)[0] == 4
    assert snapshot(Path(fedora.root)) == before


@needs_dconf
def test_files_get_their_modes_whatever_the_umask(tmp_path):
    old = os.umask(0)
    try:
        paths = make_system(tmp_path / "root", "ubuntu")
        assert on(paths)[0] == 0
    finally:
        os.umask(old)
    root = Path(paths.root)
    for f in ("etc/fedora-glass/login/look.json", "etc/fedora-glass/login/picture.jpg",
              f"etc/dconf/db/{lg.OWN_DB}", f"etc/dconf/db/{lg.OWN_DB}.d/{lg.OUR_FILE}",
              f"etc/dconf/db/{lg.OWN_DB}.d/locks/{lg.OUR_FILE}", "etc/dconf/profile/gdm",
              "var/lib/fedora-glass/login/state.json", "var/lib/fedora-glass/login/trial"):
        assert stat.S_IMODE(os.stat(root / f).st_mode) == 0o644, f
    for d in ("etc/fedora-glass", "etc/fedora-glass/login", f"etc/dconf/db/{lg.OWN_DB}.d",
              f"etc/dconf/db/{lg.OWN_DB}.d/locks", "etc/dconf/profile", "var/lib/fedora-glass/login"):
        assert stat.S_IMODE(os.stat(root / d).st_mode) == 0o755, d
    assert not [n for n in os.listdir(root / "etc/dconf/db") if n.startswith(".")]
    assert not [n for n in os.listdir(paths.state_dir) if n.startswith(".work")]


@needs_dconf
def test_a_change_of_look_keeps_the_token_and_the_trial(fedora):
    assert on(fedora)[0] == 0
    s1 = state(fedora)
    assert s1["state"] == "trial" and os.path.isfile(fedora.trial)
    assert on(fedora, picture="glow", tint="#203040")[0] == 0
    s2 = state(fedora)
    assert s2["token"] == s1["token"] and s2["state"] == "trial" and s2["values"]["picture"] == "glow"
    look = json.loads((Path(fedora.conf_dir) / "look.json").read_text())
    assert look["token"] == s1["token"] and look["tint"] == "#203040"
    assert not os.path.exists(Path(fedora.conf_dir) / "picture.jpg")
    assert effective(fedora, "/org/gnome/desktop/background/primary-color") == "'#203040'"
    assert effective(fedora, "/org/gnome/desktop/background/picture-uri") == "''"
    assert on(fedora, picture="system")[0] == 0
    assert effective(fedora, "/org/gnome/desktop/background/primary-color") == ""
    kf = (Path(fedora.root) / "etc/dconf/db/gdm.d" / lg.OUR_FILE).read_text()
    assert "background" not in kf


@needs_dconf
def test_on_clears_why_it_was_stopped(fedora):
    Path(fedora.state_dir).mkdir(parents=True)
    Path(fedora.stopped).write_text('{"reason": "crash", "when": "x"}')
    assert on(fedora)[0] == 0
    assert not os.path.exists(fedora.stopped)


@pytest.mark.parametrize("fit", ["zoom", "spanned", "scaled", "stretched", "centered", "wallpaper"])
def test_each_fit_is_gnomes_picture_options(fit):
    v = lg.check_values({"fit": fit})
    assert v["fit"] == fit and list(v) == list(lg.DEFAULTS) and lg.DEFAULTS["fit"] == "zoom"
    key, locks = lg.keyfile([], {**v, "_kind": "png"})
    assert f"picture-options='{fit}'\n".encode() in key
    assert b"/org/gnome/desktop/background/picture-options\n" in locks
    assert json.loads(lg.look_json("a" * 32, v))["fit"] == fit


@pytest.mark.parametrize("picture", ["glow", "system"])
def test_fit_changes_no_key_without_my_wallpaper(picture):
    a = lg.keyfile([], lg.check_values({"picture": picture, "fit": "spanned"}))
    b = lg.keyfile([], lg.check_values({"picture": picture, "fit": "zoom"}))
    assert a == b and b"spanned" not in a[0]
    assert json.loads(lg.look_json("a" * 32, lg.check_values({"picture": picture, "fit": "spanned"})))["fit"] == "spanned"


@needs_dconf
def test_the_fit_reaches_the_login_screen_and_the_state(fedora):
    assert on(fedora, fit="spanned")[0] == 0
    assert effective(fedora, "/org/gnome/desktop/background/picture-options") == "'spanned'"
    assert state(fedora)["values"]["fit"] == "spanned"
    assert lg.status(fedora)["values"]["fit"] == "spanned"
    assert json.loads((Path(fedora.conf_dir) / "look.json").read_text())["fit"] == "spanned"


@needs_dconf
def test_a_state_file_from_before_fit_is_read_as_zoom(fedora):
    assert on(fedora)[0] == 0
    s = state(fedora)
    del s["values"]["fit"]
    Path(fedora.state).write_text(json.dumps(s))
    assert lg.read_state(fedora)["values"]["fit"] == "zoom"
    assert guard(fedora) == "trial"
    assert state(fedora)["values"]["fit"] == "zoom"


# ---- disabled-extensions -------------------------------------------------------------------

def test_the_keyfile_locks_a_disabled_list_without_us():
    v = lg.check_values({"picture": "system"})
    key, locks = lg.keyfile(["a@b"], v, ["x@y", UUID])
    assert b"disabled-extensions=['x@y']\n" in key
    assert b"/org/gnome/shell/disabled-extensions\n" in locks
    key, _ = lg.keyfile([], v, [UUID])
    assert b"disabled-extensions=@as []\n" in key
    with pytest.raises(lg.Unavailable):
        lg.keyfile([], v, ["it's"])


@needs_dconf
@pytest.mark.parametrize("kind", ["fedora", "ubuntu"])
def test_gnomes_own_disable_in_the_greeter_user_db_loses_against_the_lock(tmp_path, kind):
    paths = make_system(tmp_path / "root", kind)
    assert on(paths)[0] == 0
    hostile = f"[org/gnome/shell]\ndisabled-extensions=['{UUID}']\nenabled-extensions=@as []\n"
    assert effective(paths, "/org/gnome/shell/disabled-extensions", user_keyfile=hostile) == "@as []"
    assert UUID in effective(paths, user_keyfile=hostile)


@needs_dconf
def test_an_admins_disabled_list_of_other_extensions_is_kept(tmp_path):
    paths = make_system(tmp_path / "root", "fedora")
    root = Path(paths.root)
    (root / "etc/dconf/db/gdm.d/10-admin").write_text(
        f"[org/gnome/shell]\ndisabled-extensions=['other@x.y', '{UUID}']\n")
    subprocess.run([DCONF, "compile", str(root / "etc/dconf/db/gdm"), str(root / "etc/dconf/db/gdm.d")], check=True)
    before = snapshot(root)
    assert on(paths)[0] == 0
    assert effective(paths, "/org/gnome/shell/disabled-extensions") == "['other@x.y']"
    assert lg.turn_off(paths) == []
    assert snapshot(root) == before
    assert effective(paths, "/org/gnome/shell/disabled-extensions") == f"['other@x.y', '{UUID}']"


@needs_dconf
@pytest.mark.parametrize("kind", ["fedora", "arch"])
def test_an_admin_lock_that_disables_us_is_policy_and_changes_nothing(tmp_path, kind):
    paths = make_system(tmp_path / "root", kind)
    compile_db(Path(paths.root) / FILE_DB[kind], f"[org/gnome/shell]\ndisabled-extensions=['{UUID}']\n",
               "/org/gnome/shell/disabled-extensions\n")
    before = snapshot(Path(paths.root))
    assert on(paths) == (3, "policy")
    assert snapshot(Path(paths.root)) == before


@needs_dconf
def test_guard_turns_it_off_when_an_admin_later_locks_us_disabled(fedora):
    assert on(fedora)[0] == 0
    compile_db(Path(fedora.root) / FILE_DB["fedora"], f"[org/gnome/shell]\ndisabled-extensions=['{UUID}']\n",
               "/org/gnome/shell/disabled-extensions\n")
    assert guard(fedora) == "off: error"
    assert lg.switch_gone(fedora) == []


# ---- the painted glass of earlier versions ------------------------------------------------

def painted(paths: lg.Paths, works: bool) -> tuple[Path, Path]:
    """The record of the painted glass, and a fake of its helper that logs each call and
    whether the new glass was already in at that moment."""
    root = Path(paths.root)
    old = root / "var/lib/liquid-glass/login-screen.json"
    old.parent.mkdir(parents=True)
    old.write_text('{"written": "abc", "original": "def"}')
    log = root / "undo.log"
    look = Path(paths.conf_dir) / "look.json"
    script(root / "usr/libexec/liquid-glass-login-screen",
           f'echo "$@ new-glass-in=$(test -f {look} && echo yes || echo no)" >> {log}\n'
           + (f"rm -f {old}\nexit 0" if works else "exit 1"))
    return old, log


def without(snap: dict, *names: str) -> dict:
    return {k: v for k, v in snap.items() if k not in names}


@needs_dconf
def test_the_painted_glass_goes_only_after_the_new_glass_is_in(fedora):
    old, log = painted(fedora, works=True)
    assert on(fedora)[0] == 0
    assert log.read_text() == "undo new-glass-in=yes\n"
    assert not old.exists() and UUID in effective(fedora)


@needs_dconf
def test_a_failing_painted_glass_undo_rolls_the_new_glass_back(fedora):
    old, log = painted(fedora, works=False)
    before = snapshot(Path(fedora.root))
    code, msg = on(fedora)
    assert code == 4 and "painted" in msg
    assert log.read_text() == "undo new-glass-in=yes\n"
    assert without(snapshot(Path(fedora.root)), "undo.log") == without(before, "undo.log")
    assert old.exists() and not os.path.exists(fedora.state)


@needs_dconf
def test_a_painted_glass_record_that_stays_rolls_the_new_glass_back(fedora):
    old, log = painted(fedora, works=False)
    script(Path(fedora.old_helper), f'echo "$@" >> {log}\nexit 0')       # says yes, does nothing
    before = snapshot(Path(fedora.root))
    assert on(fedora)[0] == 4
    assert without(snapshot(Path(fedora.root)), "undo.log") == without(before, "undo.log")


@needs_dconf
def test_a_failure_of_the_new_glass_keeps_the_painted_glass(fedora):
    old, log = painted(fedora, works=True)
    root = Path(fedora.root)
    (root / "usr/bin/dconf").unlink()
    script(root / "usr/bin/dconf", f'[ "$1" = compile ] && case "$2" in */etc/dconf/db/.fedora-glass-*) exit 1;; esac\nexec {DCONF} "$@"')
    before = snapshot(root)
    assert on(fedora)[0] == 4
    assert not log.exists() and old.exists()            # the old helper never ran
    assert snapshot(root) == before


@needs_dconf
def test_a_policy_refusal_keeps_the_painted_glass(fedora):
    old, log = painted(fedora, works=True)
    compile_db(Path(fedora.root) / FILE_DB["fedora"], "[org/gnome/shell]\nenabled-extensions=['x@y']\n",
               "/org/gnome/shell/enabled-extensions\n")
    before = snapshot(Path(fedora.root))
    assert on(fedora) == (3, "policy")
    assert not log.exists() and old.exists()
    assert snapshot(Path(fedora.root)) == before


# ---- off -------------------------------------------------------------------------------------

@needs_dconf
@pytest.mark.parametrize("damage", ["missing", "garbled", "not-json", "a-folder"])
def test_off_works_without_a_good_state_file(tmp_path, damage):
    paths = make_system(tmp_path / "root", "ubuntu", base_exts="['a@b.c']")
    before = snapshot(Path(paths.root))
    assert on(paths)[0] == 0
    st = Path(paths.state)
    st.unlink()
    if damage == "garbled":
        st.write_text('{"version": 1, "state": "on", "made": "/etc", "profile": 7}')
    elif damage == "not-json":
        st.write_bytes(b"\xff\x00{")
    elif damage == "a-folder":
        st.mkdir()
    problems = lg.turn_off(paths)
    assert not [p for p in problems if p.startswith("still there")]
    assert lg.switch_gone(paths) == []
    assert effective(paths) == "['a@b.c']"
    after = snapshot(Path(paths.root))
    # Without its record, only the empty folder it made for the profile may stay.
    after.pop("etc/dconf/profile", None)
    assert after == before


@needs_dconf
def test_off_twice_and_off_when_never_on(fedora):
    before = snapshot(Path(fedora.root))
    assert lg.turn_off(fedora) == []
    assert snapshot(Path(fedora.root)) == before
    assert on(fedora)[0] == 0
    assert lg.turn_off(fedora) == []
    assert lg.turn_off(fedora) == []
    assert snapshot(Path(fedora.root)) == before


@needs_dconf
def test_off_by_the_guard_says_why_and_off_by_the_person_does_not(fedora):
    assert on(fedora)[0] == 0
    with lg.Lock(fedora):
        lg._off_locked(fedora, "crash")
    s = json.loads(Path(fedora.stopped).read_text())
    assert s["reason"] == "crash" and s["when"].endswith("Z")
    assert lg.status(fedora)["stopped"] == "crash"
    assert lg.turn_off(fedora) == []
    assert not os.path.exists(fedora.stopped)


@needs_dconf
def test_off_keeps_the_state_while_a_db_cannot_be_recompiled(fedora):
    assert on(fedora)[0] == 0
    root = Path(fedora.root)
    (root / "etc/dconf/db/gdm.d/50-broken").write_text("not a keyfile\n")
    problems = lg.turn_off(fedora)
    assert any(p.startswith("still there") for p in problems)
    assert os.path.exists(fedora.state)          # so the guard tries again at the next boot
    (root / "etc/dconf/db/gdm.d/50-broken").unlink()
    assert lg.turn_off(fedora) == []
    assert not os.path.exists(fedora.state)
    assert effective(fedora) == ""


# ---- the health notes ---------------------------------------------------------------------

def test_good_notes_are_read_from_each_gdm_folder_and_seat(fedora):
    t = "ab" * 16
    note(fedora, t, "ok")
    note(fedora, t, "starting", gdm="var/lib/gdm3", seat="seat1")
    assert sorted(n["phase"] for n in lg.read_notes(fedora)) == ["ok", "starting"]


@pytest.mark.parametrize("raw", [
    b"{", b"[]", b"null", b'"x"', b"\xff\xfe",
    b'{"v": 1, "token": "' + b"a" * 32 + b'", "boot": "' + BOOT_A.encode() + b'", "phase": "ok"}',
    b'{"v": true, "token": "", "boot": "", "phase": "ok", "verified": ""}',
    b'{"v": 2, "token": "", "boot": "", "phase": "ok", "verified": ""}',
    b'{"v": 1, "token": "' + b"A" * 32 + b'", "boot": "", "phase": "ok", "verified": ""}',
    b'{"v": 1, "token": "' + b"a" * 31 + b'", "boot": "", "phase": "ok", "verified": ""}',
    b'{"v": 1, "token": "", "boot": "../../etc", "phase": "ok", "verified": ""}',
    b'{"v": 1, "token": "", "boot": "", "phase": "crashed", "verified": ""}',
    b'{"v": 1, "token": "", "boot": "", "phase": ["ok"], "verified": ""}',
    b'{"v": 1, "token": "", "boot": "", "phase": "ok", "verified": 1}',
    b'{"v": 1, "token": "", "boot": "", "phase": "ok", "verified": "", "more": 1}',
    b'{"v": 1, "v": 1, "token": "", "boot": "", "phase": "ok", "verified": ""}',
    b'{"v": 1, "token": "", "boot": "", "phase": "ok", "verified": ""}' + b" " * 5000,
])
def test_bad_notes_are_no_notes(fedora, raw):
    note(fedora, "", raw=raw)
    assert lg.read_notes(fedora) == []


@pytest.mark.parametrize("level", ["gdm", "seat0", "state", "fedora-glass-login", "health.json"])
def test_a_link_at_any_level_is_never_followed(tmp_path, fedora, level):
    t = "cd" * 16
    real = make_system(tmp_path / "elsewhere", "fedora")
    good = note(real, t, "safe")
    root = Path(fedora.root)
    target = {"gdm": good.parents[3], "seat0": good.parents[2], "state": good.parents[1],
              "fedora-glass-login": good.parent, "health.json": good}[level]
    link = {"gdm": root / "var/lib/gdm", "seat0": root / "var/lib/gdm/seat0", "state": root / "var/lib/gdm/seat0/state",
            "fedora-glass-login": root / "var/lib/gdm/seat0/state/fedora-glass-login",
            "health.json": root / "var/lib/gdm/seat0/state/fedora-glass-login/health.json"}[level]
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(target, link)
    assert lg.read_notes(fedora) == []


def test_a_fifo_a_folder_or_a_huge_file_is_no_note(fedora):
    d = note(fedora, "", "ok").parent
    (d / "health.json").unlink()
    os.mkfifo(d / "health.json")
    assert lg.read_notes(fedora) == []                 # and it does not hang
    (d / "health.json").unlink()
    (d / "health.json").mkdir()
    assert lg.read_notes(fedora) == []
    (d / "health.json").rmdir()
    with open(d / "health.json", "wb") as f:
        f.truncate(1 << 30)
    assert lg.read_notes(fedora) == []


def test_odd_seat_names_are_not_walked(fedora):
    note(fedora, "", "ok", seat="..")
    note(fedora, "", "ok", seat="notaseat")
    assert lg.read_notes(fedora) == []


# ---- the guard -----------------------------------------------------------------------------

def guard(paths) -> str:
    return lg.guard_boot(paths)


@needs_dconf
def test_guard_kernel_argument_turns_it_off(fedora):
    before = snapshot(Path(fedora.root))
    assert on(fedora)[0] == 0
    Path(fedora.cmdline).write_text("ro quiet fedora-glass-login=off\n")
    assert guard(fedora) == "off: kernel-arg"
    assert snapshot(Path(fedora.root)) == {**before, "proc/cmdline": snapshot(Path(fedora.root))["proc/cmdline"]}
    assert lg.status(fedora)["stopped"] == "kernel-arg"


@needs_dconf
def test_guard_a_similar_kernel_word_is_not_the_switch(fedora):
    assert on(fedora)[0] == 0
    Path(fedora.cmdline).write_text("ro xfedora-glass-login=off fedora-glass-login=offx\n")
    assert guard(fedora) == "trial"


@needs_dconf
def test_guard_new_gnome_not_supported_turns_it_off_with_that_reason(fedora):
    assert on(fedora)[0] == 0
    script(Path(fedora.root) / "usr/bin/gnome-shell", 'echo "GNOME Shell 52.0"')
    assert guard(fedora) == "off: gnome-version"
    assert lg.status(fedora)["stopped"] == "gnome-version"
    assert lg.switch_gone(fedora) == [] and effective(fedora) == ""


@needs_dconf
def test_guard_add_on_gone_turns_it_off_as_an_error(fedora):
    assert on(fedora)[0] == 0
    shutil.rmtree(fedora.addon)
    assert guard(fedora) == "off: error"
    assert effective(fedora) == ""


@needs_dconf
@pytest.mark.parametrize("phase,boot,off", [("safe", BOOT_A, True), ("error", BOOT_A, True),
                                            ("starting", BOOT_B, True), ("starting", BOOT_A, False),
                                            ("ok", BOOT_B, False)])
def test_guard_crash_notes(fedora, phase, boot, off):
    assert on(fedora)[0] == 0
    note(fedora, state(fedora)["token"], phase, boot=boot)
    assert (guard(fedora) == "off: crash") == off


@needs_dconf
def test_guard_ignores_notes_of_another_token(fedora):
    assert on(fedora)[0] == 0
    note(fedora, "ef" * 16, "safe")
    assert guard(fedora) == "trial"


@needs_dconf
def test_guard_a_hostile_link_to_a_crash_note_changes_nothing(tmp_path, fedora):
    assert on(fedora)[0] == 0
    other = tmp_path / "other"
    other.mkdir()
    (other / "health.json").write_text(json.dumps({"v": 1, "token": state(fedora)["token"], "boot": BOOT_A,
                                                   "phase": "safe", "verified": ""}))
    d = Path(fedora.root) / "var/lib/gdm/seat0/state/fedora-glass-login"
    d.mkdir(parents=True)
    os.symlink(other / "health.json", d / "health.json")
    assert guard(fedora) == "trial"


@needs_dconf
def test_guard_trial_ends_with_a_login_through_the_glass(fedora):
    assert on(fedora)[0] == 0
    assert guard(fedora) == "trial"
    s = state(fedora)
    assert s["trial_boots"] == 1 and s["last_boot"] == BOOT_A
    reboot(fedora, BOOT_B)
    note(fedora, s["token"], "ok", boot=BOOT_A, verified=s["token"])
    assert guard(fedora) == "on"
    assert state(fedora)["state"] == "on" and not os.path.exists(fedora.trial)
    assert lg.status(fedora)["state"] == "on"


@needs_dconf
def test_guard_trial_without_a_login_turns_it_off_at_the_second_boot(fedora):
    before = snapshot(Path(fedora.root))
    assert on(fedora)[0] == 0
    assert guard(fedora) == "trial"
    reboot(fedora, BOOT_B)
    note(fedora, state(fedora)["token"], "ok", boot=BOOT_A)      # the glass ran, but nobody got in
    assert guard(fedora) == "off: no-login"
    after = snapshot(Path(fedora.root))
    assert {k: v for k, v in after.items() if not k.startswith(("var/lib/gdm", "proc"))} == \
        {k: v for k, v in before.items() if not k.startswith(("var/lib/gdm", "proc"))}
    assert lg.status(fedora)["stopped"] == "no-login"


@needs_dconf
@pytest.mark.parametrize("conf", ["/etc/gdm/custom.conf", "/etc/gdm3/custom.conf"])
def test_guard_trial_waits_while_gdm_logs_in_by_itself(fedora, conf):
    f = Path(fedora.p(conf))
    f.parent.mkdir(parents=True)
    f.write_text("# GDM\n[daemon]\n  AutomaticLoginEnable = True\nAutomaticLogin=dino\n[security]\n")
    assert on(fedora)[0] == 0
    for b in (BOOT_A, BOOT_B, BOOT_A):
        reboot(fedora, b)
        assert guard(fedora) == "trial (automatic login)"
    assert state(fedora)["trial_boots"] == 0


def test_automatic_login_needs_both_keys_in_the_daemon_section(fedora):
    f = Path(fedora.p("/etc/gdm/custom.conf"))
    f.parent.mkdir(parents=True)
    for text, want in (("[daemon]\nAutomaticLoginEnable=true\n", False),
                       ("[daemon]\nAutomaticLogin=dino\n", False),
                       ("[security]\nAutomaticLoginEnable=true\nAutomaticLogin=dino\n", False),
                       ("[daemon]\nAutomaticLoginEnable=false\nAutomaticLogin=dino\n", False),
                       ("[Daemon]\nautomaticloginenable=1\nAutomaticLogin = dino\n", True),
                       ("[daemon]\nTimedLoginEnable=true\nTimedLogin=dino\n", True),
                       ("\xff garbage\n[daemon\n", False)):
        f.write_text(text)
        assert lg.automatic_login(fedora) is want, text


@needs_dconf
def test_guard_on_counts_silent_boots_and_stops_at_three(fedora):
    assert on(fedora)[0] == 0
    token = state(fedora)["token"]
    note(fedora, token, "ok", verified=token)
    assert guard(fedora) == "on"
    boots = [BOOT_B, BOOT_A, BOOT_B, BOOT_A]
    # A login screen that ran last boot resets the count.
    reboot(fedora, boots[0])
    note(fedora, token, "ok", boot=BOOT_A)
    assert guard(fedora) == "kept" and state(fedora)["silent_boots"] == 0
    shutil.rmtree(Path(fedora.root) / "var/lib/gdm")
    for i, b in enumerate(boots[1:], 1):
        reboot(fedora, b)
        got = guard(fedora)
        if i < 3:
            assert got == "kept" and state(fedora)["silent_boots"] == i
        else:
            assert got == "off: silent"


@needs_dconf
def test_guard_on_with_automatic_login_is_not_silent(fedora):
    assert on(fedora)[0] == 0
    token = state(fedora)["token"]
    note(fedora, token, "ok", verified=token)
    assert guard(fedora) == "on"
    shutil.rmtree(Path(fedora.root) / "var/lib/gdm")
    f = Path(fedora.p("/etc/gdm/custom.conf"))
    f.parent.mkdir(parents=True)
    f.write_text("[daemon]\nAutomaticLoginEnable=true\nAutomaticLogin=dino\n")
    for b in (BOOT_B, BOOT_A, BOOT_B, BOOT_A):
        reboot(fedora, b)
        assert guard(fedora) == "kept"
    assert state(fedora)["silent_boots"] == 0


@needs_dconf
def test_guard_a_new_add_on_starts_a_new_trial(fedora):
    assert on(fedora)[0] == 0
    s = state(fedora)
    note(fedora, s["token"], "ok", verified=s["token"])
    assert guard(fedora) == "on"
    (Path(fedora.addon) / "extension.js").write_text("export default class { /* 2 */ }\n")
    reboot(fedora, BOOT_B)
    assert guard(fedora) == "new trial"
    s2 = state(fedora)
    assert s2["token"] != s["token"] and s2["state"] == "trial" and s2["trial_boots"] == 0
    assert os.path.exists(fedora.trial)
    assert json.loads((Path(fedora.conf_dir) / "look.json").read_text())["token"] == s2["token"]
    # The old token's notes (verified) do not end the new trial.
    reboot(fedora, BOOT_A)
    assert guard(fedora) == "trial"


@needs_dconf
def test_guard_heals_deleted_or_edited_files(fedora):
    assert on(fedora)[0] == 0
    root = Path(fedora.root)
    want = snapshot(root)
    (Path(fedora.conf_dir) / "look.json").write_text('{"evil": 1}')
    (Path(fedora.conf_dir) / "picture.jpg").unlink()
    (root / "etc/dconf/db/gdm.d" / lg.OUR_FILE).write_text("[org/gnome/shell]\nenabled-extensions=@as []\n")
    (root / "etc/dconf/db/gdm.d/locks" / lg.OUR_FILE).unlink()
    assert guard(fedora) == "trial"
    assert snapshot(root) == want
    assert UUID in effective(fedora)


@needs_dconf
def test_guard_follows_a_distro_profile_change(tmp_path):
    paths = make_system(tmp_path / "root", "ubuntu")
    assert on(paths)[0] == 0
    root = Path(paths.root)
    assert state(paths)["route"] == "b"
    # A distro update now reads a system db, like Fedora: the switch moves there.
    (root / "usr/share/dconf/profile/gdm").write_text(PROFILES["fedora"].replace("/usr/share/gdm", "/var/lib/gdm3"))
    (root / "etc/dconf/db/gdm.d/locks").mkdir(parents=True)
    assert guard(paths) == "trial"
    assert state(paths)["route"] == "a"
    assert not (root / "etc/dconf/profile/gdm").exists()
    assert not (root / f"etc/dconf/db/{lg.OWN_DB}").exists()
    assert UUID in effective(paths)
    assert lg.turn_off(paths) == []
    assert lg.switch_gone(paths) == [] and effective(paths) == ""


@needs_dconf
def test_guard_follows_a_distro_profile_edit_on_route_b(tmp_path):
    paths = make_system(tmp_path / "root", "arch")
    assert on(paths)[0] == 0
    root = Path(paths.root)
    new = "user-db:user\nfile-db:/usr/share/gdm/greeter-dconf-defaults\n# updated\n"
    (root / "usr/share/dconf/profile/gdm").write_text(new)
    assert guard(paths) == "trial"
    assert (root / "etc/dconf/profile/gdm").read_text() == lg.with_our_line(new)
    assert lg.turn_off(paths) == []
    assert not (root / "etc/dconf/profile/gdm").exists()


@needs_dconf
def test_guard_turns_it_off_when_a_new_admin_setting_blocks_it(fedora):
    assert on(fedora)[0] == 0
    compile_db(Path(fedora.root) / FILE_DB["fedora"], "[org/gnome/shell]\nenabled-extensions=['x@y']\n",
               "/org/gnome/shell/enabled-extensions\n")
    assert guard(fedora) == "off: error"
    assert lg.switch_gone(fedora) == []


@needs_dconf
def test_guard_garbled_state_turns_it_off(fedora):
    assert on(fedora)[0] == 0
    s = state(fedora)
    s["values"]["blur"] = 5000
    Path(fedora.state).write_text(json.dumps(s))
    assert guard(fedora) == "off: error"
    assert lg.switch_gone(fedora) == [] and not os.path.exists(fedora.state)


@needs_dconf
def test_guard_an_unexpected_exception_turns_it_off(fedora, monkeypatch):
    assert on(fedora)[0] == 0
    monkeypatch.setattr(lg, "read_notes", lambda paths: 1 / 0)
    assert guard(fedora) == "off: error"
    assert lg.switch_gone(fedora) == []


def test_guard_with_nothing_on_does_nothing(fedora):
    before = snapshot(Path(fedora.root))
    assert guard(fedora) == "nothing"
    assert snapshot(Path(fedora.root)) == before


@needs_dconf
def test_guard_check(fedora):
    assert on(fedora)[0] == 0
    token = state(fedora)["token"]
    assert lg.guard_check(fedora) == "nothing"
    note(fedora, token, "ok")
    assert lg.guard_check(fedora) == "nothing"
    note(fedora, token, "ok", verified=token)
    assert lg.guard_check(fedora) == "on"
    assert state(fedora)["state"] == "on" and not os.path.exists(fedora.trial)
    assert lg.guard_check(fedora) == "nothing"


@needs_dconf
def test_guard_check_crash_note(fedora):
    assert on(fedora)[0] == 0
    note(fedora, state(fedora)["token"], "safe")
    assert lg.guard_check(fedora) == "off: crash"
    assert lg.switch_gone(fedora) == []


@pytest.mark.parametrize("out,want", [
    (b"GNOME Shell 51.0\n", ("51", "51.0")), (b"GNOME Shell 51.1\n", ("51", "51.1")),
    (b"GNOME Shell 51\n", ("51", "51")), (b"GNOME Shell 52.beta\n", ("52", "52.beta")),
    (b"GNOME Shell 51.0~rc+git20261101\n", ("51", "51.0~rc+git20261101")),
    (b"GNOME Shell 51.0.1.2.3.4.5.6.7.8.9.10\n", ("", "")), (b"GNOME Shell 51.0 extra\n", ("", "")),
    (b"GNOME Shell 51.0'\n", ("", "")), (b"gnome-shell 51.0\n", ("", "")), (b"", ("", "")),
    (b"GNOME Shell .51\n", ("", "")),
])
def test_the_gnome_version_is_read_strictly(tmp_path, out, want):
    sh = tmp_path / "usr/bin/gnome-shell"
    sh.parent.mkdir(parents=True)
    (tmp_path / "out").write_bytes(out)
    script(sh, f"cat {tmp_path / 'out'}")
    assert lg.gnome_version(lg.Paths(str(tmp_path))) == want


@needs_dconf
def test_guard_a_gnome_point_release_starts_a_new_trial(fedora):
    assert on(fedora)[0] == 0
    s = state(fedora)
    assert (s["gnome"], s["gnome_full"]) == ("51", "51.0")
    note(fedora, s["token"], "ok", verified=s["token"])
    assert guard(fedora) == "on"
    script(Path(fedora.root) / "usr/bin/gnome-shell", 'echo "GNOME Shell 51.1"')
    reboot(fedora, BOOT_B)
    assert guard(fedora) == "new trial"
    s2 = state(fedora)
    assert s2["token"] != s["token"] and s2["state"] == "trial" and s2["gnome_full"] == "51.1"
    reboot(fedora, BOOT_A)
    assert guard(fedora) == "trial"


@needs_dconf
def test_on_after_a_gnome_point_release_is_a_new_start(fedora):
    assert on(fedora)[0] == 0
    token = state(fedora)["token"]
    assert on(fedora, accent="#00ff00")[0] == 0 and state(fedora)["token"] == token
    script(Path(fedora.root) / "usr/bin/gnome-shell", 'echo "GNOME Shell 51.2"')
    assert on(fedora, accent="#00ff00")[0] == 0
    assert state(fedora)["token"] != token and state(fedora)["gnome_full"] == "51.2"


@needs_dconf
def test_a_state_file_without_the_full_version_reads_as_a_version_change(fedora):
    assert on(fedora)[0] == 0
    s = state(fedora)
    note(fedora, s["token"], "ok", verified=s["token"])
    assert guard(fedora) == "on"
    s = state(fedora)
    del s["gnome_full"]
    Path(fedora.state).write_text(json.dumps(s))
    assert lg.status(fedora)["state"] == "on"           # still read, not garbled
    reboot(fedora, BOOT_B)
    assert guard(fedora) == "new trial"
    assert state(fedora)["gnome_full"] == "51.0"


@needs_dconf
def test_guard_off_finishes_when_the_etc_folder_is_a_mount_point(fedora, monkeypatch):
    """Under ProtectSystem=strict /etc/fedora-glass is a bind mount: rmdir gives EBUSY. That
    must not stop off (state.json gone, stopped.json written) nor count as a problem."""
    assert on(fedora)[0] == 0
    real_rmdir = os.rmdir

    def busy(path, *a, **kw):
        if os.path.abspath(str(path)) == os.path.abspath(fedora.conf_parent):
            raise OSError(16, "Device or resource busy", str(path))
        return real_rmdir(path, *a, **kw)
    monkeypatch.setattr(os, "rmdir", busy)
    Path(fedora.cmdline).write_text("fedora-glass-login=off\n")
    with lg.Lock(fedora):
        assert lg._off_locked(fedora, "kernel-arg") == []
    assert not os.path.exists(fedora.state) and lg.status(fedora)["stopped"] == "kernel-arg"
    assert lg.switch_gone(fedora) == [] and not os.path.exists(fedora.conf_dir)
    assert os.path.isdir(fedora.conf_parent)            # only the empty mount point stays


# ---- status and the command line ------------------------------------------------------------

@needs_dconf
def test_status_shape(fedora):
    s = lg.status(fedora)
    assert s == {"version": 1, "available": True, "why": "", "state": "off", "stopped": "", "values": None,
                 "picture_sha256": ""}
    assert on(fedora)[0] == 0
    s = lg.status(fedora)
    assert s["state"] == "trial" and s["values"] == lg.DEFAULTS and s["available"] is True
    assert s["picture_sha256"] == lg.sha256_bytes(JPEG)
    json.dumps(s)


def test_status_when_nothing_is_there(tmp_path):
    (tmp_path / "var/lib").mkdir(parents=True)
    s = lg.status(lg.Paths(str(tmp_path)))
    assert s["available"] is False and s["why"] == "no-gdm" and s["state"] == "off"
    assert set(s) == {"version", "available", "why", "state", "stopped", "values", "picture_sha256"}


@pytest.fixture
def main_root(tmp_path, monkeypatch):
    """main() always works on "/": for these tests its Paths is pointed at a temporary system."""
    paths = make_system(tmp_path / "root", "fedora") if os.access(DCONF, os.X_OK) else None
    real = lg.Paths
    monkeypatch.setattr(lg, "Paths", lambda root="/": real(str(tmp_path / "root")))
    kept = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGHUP)}
    yield paths
    for sig, handler in kept.items():
        signal.signal(sig, handler)


@needs_dconf
def test_a_signal_half_way_rolls_on_back(main_root, monkeypatch):
    if os.geteuid() != 0:
        monkeypatch.setattr(os, "geteuid", lambda: 0)
    root = Path(main_root.root)
    (root / "usr/bin/dconf").unlink()
    # The real db's compile is where systemd's timeout (or a closed terminal) strikes.
    script(root / "usr/bin/dconf", '[ "$1" = compile ] && case "$2" in */etc/dconf/db/.fedora-glass-*) '
           f'kill -TERM $PPID; sleep 0.3;; esac\nexec {DCONF} "$@"')
    before = snapshot(root)
    assert lg.main(["x", "on", "{}"], stdin=io.BytesIO(JPEG)) == 4
    assert snapshot(root) == before


@needs_dconf
def test_a_signal_half_way_through_the_guard_turns_it_off(main_root, monkeypatch):
    if os.geteuid() != 0:
        monkeypatch.setattr(os, "geteuid", lambda: 0)
    root = Path(main_root.root)
    assert on(main_root)[0] == 0
    (root / "etc/fedora-glass/login/look.json").unlink()       # so the guard has something to write
    (root / "etc/dconf/db/gdm.d" / lg.OUR_FILE).write_text("[x]\n")
    (root / "usr/bin/dconf").unlink()
    script(root / "usr/bin/dconf", '[ "$1" = compile ] && case "$2" in */etc/dconf/db/.fedora-glass-*) '
           f'kill -TERM $PPID; sleep 0.3;; esac\nexec {DCONF} "$@"')
    assert lg.main(["x", "guard", "boot"]) == 0
    assert lg.switch_gone(main_root) == [] and not os.path.exists(main_root.state)


def test_main_usage_and_root(main_root, monkeypatch, capsys):
    for argv in ([], ["x"], ["status", "x"], ["on"], ["on", "{}", "x"], ["guard"], ["guard", "now"], ["off", "-f"]):
        assert lg.main(["fedora-glass-login", *argv]) == 2
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    for argv in (["off"], ["on", "{}"], ["guard", "boot"], ["guard", "check"]):
        assert lg.main(["fedora-glass-login", *argv]) == 77


@needs_dconf
def test_main_exit_codes(main_root, monkeypatch, capsys):
    if os.geteuid() != 0:
        monkeypatch.setattr(os, "geteuid", lambda: 0)
    assert lg.main(["x", "status"]) == 0
    assert json.loads(capsys.readouterr().out)["available"] is True
    assert lg.main(["x", "on", '{"blur": "a lot"}'], stdin=io.BytesIO(JPEG)) == 2
    assert lg.main(["x", "on", "{}"], stdin=io.BytesIO(b"GIF89a")) == 2
    assert lg.main(["x", "on", "{}"], stdin=io.BytesIO(b"")) == 2
    assert not os.path.exists(main_root.state)
    capsys.readouterr()
    assert lg.main(["x", "on", '{"accent": "#FF8800"}'], stdin=io.BytesIO(JPEG)) == 0
    assert capsys.readouterr().out.strip() == "trial"
    assert lg.main(["x", "on", '{"picture": "glow"}'], stdin=io.BytesIO(b"")) == 0
    assert lg.main(["x", "guard", "boot"]) == 0
    assert lg.main(["x", "guard", "check"]) == 0
    assert lg.main(["x", "off"]) == 0
    assert lg.main(["x", "off"]) == 0
    shutil.rmtree(main_root.addon)
    capsys.readouterr()
    assert lg.main(["x", "on", "{}"], stdin=io.BytesIO(JPEG)) == 3
    assert capsys.readouterr().out.strip() == "no-addon"


def test_main_sets_the_umask(main_root, monkeypatch):
    old = os.umask(0o077)
    try:
        lg.main(["x"])
        assert os.umask(0o077) == 0o022
    finally:
        os.umask(old)


def test_the_helper_runs_isolated_and_on_its_own():
    text = Path(lg.__file__).read_text()
    assert text.startswith("#!/usr/bin/python3 -IS\n")
    imports = {line.split()[1].split(".")[0] for line in text.splitlines() if line.startswith(("import ", "from "))}
    assert imports <= {"__future__", "fcntl", "hashlib", "json", "math", "os", "re", "secrets", "shutil", "signal",
                       "stat", "subprocess", "sys", "tempfile", "time"}
    assert "os.environ" not in text and "shell=True" not in text and "getenv" not in text


def test_the_cli_login_screen_off_needs_root_and_runs_the_helper(monkeypatch, capsys):
    from fedoraglass import __main__ as cli
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    assert cli.main(["login-screen", "off"]) == 1
    assert "Run: sudo fedora-glass login-screen off" in capsys.readouterr().out
    ran = []
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "execv", lambda path, args: ran.append((path, args)) or 0)
    monkeypatch.setattr(os.path, "exists", lambda p: True)
    cli.main(["login-screen", "off"])
    assert ran == [("/usr/libexec/fedora-glass-login", ["/usr/libexec/fedora-glass-login", "off"])]


@pytest.mark.parametrize("st,words", [
    ({"available": True, "why": "", "state": "off", "stopped": "", "values": None}, "off"),
    ({"available": True, "why": "", "state": "trial", "stopped": "", "values": {}}, "trial"),
    ({"available": True, "why": "", "state": "on", "stopped": "", "values": {}}, "on"),
    ({"available": False, "why": "not-gdm", "state": "off", "stopped": "crash", "values": None}, "did not start"),
])
def test_the_cli_login_screen_status_summary(monkeypatch, capsys, st, words):
    from fedoraglass import __main__ as cli
    monkeypatch.setattr(lg, "status", lambda paths: {"version": 1, "picture_sha256": "", **st})
    assert cli.main(["login-screen", "status"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Glass login screen:") and words in out.lower()
