"""Fedora Glass on Fedora, Ubuntu and Arch: the right commands, packages and repositories."""
from __future__ import annotations

import gzip
import io
import lzma
import os
import re
import subprocess
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


def test_removing_on_ubuntu_takes_the_repository_entry_too():
    """The repository entry is one of the package's config files: `apt-get remove` keeps
    those, `purge` takes them away. The command the app runs through pkexec, and the one it
    shows for a terminal, both purge."""
    d = distro.DEBIAN
    assert [d.manager, *d.remove_args, "fedora-glass"] == ["/usr/bin/apt-get", "purge", "-y", "fedora-glass"]
    assert d.remove_command() == "sudo apt purge fedora-glass"
    assert distro.FEDORA.remove_args == ("remove", "-y", "--no-autoremove")      # unchanged
    assert distro.ARCH.remove_args == ("-R", "--noconfirm")


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


def _deb_scripts(tmp_path):
    """postinst and postrm of the .deb, pointed at a folder here instead of /etc/apt, with
    stand-ins for systemctl and dpkg-maintscript-helper; returns run(script, *args)."""
    build = (PKG / "deb/build-deb.sh").read_text()
    norm = re.search(r"entries_sum\(\) \{ (sed .*?) \| sha256sum", build).group(1)
    def entries_sum(f):
        return subprocess.run(["sh", "-c", norm.replace('"$1"', '"$0"') + " | sha256sum | cut -d' ' -f1", str(f)],
                              capture_output=True, text=True, check=True).stdout.strip()
    share = tmp_path / "share"
    share.mkdir()
    for name in ("fedora-glass.sources", "fedora-glass.pref"):
        (share / name).write_text((PKG / "deb" / name).read_text())
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    # Remembers whether the watcher is turned on, in tmp_path/watch-enabled.
    (bin_ / "systemctl").write_text(
        f"""#!/bin/sh
state={tmp_path}/watch-enabled
case " $* " in
  *" enable "*) : > "$state" ;;
  *" disable "*) rm -f "$state" ;;
  *" is-enabled "*) [ -e "$state" ]; exit $? ;;
esac
exit 0
""")
    # The real helper deletes what preinst set aside as unchanged; that's all needed here.
    (bin_ / "dpkg-maintscript-helper").write_text(
        "#!/bin/sh\n[ \"$1\" = rm_conffile ] && [ \"$DPKG_MAINTSCRIPT_NAME\" = postinst ] && rm -f \"$2.dpkg-remove\"\nexit 0\n")
    for f in bin_.iterdir():
        f.chmod(0o755)
    def fix(text):
        return (text.replace("/etc/apt/", f"{tmp_path}/etc/apt/")
                    .replace("/usr/share/fedora-glass/apt/", f"{share}/")
                    .replace("/var/lib/fedora-glass", f"{tmp_path}/var/lib/fedora-glass")
                    .replace("@SOURCES_SUM@", entries_sum(PKG / "deb/fedora-glass.sources"))
                    .replace("@PREF_SUM@", entries_sum(PKG / "deb/fedora-glass.pref")))
    scripts = {}
    for name in ("postinst", "prerm", "postrm"):
        scripts[name] = tmp_path / name
        scripts[name].write_text(fix((PKG / "deb" / name).read_text()))
    def run(name, *args):
        out = subprocess.run(["sh", str(scripts[name]), *args], capture_output=True, text=True, timeout=30,
                             env={"PATH": f"{bin_}:/usr/bin:/bin", "DPKG_MAINTSCRIPT_NAME": name,
                                  "DPKG_MAINTSCRIPT_PACKAGE": "fedora-glass"})
        assert out.returncode == 0, out.stderr
        return out.stdout
    return run, tmp_path / "etc/apt/sources.list.d/fedora-glass.sources", \
        tmp_path / "etc/apt/preferences.d/fedora-glass.pref", tmp_path / "var/lib/fedora-glass/apt-entry-removed"


