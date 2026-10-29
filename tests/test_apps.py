from __future__ import annotations

import io
import json
import re
import zipfile

import pytest

from liquidglass import palette
from liquidglass.render import apps as ra
from liquidglass.settings import Settings
from liquidglass.targets import apps as ta
from liquidglass.targets import myapps
from liquidglass.targets.base import Command, Context, WriteFile

CASES = [(d, f) for d in (True, False) for f in (0.0, 1.0)]
HEX = re.compile(r"#[0-9a-f]{6}(?:[0-9a-f]{2})?")


def toks(dark, frost, **kw):
    return palette.build(Settings(frost=frost, **kw), dark=dark)


def ctx_for(env, dark=True, frost=0.4, **kw):
    s = Settings(frost=frost, scheme=kw.pop("scheme", "dark" if dark else "light"), **kw)
    d, l = palette.build(s, dark=True), palette.build(s, dark=False)
    return Context(settings=s, tokens=d if dark else l, dark=d, light=l, env=env)


def by_name(plan):
    return {a.path.name: a for a in plan if isinstance(a, WriteFile)}


def balanced(css: str) -> bool:
    depth = 0
    for ch in css:
        depth += ch == "{"
        depth -= ch == "}"
        if depth < 0:
            return False
    return depth == 0


# ---- text helpers ------------------------------------------------------------------------
def test_merge_json_keeps_keys_and_rejects_comments():
    out = ra.merge_json_text('{"a": 1, "workbench.colorTheme": "x"}', {"workbench.colorTheme": "y"})
    assert json.loads(out) == {"a": 1, "workbench.colorTheme": "y"}
    assert ra.merge_json_text('{\n // comment\n "a": 1}', {"b": 2}) is None
    assert ra.merge_json_text("[1]", {"b": 2}) is None
    assert json.loads(ra.merge_json_text(None, {"b": 2})) == {"b": 2}
    assert json.loads(ra.merge_json_text("  ", {"b": 2})) == {"b": 2}


def test_ini_set_preserves_other_lines():
    ini = "[General]\nx=1\n\n[Preferences]\nA\\B=1\nGeneral\\UseCustomUITheme=false\n\n[Other]\nz=3\n"
    out = ra.ini_set(ini, "Preferences", {"General\\UseCustomUITheme": "true", "General\\CustomUIThemePath": "/p"})
    assert out == ("[General]\nx=1\n\n[Preferences]\nA\\B=1\nGeneral\\UseCustomUITheme=true\n"
                   "General\\CustomUIThemePath=/p\n\n[Other]\nz=3\n")
    assert ra.ini_set(out, "Preferences", {"General\\UseCustomUITheme": "true"}) == out


def test_ini_set_creates_section_and_handles_no_trailing_newline():
    assert ra.ini_set("", "S", {"k": "v"}) == "[S]\nk=v\n"
    assert ra.ini_set("[A]\nx=1", "S", {"k": "v"}) == "[A]\nx=1\n\n[S]\nk=v\n"
    assert ra.ini_set("[S]\nx=1", "S", {"k": "v"}) == "[S]\nx=1\nk=v\n"


# ---- VS Code --------------------------------------------------------------------------------
@pytest.mark.parametrize("dark,frost", CASES)
def test_vscode_theme(dark, frost):
    th = ra.vscode_theme(toks(dark, frost))
    assert th["type"] == ("dark" if dark else "light")
    assert len(th["colors"]) > 150 and th["tokenColors"]
    assert all(HEX.fullmatch(v) for v in th["colors"].values()), \
        [k for k, v in th["colors"].items() if not HEX.fullmatch(v)]
    assert "None" not in json.dumps(th)


def test_vsix_structure():
    data = ra.vsix_bytes(toks(True, 0.3), toks(False, 0.3))
    z = zipfile.ZipFile(io.BytesIO(data))
    assert z.testzip() is None
    names = set(z.namelist())
    assert {"[Content_Types].xml", "extension.vsixmanifest", "extension/package.json",
            "extension/themes/liquid-glass-dark-color-theme.json",
            "extension/themes/liquid-glass-light-color-theme.json"} <= names
    pkg = json.loads(z.read("extension/package.json"))
    assert f"{pkg['publisher']}.{pkg['name']}" == "djshiye.liquid-glass-theme"
    for t in pkg["contributes"]["themes"]:
        assert "extension/" + t["path"][2:] in names
        json.loads(z.read("extension/" + t["path"][2:]))
    import xml.dom.minidom as md
    md.parseString(z.read("[Content_Types].xml"))
    md.parseString(z.read("extension.vsixmanifest"))
    assert ra.vsix_bytes(toks(True, 0.3), toks(False, 0.3)) == data   # deterministic


