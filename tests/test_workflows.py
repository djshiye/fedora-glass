"""The GitHub workflows and the packaging around them: what runs when, with which rights,
and that the three Linux packages agree with each other."""
from __future__ import annotations

import gzip
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from tests.ci_guard import required

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github/workflows"
PKG = ROOT / "packaging"


def _text(name: str) -> str:
    return (WF / name).read_text()


def _jobs(text: str) -> dict[str, str]:
    """Each job's block of a workflow, by name."""
    body = text[text.index("\njobs:\n") + 7:]
    parts = re.split(r"\n  ([a-z][\w-]*):\n", "\n" + body)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def _run_blocks(text: str) -> list[str]:
    """The shell of every `run:` step."""
    blocks, lines = [], text.splitlines()
    for n, line in enumerate(lines):
        m = re.match(r"(\s*)(?:- )?run:\s*(.*)", line)
        if not m:
            continue
        if m.group(2) not in ("|", ">", "|-"):
            blocks.append(m.group(2))
            continue
        indent = len(m.group(1)) + 2
        body = []
        for l in lines[n + 1:]:
            if l.strip() and len(l) - len(l.lstrip()) < indent:
                break
            body.append(l)
        blocks.append("\n".join(body))
    return blocks


@pytest.mark.parametrize("name", sorted(p.name for p in WF.glob("*.yml")))
def test_every_workflow_has_read_only_defaults_and_a_timeout(name):
    text = _text(name)
    assert re.search(r"^permissions:", text, re.M), name
    top = text[text.index("\npermissions:") + 1:].split("\n\n", 1)[0]
    if name != "dnf-repo.yml":
        assert "write" not in top, name
    for job, block in _jobs(text).items():
        if "uses: ./" in block.split("steps:")[0] and "runs-on" not in block:
            continue                                     # a call of another workflow
        assert "timeout-minutes:" in block or name == "dnf-repo.yml", (name, job)


@pytest.mark.parametrize("name", sorted(p.name for p in WF.glob("*.yml")))
def test_no_expression_in_a_run_step(name):
    """`${{ }}` pasted into a shell script is how a title or a branch name becomes a command:
    values reach scripts through env: only. A matrix value from this file is no input, so the
    release checks (whose matrices are literal) may keep theirs."""
    for block in _run_blocks(_text(name)):
        for expr in re.findall(r"\$\{\{(.*?)\}\}", block):
            assert re.fullmatch(r"\s*matrix\.[a-z]+\s*", expr) or "matrix.dock" in expr, (name, expr)


def test_quick_tests_on_every_pull_request_and_push_to_main():
    text = _text("quick-tests.yml")
    assert "pull_request:" in text and "push:\n    branches: [main]" in text
    for path in ("fedoraglass/**", "tests/**", "packaging/**"):
        assert text.count(f'"{path}"') == 2, path        # in both triggers
    assert "pull_request_target" not in text
    assert "cancel-in-progress: true" in text and "group: quick-tests-${{ github.ref }}" in text
    assert re.search(r"^permissions:\n  contents: read\n", text, re.M)
    job = _jobs(text)["tests"]
    assert "timeout-minutes:" in job and "python3-gi" in job and "gjs" in job
    assert "node --import ./tests/js/register.mjs --test tests/js/*.test.mjs" in job
    assert "python3 -m pytest" in job


def test_packages_workflow_does_not_cancel_a_release():
    text = _text("packages.yml")
    assert "concurrency:" in text
    # Only a pull request's older run is replaced; the group differs from the Release caller's.
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in text
    assert "group: release\n" in _text("release.yml") and "group: packages-" in text


