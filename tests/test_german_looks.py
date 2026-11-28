"""German tells a saved look and the light/dark style apart: a look is a "Look", "Stil" is only
the light/dark style (and the motion style, the style files)."""

import re

from fedoraglass import i18n

# "Stil" that really means the light/dark style stays.
LIGHT_DARK = re.compile(r"(?:hellen|dunklen)(?: und| oder)? ?(?:hellen|dunklen)? Stil|Heller Stil|Dunkler Stil")


def _de():
    text = (i18n.PO_DIR / "de.po").read_text(encoding="utf-8")
    return {e["id"]: e["str"] for e in i18n.parse_po(text) if e["id"] and e["ctx"] is None}


def test_no_saved_look_is_called_stil_in_german():
    bad = {}
    for msgid, msgstr in _de().items():
        if not re.search(r"\blooks?\b", msgid, re.I):
            continue
        if "style files" in msgid:                    # the GTK style files, not a look
            continue
        if re.search(r"stil", LIGHT_DARK.sub("", msgstr), re.I):
            bad[msgid] = msgstr
    assert not bad, bad


def test_the_day_and_night_card_reads_look_for_looks_and_stil_for_light_and_dark():
    de = _de()
    assert de["Light style"] == "Heller Stil"
    assert de["Dark style"] == "Dunkler Stil"
    assert de["Look for the light style"] == "Look für Hell"
    assert de["Look for the dark style"] == "Look für Dunkel"
    assert "Stil" not in de["Same look"]
    assert de["Your looks"] == "Ihre Looks"
    both = de["Save two looks to switch between them with GNOME's light and dark style."]
    assert "zwei Looks" in both and "hellen und dunklen Stil" in both
