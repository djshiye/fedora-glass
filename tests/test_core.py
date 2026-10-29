from __future__ import annotations

import json
from dataclasses import dataclass

from liquidglass import palette, settings
from liquidglass.color import Color
from liquidglass.engine import Engine
from liquidglass.settings import Settings
from liquidglass.targets.base import Command, Context, GSet, Target, WriteFile


@dataclass
class FileTarget(Target):
    def plan(self, ctx: Context):
        p = ctx.env.config / "gtk-4.0/gtk.css"
        return [WriteFile(p, f"/* {ctx.tokens.chrome.css} */"),
                GSet("org.gnome.desktop.interface", "gtk-theme", "'adw-gtk3-dark'"),
                GSet("org.gnome.desktop.interface", "no-such-key", "1"),
                Command(("flatpak", "override", "--user"), "test", undo=("flatpak", "undo"))]


def make_engine(env):
    return Engine(env, [FileTarget(id="t", name="Test")])


# ---- colour and palette ----------------------------------------------------------
def test_color_roundtrip_and_formats():
    c = Color.hex("#3584e4").with_alpha(0.5)
    assert c.hex6 == "#3584e4"
    assert c.hex8 == "#3584e480"
    assert c.argb == "#803584e4"
    assert c.css == "rgba(53,132,228,0.500)"


def test_frost_moves_every_surface_monotonically():
    for dark in (True, False):
        t0 = palette.build(Settings(frost=0), dark=dark)
        t1 = palette.build(Settings(frost=1), dark=dark)
        for name in ("window", "chrome", "view", "popover"):
            assert getattr(t0, name).a < getattr(t1, name).a, name
        assert t0.blur_radius < t1.blur_radius
        assert t0.highlight.a > t1.highlight.a


def _over(surface: Color, backdrop: Color) -> Color:
    return backdrop.mix(surface.with_alpha(1), surface.a)


def test_text_contrast_on_glass():
    """Body text must stay readable (WCAG 4.5:1) whatever is behind the glass:
    content views over the most hostile backdrop (white behind dark glass,
    black behind light glass), chrome and window over an average photo."""
    grey = Color(0.5, 0.5, 0.5)
    for dark in (True, False):
        hostile = Color(1, 1, 1) if dark else Color(0, 0, 0)
        for f in (0.0, 0.25, 0.5, 0.75, 1.0):
            t = palette.build(Settings(frost=f), dark=dark)
            assert t.fg.contrast(_over(t.view, hostile)) >= 4.5, ("view", dark, f)
            assert t.fg.contrast(_over(t.window, grey)) >= 4.5, ("window", dark, f)
            assert t.fg.contrast(_over(t.chrome, grey)) >= 4.5, ("chrome", dark, f)
            assert t.fg.contrast(_over(t.popover, hostile)) >= 4.5, ("popover", dark, f)


def test_reduce_transparency_is_nearly_opaque():
    t = palette.build(Settings(reduce_transparency=True), dark=True)
    assert min(t.window.a, t.chrome.a, t.view.a, t.popover.a) >= 0.95
    assert t.blur_radius == 0


def test_settings_normalize_and_roundtrip(tmp_path):
    s = Settings(frost=3, radius=99, accent="nope", scheme="weird", tint="red").normalized()
    assert (s.frost, s.radius, s.accent, s.scheme, s.tint) == (1.0, 32, "system", "auto", Settings.tint)
    p = settings.save(Settings(frost=0.2, targets={"qt": False}), tmp_path / "s.json")
    back = settings.load(p)
    assert back.frost == 0.2 and back.target_enabled("qt") is False and back.target_enabled("gtk4")
    p.write_text("{broken")
    assert settings.load(p) == Settings()


def test_presets_reset_overrides():
    s = settings.apply_preset(Settings(opacity=0.3, blur=5), "Frosted")
    assert s.frost == 0.8 and s.opacity is None and s.blur is None


# ---- engine ---------------------------------------------------------------------------
def test_apply_then_revert_restores_symlink_and_settings(fake_env):
    css = fake_env.config / "gtk-4.0/gtk.css"
    theme = fake_env.home / ".themes/Orchis/gtk.css"
    theme.parent.mkdir(parents=True)
    theme.write_text("orchis")
    css.parent.mkdir(parents=True)
    css.symlink_to(theme)

    eng = make_engine(fake_env)
    res = eng.apply(Settings())
    assert [r.status for r in res] == ["applied"]
    assert not css.is_symlink() and css.read_text().startswith("/* rgba(")
    assert theme.read_text() == "orchis"  # never wrote through the link
    assert fake_env.gs[("org.gnome.desktop.interface", None)]["gtk-theme"] == "'adw-gtk3-dark'"
    assert "no-such-key" not in fake_env.gs[("org.gnome.desktop.interface", None)]
    assert ["flatpak", "override", "--user"] in fake_env.commands
    tokens = json.loads((fake_env.config / "liquid-glass/tokens.json").read_text())
    assert tokens["dark"] is True and tokens["version"] == 1

    # A second apply must not overwrite the original backup with our own output.
    eng.apply(Settings(frost=1))
    assert eng.revert() == []
    assert css.is_symlink() and css.resolve() == theme.resolve()
    assert fake_env.gs[("org.gnome.desktop.interface", None)]["gtk-theme"] == "'Adwaita'"
    assert ["flatpak", "undo"] in fake_env.commands


