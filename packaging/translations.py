#!/usr/bin/env python3
"""Keeps the translation files in step with the code.

    python3 -I packaging/translations.py update   # after changing words in the code
    python3 -I packaging/translations.py check    # what the tests run: nothing missing or stale

update finds every marked word (qsTr in QML, _() and N_() in Python, _() in the Shell
extension), writes fedoraglass/data/po/fedora-glass.pot, brings each language's .po in step
(new words added empty, words the code no longer has dropped, translations kept), and
rewrites the extension's strings.js from the .po files.

To add a language: copy fedora-glass.pot to <code>.po, translate it, add the code to
LANGUAGES in fedoraglass/i18n.py, run update.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fedoraglass import i18n  # noqa: E402

PKG = ROOT / "fedoraglass"
QML = PKG / "gui" / "qml"
EXT = PKG / "data" / "extension" / "liquid-glass@djshiye.github.io"
POT = i18n.PO_DIR / "fedora-glass.pot"
STRINGS_JS = EXT / "strings.js"

_QML_STR = r'"((?:[^"\\]|\\.)*)"'
QSTR = re.compile(r"\bqsTr\(\s*" + _QML_STR + r"(?:\s*,\s*" + _QML_STR + r")?\s*[,)]")
JS_STR = re.compile(r"(?<![\w.])_\(\s*'((?:[^'\\]|\\.)*)'\s*\)")
_JS_ESC = {"n": "\n", "t": "\t", "'": "'", '"': '"', "\\": "\\"}


def _js_unquote(s: str) -> str:
    return re.sub(r"\\(.)", lambda m: _JS_ESC.get(m.group(1), m.group(1)), s)


def _where(path: Path, text: str, pos: int) -> str:
    return f"{path.relative_to(ROOT)}:{text.count(chr(10), 0, pos) + 1}"


def qml_words() -> dict[tuple[str | None, str], list[str]]:
    found: dict[tuple[str | None, str], list[str]] = {}
    for path in sorted([*QML.rglob("*.qml"), *QML.rglob("*.js")]):
        text = path.read_text(encoding="utf-8")
        for m in QSTR.finditer(text):
            word = _js_unquote(m.group(1))
            ctx = _js_unquote(m.group(2)) if m.group(2) else None
            found.setdefault((ctx, word), []).append(_where(path, text, m.start()))
    return found


def python_words() -> dict[tuple[str | None, str], list[str]]:
    found: dict[tuple[str | None, str], list[str]] = {}
    for path in sorted(PKG.rglob("*.py")):
        if path.name == "i18n.py":
            continue
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            name = node.func.id
            args = node.args
            if name in ("_", "N_") and len(args) == 1:
                key = (None, args[0])
            elif name == "pgettext" and len(args) == 2:
                if not (isinstance(args[0], ast.Constant) and isinstance(args[0].value, str)):
                    raise SystemExit(f"{path.relative_to(ROOT)}:{node.lineno}: pgettext needs a plain context")
                key = (args[0].value, args[1])
            else:
                continue
            arg = key[1]
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                raise SystemExit(f"{path.relative_to(ROOT)}:{node.lineno}: {name}() needs a plain string "
                                 "(use .format() after it, not an f-string)")
            found.setdefault((key[0], arg.value), []).append(f"{path.relative_to(ROOT)}:{node.lineno}")
    return found


def extension_words() -> dict[tuple[str | None, str], list[str]]:
    found: dict[tuple[str | None, str], list[str]] = {}
    for path in sorted(EXT.glob("*.js")):
        if path.name == "strings.js":
            continue
        text = path.read_text(encoding="utf-8")
        for m in JS_STR.finditer(text):
            found.setdefault((None, _js_unquote(m.group(1))), []).append(_where(path, text, m.start()))
    return found


def all_words() -> dict[tuple[str | None, str], list[str]]:
    out: dict[tuple[str | None, str], list[str]] = {}
    for part in (qml_words(), python_words(), extension_words()):
        for k, v in part.items():
            out.setdefault(k, []).extend(v)
    return dict(sorted(out.items(), key=lambda kv: (kv[1][0], kv[0][1])))


def _quote(s: str) -> str:
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t")
    if "\n" not in s:
        return f'"{s}"'
    parts = s.split("\n")
    lines = [p + "\\n" for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])
    return '""\n' + "\n".join(f'"{p}"' for p in lines)


def _entry(ctx: str | None, word: str, translation: str, places: list[str], extra: list[str]) -> str:
    out = [c for c in extra if c.startswith("# ") or c.startswith("#.") or c.startswith("#,")]
    out = [c for c in out if not c.startswith("#:")]
    out += [f"#: {p}" for p in places[:3]]
    if ctx is not None:
        out.append(f"msgctxt {_quote(ctx)}")
    out.append(f"msgid {_quote(word)}")
    out.append(f"msgstr {_quote(translation)}")
    return "\n".join(out)


def _header(lang: str | None) -> str:
    name = i18n.LANGUAGES.get(lang, "") if lang else ""
    return "\n".join([
        f"# Fedora Glass: {name or 'template'} words.",
        "# Keep the %1, %2 and {name} markers exactly as they are; they are filled in by the app.",
        'msgid ""',
        'msgstr ""',
        '"Project-Id-Version: fedora-glass\\n"',
        f'"Language: {lang or ""}\\n"',
        '"MIME-Version: 1.0\\n"',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Content-Transfer-Encoding: 8bit\\n"',
    ])


def render_po(lang: str | None, words, old: dict) -> str:
    blocks = [_header(lang)]
    for (ctx, word), places in words.items():
        prev = old.get((ctx, word), {})
        blocks.append(_entry(ctx, word, prev.get("str", "") if lang else "", places, prev.get("comments", [])))
    return "\n\n".join(blocks) + "\n"


def read_po(lang: str) -> dict:
    path = i18n.PO_DIR / f"{lang}.po"
    if not path.exists():
        return {}
    return {(e["ctx"], e["id"]): e for e in i18n.parse_po(path.read_text(encoding="utf-8")) if e["id"]}


def render_strings_js() -> str:
    """The Shell extension's few words, in every language, as a small JS module (the Shell
    and the extension's settings window both import it; no compiled .mo files)."""
    words = sorted({w for (_c, w) in extension_words()})
    table = {}
    for lang in sorted(i18n.LANGUAGES):
        cat = {k: e["str"] for k, e in read_po(lang).items() if e["str"] and not e.get("fuzzy")}
        got = {w: cat[(None, w)] for w in words if (None, w) in cat}
        if got:
            table[lang] = got
    body = json.dumps(table, ensure_ascii=False, indent=4, sort_keys=True)
    return f"""// Made by packaging/translations.py from fedoraglass/data/po/*.po: do not edit by hand.
// The extension's words in the languages the app speaks; English when there is none.

import GLib from 'gi://GLib';

const WORDS = {body};

function pick() {{
    for (const name of GLib.get_language_names?.() ?? []) {{
        const code = name.split('.')[0].split('@')[0];
        if (code === 'C' || code === 'POSIX' || code.startsWith('en'))
            return null;
        if (WORDS[code])
            return WORDS[code];
        const base = code.split('_')[0];
        if (WORDS[base])
            return WORDS[base];
        if (base === 'pt' && WORDS.pt_BR)
            return WORDS.pt_BR;
    }}
    return null;
}}

let words;

/** The word in the session's language, or the English it was given. */
export function _(text) {{
    words ??= pick() ?? {{}};
    return words[text] ?? text;
}}
"""


