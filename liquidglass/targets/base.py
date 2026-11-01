"""What a theming target is, and the actions it can ask for.

A target never touches the system itself. Its plan() returns a list of
actions; the engine backs up whatever an action will change (the first time
Liquid Glass ever changes it), then performs it. That keeps every change
reversible and lets the app show exactly what Apply will do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..env import Env
    from ..palette import Tokens
    from ..settings import Settings


# ---- actions ---------------------------------------------------------------
@dataclass(frozen=True)
class WriteFile:
    path: Path
    content: str | bytes
    mode: int = 0o644

    def describe(self) -> str:
        return f"write {self.path}"


@dataclass(frozen=True)
class GSet:
    schema: str
    key: str
    value: str                 # GVariant text, e.g. "true", "'name'", "0.5"
    path: str | None = None    # for relocatable schemas
    optional: bool = True      # skip silently if the key doesn't exist on this version
    # Another app's own setting: if the user changes it after us, undoing leaves their choice.
    keep_user_change: bool = False

    def describe(self) -> str:
        where = f"{self.schema}:{self.path}" if self.path else self.schema
        return f"set {where} {self.key} = {self.value}"


@dataclass(frozen=True)
class GReset:
    """Put a gsettings key back the way it was before this target changed it, if it did.
    For options the user has since turned off; a key we never touched is left alone."""
    schema: str
    key: str
    path: str | None = None

    def describe(self) -> str:
        return f"restore {self.schema} {self.key} if Liquid Glass changed it"


@dataclass(frozen=True)
class Command:
    """An unprivileged helper command. `touches` lists files it changes, so
    they're backed up first and restored on revert."""
    argv: tuple[str, ...]
    why: str
    touches: tuple[Path, ...] = ()
    undo: tuple[str, ...] | None = None  # command that reverses it, run on revert

    def describe(self) -> str:
        return f"run {' '.join(self.argv)}  ({self.why})"


@dataclass(frozen=True)
class ListEdit:
    """Add or remove items in a gsettings string list (e.g. enabled-extensions).
    Revert undoes only these items, so changes the user made since are kept."""
    schema: str
    key: str
    add: tuple[str, ...] = ()
    remove: tuple[str, ...] = ()
    path: str | None = None

    def describe(self) -> str:
        parts = [f"add {', '.join(self.add)}" if self.add else "", f"remove {', '.join(self.remove)}" if self.remove else ""]
        return f"{self.schema} {self.key}: {' and '.join(p for p in parts if p)}"


@dataclass(frozen=True)
class FlatpakOverride:
    """Extra permissions/environment for every Flatpak app (the user's global override).
    Revert removes exactly what was added."""
    filesystems: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()

    def describe(self) -> str:
        bits = [f"filesystem {f}" for f in self.filesystems] + [f"env {k}={v}" for k, v in self.env]
        return f"flatpak override for all apps: {', '.join(bits)}"


Action = WriteFile | GSet | GReset | Command | ListEdit | FlatpakOverride


# ---- context and target -------------------------------------------------------
@dataclass
class Context:
    settings: "Settings"
    tokens: "Tokens"          # the scheme in use right now
    dark: "Tokens"            # both schemes, for CSS that switches by itself
    light: "Tokens"
    env: "Env"
    # Whether GNOME Shell is running our glass extension right now. The Shell only
    # loads a new extension at login, so right after the first Apply it is False.
    glass_running: bool = True


@dataclass
class Detection:
    available: bool
    detail: str = ""


@dataclass
class Target:
    id: str = ""
    name: str = ""
    group: str = "Apps"       # "Desktop", "Panel", "Terminal", "Apps", "My apps"
    summary: str = ""
    # Manual follow-up the user has to do once (shown in the app), if any.
    notes: list[str] = field(default_factory=list)
    # False when the output already covers dark and light by itself, so the
    # dark/light watcher can skip it.
    scheme_dependent: bool = True
    # True for Shell parts (Shell theme, Dash to Panel, ArcMenu) whose look only works
    # with the glass behind it. They wait until the glass extension runs.
    waits_for_glass: bool = False

    def detect(self, env: "Env") -> Detection:
        return Detection(True)

    def plan(self, ctx: Context) -> list[Action]:
        raise NotImplementedError

    def live_notes(self, ctx: Context) -> list[str]:
        """Notes for the current system (a target may add some at runtime)."""
        return list(self.notes)
