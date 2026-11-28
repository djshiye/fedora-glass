"""The byte code of the installed app fits the PC's own Python (packaging/bytecode.sh, run by
the packages as /usr/libexec/fedora-glass-bytecode).

The packages ship the byte code of the Python they were built with and name its cache tag in
/usr/share/fedora-glass/bytecode-tag. On a PC with another Python (the rpm built on Fedora 44
also serves Fedora 45) `fit` compiles for the PC's Python too, hash-checked (rpm and .deb only);
`drop` takes away what the package did not ship, so a removal leaves nothing.
A tree built by install-tree.sh stands in for the installed folder, and "another Python" is
made by renaming what was shipped to cpython-399: no second Python is needed.
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packaging"
PY = "/usr/bin/python3"          # the Python the launcher and the script run
OTHER = "cpython-399"

pytestmark = pytest.mark.skipif(not os.access(PY, os.X_OK), reason="no /usr/bin/python3 here")


def _tag_of(python: str) -> str:
    return subprocess.run([python, "-I", "-c", "import sys; print(sys.implementation.cache_tag)"],
                          capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """A package tree made by install-tree.sh, as the .deb and the Arch package get it."""
    base = tmp_path_factory.mktemp("bytecode")
    work, dest = base / "src", base / "dest"
    work.mkdir()
    for name in ("fedoraglass", "data", "packaging", "LICENSE", "LICENSES", "THIRD-PARTY-NOTICES.md"):
        src = ROOT / name
        if src.is_dir():
            shutil.copytree(src, work / name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy(src, work / name)
    r = subprocess.run(["sh", str(PKG / "install-tree.sh"), str(work), str(dest)],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    return dest


@pytest.fixture
def tree(built, tmp_path):
    """A fresh copy of the installed code folder and the script: (code folder, script)."""
    code = tmp_path / "share/fedora-glass"
    shutil.copytree(built / "usr/share/fedora-glass", code, symlinks=True)
    return code, built / "usr/libexec/fedora-glass-bytecode"


def _shipped_tag(code: Path) -> str:
    return (code / "bytecode-tag").read_text().strip()


def _retag(code: Path, new: str):
    """As if the package had been built with the Python whose cache tag is `new`."""
    old = _shipped_tag(code)
    for p in list(code.rglob(f"*.{old}.pyc")):
        p.rename(p.with_name(p.name.replace(f".{old}.pyc", f".{new}.pyc")))
    (code / "bytecode-tag").write_text(new + "\n")


def _run(script: Path, *args: str):
    r = subprocess.run(["sh", str(script), *args], capture_output=True, text=True, timeout=300,
                       env={"PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stderr
    return r


def _snapshot(top: Path) -> dict:
    """Every path below `top` (links not followed) with what it is and holds."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(top):
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            st = p.lstat()
            if stat.S_ISLNK(st.st_mode):
                out[str(p.relative_to(top))] = ("link", os.readlink(p))
            elif stat.S_ISDIR(st.st_mode):
                out[str(p.relative_to(top))] = ("dir", stat.S_IMODE(st.st_mode))
            else:
                out[str(p.relative_to(top))] = ("file", p.read_bytes(), stat.S_IMODE(st.st_mode), st.st_mtime_ns)
    return out


def _flags(pyc: Path) -> int:
    return int.from_bytes(pyc.read_bytes()[4:8], "little")


def _modules(code: Path):
    return [p for p in code.rglob("*.py") if "__pycache__" not in p.parts]


def _version(code: Path, *flags: str) -> str:
    """fedoraglass.__version__ as the PC's Python sees it, without writing byte code."""
    r = subprocess.run([PY, "-I", "-B", *flags, "-c",
                        "import sys; sys.path.insert(0, sys.argv[1]); import fedoraglass; print(fedoraglass.__version__)",
                        str(code)], capture_output=True, text=True, check=True, timeout=60)
    return r.stdout.strip()


