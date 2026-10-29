"""Renderers for third-party apps that are neither GTK nor Qt-themed by us.

Every function takes Tokens (and returns text or bytes) so the apps follow the
glass settings. Apps that cannot be translucent (VS Code, Obsidian, Qt apps
with QSS) get opaque colours composed from the same surfaces.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

from ..color import BLACK, WHITE, Color
from ..palette import Tokens
from .terminal import derive

# ---- small text editors that keep the user's own lines ----------------------


def merge_json_text(existing: str | None, updates: dict) -> str | None:
    """Merge top-level keys into a JSON object. None if `existing` is not plain JSON
    (VS Code settings may contain comments), so callers can skip instead of clobbering."""
    if existing is None or not existing.strip():
        data: dict = {}
    else:
        try:
            data = json.loads(existing)
        except ValueError:
            return None
        if not isinstance(data, dict):
            return None
    data.update(updates)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def read_text(path: Path) -> str | None:
    try:
        if path.is_symlink():
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def ini_set(text: str, section: str, values: dict[str, str]) -> str:
    """Set keys inside [section] of an INI/QSettings file; every other byte is untouched."""
    lines = text.splitlines(keepends=True)
    nl = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
    start = end = None
    for i, ln in enumerate(lines):
        m = re.match(r"\s*\[(.*)\]\s*$", ln)
        if m:
            if start is not None:
                end = i
                break
            if m.group(1) == section:
                start = i
    if start is None:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += nl
        lines.append(f"{'' if not lines else nl}[{section}]{nl}")
        start, end = len(lines) - 1, len(lines)
    elif end is None:
        end = len(lines)
        if not lines[-1].endswith(("\n", "\r")):
            lines[-1] += nl
    pending = dict(values)
    for i in range(start + 1, end):
        key = lines[i].split("=", 1)[0].strip() if "=" in lines[i] else None
        if key in pending:
            lines[i] = f"{key}={pending.pop(key)}{nl}"
    insert = [f"{k}={v}{nl}" for k, v in pending.items()]
    # keep a blank separator line after the section where there is one
    at = end
    while at - 1 > start and not lines[at - 1].strip():
        at -= 1
    lines[at:at] = insert
    return "".join(lines)


def conf_set(text: str, values: dict[str, str]) -> str:
    """Replace `key = value` lines (btop.conf style); other lines stay byte-identical."""
    lines = text.splitlines(keepends=True)
    nl = "\n"
    pending = dict(values)
    for i, ln in enumerate(lines):
        m = re.match(r"\s*([A-Za-z0-9_]+)\s*=", ln)
        if m and m.group(1) in pending:
            ending = ln[len(ln.rstrip("\r\n")):] or nl
            lines[i] = f"{m.group(1)} = {pending.pop(m.group(1))}{ending}"
    if pending:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += nl
        lines += [f"{k} = {v}{nl}" for k, v in pending.items()]
    return "".join(lines)


def _o(c: Color) -> Color:
    return c.with_alpha(1.0)


# ---- VS Code -------------------------------------------------------------------
VSCODE_PUBLISHER = "djshiye"
VSCODE_NAME = "liquid-glass-theme"
VSCODE_ID = f"{VSCODE_PUBLISHER}.{VSCODE_NAME}"
VSCODE_VERSION = "1.0.0"
VSCODE_LABELS = {True: "Liquid Glass Dark", False: "Liquid Glass Light"}


def vscode_theme(t: Tokens) -> dict:
    p = derive(t)
    n = p.named()
    bg = _o(t.view)
    side = _o(t.window.mix(BLACK if t.dark else WHITE, 0.0))
    chrome = _o(t.chrome)
    ink = p.fg
    dim = p.dim
    edge = t.divider.hex8
    acc = p.accent
    hov = t.hover.hex8
    sel = p.selection_bg
    widget = _o(t.popover)

    colors = {
        "foreground": ink.hex6, "descriptionForeground": dim.hex6, "disabledForeground": dim.hex6,
        "errorForeground": n["bright_red"].hex6, "focusBorder": acc.hex6,
        "widget.shadow": t.shadow.hex8, "selection.background": sel.hex6,
        "icon.foreground": ink.hex6, "sash.hoverBorder": acc.hex6,
        "textLink.foreground": acc.hex6, "textLink.activeForeground": acc.hex6,
        "textCodeBlock.background": chrome.hex6,
        "editor.background": bg.hex6, "editor.foreground": ink.hex6,
        "editorLineNumber.foreground": dim.hex6, "editorLineNumber.activeForeground": ink.hex6,
        "editor.selectionBackground": sel.hex6,
        "editor.inactiveSelectionBackground": sel.with_alpha(0.55).hex8,
        "editor.selectionHighlightBackground": sel.with_alpha(0.45).hex8,
        "editor.wordHighlightBackground": t.hover.hex8,
        "editor.findMatchBackground": acc.with_alpha(0.45).hex8,
        "editor.findMatchHighlightBackground": acc.with_alpha(0.25).hex8,
        "editor.lineHighlightBackground": t.card.hex8 if t.dark else BLACK.with_alpha(0.04).hex8,
        "editor.lineHighlightBorder": "#00000000",
        "editorCursor.foreground": p.cursor.hex6,
        "editorWhitespace.foreground": t.divider.hex8,
        "editorIndentGuide.background1": t.divider.hex8,
        "editorIndentGuide.activeBackground1": dim.with_alpha(0.5).hex8,
        "editorBracketMatch.background": acc.with_alpha(0.25).hex8,
        "editorBracketMatch.border": acc.with_alpha(0.6).hex8,
        "editorGutter.background": bg.hex6,
        "editorGutter.addedBackground": n["green"].hex6,
        "editorGutter.modifiedBackground": n["yellow"].hex6,
        "editorGutter.deletedBackground": n["red"].hex6,
        "editorError.foreground": n["bright_red"].hex6,
        "editorWarning.foreground": n["yellow"].hex6,
        "editorInfo.foreground": n["blue"].hex6,
        "editorWidget.background": widget.hex6, "editorWidget.border": edge,
        "editorSuggestWidget.background": widget.hex6, "editorSuggestWidget.border": edge,
        "editorSuggestWidget.selectedBackground": sel.hex6,
        "editorHoverWidget.background": widget.hex6, "editorHoverWidget.border": edge,
        "editorGroup.border": edge, "editorGroupHeader.tabsBackground": chrome.hex6,
        "tab.activeBackground": bg.hex6, "tab.inactiveBackground": chrome.hex6,
        "tab.activeForeground": ink.hex6, "tab.inactiveForeground": dim.hex6,
        "tab.border": "#00000000", "tab.activeBorderTop": acc.hex6,
        "tab.hoverBackground": _o(t.chrome.mix(ink, 0.06)).hex6,
        "activityBar.background": chrome.hex6, "activityBar.foreground": ink.hex6,
        "activityBar.inactiveForeground": dim.hex6, "activityBar.border": edge,
        "activityBarBadge.background": acc.hex6, "activityBarBadge.foreground": t.accent_fg.hex6,
        "sideBar.background": side.hex6, "sideBar.foreground": ink.hex6, "sideBar.border": edge,
        "sideBarTitle.foreground": ink.hex6, "sideBarSectionHeader.background": "#00000000",
        "sideBarSectionHeader.border": edge,
        "list.activeSelectionBackground": sel.hex6, "list.activeSelectionForeground": ink.hex6,
        "list.inactiveSelectionBackground": t.hover.hex8, "list.hoverBackground": hov,
        "list.highlightForeground": acc.hex6, "list.focusBackground": sel.hex6,
        "tree.indentGuidesStroke": t.divider.hex8,
        "titleBar.activeBackground": chrome.hex6, "titleBar.activeForeground": ink.hex6,
        "titleBar.inactiveBackground": chrome.hex6, "titleBar.inactiveForeground": dim.hex6,
        "titleBar.border": edge,
        "menu.background": widget.hex6, "menu.foreground": ink.hex6,
        "menu.selectionBackground": sel.hex6, "menu.selectionForeground": ink.hex6,
        "menu.separatorBackground": edge,
        "menubar.selectionBackground": hov,
        "statusBar.background": chrome.hex6, "statusBar.foreground": ink.hex6,
        "statusBar.border": edge, "statusBar.noFolderBackground": chrome.hex6,
        "statusBar.debuggingBackground": n["yellow"].mix(bg, 0.5).hex6,
        "statusBarItem.hoverBackground": hov, "statusBarItem.remoteBackground": acc.hex6,
        "statusBarItem.remoteForeground": t.accent_fg.hex6,
        "panel.background": bg.hex6, "panel.border": edge,
        "panelTitle.activeForeground": ink.hex6, "panelTitle.inactiveForeground": dim.hex6,
        "panelTitle.activeBorder": acc.hex6,
        "button.background": t.accent.with_alpha(1).hex6, "button.foreground": t.accent_fg.hex6,
        "button.hoverBackground": _o(t.accent.mix(WHITE, 0.12)).hex6,
        "button.secondaryBackground": _o(t.chrome.mix(ink, 0.10)).hex6,
        "button.secondaryForeground": ink.hex6,
        "input.background": chrome.hex6, "input.foreground": ink.hex6, "input.border": edge,
        "input.placeholderForeground": dim.hex6, "inputOption.activeBorder": acc.hex6,
        "inputOption.activeBackground": acc.with_alpha(0.25).hex8,
        "dropdown.background": widget.hex6, "dropdown.foreground": ink.hex6, "dropdown.border": edge,
        "badge.background": acc.hex6, "badge.foreground": t.accent_fg.hex6,
        "progressBar.background": acc.hex6,
        "scrollbar.shadow": "#00000000",
        "scrollbarSlider.background": ink.with_alpha(0.14).hex8,
        "scrollbarSlider.hoverBackground": ink.with_alpha(0.24).hex8,
        "scrollbarSlider.activeBackground": ink.with_alpha(0.34).hex8,
        "breadcrumb.foreground": dim.hex6, "breadcrumb.focusForeground": ink.hex6,
        "breadcrumb.activeSelectionForeground": ink.hex6, "breadcrumbPicker.background": widget.hex6,
        "notifications.background": widget.hex6, "notifications.foreground": ink.hex6,
        "notifications.border": edge, "notificationCenterHeader.background": chrome.hex6,
        "quickInput.background": widget.hex6, "quickInput.foreground": ink.hex6,
        "quickInputList.focusBackground": sel.hex6,
        "pickerGroup.foreground": acc.hex6, "pickerGroup.border": edge,
        "peekView.border": acc.hex6, "peekViewEditor.background": chrome.hex6,
        "peekViewResult.background": widget.hex6, "peekViewTitle.background": chrome.hex6,
        "gitDecoration.modifiedResourceForeground": n["yellow"].hex6,
        "gitDecoration.addedResourceForeground": n["green"].hex6,
        "gitDecoration.deletedResourceForeground": n["red"].hex6,
        "gitDecoration.untrackedResourceForeground": n["bright_green"].hex6,
        "gitDecoration.ignoredResourceForeground": dim.hex6,
        "gitDecoration.conflictingResourceForeground": n["magenta"].hex6,
        "diffEditor.insertedTextBackground": n["green"].with_alpha(0.16).hex8,
        "diffEditor.removedTextBackground": n["red"].with_alpha(0.16).hex8,
        "terminal.background": bg.hex6, "terminal.foreground": ink.hex6,
        "terminal.selectionBackground": sel.hex6, "terminalCursor.foreground": p.cursor.hex6,
        "terminal.border": edge,
        "terminal.ansiBlack": p.ansi[0].hex6, "terminal.ansiBrightBlack": p.ansi[8].hex6,
        "terminal.ansiWhite": p.ansi[7].hex6, "terminal.ansiBrightWhite": p.ansi[15].hex6,
    }
    for i, name in enumerate(("Red", "Green", "Yellow", "Blue", "Magenta", "Cyan"), start=1):
        colors[f"terminal.ansi{name}"] = p.ansi[i].hex6
        colors[f"terminal.ansiBright{name}"] = p.ansi[i + 8].hex6

    def tok(scope: str | list[str], fg: Color, style: str = "") -> dict:
        s: dict = {"foreground": fg.hex6}
        if style:
            s["fontStyle"] = style
        return {"scope": scope, "settings": s}

    tokens = [
        tok(["comment", "punctuation.definition.comment"], dim, "italic"),
        tok(["string", "string.quoted"], n["green"]),
        tok(["constant.numeric", "constant.language", "constant.character"], n["yellow"]),
        tok(["constant.character.escape", "string.regexp"], n["bright_cyan"]),
        tok(["keyword", "storage", "storage.type", "keyword.control"], n["magenta"]),
        tok("keyword.operator", n["cyan"]),
        tok(["entity.name.function", "support.function", "meta.function-call"], n["blue"]),
        tok(["entity.name.type", "entity.name.class", "support.class", "support.type"], n["bright_cyan"]),
        tok(["variable", "variable.other"], ink),
        tok(["variable.parameter", "variable.language"], n["bright_red"], "italic"),
        tok(["entity.name.tag", "markup.deleted"], n["red"]),
        tok(["entity.other.attribute-name", "support.type.property-name"], n["yellow"]),
        tok(["punctuation", "meta.brace"], _o(ink.mix(bg, 0.25))),
        tok(["markup.heading", "entity.name.section"], acc, "bold"),
        tok("markup.bold", ink, "bold"),
        tok("markup.italic", ink, "italic"),
        tok(["markup.inserted"], n["green"]),
        tok(["markup.underline.link", "string.other.link"], acc, "underline"),
        tok("invalid", n["bright_red"], "underline"),
    ]
    return {
        "$schema": "vscode://schemas/color-theme",
        "name": VSCODE_LABELS[t.dark],
        "type": "dark" if t.dark else "light",
        "semanticHighlighting": True,
        "colors": colors,
        "tokenColors": tokens,
    }


def vscode_theme_file(dark: bool) -> str:
    return f"themes/liquid-glass-{'dark' if dark else 'light'}-color-theme.json"


def vsix_bytes(dark: Tokens, light: Tokens) -> bytes:
    """A VSIX is a zip with a manifest, content types and the extension folder.
    Timestamps are fixed so identical tokens give identical bytes."""
    pkg = {
        "name": VSCODE_NAME, "displayName": "Liquid Glass", "publisher": VSCODE_PUBLISHER,
        "version": VSCODE_VERSION, "description": "Glass-matched colour themes.",
        "engines": {"vscode": "^1.60.0"}, "categories": ["Themes"], "license": "MIT",
        "contributes": {"themes": [
            {"label": VSCODE_LABELS[True], "uiTheme": "vs-dark", "path": "./" + vscode_theme_file(True)},
            {"label": VSCODE_LABELS[False], "uiTheme": "vs", "path": "./" + vscode_theme_file(False)},
        ]},
    }
    content_types = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension=".json" ContentType="application/json"/>'
        '<Default Extension=".vsixmanifest" ContentType="text/xml"/>'
        '</Types>\n')
    manifest = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">'
        f'<Metadata><Identity Language="en-US" Id="{VSCODE_NAME}" Version="{VSCODE_VERSION}" '
        f'Publisher="{VSCODE_PUBLISHER}"/>'
        '<DisplayName>Liquid Glass</DisplayName><Description xml:space="preserve">'
        'Glass-matched colour themes.</Description><Tags>theme</Tags>'
        '<Categories>Themes</Categories><GalleryFlags>Public</GalleryFlags>'
        '<Properties><Property Id="Microsoft.VisualStudio.Code.Engine" Value="^1.60.0"/></Properties>'
        '</Metadata><Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation>'
        '<Dependencies/><Assets>'
        '<Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/>'
        '</Assets></PackageManifest>\n')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        def add(name: str, text: str) -> None:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, text)
        add("[Content_Types].xml", content_types)
        add("extension.vsixmanifest", manifest)
        add("extension/package.json", json.dumps(pkg, indent=2) + "\n")
        add("extension/" + vscode_theme_file(True), json.dumps(vscode_theme(dark), indent=2) + "\n")
        add("extension/" + vscode_theme_file(False), json.dumps(vscode_theme(light), indent=2) + "\n")
    return buf.getvalue()


# ---- Discord (Vencord theme) ----------------------------------------------------
DISCORD_THEME_FILE = "liquid-glass.theme.css"


def _discord_vars(t: Tokens) -> str:
    base = t.window
    chrome = t.chrome
    view = t.view
    rows = {
        "--lg-window": base.css, "--lg-chrome": chrome.css, "--lg-view": view.css,
        "--lg-popover": _o(t.popover).css, "--lg-card": t.card.css, "--lg-hover": t.hover.css,
        "--lg-active": t.active.css, "--lg-edge": t.edge.css, "--lg-rim": t.highlight.css,
        "--lg-fg": t.fg.css, "--lg-dim": t.fg_dim.css, "--lg-faint": t.fg_faint.css,
        "--lg-accent": t.accent.css, "--lg-accent-fg": t.accent_fg.css,
        "--lg-accent-text": t.accent_text.css, "--lg-selection": t.selection.css,
        "--lg-danger": t.destructive.css, "--lg-success": t.success.css, "--lg-warning": t.warning.css,
        "--lg-shadow": t.shadow.css,
    }
    return "\n".join(f"  {k}: {v};" for k, v in rows.items())


def discord_css(dark: Tokens, light: Tokens) -> str:
    r, rs = dark.radius, dark.radius_small
    return f"""/**
 * @name Liquid Glass
 * @description Translucent glass surfaces that follow the Liquid Glass settings.
 * @author Liquid Glass
 * @version 1.0.0
 */