def test_deb_apt_source_is_made_by_the_scripts_not_a_conffile():
    """A conffile outlives `apt remove` while the key it names doesn't, and then every
    `apt update` fails: the source and pin are made by postinst and taken by postrm."""
    build = (PKG / "deb/build-deb.sh").read_text()
    assert "conffiles" not in build.replace("not conffiles", "")
    assert "/etc/apt" not in build.replace("in /etc/apt from here", "")
    assert '"$root/usr/share/fedora-glass/apt/fedora-glass.sources"' in build
    assert '"$root/usr/share/fedora-glass/apt/fedora-glass.pref"' in build
    assert "packaging/deb/preinst packaging/deb/postinst packaging/deb/prerm" in build
    # The move off conffiles, the same in all three scripts.
    for name in ("preinst", "postinst", "postrm"):
        assert 'dpkg-maintscript-helper rm_conffile "$f" 1.5.20~ fedora-glass -- "$@"' in (PKG / "deb" / name).read_text()
    # The same "comments aside" in build-deb.sh, postinst and postrm.
    norm = "sed -e 's/[[:space:]]*$//' -e '/^#/d' -e '/^$/d'"
    for text in (build, (PKG / "deb/postinst").read_text(), (PKG / "deb/postrm").read_text()):
        assert norm in text


def test_deb_apt_source_lifecycle(tmp_path):
    run, src, pref, mark = _deb_scripts(tmp_path)
    ours = (PKG / "deb/fedora-glass.sources").read_text()
    # First install.
    run("postinst", "configure", "")
    assert src.read_text() == ours and pref.read_text() == (PKG / "deb/fedora-glass.pref").read_text()
    # apt remove: both go, so `apt update` keeps working without the key.
    run("postrm", "remove")
    assert not src.exists() and not pref.exists() and mark.exists()
    # Installed again (dpkg passes the last version): back, as we took them away.
    run("postinst", "configure", "1.5.20-1")
    assert src.read_text() == ours and pref.exists() and not mark.exists()
    # You deleted the source: an upgrade doesn't bring it back.
    src.unlink()
    run("postinst", "configure", "1.5.20-1")
    assert not src.exists()
    # ... and removing the package takes the pin too.
    run("postrm", "remove")
    assert not pref.exists() and not mark.exists()
    run("postrm", "purge")
    assert not (tmp_path / "var/lib/fedora-glass").exists()


def test_deb_keeps_a_source_you_changed(tmp_path):
    run, src, pref, mark = _deb_scripts(tmp_path)
    run("postinst", "configure", "")
    src.write_text(src.read_text() + "Enabled: no\n")
    run("postinst", "configure", "1.5.20-1")
    assert src.read_text().endswith("Enabled: no\n")
    # Turned off by you: harmless without the key, so it stays, and so does the pin.
    run("postrm", "remove")
    assert src.exists() and pref.exists()
    # Purge takes everything, as it did when these were conffiles.
    run("postrm", "purge")
    assert not src.exists() and not pref.exists()


def test_deb_turns_off_a_changed_source_that_needs_the_removed_key(tmp_path):
    run, src, pref, mark = _deb_scripts(tmp_path)
    run("postinst", "configure", "")
    src.write_text(src.read_text() + "Architectures: all\n")
    out = run("postrm", "remove")
    disabled = src.with_name(src.name + ".disabled")
    assert not src.exists() and disabled.read_text().endswith("Architectures: all\n")
    assert "turned off" in out and not pref.exists()
    run("postrm", "purge")
    assert not disabled.exists()


def test_deb_first_install_after_the_readme_steps(tmp_path):
    """The README adds the key and the source by hand before `apt install fedora-glass`:
    the same entries without our comments become ours (one entry, no question asked)."""
    run, src, pref, mark = _deb_scripts(tmp_path)
    src.parent.mkdir(parents=True)
    entries = [l for l in (PKG / "deb/fedora-glass.sources").read_text().splitlines()
               if l and not l.startswith("#")]
    src.write_text("\n".join(entries) + "\n")
    run("postinst", "configure", "")
    assert src.read_text() == (PKG / "deb/fedora-glass.sources").read_text() and pref.exists()
    # Paths the README uses: the same as the package's.
    assert "Signed-By: /usr/share/keyrings/fedora-glass.asc\n" in src.read_text()


def test_deb_upgrade_from_conffile_versions(tmp_path):
    """From 1.5.19 and older, preinst sets the old conffiles aside (dpkg-maintscript-helper):
    an unchanged one is replaced by ours, one you changed goes back as you left it."""
    run, src, pref, mark = _deb_scripts(tmp_path)
    src.parent.mkdir(parents=True)
    pref.parent.mkdir(parents=True)
    src.with_name(src.name + ".dpkg-backup").write_text("Types: deb\nEnabled: no\n")
    pref.with_name(pref.name + ".dpkg-remove").write_text((PKG / "deb/fedora-glass.pref").read_text())
    run("postinst", "configure", "1.5.19-1")
    assert src.read_text() == "Types: deb\nEnabled: no\n"
    assert pref.read_text() == (PKG / "deb/fedora-glass.pref").read_text()
    assert not pref.with_name(pref.name + ".dpkg-remove").exists()