def test_the_tree_names_the_python_its_byte_code_is_for(built):
    code = built / "usr/share/fedora-glass"
    tag = (code / "bytecode-tag").read_text()
    assert re.fullmatch(r"[a-z][a-z0-9_-]*\n", tag), tag
    assert stat.S_IMODE((code / "bytecode-tag").stat().st_mode) == 0o644
    pycs = list(code.rglob("*.pyc"))
    assert pycs and all(p.name.endswith(f".{tag.strip()}.pyc") for p in pycs)
    script = built / "usr/libexec/fedora-glass-bytecode"
    assert script.read_bytes() == (PKG / "bytecode.sh").read_bytes()
    assert stat.S_IMODE(script.stat().st_mode) == 0o755


def test_fit_compiles_for_another_python_and_keeps_what_was_shipped(tree):
    code, script = tree
    _retag(code, OTHER)
    shipped = {p: p.read_bytes() for p in code.rglob(f"*.{OTHER}.pyc")}
    stale = code / "fedoraglass/__pycache__/stale.cpython-388.pyc"
    stale.write_bytes(b"left by a root run of an older Python")
    _run(script, "fit", str(code))
    mine = _tag_of(PY)
    assert mine != OTHER
    for mod in _modules(code):
        pyc = mod.parent / "__pycache__" / f"{mod.stem}.{mine}.pyc"
        assert pyc.is_file(), pyc
        # Hash based and checked (0b11): Python compares the source's content, never its date.
        assert _flags(pyc) == 0b11, pyc
        assert stat.S_IMODE(pyc.stat().st_mode) == 0o644
    assert {p: p.read_bytes() for p in code.rglob(f"*.{OTHER}.pyc")} == shipped
    assert not stale.exists()
    assert (code / "bytecode-tag").read_text() == OTHER + "\n"
    assert all(stat.S_IMODE(d.stat().st_mode) == 0o755 for d in code.rglob("__pycache__"))


def test_a_changed_file_with_the_same_size_and_date_is_never_run_from_old_byte_code(tree, tmp_path):
    """All files of a release share one date: 1.7.6 and 1.7.7 differed only in the version
    line. Byte code that is checked by date and size would go on running the old code."""
    code, script = tree
    _retag(code, OTHER)
    _run(script, "fit", str(code))
    init = code / "fedoraglass/__init__.py"
    before = init.stat()
    old = init.read_text()
    current = re.search(r'__version__ = "([0-9.]+)"', old).group(1)
    newer = current[:-1] + str((int(current[-1]) + 1) % 10)
    assert len(newer) == len(current)
    # What date-checked byte code would do: a copy with Python's ordinary (timestamp) files.
    dated = tmp_path / "dated"
    shutil.copytree(code, dated)
    subprocess.run([PY, "-I", "-m", "compileall", "-q", "-f", "--invalidation-mode", "timestamp", str(dated)],
                   check=True, capture_output=True)
    for folder in (code, dated):
        f = folder / "fedoraglass/__init__.py"
        f.write_text(old.replace(f'"{current}"', f'"{newer}"'))
        os.utime(f, ns=(before.st_atime_ns, before.st_mtime_ns))
        assert f.stat().st_size == before.st_size
    assert _version(dated) == current                       # the old code runs: the trap
    assert _version(code) == newer                          # hash-checked: the new code runs
    _run(script, "fit", str(code))
    pyc = code / f"fedoraglass/__pycache__/__init__.{_tag_of(PY)}.pyc"
    assert _flags(pyc) == 0b11
    # It holds the new source's hash (as the PC's Python works it out).
    want = subprocess.run([PY, "-I", "-c", "import importlib.util, sys; "
                           "print(importlib.util.source_hash(open(sys.argv[1], 'rb').read()).hex())", str(init)],
                          capture_output=True, text=True, check=True).stdout.strip()
    assert pyc.read_bytes()[8:16].hex() == want
    assert _version(code) == newer


def test_fit_with_the_same_python_compiles_nothing_and_changes_nothing(tree):
    code, script = tree
    _retag(code, _tag_of(PY))
    before = _snapshot(code)
    _run(script, "fit", str(code))
    assert _snapshot(code) == before


def test_drop_leaves_exactly_what_was_shipped(tree):
    code, script = tree
    _retag(code, OTHER)
    shipped = _snapshot(code)
    _run(script, "fit", str(code))
    assert _snapshot(code) != shipped
    (code / "fedoraglass/__pycache__/stale.cpython-388.pyc").write_bytes(b"x")
    (code / "fedoraglass/__pycache__/stale.cpython-388.opt-1.pyc").write_bytes(b"x")
    alone = code / "fedoraglass/data/__pycache__"
    assert not alone.exists()
    alone.mkdir()
    (alone / "only.cpython-315.pyc").write_bytes(b"x")
    _run(script, "drop", str(code))
    assert _snapshot(code) == shipped
    assert not alone.exists()
    assert all(any(d.iterdir()) for d in code.rglob("__pycache__"))


