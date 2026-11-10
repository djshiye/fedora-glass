"""fedora-glass-sign, run against fake gh, gpg, rpm and curl: it signs only what the Release
workflow built from a commit on main, carries older releases over only when they are already
signed by the maintainer's key, and in auto mode keeps publishing until the site has it."""
from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_distro import _fake_deb, _fake_pkg, _load_repo_index  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SIGN = ROOT / "packaging" / "fedora-glass-sign"
FPR = "D49A308168257FDBF9D5AE14BD1AC1C6F56A7252"
SHA = "a" * 40
PY = sys.executable

FAKES = {
    "gh": r'''
import os, shutil, sys
F = os.environ["FAKE"]; a = sys.argv[1:]
open(f"{F}/gh.log", "a").write(" ".join(a) + "\n")
def rd(name, default=""):
    p = f"{F}/{name}"
    return open(p).read() if os.path.exists(p) else default
def opt(name):
    return a[a.index(name) + 1] if name in a else None
rel = f"{F}/releases"
if a[:2] == ["auth", "status"]: sys.exit(0)
if a[:2] == ["attestation", "verify"]:
    if "--help" in a: sys.exit(0)
    ref, ident = opt("--source-ref"), opt("--cert-identity")
    ok = (os.path.basename(a[2]) in rd("attested").split()
          and opt("--repo") == "djshiye/fedora-glass" and opt("--source-digest") == rd("tagsha").strip()
          and ident == f"https://github.com/djshiye/fedora-glass/.github/workflows/release.yml@{ref}"
          and ref == rd("attest_ref", ref) and "--deny-self-hosted-runners" in a)
    sys.exit(0 if ok else 1)
if a[0] == "api":
    path = [x for x in a[1:] if x.startswith("repos/")][0]
    if "/contents/packaging/" in path: print("PUBLIC KEY"); sys.exit(0)
    if "/git/ref/tags/" in path: print("commit " + rd("tagsha").strip()); sys.exit(0)
    if "/compare/main..." in path:
        assert path.endswith("..." + rd("tagsha").strip()), path
        print(rd("compare", "behind").strip()); sys.exit(0)
    sys.exit(1)
if a[:2] == ["release", "view"]:
    tags = sorted(os.listdir(rel), key=lambda t: [int(x) for x in t[1:].split(".")])
    if "assets" in a:
        print("\n".join(sorted(os.listdir(f"{rel}/{a[2]}")))); sys.exit(0)
    print(tags[-1]); sys.exit(0)
if a[:2] == ["release", "list"]:
    print("\n".join(os.listdir(rel))); sys.exit(0)
if a[:2] == ["release", "download"]:
    src = f"{rel}/{a[2]}/{opt('-p')}"
    if not os.path.exists(src): sys.exit(1)
    shutil.copy(src, opt("-D")); sys.exit(0)
if a[:2] == ["release", "upload"]:
    os.makedirs(f"{F}/uploaded", exist_ok=True); shutil.copy(a[3], f"{F}/uploaded/"); sys.exit(0)
if a[:2] == ["workflow", "run"]:
    open(f"{F}/workflow_runs", "a").write(" ".join(a) + "\n"); sys.exit(0)
if a[:2] == ["run", "list"]:
    print(rd("runs").strip()); sys.exit(0)
sys.exit(f"fake gh: unexpected {a}")
''',
    "gpg": r'''
import os, sys
F = os.environ["FAKE"]; a = sys.argv[1:]; FPR = "%s"
if "--list-secret-keys" in a:
    print(f"sec:u:4096:1:BD1AC1C6F56A7252:1::::::scESC:\nfpr:::::::::{FPR}:"); sys.exit(0)
if "show-only" in a:
    print(f"pub:-:4096:1:BD1AC1C6F56A7252:1::::::scESC:\nfpr:::::::::{FPR}:"); sys.exit(0)
if "--dearmor" in a:
    sys.stdout.write(sys.stdin.read()); sys.exit(0)
if "--detach-sign" in a or "--clearsign" in a:
    out = a[a.index("-o") + 1] if "-o" in a else a[-1] + ".asc"
    open(f"{F}/signed.log", "a").write(os.path.basename(a[-1]) + "\n")
    open(out, "w").write("SIG\n"); sys.exit(0)
sys.exit(f"fake gpg: unexpected {a}")
''' % FPR,
    "gpgv": r'''
import sys
files = [x for x in sys.argv[1:] if not x.startswith("--") and "main.gpg" not in x]
sys.exit(1 if "BAD" in open(files[0]).read() else 0)
''',
    "rpmsign": r'''
import os, sys
F = os.environ["FAKE"]
for p in sys.argv[1:]:
    if p.endswith(".rpm"):
        open(f"{F}/rpmsign.log", "a").write(os.path.basename(p) + "\n")
        open(p, "a").write("SIGNED\n")
''',
    "rpmkeys": r'''
import sys
a = sys.argv[1:]
if "--import" in a: sys.exit(0)
sys.exit(0 if "SIGNED" in open(a[-1]).read() else 1)
''',
    "rpm": r'''
import sys
a = sys.argv[1:]
name, ver, rel = open(a[-1]).read().split("\n")[0].split()
fmt = a[a.index("--qf") + 1].replace("\\n", "\n")
sys.stdout.write(fmt.replace("%{name}", name).replace("%{version}", ver).replace("%{release}", rel))
''',
    "createrepo_c": r'''
import os, sys
d = sys.argv[-1]; os.makedirs(f"{d}/repodata", exist_ok=True)
open(f"{d}/repodata/repomd.xml", "w").write(" ".join(sorted(n for n in os.listdir(d) if n.endswith(".rpm"))))
''',
    "curl": r'''
import os, sys
F = os.environ["FAKE"]
p = f"{F}/site_version"
if not os.path.exists(p): sys.exit(22)
sys.stdout.write(open(p).read())
''',
    "notify-send": r'''
import os, sys
open(os.environ["FAKE"] + "/notify.log", "a").write(sys.argv[-2] + " | " + sys.argv[-1] + "\n")
''',
}