def test_release_builds_in_parallel_and_publishes_a_draft_at_the_end():
    text = _text("release.yml")
    jobs = _jobs(text)
    assert set(jobs) == {"checks", "packages", "rpm", "release"}
    for early in ("checks", "packages", "rpm"):
        assert "needs:" not in jobs[early], early            # they run side by side
    assert "needs: [checks, packages, rpm]" in jobs["release"]
    assert "contents: write" not in jobs["rpm"] and "contents: write" in jobs["release"]
    top = text[text.index("\npermissions:") + 1:].split("\n\n", 1)[0]
    assert top.strip() == "permissions:\n  contents: read"
    release = jobs["release"]
    # A draft, on a tag that exists already (made with the workflow's own token, which starts
    # no workflow, so publishing the draft later does not start this one again).
    assert "gh release create" in release and "--draft" in release and "--verify-tag" in release
    assert "--target" not in release
    assert 'git/refs" -f ref="refs/tags/$TAG" -f sha="$GITHUB_SHA"' in release
    assert '[ "$on_tag" = "$GITHUB_SHA" ]' in release
    assert text.count("gh release create") == 1


def test_rpm_job_installs_upgrades_and_removes_the_package():
    rpm = _jobs(_text("release.yml"))["rpm"]
    assert "container: fedora:44@sha256:" in rpm
    assert rpm.index("rpmbuild -bb") < rpm.index("packaging/rpm-install-test.sh") < rpm.index("actions/upload-artifact")
    script = (PKG / "rpm-install-test.sh").read_text()
    assert stat.S_IMODE((PKG / "rpm-install-test.sh").stat().st_mode) & 0o111
    # The new package on a clean system, with the smoke check, then the previous release's
    # package checked against its SHA256SUMS and upgraded, then Liquid Glass 1.4.4.
    assert "qa/package-smoke.sh" in script and "sha256sum --quiet -c" in script
    assert 'fetch_or_skip "$prev" fedora-glass.noarch.rpm' in script and "fetch_or_skip v1.4.4 liquid-glass.noarch.rpm" in script
    assert script.index("Clean install") < script.index("Upgrade from the previous release") < script.index("Move from Liquid Glass 1.4.4")
    # Not the website: only the files built here and the old release assets. Our repositories
    # are switched off only once their file exists: dnf 5 refuses an option for a repository
    # it doesn't know, as on the clean image before the first install.
    assert "--setopt=%s.enabled=0" in script and "for id in fedora-glass liquid-glass" in script
    assert "/etc/yum.repos.d/*.repo" in script
    assert "--setopt=fedora-glass.enabled=0" not in script


def test_release_checks_build_the_image_once_per_gnome_and_every_lane_loads_it():
    checks = _text("release-checks.yml")
    jobs = _jobs(checks)
    assert "image" in jobs and "mode: build" in jobs["image"]
    for lane in ("desktop", "ubuntu", "stock"):
        assert "needs: image" in jobs[lane], lane
        assert "mode: load" in jobs[lane] and "mode: build" not in jobs[lane], lane
        assert "if:" not in jobs[lane].split("steps:")[0], lane       # the image job's gate covers them
    action = (ROOT / ".github/actions/test-image/action.yml").read_text()
    assert not (ROOT / ".github/actions/base-image").exists()
    # One cache entry per GNOME, recipe and day, saved with actions/cache (pinned by sha).
    assert "lgqa-image-gnome${{ inputs.gnome }}-${{ steps.info.outputs.recipe }}-${{ steps.info.outputs.day }}" in action
    assert "docker save" in action and "docker load" in action and "lookup-only: true" in action
    assert len(re.findall(r"actions/cache/(?:restore|save)@[0-9a-f]{40}  # v", action)) == 3
    assert "${{" not in "\n".join(_run_blocks(action))               # values reach the shell through env only
    # What is built comes from run.sh itself, not a second copy of its table.
    assert "qa/desktop/run.sh --gnome" in action and "--image-info" in action and "--build-only" in action
    assert "lgqa.recipe" in (ROOT / "qa/desktop/run.sh").read_text()