.theme-dark {{
{_discord_vars(dark)}
}}
.theme-light {{
{_discord_vars(light)}
}}

:root {{
  --lg-radius: {r}px;
  --lg-radius-small: {rs}px;
}}

/* Discord's own palette, mapped onto the glass surfaces (old and new variable names). */
.theme-dark, .theme-light {{
  --background-primary: var(--lg-view);
  --background-secondary: var(--lg-chrome);
  --background-secondary-alt: var(--lg-chrome);
  --background-tertiary: var(--lg-window);
  --background-floating: var(--lg-popover);
  --background-accent: var(--lg-card);
  --background-mobile-primary: var(--lg-view);
  --background-mobile-secondary: var(--lg-chrome);
  --background-modifier-hover: var(--lg-hover);
  --background-modifier-active: var(--lg-active);
  --background-modifier-selected: var(--lg-selection);
  --background-modifier-accent: var(--lg-edge);
  --bg-base-primary: var(--lg-view);
  --bg-base-secondary: var(--lg-chrome);
  --bg-base-tertiary: var(--lg-window);
  --bg-surface-overlay: var(--lg-popover);
  --bg-surface-raised: var(--lg-card);
  --bg-overlay-1: var(--lg-chrome);
  --bg-overlay-2: var(--lg-chrome);
  --bg-overlay-3: var(--lg-window);
  --chat-background: transparent;
  --channeltextarea-background: var(--lg-card);
  --header-primary: var(--lg-fg);
  --header-secondary: var(--lg-dim);
  --text-normal: var(--lg-fg);
  --text-default: var(--lg-fg);
  --text-muted: var(--lg-dim);
  --text-secondary: var(--lg-dim);
  --text-link: var(--lg-accent-text);
  --interactive-normal: var(--lg-dim);
  --interactive-hover: var(--lg-fg);
  --interactive-active: var(--lg-fg);
  --interactive-muted: var(--lg-faint);
  --channels-default: var(--lg-dim);
  --brand-experiment: var(--lg-accent);
  --brand-500: var(--lg-accent);
  --brand-560: var(--lg-accent);
  --brand-600: var(--lg-accent);
  --button-filled-brand-background: var(--lg-accent);
  --button-filled-brand-text: var(--lg-accent-fg);
  --status-danger: var(--lg-danger);
  --status-positive: var(--lg-success);
  --status-warning: var(--lg-warning);
  --border-subtle: var(--lg-edge);
  --border-faint: var(--lg-edge);
  --border-normal: var(--lg-edge);
  --scrollbar-thin-thumb: var(--lg-hover);
  --scrollbar-auto-thumb: var(--lg-active);
  --scrollbar-auto-track: transparent;
}}

