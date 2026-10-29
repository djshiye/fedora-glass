"""User settings: what the customizer edits and every renderer reads.

Stored as JSON in ~/.config/liquid-glass/settings.json. Unknown keys are
ignored and missing keys fall back to defaults, so old files keep working.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

# GNOME's own accent colours (Settings > Appearance), so "system" matches the desktop.
GNOME_ACCENTS = {
    "blue": "#3584e4", "teal": "#2190a4", "green": "#3a944a", "yellow": "#c88800",
    "orange": "#ed5b00", "red": "#e62d42", "pink": "#d56199", "purple": "#9141ac",
    "slate": "#6f8396",
}

SCHEMES = ("auto", "dark", "light")
PANEL_STYLES = ("floating", "docked")


@dataclass
class Settings:
    # The headline control: 0 = liquid (clear, sharp, bright rim light),
    # 1 = frosted (milky, heavily blurred, quiet edges).
    frost: float = 0.45
    scheme: str = "auto"            # auto follows GNOME's dark/light style
    accent: str = "system"          # "system", a GNOME accent name, or "#rrggbb"
    tint: str = "#8fa8c8"           # colour the glass leans towards
    tint_strength: float = 0.15     # 0..1
    radius: int = 18                # base corner radius in px
    highlight: float = 0.7          # specular rim light strength, 0..1
    # Fine-tune overrides; None means "follow the frost slider".
    opacity: float | None = None    # 0..1, how solid chrome surfaces are
    blur: int | None = None         # blur radius in px
    reduce_transparency: bool = False  # accessibility: near-opaque everything

    panel_style: str = "floating"   # Dash to Panel: floating pill or edge-docked
    panel_margin: int = 8
    blur_app_windows: bool = True   # Blur my Shell blur behind app windows
    terminal_opacity: float | None = None

    # Target id -> enabled. Missing ids default to enabled.
    targets: dict[str, bool] = field(default_factory=dict)

    def target_enabled(self, target_id: str) -> bool:
        return self.targets.get(target_id, True)

    # ---- validation ---------------------------------------------------
    def normalized(self) -> "Settings":
        s = Settings(**asdict(self))
        s.frost = _clamp(float(s.frost))
        s.tint_strength = _clamp(float(s.tint_strength))
        s.highlight = _clamp(float(s.highlight))
        s.radius = int(min(32, max(0, int(s.radius))))
        s.panel_margin = int(min(32, max(0, int(s.panel_margin))))
        if s.opacity is not None:
            s.opacity = _clamp(float(s.opacity))
        if s.blur is not None:
            s.blur = int(min(100, max(0, int(s.blur))))
        if s.terminal_opacity is not None:
            s.terminal_opacity = min(1.0, max(0.3, float(s.terminal_opacity)))
        if s.scheme not in SCHEMES:
            s.scheme = "auto"
        if s.panel_style not in PANEL_STYLES:
            s.panel_style = "floating"
        if not (s.accent == "system" or s.accent in GNOME_ACCENTS or _is_hex(s.accent)):
            s.accent = "system"
        if not _is_hex(s.tint):
            s.tint = Settings.tint
        s.targets = {str(k): bool(v) for k, v in dict(s.targets).items()}
        return s


def _clamp(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def _is_hex(v: object) -> bool:
    if not isinstance(v, str) or not v.startswith("#") or len(v) not in (4, 7):
        return False
    return all(c in "0123456789abcdefABCDEF" for c in v[1:])


# ---- presets ----------------------------------------------------------
PRESETS: dict[str, dict] = {
    "Liquid": {"frost": 0.0, "highlight": 0.9, "tint_strength": 0.08},
    "Clear": {"frost": 0.25, "highlight": 0.8, "tint_strength": 0.12},
    "Balanced": {"frost": 0.45, "highlight": 0.7, "tint_strength": 0.15},
    "Frosted": {"frost": 0.8, "highlight": 0.45, "tint_strength": 0.18},
    "Solid": {"frost": 1.0, "highlight": 0.3, "tint_strength": 0.2, "opacity": 0.92},
}


def apply_preset(s: Settings, name: str) -> Settings:
    data = asdict(s)
    data.update({"opacity": None, "blur": None})
    data.update(PRESETS[name])
    return Settings(**data).normalized()


# ---- storage ------------------------------------------------------------
def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "liquid-glass"


def settings_path() -> Path:
    return config_dir() / "settings.json"


def load(path: Path | None = None) -> Settings:
    path = path or settings_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(raw, dict):
        return Settings()
    known = {f.name for f in fields(Settings)}
    try:
        return Settings(**{k: v for k, v in raw.items() if k in known}).normalized()
    except (TypeError, ValueError):
        return Settings()


def save(s: Settings, path: Path | None = None) -> Path:
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(s.normalized()), indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path