def test_vscode_plan_installs_and_merges(fake_env):
    (fake_env.config / "Code/User").mkdir(parents=True)
    sp = fake_env.config / "Code/User/settings.json"
    sp.write_text('{"editor.fontSize": 15}')
    plan = ta.VSCode().plan(ctx_for(fake_env, scheme="auto"))
    cmd = next(a for a in plan if isinstance(a, Command))
    assert cmd.argv[:2] == ("code", "--install-extension") and cmd.argv[-1] == "--force"
    assert cmd.undo == ("code", "--uninstall-extension", "djshiye.liquid-glass-theme")
    assert cmd.argv[2].endswith("liquid-glass/vscode/liquid-glass.vsix")
    st = json.loads(by_name(plan)["settings.json"].content)
    assert st["editor.fontSize"] == 15 and st["workbench.colorTheme"] == "Liquid Glass Dark"
    assert st["workbench.preferredLightColorTheme"] == "Liquid Glass Light"


def test_vscode_skips_commented_settings_and_unchanged_install(fake_env):
    (fake_env.config / "Code/User").mkdir(parents=True)
    (fake_env.config / "Code/User/settings.json").write_text('{\n// hi\n"a": 1}')
    c = ctx_for(fake_env)
    plan = ta.VSCode().plan(c)
    assert "settings.json" not in by_name(plan)
    assert "comments" in ta.VSCode().live_notes(c)[0]
    # already installed with identical bytes: no reinstall
    vsix = next(a for a in plan if isinstance(a, WriteFile))
    vsix.path.parent.mkdir(parents=True)
    vsix.path.write_bytes(vsix.content)
    (fake_env.home / ".vscode/extensions/djshiye.liquid-glass-theme-1.0.0").mkdir(parents=True)
    assert not any(isinstance(a, Command) for a in ta.VSCode().plan(c))


# ---- Discord ------------------------------------------------------------------------------------
@pytest.mark.parametrize("dark,frost", CASES)
def test_discord_css(dark, frost):
    css = ra.discord_css(toks(True, frost), toks(False, frost))
    assert css.startswith("/**") and "@name Liquid Glass" in css
    assert balanced(css) and "None" not in css and ".theme-dark" in css and ".theme-light" in css


def test_discord_plan_enables_theme_when_settings_exist(fake_env):
    v = fake_env.home / ".var/app/com.discordapp.Discord/config/Vencord"
    (v / "settings").mkdir(parents=True)
    (v / "settings/settings.json").write_text('{"enabledThemes": ["other.css"], "plugins": {"a": {"enabled": true}}}')
    plan = ta.Discord().plan(ctx_for(fake_env))
    files = by_name(plan)
    assert files["liquid-glass.theme.css"].path == v / "themes/liquid-glass.theme.css"
    st = json.loads(files["settings.json"].content)
    assert st["enabledThemes"] == ["other.css", "liquid-glass.theme.css"] and st["plugins"]["a"]["enabled"]


def test_discord_no_settings_file_only_writes_theme(fake_env):
    (fake_env.config / "Vencord").mkdir(parents=True)
    assert [a.path.name for a in ta.Discord().plan(ctx_for(fake_env))] == ["liquid-glass.theme.css"]


# ---- Obsidian -------------------------------------------------------------------------------------
def test_obsidian_plan(fake_env, tmp_path):
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / ".obsidian/appearance.json").write_text('{"baseFontSize": 17, "cssTheme": ""}')
    cfg = fake_env.config / "obsidian"
    cfg.mkdir(parents=True)
    (cfg / "obsidian.json").write_text(json.dumps({"vaults": {
        "a": {"path": str(vault)}, "b": {"path": str(tmp_path / "gone")}, "c": {"path": "relative"}}}))
    plan = ta.Obsidian().plan(ctx_for(fake_env))
    files = by_name(plan)
    assert files["theme.css"].path == vault / ".obsidian/themes/Liquid Glass/theme.css"
    assert json.loads(files["manifest.json"].content)["name"] == "Liquid Glass"
    assert json.loads(files["appearance.json"].content) == {"baseFontSize": 17, "cssTheme": "Liquid Glass"}
    assert len(plan) == 3
    assert balanced(files["theme.css"].content)


# ---- qBittorrent and Prism ----------------------------------------------------------------------------
def _qt_ok(qss: str) -> list[str]:
    """Polish real widgets with the sheet; Qt warns "Could not parse stylesheet" on bad syntax."""
    qtw = pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtCore import qInstallMessageHandler
    msgs: list[str] = []
    qInstallMessageHandler(lambda t, c, m: msgs.append(m))
    app = qtw.QApplication.instance() or qtw.QApplication([])
    w = qtw.QWidget()
    lay = qtw.QVBoxLayout(w)
    for kind in (qtw.QPushButton, qtw.QLineEdit, qtw.QComboBox, qtw.QTabBar, qtw.QProgressBar, qtw.QMenuBar):
        lay.addWidget(kind())
    w.setStyleSheet(qss)
    w.show()
    app.processEvents()
    qInstallMessageHandler(None)
    return [m for m in msgs if "parse" in m.lower()]