def test_new_file_is_removed_on_revert(fake_env):
    eng = make_engine(fake_env)
    eng.apply(Settings())
    css = fake_env.config / "gtk-4.0/gtk.css"
    assert css.exists()
    eng.revert("t")
    assert not css.exists()


def test_disabling_a_target_reverts_it(fake_env):
    eng = make_engine(fake_env)
    eng.apply(Settings())
    res = eng.apply(Settings(targets={"t": False}))
    assert [r.status for r in res] == ["reverted"]
    assert not (fake_env.config / "gtk-4.0/gtk.css").exists()


def test_broken_target_does_not_stop_others(fake_env):
    @dataclass
    class Boom(Target):
        def plan(self, ctx):
            raise RuntimeError("bad")

    eng = Engine(fake_env, [Boom(id="b", name="Boom"), FileTarget(id="t", name="Test")])
    res = {r.target: r.status for r in eng.apply(Settings())}
    assert res == {"b": "failed", "t": "applied"}


def test_dry_run_changes_nothing(fake_env):
    fake_env.dry_run = True
    eng = make_engine(fake_env)
    eng.apply(Settings())
    assert not (fake_env.config / "gtk-4.0/gtk.css").exists()
    assert fake_env.commands == []


# ---- review regressions ---------------------------------------------------------------
@dataclass
class TwoCss(Target):
    folder: str = ""

    def plan(self, ctx):
        return [WriteFile(ctx.env.config / self.folder / "gtk.css", f"/* {self.id} */")]


def test_backups_of_same_named_files_never_collide(fake_env):
    """gtk-3.0/gtk.css and gtk-4.0/gtk.css must keep separate originals, whatever the order."""
    g3, g4 = fake_env.config / "gtk-3.0/gtk.css", fake_env.config / "gtk-4.0/gtk.css"
    for p, text in ((g3, "mine3"), (g4, "mine4")):
        p.parent.mkdir(parents=True)
        p.write_text(text)
    eng = Engine(fake_env, [TwoCss(id="a", folder="gtk-3.0"), TwoCss(id="b", folder="gtk-4.0")])
    eng.apply(Settings())
    eng.revert("a")
    eng.apply(Settings())          # re-records a, while b's copy still exists
    assert eng.revert() == []
    assert (g3.read_text(), g4.read_text()) == ("mine3", "mine4")
    assert not list((fake_env.state / "liquid-glass/backup/files").iterdir())   # copies cleaned up


def test_flatpak_override_is_undone_item_by_item(fake_env):
    from liquidglass.targets.base import FlatpakOverride

    @dataclass
    class Fp(Target):
        ov: FlatpakOverride = FlatpakOverride()

        def plan(self, ctx):
            return [self.ov]

    f = fake_env.data / "flatpak/overrides/global"
    f.parent.mkdir(parents=True)
    f.write_text("[Context]\nfilesystems=~/Games:ro;\n")
    gtk = Fp(id="gtk", ov=FlatpakOverride(filesystems=("xdg-config/gtk-4.0:ro",)))
    qt = Fp(id="qt", ov=FlatpakOverride(filesystems=("xdg-config/Kvantum:ro",), env=(("QT_STYLE_OVERRIDE", "kvantum"),)))
    eng = Engine(fake_env, [gtk, qt])
    eng.apply(Settings())
    eng.apply(Settings())                                     # idempotent
    text = f.read_text()
    assert "filesystems=~/Games:ro;xdg-config/gtk-4.0:ro;xdg-config/Kvantum:ro;" in text
    assert "QT_STYLE_OVERRIDE=kvantum" in text
    # The user adds their own override afterwards; reverting qt only removes qt's items.
    f.write_text(text.replace("Kvantum:ro;", "Kvantum:ro;xdg-music;"))
    eng.revert("qt")
    text = f.read_text()
    assert "xdg-config/Kvantum" not in text and "QT_STYLE_OVERRIDE" not in text
    assert "xdg-config/gtk-4.0:ro" in text and "xdg-music" in text
    eng.revert()
    assert f.read_text().strip() == "[Context]\nfilesystems=~/Games:ro;xdg-music;"


def test_revert_removes_token_files_and_watcher_sees_nothing_applied(fake_env):
    eng = make_engine(fake_env)
    eng.apply(Settings())
    assert eng.is_applied()
    eng.revert()
    assert not eng.is_applied()
    assert not (fake_env.config / "liquid-glass/tokens.json").exists()


def test_write_never_follows_planted_temp_links(fake_env):
    victim = fake_env.home / "victim"
    victim.write_text("safe")
    css = fake_env.config / "gtk-4.0/gtk.css"
    css.parent.mkdir(parents=True)
    (css.parent / ".gtk.css.lg-tmp").symlink_to(victim)     # the old fixed temp name
    make_engine(fake_env).apply(Settings())
    assert victim.read_text() == "safe"
