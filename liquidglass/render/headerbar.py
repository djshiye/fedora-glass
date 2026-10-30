"""Window header bars: height and how see-through they are.

Appended to the GTK 4 and GTK 3 stylesheets. Both controls default to
"leave GNOME's look alone", so nothing is written until the user moves them.

Height. libadwaita 1.9 builds a 47 px bar from 6 + 34 + 7: box padding around
34 px tall buttons (24 px min-height + 5 px padding). Taller bars only grow the
padding; bars under 40 px also slim the buttons to 30 px so they still fit.
Apps that stack bars in a toolbar view (Files, Text Editor) get 3 px of extra
padding around the stack, which the rules take back off the bar itself.
Dialogs with nothing but a close button (.default-decoration) keep their own
small bar.

See-through. GTK 4 paints the window background under the header bar, so a
bar can never be clearer than the window by painting the bar. Instead the
window background itself becomes two bands: the header colour for the top
`height` px and the normal window colour below. That only lines up because
the height control fixes every header bar to the same height, which is why
the see-through control turns the height rules on too. GTK 3 header bars
paint their own background, so there the bar simply takes the colour.
Ptyxis paints its window and top bar from its own style sheet, which outranks
ours, so its bar gets the same glass through the palette's TitlebarBackground
(see ptyxis_titlebar). Its height follows the header bar rules like any app.

Running apps keep the style sheet they started with. Terminal quits a few
seconds after its last window closes; Files stays running in the background,
so it shows changes only once it is quit (`nautilus -q`) and reopened.
"""

from __future__ import annotations

from ..palette import Tokens
from ..settings import Settings

GNOME_HEIGHT = 47       # libadwaita's own header bar height
_BUTTON = 34            # libadwaita header bar button height
_SLIM_BUTTON = 30       # button height used for bars under 40 px
_COLLAPSE = 3           # padding libadwaita puts above and below bars in a .collapse-spacing box

COMMENT = "/* ---- header bars: height and glass (Liquid Glass settings) ---- */\n"


def header_color(s: Settings, t: Tokens):
    """The header bar colour for one scheme, or None to keep the window glass."""
    if s.header_opacity is None or s.reduce_transparency:
        return None
    return t.window.with_alpha(s.header_opacity)


def active(s: Settings) -> bool:
    return s.header_height != GNOME_HEIGHT or (s.header_opacity is not None and not s.reduce_transparency)


def _padding(height: int, border: int = 0) -> tuple[int, int, int]:
    """(top, bottom, button padding) for a bar of `height` px. GTK 3 buttons add a
    1 px border top and bottom (`border=2`)."""
    button, button_pad = (_SLIM_BUTTON, 3) if height < 40 else (_BUTTON, 5)
    room = max(0, height - button - border)
    top = room // 2
    return top, room - top, button_pad


def _height_rules(height: int, gtk3: bool) -> str:
    top, bottom, bpad = _padding(height, border=2 if gtk3 else 0)
    bar = "headerbar:not(.default-decoration)"
    if gtk3:
        # GTK 3 centres header bar contents with margins on each child (8 px in Adwaita),
        # not padding, so those margins are what sets the height.
        rows = [f"{bar} {{ min-height: {height}px; padding-top: 0; padding-bottom: 0; }}",
                f"{bar} button, {bar} entry, {bar} spinbutton, {bar} separator, {bar} switch, "
                f"{bar} combobox, {bar} stackswitcher {{ margin-top: {top}px; margin-bottom: {bottom}px; }}",
                f"{bar} stackswitcher button, {bar} combobox button {{ margin-top: 0; margin-bottom: 0; }}"]
    else:
        # Bars stacked in a toolbar view sit in a .collapse-spacing box that adds 3 px above
        # and below (libadwaita 1.9), so those bars give the 6 px back to keep the total.
        rows = [f"{bar} {{ min-height: {height}px; }}",
                f"{bar} > windowhandle > box {{ padding-top: {top}px; padding-bottom: {bottom}px; }}",
                f".collapse-spacing {bar} {{ min-height: {height - 2 * _COLLAPSE}px; }}",
                f".collapse-spacing {bar} > windowhandle > box {{ padding-top: {top - _COLLAPSE}px; "
                f"padding-bottom: {bottom - _COLLAPSE}px; }}"]
    if bpad != 5:
        rows.append(f"{bar} button, {bar} menubutton > button, {bar} splitbutton > button, "
                    f"{bar} splitbutton > menubutton > button {{ min-height: 24px; padding-top: {bpad}px; padding-bottom: {bpad}px; }}")
        rows.append(f"{bar} entry, {bar} spinbutton, {bar} dropdown > button {{ min-height: {_SLIM_BUTTON}px; }}")
        # Files: path buttons keep their own flat 24 px and sit closer to the path bar's edge.
        rows.append(f"{bar} .nautilus-path-button {{ padding-top: 0; padding-bottom: 0; margin-top: 1px; margin-bottom: 1px; }}")
    if height < GNOME_HEIGHT:
        # Files: the hidden search field's filter button adds 5 px above and below.
        rows.append(f"{bar} .nautilus-query-editor > menubutton > button {{ margin-top: 0; margin-bottom: 0; }}")
    return "\n".join(rows) + "\n"


def gtk4_css(s: Settings, dark: Tokens, light: Tokens | None = None) -> str:
    if not active(s):
        return ""
    s = s.normalized()
    out = [COMMENT, _height_rules(s.header_height, gtk3=False)]
    if header_color(s, dark) is not None:
        h = s.header_height
        if light is not None:
            for name, t in (("light", light), ("dark", dark)):
                out.append(f"@media (prefers-color-scheme: {name}) {{\n:root {{ --lg-header-bg: {header_color(s, t).css}; }}\n}}\n")
        else:
            out.append(f":root {{ --lg-header-bg: {header_color(s, dark).css}; }}\n")
        # Two bands: header glass on top, the usual window glass below.
        band = (f"linear-gradient(to bottom, var(--lg-header-bg) {h}px, "
                f"var(--window-bg-color) {h}px)")
        out.append(f"window.background:not(.popup):not(.tooltip) {{ background-color: transparent; background-image: {band}; }}\n")
        # Windows that have no header bar at the top would show the band, so they keep one colour.
        out.append("window.background.dialog.message, window.background.solid-csd { "
                   "background-image: none; background-color: var(--window-bg-color); }\n")
    return "".join(out)


def gtk3_css(s: Settings, t: Tokens) -> str:
    if not active(s):
        return ""
    s = s.normalized()
    out = [COMMENT, _height_rules(s.header_height, gtk3=True)]
    c = header_color(s, t)
    if c is not None:
        out.append(f"headerbar, .titlebar, headerbar:backdrop, .titlebar:backdrop {{ background-color: {c.css}; }}\n")
    return "".join(out)


def ptyxis_titlebar(s: Settings, t: Tokens, window_opacity: float):
    """Colour for Ptyxis's top bar, so it reads as the same glass as other header bars.

    Ptyxis draws the bar over its window background, which already has the terminal's
    opacity, so the bar adds just enough to land on the header's alpha (or the
    window glass alpha when the user hasn't set one)."""
    s = s.normalized()
    target = t.window.a if s.header_opacity is None or s.reduce_transparency else s.header_opacity
    if window_opacity >= 1.0:
        alpha = 0.0
    else:
        alpha = max(0.0, 1.0 - (1.0 - target) / (1.0 - window_opacity))
    return t.window.with_alpha(round(alpha, 3))

