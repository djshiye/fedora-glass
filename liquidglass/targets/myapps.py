"""Apps from the same author (Clipperino, RGBeast, Wheelguard). They need no files of their own: they follow the tokens."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..env import Env
from .apps import AppTarget, installed
from .base import Action, Context, Detection, Target


@dataclass
class MyApp(AppTarget):
    group: str = "My apps"
    scheme_dependent: bool = False
    cmd: str = ""
    desktop_id: str = ""
    flatpak: str | None = None

    def detect(self, env: Env) -> Detection:
        if installed(env, cmds=(self.cmd,), flatpak=self.flatpak or self.desktop_id or None,
                     desktop=(self.desktop_id,) if self.desktop_id else ()):
            return Detection(True)
        return Detection(False, f"{self.name} is not installed")

    def plan(self, ctx: Context) -> list[Action]:
        return []


@dataclass
class Wheelguard(MyApp):
    def live_notes(self, ctx: Context) -> list[str]:
        return list(self.notes) + [f"Token file: {ctx.env.config / 'liquid-glass/tokens.json'}"]


TARGETS: list[Target] = [
    MyApp(id="clipperino", name="Clipperino", cmd="clipperino", desktop_id="io.github.djshiye.Clipperino",
          summary="Themed through GTK 4.",
          notes=["Clipperino uses libadwaita, so the GTK 4 target already themes it."]),
    MyApp(id="rgbeast", name="RGBeast", cmd="rgbeast", desktop_id="io.github.djshiye.RGBeast",
          summary="Themed through GTK 4.",
          notes=["RGBeast uses libadwaita, so the GTK 4 target already themes it."]),
    Wheelguard(id="wheelguard", name="Wheelguard", cmd="wheelguard-settings",
               desktop_id="io.github.djshiye.Wheelguard",
               summary="Follows Liquid Glass by itself: it reads the Liquid Glass colours and watches them for changes.",
               notes=["Wheelguard's Qt Quick UI takes its colours from the token file Liquid Glass writes "
                      "on every Apply. Its shell-extension popup is themed by the Shell target."]),
]
