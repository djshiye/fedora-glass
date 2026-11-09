"""Fedora Glass on Fedora, Ubuntu and Arch: the right commands, packages and repositories."""
from __future__ import annotations

import gzip
import io
import lzma
import re
import tarfile
from pathlib import Path

import pytest

from fedoraglass import distro, login_screen
from fedoraglass.targets import gtk as tg

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packaging"


@pytest.mark.parametrize("text, family", [
    ('ID=fedora\nVERSION_ID=45\n', "fedora"),
    ('ID=ubuntu\nID_LIKE=debian\nVERSION_ID="26.10"\n', "debian"),
    ('ID=pop\nID_LIKE="ubuntu debian"\n', "debian"),
    ('ID=arch\n', "arch"),
    ('ID=endeavouros\nID_LIKE=arch\n', "arch"),
    ('ID=nixos\n', "other"),
])
def test_os_release(tmp_path, text, family):
    f = tmp_path / "os-release"
    f.write_text(text)
    assert distro.from_os_release(distro._read_os_release([f])).family == family


def test_hints_per_linux():
    assert distro.FEDORA.hint("kvantum") == "sudo dnf install kvantum"
    assert distro.DEBIAN.hint("kvantum") == "sudo apt install qt6-style-kvantum"
    assert distro.ARCH.hint("kvantum") == "sudo pacman -S kvantum"
    assert distro.DEBIAN.hint("adw-gtk3") == ""            # not packaged by Ubuntu
    assert distro.ARCH.remove_command() == "sudo pacman -R fedora-glass"
    assert distro.DEBIAN.manager == "/usr/bin/apt-get" and distro.ARCH.manager == "/usr/bin/pacman"


def test_gtk3_note_follows_the_linux(monkeypatch):
    monkeypatch.setattr(distro, "current", lambda: distro.ARCH)
    assert tg.gtk3_partial() == "Some GTK 3 details need adw-gtk3: sudo pacman -S adw-gtk-theme"
    monkeypatch.setattr(distro, "current", lambda: distro.DEBIAN)
    assert "adw-gtk3" in tg.gtk3_partial() and "sudo" not in tg.gtk3_partial()


def test_no_fedora_only_commands_left_in_messages():
    """Every "sudo dnf ..." a user can see goes through distro (the RPM-only spec and the
    Fedora list in distro.py are the exceptions)."""
    hits = []
    for p in (ROOT / "fedoraglass").rglob("*"):
        if p.suffix in (".py", ".qml", ".js") and p.name != "distro.py" and "/tests/" not in str(p):
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if "sudo dnf" in line and not line.lstrip().startswith(("#", "//", "return \"sudo dnf reinstall")):
                    hits.append(f"{p.relative_to(ROOT)}:{n}")
    assert hits == []


def test_login_screen_reinstall_hint(tmp_path):
    f = tmp_path / "os-release"
    f.write_text("ID=arch\n")
    assert login_screen.reinstall_hint(str(f)) == "sudo pacman -S gnome-shell"
    f.write_text("ID=fedora\n")
    assert login_screen.reinstall_hint(str(f)) == "sudo dnf reinstall gnome-shell"
    f.write_text("ID=ubuntu\nID_LIKE=debian\n")
    assert login_screen.reinstall_hint(str(f), shell_dir=str(tmp_path / "none")).startswith("sudo apt install --reinstall ")


def test_login_screen_accepts_ubuntu_yaru_link(tmp_path):
    """Ubuntu: gdm-theme.gresource -> /etc/alternatives -> theme/Yaru/gnome-shell-theme.gresource."""
    shell = tmp_path / "gnome-shell"
    (shell / "theme/Yaru").mkdir(parents=True)
    yaru = shell / "theme/Yaru/gnome-shell-theme.gresource"
    yaru.write_bytes(b"x")
    (shell / "gnome-shell-theme.gresource").write_bytes(b"y")
    alt = tmp_path / "alternatives"
    alt.mkdir()
    (alt / "gdm-theme.gresource").symlink_to(yaru)
    (shell / "gdm-theme.gresource").symlink_to(alt / "gdm-theme.gresource")
    assert login_screen.target(str(shell)) == str(yaru)
    outside = tmp_path / "evil.gresource"
    outside.write_bytes(b"z")
    (alt / "gdm-theme.gresource").unlink()
    (alt / "gdm-theme.gresource").symlink_to(outside)
    with pytest.raises(login_screen.LoginScreenError):
        login_screen.target(str(shell))


# ---- repository indexes ----------------------------------------------------------------

def _load_repo_index():
    import importlib.util
    spec = importlib.util.spec_from_file_location("repo_index", PKG / "repo_index.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_signer_carries_the_same_repo_index():
    sign = (PKG / "fedora-glass-sign").read_text()
    m = re.search(r"REPO_INDEX_PY=\$\(cat <<'REPO_INDEX_EOF'\n(.*?)REPO_INDEX_EOF\n\)", sign, re.S)
    assert m and m.group(1) == (PKG / "repo_index.py").read_text()


def _tar(files: dict, mode="w") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode=mode) as t:
        for name, data in files.items():
            i = tarfile.TarInfo(name)
            i.size = len(data)
            t.addfile(i, io.BytesIO(data))
    return buf.getvalue()


