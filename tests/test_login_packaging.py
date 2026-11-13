"""The glass login screen in the three packages: the same files at the same places with the
same modes (install-tree.sh for deb and Arch, the spec for rpm), the removal steps run only
on a real removal, and the weak dependency on dconf. No root needed.

Another part of the work writes the login helper, the add-on and the units. A test tree is
a copy of the repository, and a source that does not exist yet is replaced by a small stub
in that COPY (never in the repository), so these checks run before the real files exist.
test_the_real_sources_exist is the one that needs the real ones.
"""
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packaging"
UUID = "fedora-glass-login@djshiye.github.io"
ADDON_SRC = Path("fedoraglass/data/login-extension") / UUID
SHARED_LIST = Path("fedoraglass/data/login-extension/shared-modules.txt")
EXT_SRC = Path("fedoraglass/data/extension/liquid-glass@djshiye.github.io")
UNITS = ("fedora-glass-login-guard.service", "fedora-glass-login-guard-check.path",
         "fedora-glass-login-guard-check.service")
LINKED = ("fedora-glass-login-guard.service", "fedora-glass-login-guard-check.path")

HELPER = "usr/libexec/fedora-glass-login"
ADDON = f"usr/share/gdm/greeter/gnome-shell/extensions/{UUID}"
UNIT_DIR = "usr/lib/systemd/system"
MACROS = {"%{_libexecdir}": "/usr/libexec", "%{_datadir}": "/usr/share", "%{_unitdir}": "/usr/lib/systemd/system",
          "%{buildroot}": ""}