def _rpm(path: Path, name: str, ver: str, signed=False):
    path.write_text(f"{name} {ver} 1.fc44\n" + ("SIGNED\n" if signed else ""))


def _add_release(fake: Path, tag: str, files: dict[str, bytes | Path]):
    d = fake / "releases" / tag
    d.mkdir(parents=True)
    sums = []
    for name, src in files.items():
        data = src.read_bytes() if isinstance(src, Path) else src
        (d / name).write_bytes(data)
        if name != "dnf-repo.tar.gz":
            sums.append(f"{hashlib.sha256(data).hexdigest()}  {name}")
    (d / "SHA256SUMS").write_text("\n".join(sums) + "\n")


def _new_release(tmp: Path, fake: Path, ver: str):
    """A release as release.yml makes it: packages under fixed names, plus SHA256SUMS."""
    src = tmp / f"src-{ver}"
    src.mkdir()
    _rpm(src / "fg.rpm", "fedora-glass", ver)
    _rpm(src / "lg.rpm", "liquid-glass", ver)
    _fake_deb(src / "fg.deb", f"{ver}-1")
    _fake_pkg(src / "fg.pkg.tar.xz", f"{ver}-1")
    _add_release(fake, f"v{ver}", {"fedora-glass.noarch.rpm": src / "fg.rpm", "liquid-glass.noarch.rpm": src / "lg.rpm",
                                   "fedora-glass.deb": src / "fg.deb", "fedora-glass.pkg.tar.xz": src / "fg.pkg.tar.xz"})