def test_rpm_needs_gnome_50_like_the_deb():
    spec = (PKG / "fedora-glass.spec").read_text()
    assert spec.count("Requires:       gnome-shell >= 50~\n") == 2
    assert "Requires:       gnome-shell\n" not in spec
    assert "gnome-shell (>= 50~)" in (PKG / "deb/control.in").read_text()


def _install_sh(tmp_path, fakes, *args):
    bin_ = tmp_path / "fakebin"
    bin_.mkdir(exist_ok=True)
    for name, body in fakes.items():
        (bin_ / name).write_text("#!/bin/sh\n" + body + "\n")
        (bin_ / name).chmod(0o755)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return subprocess.run(["bash", str(ROOT / "install.sh"), *args], capture_output=True, text=True,
                          timeout=120, stdin=subprocess.DEVNULL,
                          env={"PATH": f"{bin_}:/usr/bin:/bin", "HOME": str(home)}), home


@pytest.mark.parametrize("fakes, remove", [
    ({"rpm": '[ "$2" = fedora-glass ]'}, "sudo dnf remove fedora-glass"),
    ({"rpm": "exit 1", "dpkg-query": "printf 'install ok installed'"}, "sudo apt remove fedora-glass"),
    ({"rpm": "exit 1", "dpkg-query": "exit 1", "pacman": '[ "$2" = fedora-glass ]'}, "sudo pacman -R fedora-glass"),
])
def test_install_sh_refuses_when_the_package_is_installed(tmp_path, fakes, remove):
    """A copy in the home folder would take the place of the package's launcher, app-grid
    entry and watcher, and keep running an older Fedora Glass after every update."""
    if os.geteuid() == 0:
        pytest.skip("install.sh refuses root first")
    out, home = _install_sh(tmp_path, fakes, "--no-gui")
    assert out.returncode == 1
    assert "already installed as a package" in out.stdout and remove in out.stdout
    assert "--alongside-package" in out.stdout
    assert not any(home.iterdir())          # nothing written


def test_install_sh_option_for_developers():
    s = (ROOT / "install.sh").read_text()
    assert "--alongside-package) alongside=1;;" in s
    assert 'if [[ -n "$pkg" && $alongside -eq 0 ]]; then' in s
    # A removed package that left its settings behind (dpkg's config-files) doesn't count.
    assert "grep -q 'ok installed'" in s
    # The check comes before anything is installed.
    assert s.index("already installed as a package") < s.index("# ---- system packages")


def test_deb_watcher_comes_back_after_remove_and_install(tmp_path):
    """`apt remove` then `apt install` hands postinst the old version, which looked like an
    upgrade, so the dark/light watcher stayed off. prerm leaves a mark when it was on."""
    run, src, pref, mark = _deb_scripts(tmp_path)
    on = tmp_path / "watch-enabled"
    run("postinst", "configure", "")
    assert on.exists()
    run("prerm", "remove")
    assert not on.exists()
    run("postrm", "remove")
    run("postinst", "configure", "1.5.22-1")
    assert on.exists()
    # The mark is used up: an upgrade after you turned the watcher off keeps it off.
    on.unlink()
    run("postinst", "configure", "1.5.23-1")
    assert not on.exists()
    assert not (tmp_path / "var/lib/fedora-glass/watch-was-on").exists()


def test_deb_watcher_you_turned_off_stays_off_through_remove_and_install(tmp_path):
    run, src, pref, mark = _deb_scripts(tmp_path)
    on = tmp_path / "watch-enabled"
    run("postinst", "configure", "")
    on.unlink()                                     # turned off by the admin
    run("prerm", "remove")
    run("postrm", "remove")
    run("postinst", "configure", "1.5.22-1")
    assert not on.exists()


def test_deb_upgrade_leaves_the_watcher_as_it_is(tmp_path):
    run, src, pref, mark = _deb_scripts(tmp_path)
    on = tmp_path / "watch-enabled"
    run("postinst", "configure", "")
    on.unlink()
    run("prerm", "upgrade", "1.5.23-1")             # prerm upgrade: no mark, no change
    run("postinst", "configure", "1.5.22-1")
    assert not on.exists()


def test_deb_purge_takes_the_watcher_mark(tmp_path):
    run, src, pref, mark = _deb_scripts(tmp_path)
    run("postinst", "configure", "")
    run("prerm", "remove")
    run("postrm", "remove")
    assert (tmp_path / "var/lib/fedora-glass/watch-was-on").exists()
    run("postrm", "purge")
    assert not (tmp_path / "var/lib/fedora-glass").exists()
