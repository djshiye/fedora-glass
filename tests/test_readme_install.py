"""The install blocks in the README: each one pins the signing key's fingerprint and installs
from the signed repository. The Fedora and Ubuntu blocks are run here with fake sudo, curl,
wget, dnf and apt and the real gpg, against the real key and against swapped keys."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()
KEY = ROOT / "packaging" / "RPM-GPG-KEY-fedora-glass"
FPR = "D49A308168257FDBF9D5AE14BD1AC1C6F56A7252"
SITE = "https://djshiye.github.io/fedora-glass"


def _block(distro: str) -> str:
    m = re.search(rf"\*\*{distro}\*\*\n\n```sh\n(.*?)```", README, re.S)
    assert m, distro
    return m.group(1)


def test_every_install_block_pins_the_key_and_uses_the_signed_repository():
    for distro in ("Fedora", "Ubuntu", "Arch Linux"):
        block = _block(distro)
        assert FPR in block, distro
        assert f"{SITE}/RPM-GPG-KEY-fedora-glass" in block, distro
        # Never an unsigned package straight from a GitHub release.
        assert "releases/latest/download" not in block and ".rpm" not in block and ".deb" not in block, distro
    fedora, ubuntu, arch = _block("Fedora"), _block("Ubuntu"), _block("Arch Linux")
    assert "sudo dnf install fedora-glass\n" in fedora and f"baseurl={SITE}/rpms/" in fedora
    for line in ("gpgcheck=1", "repo_gpgcheck=1", "metadata_expire=1h",
                 "gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-fedora-glass", "includepkgs=fedora-glass"):
        assert f"\\n{line}\\n" in fedora, line
    assert "sudo apt install fedora-glass\n" in ubuntu and f"URIs: {SITE}/apt/" in ubuntu
    # The same key path the .deb's own sources file uses, so the two never disagree.
    sources = (ROOT / "packaging/deb/fedora-glass.sources").read_text()
    assert "Signed-By: /usr/share/keyrings/fedora-glass.asc" in sources
    assert "Signed-By: /usr/share/keyrings/fedora-glass.asc\\n" in ubuntu
    # The setup files have their own names: the packages own fedora-glass.repo / .sources.
    assert "/etc/yum.repos.d/fedora-glass-setup.repo" in fedora and "/etc/yum.repos.d/fedora-glass.repo" not in fedora
    assert "/etc/apt/sources.list.d/fedora-glass-setup.sources" in ubuntu
    assert "--lsign-key D49A308168257FDBF9D5AE14BD1AC1C6F56A7252" in arch
    assert "SigLevel = Required DatabaseRequired" in arch
    assert "grep -q '^\\[fedora-glass\\]' /etc/pacman.conf ||" in arch   # pasting it twice adds it once
    # The site serves what the blocks fetch (dnf-repo.yml builds the site).
    pages = (ROOT / ".github/workflows/dnf-repo.yml").read_text()
    assert "cp packaging/fedora-glass.repo packaging/liquid-glass.repo packaging/RPM-GPG-KEY-fedora-glass site/" in pages
    # One chain per block: every line but the last two ends in && (the last one cleans up).
    for distro in ("Fedora", "Ubuntu"):
        lines = _block(distro).strip().splitlines()
        assert all(l.endswith("&&") for l in lines[:-2]), distro
        assert lines[-1].startswith("sudo rm -f ") and "setup" in lines[-1]
    assert all(l.endswith("&&") for l in arch.strip().splitlines()[:-1])


def _gpg_key(home: Path, name: str) -> bytes:
    env = dict(os.environ, GNUPGHOME=str(home))
    home.mkdir(mode=0o700)
    subprocess.run(["gpg", "--batch", "--passphrase", "", "--quick-gen-key", name, "ed25519", "sign", "never"],
                   env=env, check=True, capture_output=True, timeout=60)
    return subprocess.run(["gpg", "--batch", "--armor", "--export", name], env=env, check=True,
                          capture_output=True, timeout=60).stdout


@pytest.fixture
def box(tmp_path):
    if not shutil.which("gpg"):
        pytest.skip("needs gpg")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    log = tmp_path / "log"
    fakes = {
        "sudo": 'exec "$@"',
        "curl": 'while [ $# -gt 1 ]; do case "$1" in -*o) out="$2"; shift ;; esac; shift; done; cp "$KEYSRC" "$out"',
        "wget": 'while [ $# -gt 1 ]; do case "$1" in -*O) out="$2"; shift ;; esac; shift; done; cp "$KEYSRC" "$out"',
        "tee": 'echo "tee $*" >> "$LOG"; cat >> "$LOG"',
    }
    for cmd in ("install", "rpm", "dnf", "apt", "rm"):
        fakes[cmd] = f'echo "{cmd} $*" >> "$LOG"'
    for name, body in fakes.items():
        (bin_ / name).write_text(f"#!/bin/bash\n{body}\n")
        (bin_ / name).chmod(0o755)
    # A fresh user: no GNUPGHOME, an empty home (gpg makes ~/.gnupg itself).
    env = {k: v for k, v in os.environ.items() if k != "GNUPGHOME"}
    env.update(PATH=f"{bin_}:{os.environ['PATH']}", LOG=str(log), HOME=str(tmp_path / "home"))
    (tmp_path / "home").mkdir()

    def run(distro, key: bytes):
        (tmp_path / "key.asc").write_bytes(key)
        log.write_text("")
        r = subprocess.run(["bash", "-c", _block(distro)], env=dict(env, KEYSRC=str(tmp_path / "key.asc")),
                           capture_output=True, text=True, timeout=60)
        return r, log.read_text()
    return tmp_path, run


@pytest.mark.parametrize("distro, installer", [("Fedora", "dnf install fedora-glass"),
                                               ("Ubuntu", "apt install fedora-glass")])
def test_install_block_runs_with_the_real_key(box, distro, installer):
    _, run = box
    r, log = run(distro, KEY.read_bytes())
    assert installer in log, r.stderr
    assert "Stopped" not in r.stdout
    assert "\nrm -f " in log      # the setup file is removed again


@pytest.mark.parametrize("distro, installer", [("Fedora", "dnf install"), ("Ubuntu", "apt ")])
def test_install_block_stops_on_a_swapped_key(box, distro, installer):
    tmp, run = box
    other = _gpg_key(tmp / "other", "Someone Else <x@example.com>")
    for key in (other, KEY.read_bytes() + other, other + KEY.read_bytes(), b"not a key"):
        r, log = run(distro, key)
        assert "Stopped: not the Fedora Glass key." in r.stdout
        assert installer not in log and "install -Dm644" not in log and "tee " not in log
        assert "rpm --import" not in log
