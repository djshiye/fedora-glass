"""The project page on GitHub Pages (pages/, built into the site by dnf-repo.yml through
packaging/build-pages.sh): its install blocks are the README's, word for word, it loads
nothing from other sites, and building it never replaces the signed repositories."""
from __future__ import annotations

import html
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "pages" / "index.html").read_text()
README = (ROOT / "README.md").read_text()


def _readme_block(distro: str) -> str:
    m = re.search(rf"\*\*{distro}\*\*\n\n```sh\n(.*?)```", README, re.S)
    assert m, distro
    return m.group(1)


def _page_block(cls: str) -> str:
    m = re.search(rf'<div class="panel {cls}">\s*<pre class="code" data-copy><code>(.*?)</code></pre>', PAGE, re.S)
    assert m, cls
    return html.unescape(m.group(1))


@pytest.mark.parametrize("distro,cls", [("Fedora", "p-fedora"), ("Ubuntu", "p-ubuntu"), ("Arch Linux", "p-arch")])
def test_install_blocks_match_the_readme(distro, cls):
    assert _page_block(cls) == _readme_block(distro)


def test_page_loads_nothing_from_other_sites():
    assert "Content-Security-Policy" in PAGE and "default-src 'none'" in PAGE
    for attr in re.findall(r'\b(?:src|href)="([^"]+)"', PAGE):
        assert not attr.startswith(("http:", "//")), attr
        if attr.startswith("https:"):
            # Links people click, never something the page loads.
            assert attr.startswith("https://github.com/djshiye/fedora-glass"), attr
    loaded = re.findall(r'<(?:script|img|video|link)\b[^>]*\b(?:src|href)="([^"]+)"', PAGE)
    assert loaded and all(not u.startswith("https:") for u in loaded), loaded
    css = (ROOT / "pages" / "style.css").read_text()
    assert "@import" not in css and "http" not in css
    js = (ROOT / "pages" / "site.js").read_text()
    assert "fetch(" not in js and "XMLHttpRequest" not in js and "http" not in js


def test_page_never_takes_a_repository_name():
    names = {p.name for p in (ROOT / "pages").iterdir()}
    assert not names & {"rpms", "apt", "arch", "version.txt", "fedora-glass.repo", "liquid-glass.repo",
                        "RPM-GPG-KEY-fedora-glass", "screenshots", "icon.svg"}


def test_workflow_builds_the_page_after_the_repository_files():
    wf = (ROOT / ".github/workflows/dnf-repo.yml").read_text()
    cp = wf.index("cp packaging/fedora-glass.repo packaging/liquid-glass.repo packaging/RPM-GPG-KEY-fedora-glass site/")
    build = wf.index('sh packaging/build-pages.sh site "${TAG#v}"')
    assert cp < build < wf.index("upload-pages-artifact")


def test_build_adds_the_page_and_refuses_to_replace(tmp_path):
    site = tmp_path / "site"
    (site / "rpms").mkdir(parents=True)
    (site / "version.txt").write_text("1.7.3-1\n")
    run = lambda *a: subprocess.run(["sh", "packaging/build-pages.sh", *a], cwd=ROOT, capture_output=True, text=True)
    r = run(str(site), "1.7.3")
    assert r.returncode == 0, r.stdout + r.stderr
    index = (site / "index.html").read_text()
    assert "Version 1.7.3" in index and "@VERSION@" not in index
    for f in ("style.css", "site.js", "icon.svg", "media/demo.mp4", "media/starfield.jpg", "screenshots/desktop.jpg"):
        assert (site / f).is_file(), f
    # Every image the page shows is in the site.
    for src in re.findall(r'(?:src|poster|href)="((?:screenshots|media)/[^"]+)"', index):
        assert (site / src).is_file(), src
    assert (site / "version.txt").read_text() == "1.7.3-1\n"
    # A second run (or a page file that would clash) changes nothing.
    assert run(str(site), "1.7.3").returncode != 0
    assert run(str(tmp_path / "other"), "1.7.3").returncode != 0
    shutil.rmtree(site / "screenshots")
    assert run(str(site), "1.7.3;rm -rf /").returncode != 0
