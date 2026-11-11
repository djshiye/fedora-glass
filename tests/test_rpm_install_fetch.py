"""packaging/rpm-install-test.sh fetches older releases' packages for the upgrade checks.
Only a release that doesn't have the package skips a check; GitHub not answering, or a
file that doesn't match its SHA256SUMS, fails the run instead of passing as "not tested".
The script's own functions run here against a fake `gh`."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "packaging/rpm-install-test.sh"

pytestmark = pytest.mark.skipif(not shutil.which("bash") or not shutil.which("sha256sum"),
                                reason="needs bash and sha256sum")

FAKE_GH = r'''#!/bin/bash
# gh api [-H ...] PATH [--jq EXPR], as the script uses it. $FAKE picks what goes wrong.
args=("$@"); path=""; jq=""
for ((i = 1; i < ${#args[@]}; i++)); do
    case "${args[i]}" in
        -H) i=$((i + 1)) ;;
        --jq) i=$((i + 1)); jq="${args[i]}" ;;
        *) path="${args[i]}" ;;
    esac
done
good=$'the rpm\n'
case "$path" in
    */releases/tags/*)
        [ "$FAKE" != apierror ] || { echo "HTTP 502: Bad Gateway" >&2; exit 1; }
        [ "$FAKE" != norelease ] || { echo "HTTP 404: Not Found" >&2; exit 1; }
        case "$jq" in
            *'"SHA256SUMS"'*) echo 1 ;;
            *) [ "$FAKE" = noasset ] || echo 2 ;;
        esac ;;
    */releases/assets/1) printf '%s  pkg.rpm\n' "$(printf '%s' "$good" | sha256sum | cut -d' ' -f1)" ;;
    */releases/assets/2)
        [ "$FAKE" != cut ] || { printf 'the r'; exit 1; }
        if [ "$FAKE" = mismatch ]; then printf 'not the rpm\n'; else printf '%s' "$good"; fi ;;
    *) echo "unexpected $path" >&2; exit 1 ;;
esac
'''


def _functions() -> str:
    text = SCRIPT.read_text()
    found = re.findall(r"^(?:fetch|fetch_or_skip)\(\) \{\n.*?^\}$", text, re.M | re.S)
    assert len(found) == 2, "fetch and fetch_or_skip"
    return "\n".join(found)


def _run(tmp_path, fake):
    bin_ = tmp_path / "bin"
    bin_.mkdir(exist_ok=True)
    gh = bin_ / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    driver = ("set -euo pipefail\nwork=\"$(mktemp -d)\" repo=owner/repo\n" + _functions() +
              '\nold="$(fetch_or_skip v1.0 pkg.rpm)"\n'
              'if [ -n "$old" ]; then echo "tested $(cat "$old")"; else echo "not tested"; fi\n')
    import os
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "FAKE": fake}
    return subprocess.run(["bash", "-c", driver], env=env, capture_output=True, text=True, timeout=30)


def test_a_good_package_is_fetched(tmp_path):
    r = _run(tmp_path, "")
    assert r.returncode == 0 and r.stdout.strip() == "tested the rpm", r.stderr


@pytest.mark.parametrize("fake", ["noasset", "norelease"])
def test_a_release_without_the_package_skips_the_check(tmp_path, fake):
    r = _run(tmp_path, fake)
    assert r.returncode == 0 and r.stdout.strip() == "not tested", r.stderr


@pytest.mark.parametrize("fake", ["mismatch", "apierror", "cut"])
def test_anything_else_fails_the_run(tmp_path, fake):
    r = _run(tmp_path, fake)
    assert r.returncode != 0, r.stdout
    assert "not tested" not in r.stdout and "tested" not in r.stdout


def test_shellcheck_is_happy():
    sc = shutil.which("shellcheck")
    if sc is None:
        pytest.skip("no shellcheck here")
    r = subprocess.run([sc, str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
