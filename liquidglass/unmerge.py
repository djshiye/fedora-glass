"""Take Fedora Glass's own keys back out of another app's settings file.

Some targets don't own a whole file: they set a few keys in an app's own settings
(VS Code's settings.json, qBittorrent.conf, btop.conf, ...). Restore normally puts the
copy from before the first Apply back. When the file has changed since Apply (the user
changed a setting, or the app rewrote it), that copy would wipe those changes, so only
our keys go back to what they were before, and everything else stays as it is now.

A spec (WriteFile.edits) names the format and the keys:
    ("json", ("workbench.colorTheme", ...))     top-level keys of a JSON object
    ("ini", "Section", ("key", ...))            keys inside [Section] (QSettings style)
    ("conf", ("key", ...))                      `key = value` lines (btop.conf style)
"""
from __future__ import annotations

import json
import re

from .render.apps import conf_set, ini_set


def _ini_section(text: str, section: str) -> tuple[list[str], int | None, int]:
    lines = text.splitlines(keepends=True)
    start, end = None, len(lines)
    for i, ln in enumerate(lines):
        m = re.match(r"\s*\[(.*)\]\s*$", ln)
        if m:
            if start is not None:
                end = i
                break
            if m.group(1) == section:
                start = i
    return lines, start, end


def _ini_key(line: str) -> str | None:
    return line.split("=", 1)[0].strip() if "=" in line else None


def ini_get(text: str, section: str, key: str) -> str | None:
    lines, start, end = _ini_section(text, section)
    if start is None:
        return None
    for ln in lines[start + 1:end]:
        if _ini_key(ln) == key:
            return ln.split("=", 1)[1].rstrip("\r\n")
    return None


def ini_del(text: str, section: str, key: str) -> str:
    lines, start, end = _ini_section(text, section)
    if start is None:
        return text
    return "".join(ln for i, ln in enumerate(lines) if not (start < i < end and _ini_key(ln) == key))


_CONF = re.compile(r"\s*([A-Za-z0-9_]+)\s*=(.*)$")


def conf_get(text: str, key: str) -> str | None:
    for ln in text.splitlines():
        m = _CONF.match(ln)
        if m and m.group(1) == key:
            return m.group(2).strip()
    return None


def conf_del(text: str, key: str) -> str:
    return "".join(ln for ln in text.splitlines(keepends=True)
                   if not ((m := _CONF.match(ln.rstrip("\r\n"))) and m.group(1) == key))


def unmerge(current: str, original: str | None, spec) -> str | None:
    """`current` with the keys in `spec` put back as they were in `original` (None: the
    file did not exist, so the keys go). None when either file can't be read as that
    format, or the spec is unknown."""
    if not spec:
        return None
    kind = spec[0]
    if kind == "json":
        try:
            cur = json.loads(current) if current.strip() else {}
            orig = json.loads(original) if original and original.strip() else {}
        except ValueError:
            return None
        if not isinstance(cur, dict) or not isinstance(orig, dict):
            return None
        for k in spec[1]:
            if k in orig:
                cur[k] = orig[k]
            else:
                cur.pop(k, None)
        return json.dumps(cur, indent=2, ensure_ascii=False) + "\n"
    if kind == "ini":
        section, keys = spec[1], spec[2]
        out = current
        for k in keys:
            old = ini_get(original, section, k) if original else None
            out = ini_set(out, section, {k: old}) if old is not None else ini_del(out, section, k)
        return out
    if kind == "conf":
        out = current
        for k in spec[1]:
            old = conf_get(original, k) if original else None
            out = conf_set(out, {k: old}) if old is not None else conf_del(out, k)
        return out
    return None