def problems() -> list[str]:
    """Everything update would change, plus translations that drop a marker."""
    out = []
    words = all_words()
    if not POT.exists() or POT.read_text(encoding="utf-8") != render_po(None, words, {}):
        out.append(f"{POT.relative_to(ROOT)} is out of date: run packaging/translations.py update")
    for lang in i18n.LANGUAGES:
        old = read_po(lang)
        path = i18n.PO_DIR / f"{lang}.po"
        if not path.exists() or path.read_text(encoding="utf-8") != render_po(lang, words, old):
            out.append(f"{path.relative_to(ROOT)} is out of date: run packaging/translations.py update")
        for (ctx, word) in words:
            e = old.get((ctx, word))
            if not e or not e["str"]:
                out.append(f"{lang}: not translated: {word!r}")
                continue
            for mark in sorted(set(re.findall(r"%\d|\{\w*\}", word))):
                if e["str"].count(mark) != word.count(mark):
                    out.append(f"{lang}: {word!r} -> {e['str']!r} changes {mark}")
            if e.get("fuzzy"):
                out.append(f"{lang}: marked fuzzy: {word!r}")
    if not STRINGS_JS.exists() or STRINGS_JS.read_text(encoding="utf-8") != render_strings_js():
        out.append(f"{STRINGS_JS.relative_to(ROOT)} is out of date: run packaging/translations.py update")
    return out


def update() -> None:
    words = all_words()
    i18n.PO_DIR.mkdir(parents=True, exist_ok=True)
    POT.write_text(render_po(None, words, {}), encoding="utf-8")
    for lang in i18n.LANGUAGES:
        old = read_po(lang)
        (i18n.PO_DIR / f"{lang}.po").write_text(render_po(lang, words, old), encoding="utf-8")
    STRINGS_JS.write_text(render_strings_js(), encoding="utf-8")
    print(f"{len(words)} words")


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "check"
    if cmd == "update":
        update()
        return 0
    if cmd == "check":
        found = problems()
        for p in found[:50]:
            print(p)
        if len(found) > 50:
            print(f"... and {len(found) - 50} more")
        return 1 if found else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