def test_drop_after_a_build_with_the_same_python_keeps_the_rpms_opt_files(tree):
    """The rpm also ships .opt-1.pyc files (Fedora's %py_byte_compile makes both)."""
    code, script = tree
    tag = _shipped_tag(code)
    opt = code / f"fedoraglass/__pycache__/__init__.{tag}.opt-1.pyc"
    opt.write_bytes(b"shipped too")
    before = _snapshot(code)
    _run(script, "drop", str(code))
    _run(script, "fit", str(code))
    _run(script, "drop", str(code))
    if tag == _tag_of(PY):
        assert _snapshot(code) == before
    assert opt.read_bytes() == b"shipped too"


@pytest.mark.parametrize("tag", [None, "", "\n", "cpython/314", "..", "../x", "cpython 314", "3python",
                                 "CPython-314", "cpython-314\nx", "-cpython", "link", "cpython-311"])
def test_an_unusual_tag_makes_both_steps_do_nothing(tree, tmp_path, tag):
    code, script = tree
    _retag(code, OTHER)
    (code / "fedoraglass/__pycache__/stale.cpython-388.pyc").write_bytes(b"x")
    if tag is None:
        (code / "bytecode-tag").unlink()
    elif tag == "link":
        (tmp_path / "elsewhere").write_text(OTHER + "\n")
        (code / "bytecode-tag").unlink()
        (code / "bytecode-tag").symlink_to(tmp_path / "elsewhere")
    else:
        (code / "bytecode-tag").write_text(tag)
    before = _snapshot(code)
    for step in ("fit", "drop"):
        _run(script, step, str(code))
        assert _snapshot(code) == before, step


@pytest.mark.parametrize("step", ["fit", "drop"])
def test_links_are_never_followed(tree, tmp_path, step):
    code, script = tree
    _retag(code, OTHER)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.pyc").write_bytes(b"not ours")
    (outside / "gui.cpython-388.pyc").write_bytes(b"not ours either")
    # A link named like byte code, and a cache folder that is a link to a folder outside.
    (code / "fedoraglass/__pycache__/x.pyc").symlink_to(outside / "keep.pyc")
    cache = code / "fedoraglass/gui/__pycache__"
    shutil.rmtree(cache)
    cache.symlink_to(outside, target_is_directory=True)
    before = _snapshot(outside)
    _run(script, step, str(code))
    assert _snapshot(outside) == before
    assert (code / "fedoraglass/__pycache__/x.pyc").is_symlink() and cache.is_symlink()


def test_a_code_folder_that_is_a_link_is_left_alone(tree, tmp_path):
    code, script = tree
    _retag(code, OTHER)
    (code / "fedoraglass/__pycache__/stale.cpython-388.pyc").write_bytes(b"x")
    link = tmp_path / "linked"
    link.symlink_to(code, target_is_directory=True)
    before = _snapshot(code)
    # A slash or a dot at the end would make the link check look through the link.
    for step in ("fit", "drop"):
        for path in (str(link), f"{link}/", f"{link}//", f"{link}/."):
            _run(script, step, path)
    assert _snapshot(code) == before


def test_the_script_never_fails_and_is_clean(tmp_path):
    script = PKG / "bytecode.sh"
    text = script.read_text()
    assert text.startswith("#!/bin/sh\n") and "set -e" not in text
    assert "umask 022" in text and "--invalidation-mode checked-hash" in text
    assert re.search(r"^python=/usr/bin/python3$", text, re.M)
    assert text.rstrip().endswith("exit 0")
    assert "find -L" not in text and " -follow" not in text
    # (never without a folder here: that would be this machine's own /usr/share/fedora-glass)
    for args in ([], ["undo", str(tmp_path)], ["fit", str(tmp_path / "missing")], ["drop", str(tmp_path)]):
        _run(script, *args)


# ---- the launcher ----------------------------------------------------------------------

