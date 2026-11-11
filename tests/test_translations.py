"""Translations: every word the app shows is marked, translated in each language, and loaded."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from fedoraglass import i18n

ROOT = Path(__file__).resolve().parent.parent
QML = ROOT / "fedoraglass" / "gui" / "qml"
sys.path.insert(0, str(ROOT / "packaging"))
import translations  # noqa: E402

# Properties that hold words a person reads.
SHOWN = r"(text|title|subtitle|tip|label|caption|placeholderText|Accessible\.name|Accessible\.description|" \
        r"resetTip|autoTip|autoText|summary|state_|note|hint|detail|heading|message|what|when)"
BARE = re.compile(r"\b" + SHOWN + r"\s*:\s*\"([^\"]*[A-Za-z][^\"]*)\"")
# Shown as they are in every language.
KEEP = {"Fedora Glass", "GNOME", "ArcMenu", "Dash to Panel", "Firefox", "GitHub", "Orchis", "Qt", "GTK", "Aa",
        "Liquid Glass", "Flatpak", "Bibata", "Adwaita", "Breeze"}


def test_no_unmarked_words_in_qml():
    left = []
    for path in sorted([*QML.rglob("*.qml"), *QML.rglob("*.js")]):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("//"):
                continue
            for m in BARE.finditer(line):
                if m.group(2) not in KEEP and not m.group(2).startswith(("qrc:", "image:", "file:")):
                    left.append(f"{path.relative_to(ROOT)}:{n}: {m.group(0)}")
    assert not left, "words not wrapped in qsTr():\n" + "\n".join(left[:80])


def test_translation_files_in_step_and_complete():
    found = translations.problems()
    assert not found, "\n".join(found[:60])


def test_every_language_has_a_file():
    for lang in i18n.LANGUAGES:
        assert (i18n.PO_DIR / f"{lang}.po").is_file()


@pytest.mark.parametrize("env,want", [
    ({"LANG": "de_DE.UTF-8"}, "de"),
    ({"LANG": "fr_CA.UTF-8"}, "fr"),
    ({"LANG": "pt_PT.UTF-8"}, "pt_BR"),
    ({"LANG": "pt_BR.UTF-8"}, "pt_BR"),
    ({"LANG": "es_MX.UTF-8"}, "es"),
    ({"LANG": "en_US.UTF-8"}, None),
    ({"LANG": "C.UTF-8"}, None),
    ({}, None),
    ({"LANG": "ja_JP.UTF-8"}, None),
    ({"LANG": "en_GB.UTF-8", "LANGUAGE": "it:en"}, "it"),
    ({"LANG": "C", "LANGUAGE": "de"}, None),
    ({"LC_ALL": "es_ES.UTF-8", "LANG": "de_DE.UTF-8"}, "es"),
    ({"LANG": "de_DE.UTF-8", "FEDORA_GLASS_LANG": "fr"}, "fr"),
    ({"LANG": "sr_RS@latin"}, None),
])
def test_language_follows_the_session(env, want):
    assert i18n.pick_language(env) == want


def test_po_parser_reads_escapes_context_and_skips_fuzzy():
    text = '\n'.join([
        'msgid ""', 'msgstr ""', '"Language: de\\n"', '',
        '#: a.qml:1', 'msgid "Say \\"hi\\""', 'msgstr "Sag \\"hallo\\""', '',
        'msgctxt "preset"', 'msgid "Clear"', 'msgstr "Klar"', '',
        '#, fuzzy', 'msgid "Old"', 'msgstr "Alt"', '',
        'msgid ""', '"Two "', '"lines"', 'msgstr ""', '"Zwei "', '"Zeilen"',
    ])
    entries = i18n.parse_po(text)
    got = {(e["ctx"], e["id"]): (e["str"], bool(e.get("fuzzy"))) for e in entries if e["id"]}
    assert got[(None, 'Say "hi"')] == ('Sag "hallo"', False)
    assert got[("preset", "Clear")] == ("Klar", False)
    assert got[(None, "Old")] == ("Alt", True)
    assert got[(None, "Two lines")] == ("Zwei Zeilen", False)


def test_a_broken_po_file_falls_back_to_english(tmp_path, monkeypatch):
    (tmp_path / "de.po").write_text('msgid "Apply"\nnonsense here\n', encoding="utf-8")
    monkeypatch.setattr(i18n, "PO_DIR", tmp_path)
    assert i18n.load_catalog("de") == {}
    (tmp_path / "fr.po").write_bytes(b"\xff\xfe junk")
    assert i18n.load_catalog("fr") == {}


def test_gettext_uses_the_language_and_falls_back():
    try:
        i18n.reset("de")
        assert i18n.gettext("Apply") != "Apply"
        assert i18n.gettext("A sentence nobody wrote") == "A sentence nobody wrote"
        i18n.reset("")
        assert i18n.gettext("Apply") == "Apply"
    finally:
        i18n.reset(env={})


def test_check_command_passes():
    out = subprocess.run([sys.executable, "-I", str(ROOT / "packaging" / "translations.py"), "check"],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr


def test_open_the_verb_and_open_the_motion_are_told_apart():
    from fedoraglass import i18n
    try:
        for lang, verb, noun in (("fr", "Ouvrir", "Ouverture"), ("it", "Apri", "Apertura"),
                                 ("de", "Öffnen", "Öffnen"), ("es", "Abrir", "Apertura"),
                                 ("pt_BR", "Abrir", "Abertura")):
            i18n.reset(lang)
            assert i18n.gettext("Open") == verb
            assert i18n.pgettext("motion event", "Open") == noun
    finally:
        i18n.reset()