def _run_sh(*args):
    return subprocess.run(["bash", str(ROOT / "qa/desktop/run.sh"), *args], capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("gnome, image", [("50", "lgqa-desktop"), ("51", "lgqa-desktop-51")])
def test_run_sh_names_the_base_image_and_its_recipe(gnome, image):
    out = _run_sh("--gnome", gnome, "--image-info")                 # stops before any docker call
    assert out.returncode == 0, out.stderr
    lines = out.stdout.splitlines()
    assert lines[0] == f"image={image}" and re.fullmatch(r"recipe=[0-9a-f]{20}", lines[1]) and len(lines) == 2
    # The two GNOME versions are built differently, so their recipes differ.
    assert _run_sh("--gnome", "51" if gnome == "50" else "50", "--image-info").stdout.splitlines()[1] != lines[1]


# ---- a label that is not the workflow's own neither starts nor cancels a run ----------------
# A small evaluator for the GitHub expressions these workflows use in `if:` and in the
# concurrency group, so the real text of the workflow is what gets tested.

def _evaluate(expr: str, ctx: dict):
    tokens = re.findall(r"'(?:[^']|'')*'|[A-Za-z_][\w.*-]*|==|!=|&&|\|\||[!(),]", expr)
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def take():
        nonlocal pos
        pos += 1
        return tokens[pos - 1]

    def lookup(path):
        values = [ctx]
        for part in path.split("."):
            if part == "*":
                values = [v for item in values for v in item]
            else:
                values = [v.get(part) if isinstance(v, dict) else None for v in values]
        return values if "*" in path.split(".") else values[0]

    def truthy(v):
        return v not in (None, False, "", 0)

    def primary():
        t = take()
        if t == "!":
            return not truthy(primary())
        if t == "(":
            v = disjunction()
            assert take() == ")"
            return v
        if t.startswith("'"):
            return t[1:-1].replace("''", "'")
        if peek() == "(":
            take()
            args = []
            while peek() != ")":
                args.append(disjunction())
                if peek() == ",":
                    take()
            take()
            if t == "contains":
                return args[1] in args[0]
            if t == "format":
                return args[0].format(*args[1:])
            raise AssertionError(f"unknown function {t}")
        if t in ("true", "false"):
            return t == "true"
        return lookup(t)

    def comparison():
        left = primary()
        if peek() in ("==", "!="):
            op = take()
            right = primary()
            return (left == right) if op == "==" else (left != right)
        return left

    def conjunction():
        v = comparison()
        while peek() == "&&":
            take()
            r = comparison()
            v = r if truthy(v) else v
        return v

    def disjunction():
        v = conjunction()
        while peek() == "||":
            take()
            r = conjunction()
            v = v if truthy(v) else r
        return v

    result = disjunction()
    assert pos == len(tokens), (expr, tokens[pos:])
    return result


def _fill(text: str, ctx: dict) -> str:
    def one(m):
        v = _evaluate(m.group(1).strip(), ctx)
        return "" if v in (None, False) else str(v)
    return re.sub(r"\$\{\{(.*?)\}\}", one, text)


def _event(name, action=None, label=None, labels=()):
    ev = {"action": action, "label": {"name": label}, "pull_request": {"labels": [{"name": n} for n in labels]}}
    return {"github": {"event_name": name, "ref": "refs/pull/7/merge", "run_id": "4242", "event": ev}}


def _yaml(name):
    if required("yaml"):                       # CI installs it: missing is a failure there
        import yaml
    else:
        yaml = pytest.importorskip("yaml")
    return yaml.safe_load(_text(name))


def _job_runs(job, ctx):
    cond = job.get("if")
    if cond is None:
        return True
    cond = str(cond).strip()
    if cond.startswith("${{"):
        cond = cond[3:-2]
    return _evaluate(cond, ctx) not in (None, False, "", 0)


@pytest.mark.parametrize("name, label, jobs", [
    ("release-checks.yml", "release-checks", ["image"]),
    ("packages.yml", "packages", ["deb", "arch", "rpm"]),
])
def test_only_the_workflows_own_label_starts_or_cancels_a_run(name, label, jobs):
    doc = _yaml(name)
    assert doc[True]["pull_request"]["types"] == ["labeled", "synchronize"]    # YAML reads a bare `on` as true
    base = f"{name.split('.')[0]}-refs/pull/7/merge"

    def run(event, **kw):
        ctx = _event(event, **kw)
        return {j: _job_runs(doc["jobs"][j], ctx) for j in jobs}, _fill(doc["concurrency"]["group"], ctx)

    # A push to a pull request that has the label: runs, and replaces the run before it.
    started, group = run("pull_request", action="synchronize", labels=[label, "bug"])
    assert all(started.values()) and group == base
    # The label itself being added: the same.
    started, group = run("pull_request", action="labeled", label=label, labels=[label])
    assert all(started.values()) and group == base
    # Any other label, even on a pull request that has ours: nothing starts, and it joins a
    # group of its own, so the run in progress in `base` is not cancelled.
    for other in ("bug", "documentation", "packages" if label != "packages" else "release-checks"):
        started, group = run("pull_request", action="labeled", label=other, labels=[label, other])
        assert not any(started.values()), (other, started)
        assert group != base and group.startswith(base), group
    # A push to a pull request without the label starts nothing.
    started, _ = run("pull_request", action="synchronize", labels=["bug"])
    assert not any(started.values())
    # Not a pull request (a release, a hand-started run, a call from the Release workflow).
    first = jobs[0]
    for event in ("workflow_dispatch", "push", "workflow_call"):
        started, group = run(event)
        assert started[first] and group == base
    if name == "release-checks.yml":
        for lane in ("desktop", "ubuntu", "stock"):
            assert doc["jobs"][lane]["needs"] == "image"           # skipped together with the image job
            assert "if" not in doc["jobs"][lane]
    else:
        assert doc["concurrency"]["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"


def test_gnome_next_workflow_is_weekly_read_only_and_runs_the_tests():
    text = _text("gnome-next.yml")
    assert "schedule:" in text and "cron:" in text and "workflow_dispatch:" in text
    assert re.search(r"^permissions:\n  contents: read\n", text, re.M) and "write" not in text
    assert re.search(r"container: fedora:rawhide@sha256:[0-9a-f]{64}", text)
    assert "repoquery" in text and "gnome-shell" in text and "check-gnome-next.sh" in text
    assert "python3 -m pytest" in text and "node --import ./tests/js/register.mjs --test" in text


def _gnome_check(version: str, meta: Path | None = None):
    meta = meta or ROOT / "fedoraglass/data/extension/liquid-glass@djshiye.github.io/metadata.json"
    return subprocess.run(["sh", str(PKG / "check-gnome-next.sh"), str(meta), version], capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("version", ["50.2", "51.1", "51~rc", "49.5"])
def test_gnome_next_is_quiet_for_a_supported_gnome(version):
    r = _gnome_check(version)
    assert r.returncode == 0 and "::error" not in r.stdout


@pytest.mark.parametrize("version", ["52.alpha", "52~beta", "52.0", "53.1"])
def test_gnome_next_fails_with_a_clear_title_for_a_newer_gnome(version):
    r = _gnome_check(version)
    major = version[:2]
    assert r.returncode == 1
    assert f"::error title=GNOME {major} is coming%3A add it to Fedora Glass and test::" in r.stdout


def test_gnome_next_follows_metadata_json(tmp_path):
    meta = tmp_path / "metadata.json"
    meta.write_text('{"shell-version": ["50", "51", "52"]}')
    assert _gnome_check("52.alpha", meta).returncode == 0
    assert _gnome_check("53~alpha", meta).returncode == 1
    assert _gnome_check("garbage", meta).returncode == 2


def test_every_place_that_runs_the_tests_has_the_glib_tools_and_refuses_to_skip():
    """The login screen tests skip without gresource and glib-compile-resources. Every place
    that runs the tests installs the packages that have them and sets FEDORAGLASS_REQUIRE, so
    a missing tool fails there instead of skipping 16 tests unseen."""
    quick = _jobs(_text("quick-tests.yml"))["tests"]
    assert "libglib2.0-bin" in quick and "libglib2.0-dev-bin" in quick and "FEDORAGLASS_REQUIRE: glib yaml" in quick
    assert "python3-yaml" in quick                                   # the workflow tests read the YAML
    rawhide = _text("gnome-next.yml")
    assert "glib2-devel" in rawhide and "python3-pyyaml" in rawhide and "FEDORAGLASS_REQUIRE: glib yaml" in rawhide
    # The rpm builds run the tests in %check: the spec asks for the tools, the jobs install them.
    spec = (PKG / "fedora-glass.spec").read_text()
    for tool in ("gresource", "glib-compile-resources"):
        assert f"BuildRequires:  /usr/bin/{tool}\n" in spec
    for wf, job in (("release.yml", "rpm"), ("packages.yml", "rpm")):
        block = _jobs(_text(wf))[job]
        assert "glib2-devel" in block and "FEDORAGLASS_REQUIRE: glib" in block, wf
    # And the guard itself: it sits next to the tests that need the tools.
    assert 'required("glib")' in (ROOT / "tests/test_login_screen.py").read_text()


def test_the_guard_reads_fedoraglass_require(monkeypatch):
    monkeypatch.delenv("FEDORAGLASS_REQUIRE", raising=False)
    assert not required("glib")
    monkeypatch.setenv("FEDORAGLASS_REQUIRE", "glib yaml")
    assert required("glib") and required("yaml") and not required("other")
    monkeypatch.setenv("FEDORAGLASS_REQUIRE", "yaml,glib")
    assert required("glib")


def test_dependabot_and_issue_form_and_security_policy():
    dep = (ROOT / ".github/dependabot.yml").read_text()
    for eco in ("github-actions", "docker"):
        assert f"package-ecosystem: {eco}" in dep
    assert dep.count("interval: weekly") == 2 and dep.count("groups:") == 2 and "cooldown:" in dep
    assert '"/.github/actions/*"' in dep and '"/qa/desktop"' in dep
    form = (ROOT / ".github/ISSUE_TEMPLATE/bug.yml").read_text()
    for field in ("Linux", "GNOME version", "Fedora Glass version", "What happened", "Screenshot"):
        assert f"label: {field}\n" in form
    assert "security/advisories/new" in (ROOT / "SECURITY.md").read_text()


# ---- the three packages agree --------------------------------------------------------------

def test_the_packages_ask_for_the_same_things():
    spec = (PKG / "fedora-glass.spec").read_text()
    pkgbuild = (PKG / "arch/PKGBUILD").read_text()
    control = (PKG / "deb/control.in").read_text()
    # GNOME 50 or newer on all three.
    assert "'gnome-shell>=50'" in pkgbuild and "gnome-shell (>= 50~)" in control
    # undo-for-users needs dbus-run-session: the rpm names the file (dbus-daemon has it on
    # Fedora), Ubuntu's dbus-bin and Arch's dbus ship it.
    assert spec.count("Requires:       /usr/bin/dbus-run-session\n") == 2
    assert "dbus-bin" in control and "'dbus'" in pkgbuild
    # Ubuntu has no adw-gtk3 package (checked against the 26.04 and 26.10 archives), so the
    # .deb cannot recommend it, and the engine and install.sh do not ask for it there.
    assert "adw-gtk3" not in control
    install = (ROOT / "install.sh").read_text()
    apt_list = install.split("elif command -v apt-get", 1)[1].split("elif command -v pacman", 1)[0]
    assert "adw-gtk3" not in apt_list


def test_each_package_ships_the_metainfo_and_byte_code():
    spec = (PKG / "fedora-glass.spec").read_text()
    tree = (PKG / "install-tree.sh").read_text()
    assert spec.count("\n%{_datadir}/metainfo/io.github.djshiye.LiquidGlass.metainfo.xml\n") == 2     # %files, both packages
    assert "%py_byte_compile %{python3} %{buildroot}%{_datadir}/fedora-glass" in spec
    # The stray byte code of a working copy goes first, ours is made after it.
    assert spec.index("-name '__pycache__'") < spec.index("\n%py_byte_compile")
    assert "BuildRequires:  python-rpm-macros" in spec
    assert 'usr/share/metainfo/io.github.djshiye.LiquidGlass.metainfo.xml"' in tree
    assert tree.index("-name '__pycache__'") < tree.index("compileall") < tree.index("chmod 644")
    assert "--invalidation-mode unchecked-hash" in tree
    # The .deb and the Arch package both come from install-tree.sh.
    assert "install-tree.sh" in (PKG / "deb/build-deb.sh").read_text()
    assert "install-tree.sh" in (PKG / "arch/PKGBUILD").read_text()


def test_install_tree_ships_unchecked_hash_byte_code_and_the_metainfo(tmp_path):
    work = tmp_path / "src"
    work.mkdir()
    # A copy of what the tree needs, with a stray .pyc from "another machine" in the code.
    import shutil
    for name in ("fedoraglass", "data", "packaging", "LICENSE", "LICENSES", "THIRD-PARTY-NOTICES.md"):
        src = ROOT / name
        if src.is_dir():
            shutil.copytree(src, work / name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy(src, work / name)
    stray = work / "fedoraglass/__pycache__"
    stray.mkdir()
    (stray / "stray.cpython-312.pyc").write_bytes(b"not ours")
    dest = tmp_path / "dest"
    r = subprocess.run(["sh", str(PKG / "install-tree.sh"), str(work), str(dest)], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    code = dest / "usr/share/fedora-glass/fedoraglass"
    assert not list(code.rglob("stray*.pyc"))
    pycs = list(code.rglob("*.pyc"))
    assert len(pycs) > 20
    tag = sys.implementation.cache_tag
    assert all(p.name.endswith(f".{tag}.pyc") for p in pycs)
    # unchecked-hash: flags 0b01 (hash based, source not checked), the same bytes every build.
    assert all(int.from_bytes(p.read_bytes()[4:8], "little") == 1 for p in pycs)
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o644 for p in pycs)
    # The path inside is the installed one, not the build folder.
    main_pyc = next(p for p in pycs if p.name.startswith("__main__."))
    assert b"/usr/share/fedora-glass/fedoraglass/__main__.py" in main_pyc.read_bytes()
    assert str(dest).encode() not in main_pyc.read_bytes()
    meta = dest / "usr/share/metainfo/io.github.djshiye.LiquidGlass.metainfo.xml"
    assert meta.read_text() == (ROOT / "data/io.github.djshiye.LiquidGlass.metainfo.xml").read_text()


def test_metainfo_matches_the_desktop_file_and_the_licences():
    import xml.etree.ElementTree as ET
    meta = ROOT / "data/io.github.djshiye.LiquidGlass.metainfo.xml"
    root = ET.parse(meta).getroot()
    desktop = ROOT / "data/io.github.djshiye.LiquidGlass.desktop"
    assert root.findtext("id") == desktop.name.removesuffix(".desktop") == meta.name.removesuffix(".metainfo.xml")
    assert root.findtext("launchable") == desktop.name
    assert root.find("content_rating").get("type") == "oars-1.1"
    # The licence is the spec's, spelled the same.
    spec = (PKG / "fedora-glass.spec").read_text()
    assert root.findtext("project_license") == re.search(r"^License:\s+(.*)$", spec, re.M).group(1)
    # Screenshots come from docs/screenshots on GitHub, and those files exist.
    urls = [i.text for i in root.iter("image")]
    assert urls
    for url in urls:
        name = url.removeprefix("https://raw.githubusercontent.com/djshiye/fedora-glass/main/docs/screenshots/")
        assert name != url and (ROOT / "docs/screenshots" / name).is_file(), url
    # The last releases, newest first.
    versions = [r.get("version") for r in root.iter("release")]
    assert len(versions) >= 3
    key = lambda v: tuple(int(x) for x in v.split("."))
    assert versions == sorted(versions, key=key, reverse=True)


def test_licences_in_the_notices_match_the_spec_and_the_other_packages():
    spec = (PKG / "fedora-glass.spec").read_text()
    license_tag = re.search(r"^License:\s+(.*)$", spec, re.M).group(1)
    assert "or-later" not in license_tag
    assert re.search(r"license=\(.*\)", (PKG / "arch/PKGBUILD").read_text()).group(0).replace("'", "").replace(" ", "|") \
        == "license=(" + "|".join(t for t in license_tag.split(" AND ")) + ")"
    notices = (ROOT / "THIRD-PARTY-NOTICES.md").read_text()
    assert "or later" not in notices.split("## Mouse pointer styles", 1)[1].split("### Bibata", 1)[0].replace('no "or later" notice', "")
    for line in re.findall(r"^(?:Copyright .*?\. )?(GPL-[\d.]+(?:-only)?|CC-BY-SA-4\.0)(?: .*)?\.$", notices, re.M):
        assert line in ("GPL-3.0-only", "GPL-2.0-only", "CC-BY-SA-4.0"), line