def _fake_deb(path: Path, version: str):
    control = f"Package: fedora-glass\nVersion: {version}\nArchitecture: all\nDescription: x\n".encode()
    members = [("debian-binary", b"2.0\n"), ("control.tar.xz", lzma.compress(_tar({"./control": control}))),
               ("data.tar.xz", lzma.compress(_tar({})))]
    out = b"!<arch>\n"
    for name, data in members:
        out += f"{name:<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}`\n".encode() + data
        if len(data) & 1:
            out += b"\n"
    path.write_bytes(out)


def _fake_pkg(path: Path, version: str):
    info = (f"pkgname = fedora-glass\npkgbase = fedora-glass\npkgver = {version}\npkgdesc = x\n"
            "arch = any\nsize = 10\ndepend = gnome-shell\ndepend = python\n").encode()
    path.write_bytes(lzma.compress(_tar({".PKGINFO": info})))
    (path.parent / (path.name + ".sig")).write_bytes(b"sig-" + version.encode())


def test_apt_index(tmp_path):
    ri = _load_repo_index()
    _fake_deb(tmp_path / "fedora-glass_1.5.15-1_all.deb", "1.5.15-1")
    _fake_deb(tmp_path / "fedora-glass_1.5.16-1_all.deb", "1.5.16-1")
    assert ri.deb_info(str(tmp_path / "fedora-glass_1.5.16-1_all.deb")) == ("fedora-glass", "1.5.16-1")
    ri.apt_index(str(tmp_path))
    packages = (tmp_path / "Packages").read_bytes()
    assert gzip.decompress((tmp_path / "Packages.gz").read_bytes()) == packages
    assert packages.count(b"Package: fedora-glass") == 2 and b"Filename: ./fedora-glass_1.5.16-1_all.deb" in packages
    import hashlib
    release = (tmp_path / "Release").read_text()
    assert f" {hashlib.sha256(packages).hexdigest()} {len(packages)} Packages\n" in release


def test_arch_db_has_only_the_newest_with_its_signature(tmp_path):
    ri = _load_repo_index()
    for v in ("1.5.9-1", "1.5.15-1", "1.5.16-1"):
        _fake_pkg(tmp_path / f"fedora-glass-{v}-any.pkg.tar.xz", v)
    ri.arch_db(str(tmp_path), "fedora-glass")
    with tarfile.open(tmp_path / "fedora-glass.db") as t:
        names = t.getnames()
        desc = t.extractfile("fedora-glass-1.5.16-1/desc").read().decode()
    assert names == ["fedora-glass-1.5.16-1", "fedora-glass-1.5.16-1/desc"]
    assert "%VERSION%\n1.5.16-1\n" in desc and "%FILENAME%\nfedora-glass-1.5.16-1-any.pkg.tar.xz\n" in desc
    import base64
    assert f"%PGPSIG%\n{base64.b64encode(b'sig-1.5.16-1').decode()}\n" in desc
    assert "%DEPENDS%\ngnome-shell\npython\n" in desc
    assert (tmp_path / "fedora-glass.db.tar.gz").read_bytes() == (tmp_path / "fedora-glass.db").read_bytes()


def test_bad_names_are_refused(tmp_path):
    ri = _load_repo_index()
    _fake_deb(tmp_path / "x.deb", "1.0; rm -rf /")
    with pytest.raises(SystemExit):
        ri.deb_info(str(tmp_path / "x.deb"))


def test_packages_install_the_same_files():
    """The Ubuntu and Arch trees come from install-tree.sh, with the paths the app and the
    polkit policy expect (the RPM spec lays out the same)."""
    tree = (PKG / "install-tree.sh").read_text()
    for path in ("/usr/libexec/liquid-glass-login-screen", "/usr/libexec/fedora-glass-undo-for-users",
                 "/usr/lib/systemd/user/liquid-glass-watch.service", "/usr/share/fedora-glass",
                 "/usr/share/polkit-1/actions/io.github.djshiye.LiquidGlass.policy"):
        assert path in tree, path
    assert "/usr/libexec/liquid-glass-login-screen" in (ROOT / "data/io.github.djshiye.LiquidGlass.policy").read_text()
    sources = (PKG / "deb/fedora-glass.sources").read_text()
    assert "Signed-By: /usr/share/keyrings/fedora-glass.asc" in sources
    assert "packaging/RPM-GPG-KEY-fedora-glass \"$root/usr/share/keyrings/fedora-glass.asc\"" in (PKG / "deb/build-deb.sh").read_text()
    pref = (PKG / "deb/fedora-glass.pref").read_text()
    assert "Pin-Priority: -1" in pref and "Package: fedora-glass\n" in pref
    for script in (PKG / "deb/prerm", PKG / "arch/fedora-glass.install"):
        s = script.read_text()
        assert "fedora-glass-undo-for-users" in s and "liquid-glass-login-screen undo" in s