@pytest.mark.parametrize("dark,frost", CASES)
def test_qss_parses(dark, frost, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    qss = ra.qt_qss(toks(dark, frost))
    assert balanced(qss) and "rgba" not in qss and "None" not in qss
    assert _qt_ok(qss) == []


def test_qt_checker_catches_bad_sheet(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    assert _qt_ok("QPushButton { background: red ")


@pytest.mark.parametrize("dark,frost", CASES)
def test_qbittorrent_config_and_prism_theme(dark, frost):
    cfg = json.loads(ra.qbittorrent_config(toks(True, frost), toks(False, frost)))
    assert set(cfg) == {"colors", "colors.dark"}
    for block in cfg.values():
        assert block["Palette.Window"].startswith("#") and "Palette.TextDisabled" in block
        assert all(HEX.fullmatch(v) for v in block.values())
    pt = json.loads(ra.prism_theme_json(toks(dark, frost)))
    assert pt["widgets"] == "Fusion" and pt["qssFilePath"] == "themeStyle.css"
    assert {"Window", "Base", "Highlight", "Text"} <= set(pt["colors"])


def test_qbittorrent_plan_edits_conf(fake_env):
    conf = fake_env.config / "qBittorrent/qBittorrent.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("[BitTorrent]\nSession\\Port=1234\n\n[Preferences]\nGeneral\\Locale=en\n")
    plan = ta.QBittorrent().plan(ctx_for(fake_env))
    files = by_name(plan)
    theme_json = files["config.json"].path
    assert files["stylesheet.qss"].path.parent == theme_json.parent
    out = files["qBittorrent.conf"].content
    assert "Session\\Port=1234" in out and "General\\Locale=en" in out
    assert "General\\UseCustomUITheme=true" in out and f"General\\CustomUIThemePath={theme_json}" in out


def test_prism_plan(fake_env):
    d = fake_env.home / ".var/app/org.prismlauncher.PrismLauncher/data/PrismLauncher"
    d.mkdir(parents=True)
    (d / "prismlauncher.cfg").write_text("[General]\nApplicationTheme=dark\nLanguage=en_US\n")
    files = by_name(ta.Prism().plan(ctx_for(fake_env)))
    assert files["theme.json"].path == d / "themes/liquid-glass/theme.json"
    assert files["prismlauncher.cfg"].content == "[General]\nApplicationTheme=liquid-glass\nLanguage=en_US\n"


def test_prism_without_cfg_only_writes_theme(fake_env):
    d = fake_env.home / ".var/app/org.prismlauncher.PrismLauncher/data/PrismLauncher"
    d.mkdir(parents=True)
    assert "prismlauncher.cfg" not in by_name(ta.Prism().plan(ctx_for(fake_env)))


# ---- browsers and notes-only -------------------------------------------------------------------------------
@pytest.mark.parametrize("dark,frost", CASES)
def test_chromium_manifest(dark, frost):
    m = json.loads(ra.chromium_manifest(toks(dark, frost)))
    assert m["manifest_version"] == 3
    for k, v in m["theme"]["colors"].items():
        assert len(v) in (3, 4) and all(0 <= c <= 255 for c in v[:3]), k
    assert "toolbar" in m["theme"]["colors"] and "frame" in m["theme"]["colors"]


def test_browsers_plan_and_note(fake_env):
    c = ctx_for(fake_env)
    t = ta.Browsers()
    plan = t.plan(c)
    assert len(plan) == 1 and plan[0].path.parts[-3:] == ("liquid-glass", "chromium-theme", "manifest.json")
    assert any("Load unpacked" in n for n in t.live_notes(c))


def test_slack_theme_string_and_notes_only_targets(fake_env):
    s = ra.slack_theme(toks(True, 0.4))
    assert re.fullmatch(r"(#[0-9A-F]{6},){7}#[0-9A-F]{6}", s)
    c = ctx_for(fake_env)
    for t in ta.TARGETS + myapps.TARGETS:
        assert t.id and t.name and t.summary
        if isinstance(t, (ta.NotesOnly, myapps.MyApp)):
            assert t.plan(c) == []
    slack = next(t for t in ta.TARGETS if t.id == "slack")
    assert s in slack.live_notes(c)


def test_target_ids_unique_and_groups():
    ids = [t.id for t in ta.TARGETS + myapps.TARGETS]
    assert len(ids) == len(set(ids))
    assert {t.group for t in myapps.TARGETS} == {"My apps"}
    for want in ("discord", "vscode", "obsidian", "qbittorrent", "prism", "browsers", "slack", "steam",
                 "zoom", "claude-desktop", "libreoffice", "firefox", "clipperino", "rgbeast", "wheelguard"):
        assert want in ids


def test_detection(fake_env, monkeypatch):
    monkeypatch.setattr(type(fake_env), "which", lambda self, n: None)
    for t in ta.TARGETS + myapps.TARGETS:
        assert not t.detect(fake_env).available, t.id
    (fake_env.config / "obsidian").mkdir(parents=True)
    assert ta.Obsidian().detect(fake_env).available
    (fake_env.home / "AppImages").mkdir()
    (fake_env.home / "AppImages/qBittorrent-5.0-x86_64.AppImage").write_text("")
    assert ta.QBittorrent().detect(fake_env).available
    (fake_env.data / "applications").mkdir(parents=True)
    (fake_env.data / "applications/io.github.djshiye.Clipperino.desktop").write_text("[Desktop Entry]")
    assert myapps.TARGETS[0].detect(fake_env).available