/* The window itself must be see-through for the surfaces above to show the desktop. */
html, body, #app-mount, .appAsidePanelWrapper_a3002d, .app_a3002d {{
  background: transparent !important;
}}

[class*="sidebar_"], [class*="guilds_"], [class*="panels_"], [class*="privateChannels_"],
[class*="chatContent_"], [class*="membersWrap_"], [class*="sidebarList_"] {{
  box-shadow: inset 0 1px 0 var(--lg-rim), inset 0 0 0 1px var(--lg-edge);
}}
[class*="sidebar_"], [class*="membersWrap_"] {{
  border-radius: var(--lg-radius);
}}
[class*="chat_"] > [class*="content_"] {{
  border-radius: var(--lg-radius) 0 0 0;
}}
[class*="channelTextArea_"], [class*="searchBar_"], [class*="searchBar__"] {{
  border-radius: calc(var(--lg-radius) + 4px);
  box-shadow: inset 0 1px 0 var(--lg-rim);
}}
[class*="button_"][class*="colorBrand"], [class*="lookFilled_"][class*="colorBrand"] {{
  border-radius: 999px;
}}
[class*="layer_"] [class*="menu_"], [class*="popout_"], [class*="modal_"], [class*="tooltip_"] {{
  border-radius: var(--lg-radius-small);
  box-shadow: inset 0 1px 0 var(--lg-rim), 0 12px 32px var(--lg-shadow);
}}
"""


# ---- Obsidian ---------------------------------------------------------------------
def obsidian_manifest() -> str:
    return json.dumps({"name": "Liquid Glass", "version": "1.0.0", "minAppVersion": "1.0.0",
                       "author": "Liquid Glass"}, indent=2) + "\n"


def _obsidian_vars(t: Tokens) -> str:
    rows = {
        "--background-primary": _o(t.view).css, "--background-primary-alt": _o(t.window).css,
        "--background-secondary": _o(t.chrome).css, "--background-secondary-alt": _o(t.window).css,
        "--background-modifier-hover": t.hover.css, "--background-modifier-active-hover": t.active.css,
        "--background-modifier-border": t.edge.css, "--background-modifier-border-hover": t.edge.css,
        "--background-modifier-form-field": t.card.css, "--background-modifier-box-shadow": t.shadow.css,
        "--text-normal": t.fg.css, "--text-muted": t.fg_dim.css, "--text-faint": t.fg_faint.css,
        "--text-accent": t.accent_text.css, "--text-accent-hover": t.accent_text.css,
        "--text-on-accent": t.accent_fg.css, "--text-selection": t.selection.css,
        "--interactive-accent": t.accent.css, "--interactive-accent-hover": t.accent.css,
        "--interactive-normal": _o(t.chrome.mix(t.fg, 0.10)).css,
        "--interactive-hover": _o(t.chrome.mix(t.fg, 0.16)).css,
        "--color-red": t.destructive.css, "--color-green": t.success.css, "--color-yellow": t.warning.css,
        "--titlebar-background": _o(t.chrome).css, "--titlebar-background-focused": _o(t.chrome).css,
        "--tab-background-active": _o(t.view).css,
    }
    return "\n".join(f"  {k}: {v};" for k, v in rows.items())


def obsidian_css(dark: Tokens, light: Tokens) -> str:
    return f"""/* Liquid Glass for Obsidian. Colours come from the Liquid Glass tokens. */