def _launcher(text: str) -> str:
    return text.split("<<'LAUNCHER'\n", 1)[1].split("\nLAUNCHER\n", 1)[0]


def test_the_launcher_never_writes_byte_code_next_to_the_code(tree):
    """As root, Python would write byte code for its own version into /usr/share/fedora-glass,
    files no package owns (`dnf remove` then leaves the folder behind). -B stops that."""
    spec, inst = (PKG / "fedora-glass.spec").read_text(), (PKG / "install-tree.sh").read_text()
    assert _launcher(spec) == _launcher(inst)
    line = _launcher(inst).splitlines()[1]
    argv = shlex.split(line)
    assert argv[:4] == ["exec", "/usr/bin/python3", "-I", "-B"] and argv[4] == "-c" and argv[-1] == "$@"
    code, _ = tree
    for p in list(code.rglob("*.pyc")):          # nothing usable: Python would compile and write
        p.unlink()
    prog = argv[5].replace('"/usr/share/fedora-glass"', repr(str(code)))
    assert prog != argv[5]
    before = _snapshot(code)
    # The app's own Python (it has what the app imports); the flags are the launcher's.
    r = subprocess.run([sys.executable, *argv[2:4], "-c", prog, "--version"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and r.stdout.strip(), r.stderr
    assert _snapshot(code) == before
    # Without -B the same run does write there: the check above can see it.
    subprocess.run([sys.executable, "-I", "-c", prog, "--version"], capture_output=True, timeout=120)
    assert _snapshot(code) != before


def test_the_built_launcher_is_the_one_in_the_scripts(built):
    text = (built / "usr/bin/fedora-glass").read_text()
    assert text == _launcher((PKG / "install-tree.sh").read_text()) + "\n"


# ---- when the packages run it ----------------------------------------------------------

FIT = "/usr/libexec/fedora-glass-bytecode fit >/dev/null 2>&1 || :"
DROP = "/usr/libexec/fedora-glass-bytecode drop >/dev/null 2>&1 || :"


def _spec_sections():
    from tests.test_login_packaging import _section, _spec, _expand
    spec = _spec()
    names = re.findall(r"^(%(?:pre|post|preun|postun|posttrans|trigger\w*)(?: .*)?)$", spec, re.M)
    return {n: _expand(_section(spec, n)) for n in names}


def test_rpm_fits_after_every_install_and_drops_only_on_a_removal():
    secs = _spec_sections()
    for name, body in secs.items():
        if name in ("%posttrans", "%posttrans -n liquid-glass"):
            assert body.count(FIT) == 1 and "bytecode drop" not in body, name
        elif name in ("%preun", "%preun -n liquid-glass"):
            # inside the removal-only block, after the undo and the login screen's off
            block = re.search(r"^if \[ \$1 -eq 0 \].*?; then\n(.*)^fi\n", body, re.M | re.S).group(1)
            assert block.rstrip().splitlines()[-1] == DROP, name
            assert block.index("undo-for-users") < block.index("fedora-glass-login off") < block.index(DROP)
            assert body.count("fedora-glass-bytecode") == 1, name
        else:
            assert "fedora-glass-bytecode" not in body, name
    spec = (PKG / "fedora-glass.spec").read_text()
    assert "install -Dm755 packaging/bytecode.sh %{buildroot}%{_libexecdir}/fedora-glass-bytecode" in spec
    for files in spec.split("\n%files")[1:]:
        assert "\n%{_libexecdir}/fedora-glass-bytecode\n" in files.split("\n%changelog")[0]
    # The tag comes from the same Python that compiled, right after it.
    inst = spec.split("\n%install\n", 1)[1]
    compile_at = inst.index("%py_byte_compile %{python3} ")
    tag_at = inst.index("%{python3} -I -c 'import sys; print(sys.implementation.cache_tag)' > "
                        "%{buildroot}%{_datadir}/fedora-glass/bytecode-tag")
    assert compile_at < tag_at


def test_the_tree_writes_the_tag_with_the_python_that_compiled():
    tree = (PKG / "install-tree.sh").read_text()
    compile_line = next(x for x in tree.splitlines() if "-m compileall" in x)
    tag_line = next(x for x in tree.splitlines() if "bytecode-tag" in x and not x.startswith("#"))
    assert compile_line.split()[0] == tag_line.split()[0] == "python3"
    assert tree.index(compile_line) < tree.index(tag_line) < tree.index("-type f -exec chmod 644")
    assert 'install -Dm755 "$src/packaging/bytecode.sh" "$dest/usr/libexec/fedora-glass-bytecode"' in tree


def _arch_calls(tmp_path, func):
    text = (PKG / "arch/fedora-glass.install").read_text()
    libexec, log = tmp_path / "libexec", tmp_path / f"log-{func}"
    libexec.mkdir(exist_ok=True)
    bin_ = tmp_path / "bin"
    bin_.mkdir(exist_ok=True)
    for n in ("fedora-glass-bytecode", "fedora-glass-undo-for-users", "fedora-glass-stop-watchers",
              "liquid-glass-login-screen", "fedora-glass-login"):
        (libexec / n).write_text(f'#!/bin/sh\necho "{n} $*" >> "$LOG"\n')
        (libexec / n).chmod(0o755)
    (bin_ / "systemctl").write_text('#!/bin/sh\necho "systemctl $*" >> "$LOG"\n')
    (bin_ / "systemctl").chmod(0o755)
    body = text.replace("/usr/libexec/", f"{libexec}/").replace("/var/lib/", f"{tmp_path}/var/lib/")
    assert "/usr/" not in body
    r = subprocess.run(["sh", "-e", "-c", body + f"\n{func}\n"], capture_output=True, text=True, timeout=30,
                       env={"PATH": f"{bin_}:/usr/bin:/bin", "LOG": str(log)})
    assert r.returncode == 0, r.stderr
    return [x for x in (log.read_text().splitlines() if log.exists() else []) if "bytecode" in x or "off" in x]


def test_arch_never_makes_byte_code_that_would_block_the_next_upgrade(tmp_path):
    # pacman refuses to write over a file no package owns: byte code made on the PC for a newer
    # Python would stop the next upgrade, whose package ships exactly those files. So Arch only
    # drops what is not the package's own, on a removal.
    assert _arch_calls(tmp_path, "post_install") == []
    assert _arch_calls(tmp_path, "post_upgrade") == []
    assert _arch_calls(tmp_path, "pre_remove") == ["fedora-glass-login off", "fedora-glass-bytecode drop"]
    assert _arch_calls(tmp_path, "post_remove") == []
    text = (PKG / "arch/fedora-glass.install").read_text()
    assert "bytecode fit" not in text and text.count(DROP) == 1


def test_the_script_passes_shellcheck():
    sc = shutil.which("shellcheck")
    if sc is None:
        pytest.skip("no shellcheck here")
    r = subprocess.run([sc, str(PKG / "bytecode.sh")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


# ---- the package jobs check it on the real install -------------------------------------

def _smoke_check():
    smoke = (ROOT / "qa/package-smoke.sh").read_text()
    return smoke.split("/usr/bin/python3 -I -c '", 1)[1].split("' \"$code\" ||", 1)[0]


def test_the_package_jobs_check_the_byte_code_of_the_install(tree):
    code, script = tree
    _retag(code, OTHER)
    check = lambda: subprocess.run([PY, "-I", "-c", _smoke_check(), str(code)], capture_output=True, text=True)
    assert check().returncode != 0                      # nothing for this PC's Python yet
    _run(script, "fit", str(code))
    r = check()
    assert r.returncode == 0, r.stderr
    # A file Python wrote by itself (checked by date) is caught, and so is one of a third Python.
    init = code / "fedoraglass/__init__.py"
    subprocess.run([PY, "-I", "-c", "import py_compile, sys; py_compile.compile(sys.argv[1], "
                    "invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)", str(init)], check=True)
    assert "not hash-checked" in check().stderr
    _run(script, "fit", str(code))
    assert check().returncode == 0
    (code / "fedoraglass/__pycache__/stale.cpython-388.pyc").write_bytes(b"x")
    assert "neither shipped nor made" in check().stderr
    smoke = (ROOT / "qa/package-smoke.sh").read_text()
    assert smoke.index("files_before=") < smoke.index("$app --version") < smoke.index("files_after=")
    removed = smoke.split("--removed ]; then", 1)[1].split("\nfi\n", 1)[0]
    assert "/usr/share/fedora-glass is left behind" in removed