def _old_bundle(tmp: Path) -> bytes:
    """The signed repository published with 1.5.20: 1.5.20 and 1.5.19, with some of 1.5.19
    tampered with after signing (those must not be carried over)."""
    site = tmp / "oldsite"
    for d in ("rpms/repodata", "apt", "arch"):
        (site / d).mkdir(parents=True)
    _rpm(site / "rpms/fedora-glass-1.5.20-1.fc44.noarch.rpm", "fedora-glass", "1.5.20", signed=True)
    _rpm(site / "rpms/fedora-glass-1.5.19-1.fc44.noarch.rpm", "fedora-glass", "1.5.19", signed=True)
    _rpm(site / "rpms/liquid-glass-1.5.19-0.fc44.noarch.rpm", "liquid-glass", "1.5.19")       # not signed
    _rpm(site / "rpms/fedora-glass-1.4.0-1.fc44.noarch.rpm", "fedora-glass", "1.4.0", signed=True)  # out of window
    (site / "rpms/repodata/repomd.xml").write_text("old")
    _fake_deb(site / "apt/fedora-glass_1.5.20-1_all.deb", "1.5.20-1")
    _fake_deb(site / "apt/fedora-glass_1.5.19-1_all.deb", "1.5.19-1")
    _load_repo_index().apt_index(str(site / "apt"))
    (site / "apt/Release.gpg").write_text("SIG\n")
    _fake_deb(site / "apt/fedora-glass_1.5.19-1_all.deb", "1.5.19-1+evil")  # changed after signing
    _fake_pkg(site / "arch/fedora-glass-1.5.20-1-any.pkg.tar.xz", "1.5.20-1")
    _fake_pkg(site / "arch/fedora-glass-1.5.19-1-any.pkg.tar.xz", "1.5.19-1")
    (site / "arch/fedora-glass-1.5.19-1-any.pkg.tar.xz.sig").write_text("BAD\n")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for d in ("rpms", "apt", "arch"):
            t.add(site / d, arcname=d)
    return buf.getvalue()


@pytest.fixture
def world(tmp_path):
    fake, bin_, conf = tmp_path / "fake", tmp_path / "bin", tmp_path / "config"
    fake.mkdir(); bin_.mkdir()
    (conf / "fedora-glass-signing").mkdir(parents=True)
    (conf / "fedora-glass-signing/key-fingerprint").write_text(FPR + "\n")
    for name, body in FAKES.items():
        p = bin_ / name
        p.write_text(f"#!{PY}\n{body}")
        p.chmod(0o755)
    (fake / "tagsha").write_text(SHA + "\n")
    for v in ("1.5.19", "1.5.20", "1.5.21"):
        _new_release(tmp_path, fake, v)
    (fake / "releases/v1.5.20/dnf-repo.tar.gz").write_bytes(_old_bundle(tmp_path))
    (fake / "attested").write_text("fedora-glass.noarch.rpm liquid-glass.noarch.rpm fedora-glass.deb fedora-glass.pkg.tar.xz")
    env = dict(os.environ, PATH=f"{bin_}:{os.environ['PATH']}", FAKE=str(fake), XDG_CONFIG_HOME=str(conf),
               XDG_RUNTIME_DIR=str(tmp_path), HOME=str(tmp_path))

    def run(*args):
        return subprocess.run(["bash", str(SIGN), *args], env=env, capture_output=True, text=True, timeout=60)
    return fake, conf / "fedora-glass-signing", run


def _read(p: Path) -> str:
    return p.read_text() if p.exists() else ""


def test_signs_only_the_attested_release_and_carries_over_only_signed_packages(world):
    fake, conf, run = world
    r = run("v1.5.21")
    assert r.returncode == 0, r.stderr + r.stdout
    # Only the new release's packages were signed; the older ones were not signed again.
    assert sorted(_read(fake / "rpmsign.log").split()) == ["fedora-glass-1.5.21-1.fc44.noarch.rpm",
                                                           "liquid-glass-1.5.21-1.fc44.noarch.rpm"]
    assert "fedora-glass-1.5.19-1-any.pkg.tar.xz" not in _read(fake / "signed.log")
    with tarfile.open(fake / "uploaded/dnf-repo.tar.gz") as t:
        names = set(t.getnames())
    assert {"rpms/fedora-glass-1.5.21-1.fc44.noarch.rpm", "rpms/liquid-glass-1.5.21-1.fc44.noarch.rpm",
            "rpms/fedora-glass-1.5.20-1.fc44.noarch.rpm", "rpms/fedora-glass-1.5.19-1.fc44.noarch.rpm",
            "apt/fedora-glass_1.5.21-1_all.deb", "apt/fedora-glass_1.5.20-1_all.deb",
            "arch/fedora-glass-1.5.21-1-any.pkg.tar.xz", "arch/fedora-glass-1.5.20-1-any.pkg.tar.xz"} <= names
    # Not signed by the key, changed after signing, bad signature, or outside the window: left out.
    for n in ("rpms/liquid-glass-1.5.19-0.fc44.noarch.rpm", "rpms/fedora-glass-1.4.0-1.fc44.noarch.rpm",
              "apt/fedora-glass_1.5.19-1_all.deb", "arch/fedora-glass-1.5.19-1-any.pkg.tar.xz"):
        assert n not in names, n
    # Every package was checked against its attestation, for the tag's commit.
    log = _read(fake / "gh.log")
    assert log.count("attestation verify") >= 4 and f"--source-digest {SHA}" in log
    assert "workflow run dnf-repo.yml" in _read(fake / "workflow_runs")
    assert (conf / "publishing-v1.5.21").exists()