def _copy_tree(work: Path):
    """A copy of what install-tree.sh needs. Returns the list of sources that were stubbed."""
    for name in ("fedoraglass", "data", "packaging", "LICENSE", "LICENSES", "THIRD-PARTY-NOTICES.md"):
        src = ROOT / name
        if src.is_dir():
            shutil.copytree(src, work / name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy(src, work / name)
    stubbed = []

    def stub(rel, text):
        path = work / rel
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            stubbed.append(str(rel))

    stub("fedoraglass/login_glass.py", "#!/usr/bin/python3 -I -S\n")
    stub(ADDON_SRC / "metadata.json", "{}\n")
    stub(ADDON_SRC / "extension.js", "// stub\n")
    stub(ADDON_SRC / "sub/more.js", "// stub\n")
    existing = sorted(p.name for p in (work / EXT_SRC).glob("*.js"))[:2]
    stub(SHARED_LIST, "# stub list\n\n" + "\n".join(f"{n}  # why" for n in existing) + "\n")
    for u in UNITS:
        stub(f"data/systemd/{u}", "[Unit]\nDescription=stub\n")
    return stubbed


def _build(work: Path, dest: Path):
    return subprocess.run(["sh", str(work / "packaging/install-tree.sh"), str(work), str(dest)],
                          capture_output=True, text=True, timeout=300)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    base = tmp_path_factory.mktemp("login-pkg")
    work, dest = base / "src", base / "dest"
    work.mkdir()
    stubbed = _copy_tree(work)
    r = _build(work, dest)
    assert r.returncode == 0, r.stderr
    return work, dest, stubbed


def _mode(p: Path) -> int:
    return stat.S_IMODE(p.lstat().st_mode)


def _shared_names(work: Path):
    names = []
    for line in (work / SHARED_LIST).read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.append(line)
    return names


def test_the_real_sources_exist():
    """The package names these; if one is missing the build above only worked on a stub."""
    assert (ROOT / "fedoraglass/login_glass.py").is_file()
    assert (ROOT / ADDON_SRC / "metadata.json").is_file()
    assert (ROOT / ADDON_SRC / "extension.js").is_file()
    assert (ROOT / SHARED_LIST).is_file()
    for u in UNITS:
        assert (ROOT / "data/systemd" / u).is_file(), u
    for name in _shared_names(ROOT):
        assert (ROOT / EXT_SRC / name).is_file(), name


def test_tree_has_the_helper_the_addon_and_the_units(built):
    work, dest, _ = built
    helper = dest / HELPER
    assert helper.is_file() and not helper.is_symlink() and _mode(helper) == 0o755
    addon = dest / ADDON
    assert addon.is_dir() and _mode(addon) == 0o755
    assert (addon / "metadata.json").is_file() and (addon / "extension.js").is_file()
    # Everything from the add-on's source folder is in, with the same relative paths.
    for src in (work / ADDON_SRC).rglob("*"):
        if src.is_file() and src.suffix != ".pyc":
            assert (addon / src.relative_to(work / ADDON_SRC)).is_file(), src
    # Every shared module, copied from the desktop extension, byte for byte.
    names = _shared_names(work)
    assert names, "the list names at least one module"
    for name in names:
        got = addon / name
        assert got.is_file() and _mode(got) == 0o644, name
        assert got.read_bytes() == (work / EXT_SRC / name).read_bytes(), name
    assert not (addon / "shared-modules.txt").exists()
    # 0644 files, 0755 folders, nothing else, no byte code.
    for p in addon.rglob("*"):
        assert not p.is_symlink(), p
        assert _mode(p) == (0o755 if p.is_dir() else 0o644), p
        assert "__pycache__" not in p.parts
    for u in UNITS:
        f = dest / UNIT_DIR / u
        assert f.is_file() and not f.is_symlink() and _mode(f) == 0o644, u
        assert f.read_bytes() == (work / "data/systemd" / u).read_bytes(), u
    wants = dest / UNIT_DIR / "graphical.target.wants"
    assert sorted(p.name for p in wants.iterdir()) == sorted(LINKED)
    for u in LINKED:
        link = wants / u
        assert link.is_symlink() and os.readlink(link) == f"../{u}"
        assert link.resolve() == (dest / UNIT_DIR / u).resolve()


def test_the_polkit_file_is_still_installed(built):
    work, dest, _ = built
    f = dest / "usr/share/polkit-1/actions/io.github.djshiye.LiquidGlass.policy"
    assert f.is_file() and _mode(f) == 0o644
    assert (dest / "usr/libexec/liquid-glass-login-screen").is_file()   # the old painted glass stays


def test_a_missing_shared_module_stops_the_build(tmp_path):
    work = tmp_path / "src"
    work.mkdir()
    _copy_tree(work)
    (work / SHARED_LIST).write_text("# list\nno-such-module.js\n")
    r = _build(work, tmp_path / "dest")
    assert r.returncode != 0 and "no-such-module.js" in r.stderr


@pytest.mark.parametrize("line", ["../escape.js", "sub/x.js", ".hidden.js"])
def test_a_shared_name_cannot_leave_the_folder(tmp_path, line):
    work = tmp_path / "src"
    work.mkdir()
    _copy_tree(work)
    (work / SHARED_LIST).write_text(line + "\n")
    r = _build(work, tmp_path / "dest")
    assert r.returncode != 0 and "bad name" in r.stderr


def test_an_empty_shared_list_stops_the_build(tmp_path):
    work = tmp_path / "src"
    work.mkdir()
    _copy_tree(work)
    (work / SHARED_LIST).write_text("# nothing\n\n   \n")
    assert _build(work, tmp_path / "dest").returncode != 0


# ---- the rpm spec ----------------------------------------------------------------------

def _spec():
    return (PKG / "fedora-glass.spec").read_text()


def _expand(text: str) -> str:
    for k, v in MACROS.items():
        text = text.replace(k, v)
    return text


def _section(spec: str, header: str) -> str:
    """The text after a line equal to `header` up to the next %-directive at line start
    that starts a new section."""
    head = re.search(rf"^{re.escape(header)}$", spec, re.M)
    assert head, header
    rest = spec[head.end():]
    nxt = re.search(r"^%(?:package|description|prep|build|install|check|pre|post|preun|postun|posttrans|"
                    r"trigger\w*|files|changelog)\b", rest, re.M)
    return rest[:nxt.start()] if nxt else rest


def _login_files(block: str):
    out = set()
    for line in _expand(block).splitlines():
        line = line.strip()
        if "fedora-glass-login" in line and line.startswith("/"):
            out.add(line)
    return out


EXPECTED_FILES = {
    "/usr/libexec/fedora-glass-login",
    f"/usr/share/gdm/greeter/gnome-shell/extensions/{UUID}/",
    "/usr/lib/systemd/system/fedora-glass-login-guard.service",
    "/usr/lib/systemd/system/fedora-glass-login-guard-check.path",
    "/usr/lib/systemd/system/fedora-glass-login-guard-check.service",
    "/usr/lib/systemd/system/graphical.target.wants/fedora-glass-login-guard.service",
    "/usr/lib/systemd/system/graphical.target.wants/fedora-glass-login-guard-check.path",
}


def test_both_rpm_packages_list_the_same_login_files():
    spec = _spec()
    main, bridge = _section(spec, "%files"), _section(spec, "%files -n liquid-glass")
    assert _login_files(main) == EXPECTED_FILES
    # The old-name package is the same app by design (it carries all of the main package's
    # files, so the app it shows can use the feature), and fedora-glass replaces it.
    assert _login_files(bridge) == EXPECTED_FILES


def test_the_rpm_install_makes_every_file_the_tree_makes():
    inst = _expand(_section(spec := _spec(), "%install"))
    assert spec.count("%install\n") == 1
    assert "install -Dm755 fedoraglass/login_glass.py /usr/libexec/fedora-glass-login" in inst
    assert "/usr/share/gdm/greeter/gnome-shell/extensions/$login_ext" in inst and f"login_ext={UUID}" in inst
    assert "fedoraglass/data/login-extension/shared-modules.txt" in inst
    assert "fedoraglass/data/extension/liquid-glass@djshiye.github.io" in inst
    assert "shared module missing" in inst, "the build fails on a missing module"
    for u in UNITS:
        assert u in inst
    assert "install -Dm644 data/systemd/$unit /usr/lib/systemd/system/$unit" in inst
    for u in LINKED:
        assert f"ln -s ../{u} /usr/lib/systemd/system/graphical.target.wants/{u}" in inst
    # The same pieces as install-tree.sh, line for line where it matters.
    tree = (PKG / "install-tree.sh").read_text()
    for needle in ("install -d \"$login_dir\"", "-name '__pycache__'", "chmod 755 {}", "chmod 644 {}",
                   "shared module missing", "bad name in shared-modules.txt", "lists nothing"):
        assert needle in tree
    assert 'install -Dm755 "$src/fedoraglass/login_glass.py" "$dest/usr/libexec/fedora-glass-login"' in tree
    code = lambda t: re.sub(r"(?m)^\s*#.*$", "", t)
    assert "systemctl enable" not in code(tree) and "systemctl enable" not in code(inst)


def test_the_rpm_tree_has_no_enable_scriptlet_for_the_guard():
    spec = _spec()
    for name in ("%post", "%posttrans", "%post -n liquid-glass"):
        text = _section(spec, name) if re.search(rf"^{re.escape(name)}$", spec, re.M) else ""
        assert "login-guard" not in text, name


def test_the_policy_names_both_helpers():
    policy = (ROOT / "data/io.github.djshiye.LiquidGlass.policy").read_text()
    assert "/usr/libexec/liquid-glass-login-screen" in policy
    if "io.github.djshiye.FedoraGlass.login-glass" in policy:
        assert "/usr/libexec/fedora-glass-login" in policy


# ---- removal only, never on an upgrade -------------------------------------------------

OFF = "/usr/libexec/fedora-glass-login off"


def test_rpm_turns_the_login_screen_off_only_on_removal():
    spec = _spec()
    preun = _section(spec, "%preun")
    block = preun.split("if [ $1 -eq 0 ]; then\n", 1)[1].split("\nfi\n", 1)[0]
    assert "%{_libexecdir}/fedora-glass-login off >/dev/null 2>&1 || :" in block
    # before the files go: it is in %preun, not %postun
    assert "fedora-glass-login" not in preun.replace(block, "")
    # the old helper's undo is still there, unchanged
    assert "%{_libexecdir}/liquid-glass-login-screen undo >/dev/null 2>&1 || :" in block
    for name in ("%post", "%postun", "%posttrans", "%post -n liquid-glass"):
        assert "fedora-glass-login" not in _section(spec, name), name
    # replacing the old-name package must not turn the new feature off
    assert "login-screen" not in re.sub(r"#.*", "", _section(spec, "%preun -n liquid-glass"))
    # every call to the old helper is kept as it was
    assert "%{_libexecdir}/liquid-glass-login-screen refresh >/dev/null 2>&1 || :" in _section(spec, "%posttrans")


def test_deb_turns_the_login_screen_off_only_on_removal():
    deb = PKG / "deb"
    prerm = (deb / "prerm").read_text()
    assert prerm.count('if [ "$1" = remove ]; then') == 1
    block = prerm.split('if [ "$1" = remove ]; then\n', 1)[1].split("\nfi\n", 1)[0]
    assert f"{OFF} >/dev/null 2>&1 || :" in block
    assert "/usr/libexec/liquid-glass-login-screen undo >/dev/null 2>&1 || :" in block
    assert "fedora-glass-login" not in prerm.replace(block, "")
    for name in ("postinst", "postrm", "preinst"):
        assert "fedora-glass-login" not in (deb / name).read_text(), name


def test_arch_turns_the_login_screen_off_only_on_removal():
    text = (PKG / "arch/fedora-glass.install").read_text()
    funcs = dict(re.findall(r"^(\w+)\(\) \{\n(.*?)^\}", text, re.M | re.S))
    assert f"{OFF} >/dev/null 2>&1 || :" in funcs["pre_remove"]
    assert "/usr/libexec/liquid-glass-login-screen undo >/dev/null 2>&1 || :" in funcs["pre_remove"]
    for name, body in funcs.items():
        if name != "pre_remove":
            assert "fedora-glass-login" not in body, name
    assert "pre_upgrade" not in funcs
    assert "/usr/libexec/liquid-glass-login-screen refresh >/dev/null 2>&1 || :" in funcs["post_upgrade"]


def test_no_scriptlet_enables_or_starts_the_guard():
    for f in (PKG / "deb/postinst", PKG / "deb/prerm", PKG / "arch/fedora-glass.install"):
        assert "login-guard" not in f.read_text(), f


# ---- dconf, as a weak dependency -------------------------------------------------------

def test_dconf_is_recommended_in_every_format():
    spec = _spec()
    assert spec.count("Recommends:     dconf\n") == 2          # fedora-glass and the old-name package
    control = (PKG / "deb/control.in").read_text()
    assert re.search(r"^Recommends:.*\bdconf-cli\b", control, re.M)
    assert not re.search(r"^Depends:.*dconf", control, re.M)
    pkgbuild = (PKG / "arch/PKGBUILD").read_text()
    assert re.search(r"optdepends=\(.*?'dconf:", pkgbuild, re.S)
    assert not re.search(r"^depends=\(.*'dconf'", pkgbuild, re.M | re.S)


def test_the_smoke_check_looks_at_the_login_screen_parts():
    smoke = (ROOT / "qa/package-smoke.sh").read_text()
    for needle in ("/usr/libexec/fedora-glass-login", "root 755", "metadata.json", "extension.js", "shared-modules.txt",
                   "graphical.target.wants", "fedora-glass-login-guard-check.path", '"off"'):
        assert needle in smoke, needle
