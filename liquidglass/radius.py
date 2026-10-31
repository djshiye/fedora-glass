"""One corner-radius scale for the whole theme: the Shell, GTK 3/4, Kvantum and Qt.

The ladder at the default base radius (Settings.radius = 18) is 8 / 12 / 16 / 24 px.
For another base radius every step is scaled by base / 18 and rounded to whole px, so
the slider moves all corners together and a base of 0 gives square corners everywhere.
A part with its own radius override (Settings.parts[part]["radius"]) gets its own ladder.

Roles, and the only places each step may be used:

  xs  8   small things inside a surface: header bar hover tiles, menu items and list rows
          inside menus and popovers, tooltips, check boxes, calendar day cells, small
          badges, Qt menu items, Qt tab buttons inside a tab bar.
  s   12  buttons (linked and split buttons and menu buttons too: the outer corners of a
          linked group get s, the inner ones 0), text entries, dropdown/combo buttons,
          spin buttons, tabs, Qt QPushButton, QToolButton, QLineEdit and QComboBox.
  m   16  popovers, menus, cards and boxed lists, notification banners, the OSD, the
          Alt+Tab switcher, ArcMenu, the quick settings menu, the calendar menu, Qt QMenu,
          QGroupBox and the QTabWidget pane.
  l   24  app windows, dialogs and sheets, the floating Dash to Panel panel and the big
          Shell surfaces (overview folders and the like). The Calculator keypad also uses
          this one step for every key (see KEYPAD).
  full 999 a capsule. Only for switches, slider troughs and knobs, progress bars,
          scrollbars, search entries, chips/tags/pills that are labels, quick settings
          toggles (GNOME draws those itself) and spinners/dots. Everything else uses a
          step above.

The renderers take their numbers from here and nowhere else.
"""

from __future__ import annotations

DEFAULT_BASE = 18          # Settings.radius default: the ladder below is exact at this base
FULL = 999                 # capsule: clamps to half the height of whatever it is on

# Step sizes in px at DEFAULT_BASE.
_STEPS = {"xs": 8, "s": 12, "m": 16, "l": 24}

# The Calculator keypad uses one fixed step for every key, so the two-row "=" key
# (taller than the others) still gets the same corners as the single-row keys.
KEYPAD = "l"


def scale(r: int) -> dict[str, int]:
    """The ladder for a base radius `r`: xs, s, m, l in px, plus `full` (999)."""
    r = max(0, int(r))
    out = {k: round(v * r / DEFAULT_BASE) for k, v in _STEPS.items()}
    out["full"] = FULL
    return out