def test_a_release_started_from_main_is_accepted_too(world):
    fake, _, run = world
    (fake / "attest_ref").write_text("refs/heads/main")
    assert run("v1.5.21").returncode == 0


@pytest.mark.parametrize("missing", ["fedora-glass.deb", "liquid-glass.noarch.rpm"])
def test_nothing_is_signed_without_build_provenance(world, missing):
    fake, _, run = world
    (fake / "attested").write_text(_read(fake / "attested").replace(missing, ""))
    r = run("v1.5.21")
    assert r.returncode == 3 and "NOT signed" in r.stderr and missing in r.stderr
    assert not (fake / "rpmsign.log").exists() and not (fake / "signed.log").exists()
    assert not (fake / "uploaded").exists() and not (fake / "workflow_runs").exists()


@pytest.mark.parametrize("status", ["ahead", "diverged", ""])
def test_nothing_is_signed_when_the_tag_is_not_on_main(world, status):
    fake, _, run = world
    (fake / "compare").write_text(status + "\n")
    r = run("v1.5.21")
    assert r.returncode == 3 and "is not on main" in r.stderr
    assert "release download" not in _read(fake / "gh.log")
    assert not (fake / "rpmsign.log").exists() and not (fake / "uploaded").exists()


def test_auto_says_not_signed_and_why(world):
    fake, conf, run = world
    (fake / "attested").write_text("")
    r = run("auto")
    assert r.returncode == 1
    note = _read(fake / "notify.log")
    assert "Fedora Glass 1.5.21 was NOT signed" in note and "build provenance" in note
    assert not (fake / "rpmsign.log").exists() and (conf / "auto-failed-v1.5.21").exists()


def test_auto_notifies_publishing_then_published(world):
    fake, conf, run = world
    (fake / "site_version").write_text("1.5.20-1\n")
    assert run("auto").returncode == 0
    assert _read(fake / "notify.log").splitlines()[-1].startswith("Fedora Glass 1.5.21 is signed, publishing it now")
    # Now the release has its bundle; the site is still behind, but the run just started.
    (fake / "releases/v1.5.21/dnf-repo.tar.gz").write_bytes(b"x")
    (fake / "runs").write_text("in_progress\n")
    assert run("auto").returncode == 0
    assert len(_read(fake / "notify.log").splitlines()) == 1
    # The site has it: published.
    (fake / "runs").write_text("completed\n")
    (fake / "site_version").write_text("1.5.21-1\n")
    assert run("auto").returncode == 0
    assert _read(fake / "notify.log").splitlines()[-1].startswith("Fedora Glass 1.5.21 is published")
    assert not (conf / "publishing-v1.5.21").exists()
    # And only once.
    assert run("auto").returncode == 0
    assert len(_read(fake / "notify.log").splitlines()) == 2


