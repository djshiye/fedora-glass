"""The mouse pointer: one of the cursor styles that come with Fedora Glass."""

from __future__ import annotations

from .. import cursors
from ..cursors import IFACE, KEEP
from ..env import Env
from .base import Action, Context, Detection, GReset, GSet, Target


class Cursor(Target):
    def __init__(self) -> None:
        super().__init__(
            id="cursor", name="Mouse pointer", group="Desktop",
            summary="The pointer style and size picked on the Look page. "
                    "Restore original brings your own pointer back.",
            scheme_dependent=False,
        )

    def detect(self, env: Env) -> Detection:
        missing = [s.name for s in cursors.STYLES if cursors.theme_dir(env, s.id) is None]
        if len(missing) == len(cursors.STYLES):
            return Detection(True, "The pointer styles are not installed with this copy")
        return Detection(True)

    def plan(self, ctx: Context) -> list[Action]:
        s = ctx.settings
        out: list[Action] = []
        # The user's own choice in GNOME Tweaks or Settings after ours stays on Restore.
        if s.cursor_theme == KEEP or cursors.theme_dir(ctx.env, s.cursor_theme) is None:
            out.append(GReset(IFACE, "cursor-theme"))
        else:
            out.append(GSet(IFACE, "cursor-theme", f"'{s.cursor_theme}'", keep_user_change=True))
        if s.cursor_size:
            out.append(GSet(IFACE, "cursor-size", str(s.cursor_size), keep_user_change=True))
        else:
            out.append(GReset(IFACE, "cursor-size"))
        return out

    def live_notes(self, ctx: Context) -> list[str]:
        th = ctx.settings.cursor_theme
        if th != KEEP and cursors.theme_dir(ctx.env, th) is None:
            return ["The pointer style you picked is not installed, so your own pointer stays. "
                    "Reinstall Fedora Glass to get it back."]
        return []


TARGETS: list[Target] = [Cursor()]