body {{
  --radius-s: {dark.radius_small}px;
  --radius-m: {max(8, dark.radius // 2)}px;
  --radius-l: {dark.radius}px;
  --radius-xl: {dark.radius + 6}px;
  --input-radius: 999px;
  --button-radius: 999px;
  --accent-h: {_hsl_h(dark.accent)};
}}
.theme-dark {{
{_obsidian_vars(dark)}
  --lg-rim: {dark.highlight.css};
}}
.theme-light {{
{_obsidian_vars(light)}
  --lg-rim: {light.highlight.css};
}}
.workspace-tab-header-container, .workspace-ribbon, .nav-header, .mod-left-split .workspace-tabs,
.mod-right-split .workspace-tabs {{
  box-shadow: inset 0 1px 0 var(--lg-rim);
}}
.modal, .menu, .suggestion-container, .prompt, .tooltip, .popover {{
  border-radius: var(--radius-l);
  border: 1px solid var(--background-modifier-border);
  box-shadow: inset 0 1px 0 var(--lg-rim), 0 12px 32px var(--background-modifier-box-shadow);
}}
button, input[type="text"], input[type="search"], .dropdown, select {{
  border-radius: 999px;
}}
.workspace-tab-header.is-active {{
  box-shadow: inset 0 1px 0 var(--lg-rim);
}}
"""


def _hsl_h(c: Color) -> int:
    import colorsys
    return round(colorsys.rgb_to_hls(c.r, c.g, c.b)[0] * 360)


# ---- Qt style sheets (qBittorrent, Prism Launcher) ---------------------------------
def _palette_colors(t: Tokens) -> dict[str, str]:
    win, base = _o(t.window), _o(t.view)
    # Qt stylesheets and palettes cannot do glass; these are the opaque equivalents.
    btn = _o(t.chrome.mix(t.fg, 0.08))
    return {
        "Window": win.hex6, "WindowText": t.fg.hex6, "Base": base.hex6,
        "AlternateBase": _o(base.mix(t.fg, 0.04)).hex6, "Text": t.fg.hex6,
        "ToolTipBase": _o(t.popover).hex6, "ToolTipText": t.fg.hex6, "BrightText": WHITE.hex6,
        "Highlight": t.accent.hex6, "HighlightedText": t.accent_fg.hex6,
        "Button": btn.hex6, "ButtonText": t.fg.hex6, "Link": t.accent_text.hex6,
        "LinkVisited": t.accent_text.mix(t.fg, 0.4).hex6,
    }


def qt_qss(t: Tokens) -> str:
    """Widget style sheet shared by the Qt apps we theme through QSS. Opaque colours only:
    Qt's rgba() takes 0..255 alphas, and these windows cannot be translucent anyway."""
    win, base = _o(t.window), _o(t.view)
    chrome = _o(t.chrome)
    btn = _o(t.chrome.mix(t.fg, 0.08))
    btn_h = _o(t.chrome.mix(t.fg, 0.15))
    edge = _o(win.mix(t.fg, 0.14))
    r, rs = t.radius, t.radius_small
    dim = _o(t.fg.mix(win, 0.35))
    return f"""/* Liquid Glass */
QWidget {{ color: {t.fg.hex6}; }}
QMainWindow, QDialog {{ background: {win.hex6}; }}
QMenuBar {{ background: {chrome.hex6}; }}
QMenuBar::item {{ padding: 4px 10px; border-radius: {rs}px; background: transparent; }}
QMenuBar::item:selected {{ background: {btn_h.hex6}; }}
QMenu {{ background: {_o(t.popover).hex6}; border: 1px solid {edge.hex6}; border-radius: {rs}px; padding: 4px; }}
QMenu::item {{ padding: 5px 20px; border-radius: {max(3, rs - 2)}px; }}
QMenu::item:selected {{ background: {t.accent.hex6}; color: {t.accent_fg.hex6}; }}
QMenu::separator {{ height: 1px; background: {edge.hex6}; margin: 4px 8px; }}
QToolBar, QStatusBar {{ background: {chrome.hex6}; border: none; }}
QPushButton, QToolButton {{ background: {btn.hex6}; border: 1px solid {edge.hex6}; border-radius: {rs + 4}px; padding: 5px 14px; }}
QToolButton {{ padding: 4px 8px; }}
QPushButton:hover, QToolButton:hover {{ background: {btn_h.hex6}; }}
QPushButton:pressed, QToolButton:pressed, QPushButton:default {{ background: {t.accent.hex6}; color: {t.accent_fg.hex6}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {dim.hex6}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
  background: {base.hex6}; border: 1px solid {edge.hex6}; border-radius: {rs + 4}px; padding: 4px 8px;
  selection-background-color: {t.accent.hex6}; selection-color: {t.accent_fg.hex6}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {t.accent.hex6}; }}
QComboBox QAbstractItemView {{ background: {_o(t.popover).hex6}; border: 1px solid {edge.hex6}; selection-background-color: {t.accent.hex6}; selection-color: {t.accent_fg.hex6}; }}
QAbstractItemView {{ background: {base.hex6}; alternate-background-color: {_o(base.mix(t.fg, 0.04)).hex6};
  border: 1px solid {edge.hex6}; border-radius: {rs}px; selection-background-color: {t.accent.hex6}; selection-color: {t.accent_fg.hex6}; }}
QHeaderView::section {{ background: {chrome.hex6}; border: none; border-right: 1px solid {edge.hex6}; padding: 4px 8px; }}
QTabWidget::pane {{ border: 1px solid {edge.hex6}; border-radius: {rs}px; top: -1px; }}
QTabBar::tab {{ background: transparent; padding: 6px 14px; border-radius: {rs}px; margin: 2px; }}
QTabBar::tab:selected {{ background: {t.accent.hex6}; color: {t.accent_fg.hex6}; }}
QTabBar::tab:hover:!selected {{ background: {btn.hex6}; }}
QGroupBox {{ border: 1px solid {edge.hex6}; border-radius: {rs}px; margin-top: 10px; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QProgressBar {{ background: {btn.hex6}; border: none; border-radius: {rs}px; text-align: center; }}
QProgressBar::chunk {{ background: {t.accent.hex6}; border-radius: {rs}px; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle {{ background: {_o(win.mix(t.fg, 0.25)).hex6}; border-radius: 4px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {_o(win.mix(t.fg, 0.4)).hex6}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QSplitter::handle {{ background: {edge.hex6}; }}
QToolTip {{ background: {_o(t.popover).hex6}; color: {t.fg.hex6}; border: 1px solid {edge.hex6}; border-radius: {rs}px; padding: 4px; }}
"""


def qbittorrent_config(dark: Tokens, light: Tokens) -> str:
    """config.json for a qBittorrent folder theme: flat "Palette.*" ids, light in
    "colors", dark overrides in "colors.dark"."""
    def block(t: Tokens) -> dict[str, str]:
        out = {f"Palette.{k}": v for k, v in _palette_colors(t).items()}
        dim = _o(t.fg.mix(_o(t.window), 0.55)).hex6
        for k in ("WindowText", "Text", "ButtonText", "HighlightedText", "ToolTipText", "BrightText"):
            out[f"Palette.{k}Disabled"] = dim
        out.update({
            "TransferList.Downloading": t.success.hex6, "TransferList.ForcedDownloading": t.success.hex6,
            "TransferList.Uploading": t.accent_text.hex6, "TransferList.ForcedUploading": t.accent_text.hex6,
            "TransferList.Error": t.destructive.hex6, "TransferList.MissingFiles": t.destructive.hex6,
            "TransferList.StoppedDownloading": dim, "TransferList.StoppedUploading": dim,
            "ProgressBar": t.accent.hex6,
        })
        return out
    return json.dumps({"colors": block(light), "colors.dark": block(dark)}, indent=2) + "\n"


# ---- Prism Launcher ----------------------------------------------------------------
PRISM_THEME_ID = "liquid-glass"


def prism_theme_json(t: Tokens) -> str:
    c = _palette_colors(t)
    colors = {k: c[k] for k in ("Window", "WindowText", "Base", "AlternateBase", "ToolTipBase",
                                "ToolTipText", "Text", "Button", "ButtonText", "BrightText", "Link",
                                "Highlight", "HighlightedText")}
    colors["fadeColor"] = _o(t.window).hex6
    colors["fadeAmount"] = 0.5
    return json.dumps({"name": "Liquid Glass", "widgets": "Fusion", "qssFilePath": "themeStyle.css",
                       "colors": colors}, indent=2) + "\n"


# ---- Chromium (Brave, Helium) theme extension -----------------------------------------
def _rgb(c: Color) -> list[int]:
    return [round(c.r * 255), round(c.g * 255), round(c.b * 255)]


def chromium_manifest(t: Tokens) -> str:
    frame, tool = _o(t.window), _o(t.view.mix(t.chrome, 0.5))
    colors = {
        "frame": _rgb(frame), "frame_inactive": _rgb(_o(frame.mix(t.fg, 0.04))),
        "frame_incognito": _rgb(_o(frame.mix(BLACK, 0.2))),
        "toolbar": _rgb(tool), "toolbar_button_icon": _rgb(t.fg),
        "tab_text": _rgb(t.fg), "tab_background_text": _rgb(_o(t.fg.mix(frame, 0.3))),
        "bookmark_text": _rgb(t.fg), "ntp_background": _rgb(_o(t.view)), "ntp_text": _rgb(t.fg),
        "ntp_link": _rgb(t.accent_text), "button_background": [0, 0, 0, 0],
        "omnibox_background": _rgb(_o(frame.mix(t.fg, 0.08))), "omnibox_text": _rgb(t.fg),
    }
    return json.dumps({
        "manifest_version": 3, "name": "Liquid Glass", "version": "1.0",
        "description": "Browser colours that follow the Liquid Glass settings.",
        "theme": {"colors": colors, "properties": {"ntp_background_alignment": "center"}},
    }, indent=2) + "\n"


# ---- Slack ------------------------------------------------------------------------------
def slack_theme(t: Tokens) -> str:
    """Slack's custom sidebar theme: 8 comma-separated hex colours, in Slack's order."""
    col = _o(t.window)
    hover = _o(col.mix(t.fg, 0.10))
    parts = [col, hover, t.accent, t.accent_fg, hover, t.fg, t.success, t.destructive]
    return ",".join(c.hex6.upper() if i else c.hex6.upper() for i, c in enumerate(parts))