def test_auto_retries_a_failed_publish_a_few_times_then_stops(world):
    fake, conf, run = world
    (fake / "releases/v1.5.21/dnf-repo.tar.gz").write_bytes(b"x")
    (fake / "site_version").write_text("1.5.20-1\n")
    (fake / "runs").write_text("completed\ncompleted\n")
    marker = conf / "publishing-v1.5.21"
    for n in (1, 2, 3):
        assert run("auto").returncode == 0
        assert len(_read(fake / "workflow_runs").splitlines()) == n
        assert f"try {n} of 3" in _read(fake / "notify.log").splitlines()[-1]
        # Too soon after the last start: nothing new.
        assert run("auto").returncode == 0
        assert len(_read(fake / "workflow_runs").splitlines()) == n
        old = time.time() - 1300
        os.utime(marker, (old, old))
    r = run("auto")
    assert r.returncode == 1 and len(_read(fake / "workflow_runs").splitlines()) == 3
    assert "signed but NOT published" in _read(fake / "notify.log").splitlines()[-1]
    assert run("auto").returncode == 0     # said once, then quiet
    assert len(_read(fake / "notify.log").splitlines()) == 4


def test_auto_is_quiet_when_the_site_is_current_or_unreachable(world):
    fake, _, run = world
    (fake / "releases/v1.5.21/dnf-repo.tar.gz").write_bytes(b"x")
    (fake / "site_version").write_text("1.5.21-1\n")
    assert run("auto").returncode == 0
    (fake / "site_version").unlink()
    assert run("auto").returncode == 0
    assert not (fake / "notify.log").exists() and not (fake / "workflow_runs").exists()


def test_workflows_pin_every_action_and_release_attests_each_package():
    import re
    wf = ROOT / ".github/workflows"
    for f in wf.glob("*.yml"):
        for line in f.read_text().splitlines():
            m = re.match(r"\s*(?:-\s*)?uses:\s*(\S+)", line)
            if m and not m.group(1).startswith("./"):
                assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", m.group(1)), (f.name, line)
    rel = (wf / "release.yml").read_text()
    job = rel[rel.index("\n  rpm:\n"):]
    assert "      id-token: write" in job and "      attestations: write" in job
    step = job[job.index("- name: Build provenance"):job.index("- name: Release")]
    assert "uses: actions/attest-build-provenance@" in step
    for pattern in ("out/*.rpm", "out/*.deb", "out/*.pkg.tar.xz"):
        assert pattern in step
    # Before the release is made: a pushed tag must be on main as well, not only a hand-started run.
    gate = job[job.index("- name: Only from main"):job.index("- name: Version")]
    assert "if:" not in gate and 'git merge-base --is-ancestor "$GITHUB_SHA" origin/main' in gate
    assert "fetch-depth: 0" in job[:job.index("- name: Only from main")]
    assert job.index("- name: Only from main") < job.index("- name: Build provenance") < job.index("- name: Release")
    # The tests run once, in the spec's %check during rpmbuild.
    assert "python3 -m pytest" not in rel
    spec = (ROOT / "packaging/fedora-glass.spec").read_text()
    assert "%check\n" in spec and "python3 -m pytest -q tests" in spec.split("%check\n", 1)[1].split("\n%", 1)[0]


def test_signer_checks_provenance_before_signing():
    sign = SIGN.read_text()
    body = sign[sign.index("cmd_publish() {"):sign.index("\nnotify() {")]
    assert body.index('check_on_main "$tag"') < body.index("gh release download") < body.index("attested \"$f\"") < body.index("rpmsign --define")
    assert "--cert-identity \"https://github.com/$REPO/.github/workflows/release.yml@$ref\"" in sign
    assert "--source-digest \"$sha\"" in sign and "--deny-self-hosted-runners" in sign
    assert "behind|identical)" in sign


def test_old_liquid_glass_repo_file_checks_signatures():
    repo = (ROOT / "packaging/liquid-glass.repo").read_text()
    for line in ("gpgcheck=1", "repo_gpgcheck=1", "metadata_expire=1h", "includepkgs=liquid-glass",
                 "gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-fedora-glass"):
        assert line + "\n" in repo
    assert "gpgcheck=0" not in repo and "https://" not in repo.split("gpgkey=", 1)[1].split("\n")[0]
    # The bridge package's %posttrans still recognises the file and sets it aside.
    assert "baseurl=https://djshiye.github.io/fedora-glass/rpms/\n" in repo
