"""Translations: the app's words in the user's language, English when there is none.

The words live in plain gettext files, fedoraglass/data/po/<language>.po, the format
translators and their tools know. They are read here directly (no compiled .mo or .qm
files, so no build step and nothing binary in the package), once, when first needed.

The language is the session's (LANGUAGE, then LC_ALL, LC_MESSAGES, LANG), the way GNOME
apps pick theirs. FEDORA_GLASS_LANG overrides it, for screenshots and checks.

Code marks its words:
  Python:  _("Apply")  and  _("Saved {name}").format(name=...)   (N_("...") marks a word
           kept in a table and translated where it is shown)
  QML:     qsTr("Apply")  and  qsTr("Saved %1").arg(name)  ;  qsTr("Clear", "preset") gives a
           word that means two things a context of its own (the po file's msgctxt)
  Shell extension:  _('Glass')  from strings.js, made by packaging/translations.py
"""

from __future__ import annotations

import os
import re
from pathlib import Path

PO_DIR = Path(__file__).resolve().parent / "data" / "po"

# The languages the app speaks, by their own names (shown as they are, never translated).
LANGUAGES = {
    "de": "Deutsch",
    "es": "Español",
    "fr": "Français",
    "it": "Italiano",
    "pt_BR": "Português (Brasil)",
}

_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "r": "\r"}
_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _unquote(s: str) -> str:
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(1)), s)


def parse_po(text: str) -> list[dict]:
    """The entries of a po file: {"ctx", "id", "str", "fuzzy", "comments"}. Plurals are not
    used by this app (its code picks between two whole sentences instead)."""
    entries: list[dict] = []
    cur: dict = {}
    field = None

    def flush() -> None:
        nonlocal cur, field
        if "id" in cur:
            cur.setdefault("str", "")
            cur.setdefault("ctx", None)
            entries.append(cur)
        cur, field = {}, None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        if line.startswith("#"):
            if "id" in cur:
                flush()
            if line.startswith("#,") and "fuzzy" in line:
                cur["fuzzy"] = True
            cur.setdefault("comments", []).append(raw)
            continue
        m = re.match(r"(msgctxt|msgid|msgstr)\s+(.*)$", line)
        if m:
            key = {"msgctxt": "ctx", "msgid": "id", "msgstr": "str"}[m.group(1)]
            if key in ("ctx", "id") and "id" in cur and "str" in cur:
                flush()
            field = key
            rest = m.group(2)
        elif line.startswith('"') and field:
            rest = line
        else:
            raise ValueError(f"po line not understood: {raw!r}")
        q = _STRING.fullmatch(rest.strip())
        if not q:
            raise ValueError(f"po line not understood: {raw!r}")
        cur[field] = cur.get(field, "") + _unquote(q.group(1))
    flush()
    return entries


def load_catalog(lang: str) -> dict[tuple[str | None, str], str]:
    """(context, English) -> translation, for one language. Fuzzy and empty entries are left
    out, so those words show in English rather than wrong."""
    path = PO_DIR / f"{lang}.po"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    try:
        entries = parse_po(text)
    except ValueError:
        return {}
    return {(e["ctx"], e["id"]): e["str"] for e in entries
            if e["id"] and e["str"] and not e.get("fuzzy")}


def pick_language(env=None) -> str | None:
    """The supported language the session asks for, or None for English."""
    env = os.environ if env is None else env
    wanted: list[str] = []
    if env.get("FEDORA_GLASS_LANG"):
        wanted.append(env["FEDORA_GLASS_LANG"])
    else:
        # LANGUAGE is a list, and counts only when a real locale is set (as gettext does).
        lc = env.get("LC_ALL") or env.get("LC_MESSAGES") or env.get("LANG") or ""
        if env.get("LANGUAGE") and lc not in ("", "C", "POSIX"):
            wanted.extend(env["LANGUAGE"].split(":"))
        wanted.append(lc)
    for w in wanted:
        code = w.split(".")[0].split("@")[0].replace("-", "_")
        if not code or code in ("C", "POSIX"):
            continue
        if code.split("_")[0] == "en":
            return None
        if code in LANGUAGES:
            return code
        base = code.split("_")[0]
        if base in LANGUAGES:
            return base
        # Portuguese from Portugal (or no country) reads the Brazilian words better than English.
        if base == "pt":
            return "pt_BR"
    return None


_lang: str | None = None
_catalog: dict[tuple[str | None, str], str] | None = None


def language() -> str | None:
    _load()
    return _lang


def _load() -> dict[tuple[str | None, str], str]:
    global _lang, _catalog
    if _catalog is None:
        _lang = pick_language()
        _catalog = load_catalog(_lang) if _lang else {}
    return _catalog


def reset(lang: str | None = None, *, env=None) -> None:
    """Pick the language again (tests, and --lang). lang forces one; None asks env."""
    global _lang, _catalog
    _lang = lang if lang is not None else pick_language(env)
    _catalog = load_catalog(_lang) if _lang else {}


def lookup(text: str, ctx: str | None = None) -> str | None:
    cat = _load()
    if ctx is not None:
        hit = cat.get((ctx, text))
        if hit:
            return hit
    return cat.get((None, text))


def gettext(text: str) -> str:
    return lookup(text) or text


def pgettext(ctx: str, text: str) -> str:
    return lookup(text, ctx) or text


def N_(text: str) -> str:
    """Marks a word for translation without translating it here."""
    return text


_ = gettext


def install_qt(app) -> None:
    """Hands the app's words to Qt, so qsTr() in QML finds them, plus Qt's own (the file
    dialog's buttons). Kept on the app object so they live as long as it does."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    lang = language()
    if not lang:
        return

    class _Words(QTranslator):
        def translate(self, context, source, disambiguation=None, n=-1):
            # None (a null string) tells Qt "no translation here": an empty one would replace
            # the English with nothing.
            if not source:
                return None
            return lookup(source, disambiguation or None)

        def isEmpty(self):
            return False

    kept = [_Words(app)]
    qt = QTranslator(app)
    if qt.load(QLocale(lang), "qt", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        kept.append(qt)
    for t in kept:
        app.installTranslator(t)
    app._fg_translators = kept
