"""The app's side of the glass login screen (the root helper is fedoraglass/login_glass.py).

What the app sends to `fedora-glass-login on`, how it reads `fedora-glass-login status`,
the plain sentences for the helper's codes, and the copy of the wallpaper the login screen
gets. The helper never decodes a picture and never gets a path: the app decodes the
wallpaper as the person, scales it down, encodes it again (which drops its metadata) and
hands over only those bytes.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from .. import wallcolour
from ..i18n import N_, gettext as tr
from ..settings import Settings, clean_message

# The values the helper takes, with the contract's defaults (login-contract.md).
DEFAULTS: dict[str, Any] = {
    "accent": "#3584e4", "tint": "#1e1e2a", "tint_amount": 0.2, "frost": 0.35, "blur": 60, "dim": 0.28,
    "card": True, "clock": "bold", "picture": "wallpaper", "fit": "zoom", "battery": True, "message": "",
}
CLOCKS = ("gnome", "bold", "thin")
PICTURES = ("wallpaper", "system", "glow")
# How "My wallpaper" is placed: the desktop's own picture-options, so a picture spanned over
# two screens is spanned on the login screen too ("none", no picture, has no login meaning).
FITS = ("zoom", "spanned", "scaled", "stretched", "centered", "wallpaper")
STATES = ("off", "trial", "on")
WHY = ("no-gdm", "not-gdm", "no-addon", "no-dconf", "gnome-version", "policy")
STOPPED = ("no-login", "crash", "silent", "kernel-arg", "gnome-version", "error")

# The copy the login screen gets: big enough for one picture over two 4K screens (or a
# 5120x1440 one over two), scaled down, keeping its shape, only beyond either limit.
PICTURE_MAX_SIDE = 7680         # px, the long side
PICTURE_MAX_PIXELS = 33_177_600 # 7680x4320
PICTURE_QUALITY_STEPS = (90, 80, 70, 60, 50)    # tried in turn while the file is too big
PICTURE_MAX_BYTES = 16 << 20    # what the helper takes on stdin
STATUS_MAX = 64 * 1024          # a status answer longer than this is not the helper's
# Half a character pair (JSON can carry one) can't go in an argument; the helper drops them
# before it cleans the message, so this does the same and the two stay comparable.
_SURROGATE = re.compile("[\ud800-\udfff]")


def values(s: Settings, accent: str, fit: str = "zoom") -> dict:
    """The twelve values for the helper, from a look. `accent` is the accent colour as the
    look shows it ("#rrggbb", worked out by the palette); `fit` how the desktop places its
    wallpaper (fit_from_options). "Match my lock screen" takes the lock screen's own
    values; off, the login screen's."""
    s = s.normalized()
    m = s.login_match_lock
    out = {
        "accent": accent.lower(),
        "tint": _hex6(s.tint),
        "tint_amount": round(s.lock_tint if m else s.login_tint, 3),
        "frost": round(s.frost, 3),
        "blur": int(s.lock_blur if m else s.login_blur),
        "dim": round(s.lock_dim if m else s.login_dim, 3),
        "card": bool(s.lock_card if m else s.login_card),
        "clock": s.lock_clock if m else s.login_clock,
        "picture": s.login_picture,
        "fit": fit,
        "battery": bool(s.lock_widget_battery if m else s.login_battery),
        "message": _message(s.lock_message if m else s.login_message),
    }
    return normalized(out)


def fit_from_options(raw: Any) -> str:
    """org.gnome.desktop.background picture-options as gsettings prints it ("'spanned'")
    to a fit: "none" and anything unknown are "zoom", GNOME's own default."""
    v = raw.strip().strip("'\"") if isinstance(raw, str) else ""
    return v if v in FITS else "zoom"


def _hex6(v: str) -> str:
    v = str(v).lower()
    if len(v) == 4:            # "#abc"
        v = "#" + "".join(c * 2 for c in v[1:])
    return v


def _num(v: Any, lo: float, hi: float, default: float) -> float:
    if isinstance(v, bool):
        return default
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return min(hi, max(lo, f)) if math.isfinite(f) else default


def _is_hex6(v: Any) -> bool:
    return isinstance(v, str) and len(v) == 7 and v[0] == "#" and all(c in "0123456789abcdef" for c in v[1:].lower())


def normalized(v: Any) -> dict:
    """A values object kept inside the contract's ranges, the way the helper keeps it. The
    helper's own `status` answer is read through this too: it is data, never trusted."""
    v = v if isinstance(v, dict) else {}
    out = dict(DEFAULTS)
    for k in ("accent", "tint"):
        if _is_hex6(v.get(k)):
            out[k] = v[k].lower()
    out["tint_amount"] = round(_num(v.get("tint_amount"), 0, 1, DEFAULTS["tint_amount"]), 3)
    out["frost"] = round(_num(v.get("frost"), 0, 1, DEFAULTS["frost"]), 3)
    out["blur"] = int(round(_num(v.get("blur"), 10, 100, DEFAULTS["blur"])))
    out["dim"] = round(_num(v.get("dim"), 0, 0.65, DEFAULTS["dim"]), 3)
    for k in ("card", "battery"):
        if isinstance(v.get(k), bool):
            out[k] = v[k]
    if v.get("clock") in CLOCKS:
        out["clock"] = v["clock"]
    if v.get("picture") in PICTURES:
        out["picture"] = v["picture"]
    if v.get("fit") in FITS:            # missing (a helper from before it existed): zoom
        out["fit"] = v["fit"]
    out["message"] = _message(v.get("message", ""))
    return out


def _message(raw: Any) -> str:
    """The message as the helper keeps it: no half pairs, then one cleaned paragraph."""
    return clean_message(_SURROGATE.sub("", raw) if isinstance(raw, str) else raw)


def same_values(a: dict | None, b: dict | None) -> bool:
    """Whether two values objects give the same login screen (numbers within rounding)."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    a, b = normalized(a), normalized(b)
    for k in DEFAULTS:
        x, y = a[k], b[k]
        if isinstance(x, float) or isinstance(y, float):
            if abs(float(x) - float(y)) > 0.0005:
                return False
        elif x != y:
            return False
    return True


def parse_status(text: str) -> dict | None:
    """`fedora-glass-login status` output, checked: {"available", "why", "state", "stopped",
    "values", "picture_sha256", "leaving"}, or None when it isn't the helper's answer at all.
    leaving: a Turn off did not finish (only another off finishes it; a helper from before
    it existed says nothing, which is false)."""
    if not isinstance(text, str) or len(text) > STATUS_MAX:
        return None
    try:
        data = json.loads(text.strip() or "null")
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("version") != 1:
        return None
    state = data.get("state") if data.get("state") in STATES else "off"
    why = data.get("why") if data.get("why") in WHY else ""
    stopped = data.get("stopped") if data.get("stopped") in STOPPED else ""
    sha = data.get("picture_sha256")
    sha = sha.lower() if isinstance(sha, str) and len(sha) == 64 and all(c in "0123456789abcdef" for c in sha.lower()) else ""
    available = data.get("available") is True
    if not available and not why:
        why = "error"           # says it can't, without a reason this app knows
    raw = data.get("values")
    return {"available": available, "why": "" if available else why, "state": state,
            "stopped": stopped if state == "off" else "",
            "values": normalized(raw) if isinstance(raw, dict) else None, "picture_sha256": sha,
            "leaving": data.get("leaving") is True}


# ---- what the codes mean, in plain words --------------------------------------------------
# Phrases, not sentences: they follow "Not available: " and "Nothing was changed: ".
WHY_TEXT = {
    "no-gdm": N_("it needs GDM, GNOME's own login screen"),
    "not-gdm": N_("this PC uses a different login screen"),
    "no-addon": N_("a part of Fedora Glass is missing (installing Fedora Glass again brings it back)"),
    "no-dconf": N_("a system part it needs (dconf) is missing"),
    "gnome-version": N_("this GNOME version is not supported yet"),
    "policy": N_("the permission it needs is missing (installing Fedora Glass again brings it back)"),
    "error": N_("it could not check this PC"),
}
STOPPED_TEXT = {
    "no-login": N_("nobody logged in after it was turned on"),
    "crash": N_("the login screen had a problem with it"),
    "silent": N_("the login screen did not show it"),
    "kernel-arg": N_("it was switched off when the PC started"),
    "gnome-version": N_("this GNOME version is not supported yet"),
    "error": N_("something went wrong when the PC started"),
}


def why_text(code: str) -> str:
    return tr(WHY_TEXT.get(code) or WHY_TEXT["error"])


def stopped_text(code: str) -> str:
    return tr(STOPPED_TEXT.get(code) or STOPPED_TEXT["error"])


# ---- the picture ------------------------------------------------------------------------------
def picture_file(path: str) -> str:
    """The picture file behind a wallpaper path: a slideshow (.xml) gives its first
    picture. "" when there is none."""
    if path and path.lower().endswith(".xml"):
        path = wallcolour.slideshow_picture(path)
    return path if path and Path(path).is_file() else ""


def prepare_picture(path: str) -> bytes | None:
    """The wallpaper as the login screen gets it: decoded here, as the person, with its
    orientation applied; scaled down, keeping its shape, only beyond PICTURE_MAX_SIDE or
    PICTURE_MAX_PIXELS; and encoded again as a JPEG, so none of the file's metadata goes
    along. The quality steps down while the file is over PICTURE_MAX_BYTES; never more is
    sent. None when it can't be read (or won't fit). Call it off the UI thread: a big
    picture takes a moment."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize
    from PySide6.QtGui import QColor, QImage, QImageReader, QPainter
    if not path:
        return None
    r = QImageReader(path)
    r.setAutoTransform(True)
    size = r.size()
    if size.isValid():
        # Scaled while it decodes: a huge picture never sits in memory at full size.
        k = _shrink(size.width(), size.height())
        if k < 1:
            r.setScaledSize(QSize(max(1, int(size.width() * k)), max(1, int(size.height() * k))))
    img = r.read()
    if img.isNull():
        return None
    k = _shrink(img.width(), img.height())                     # a size only known once decoded
    if k < 1:
        img = img.scaled(QSize(max(1, int(img.width() * k)), max(1, int(img.height() * k))),
                         aspectMode=_keep_aspect(), mode=_smooth())
    # JPEG has no transparency: see-through parts sit on black, as the login screen's own
    # background would show them.
    flat = QImage(img.size(), QImage.Format.Format_RGB32)
    flat.fill(QColor("black"))
    p = QPainter(flat)
    p.drawImage(0, 0, img)
    p.end()
    for quality in PICTURE_QUALITY_STEPS:
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        ok = flat.save(buf, "JPG", quality)
        buf.close()
        out = bytes(data.data())
        if not ok or not out:
            return None
        if len(out) <= PICTURE_MAX_BYTES:
            return out
    return None


def _shrink(w: int, h: int) -> float:
    """The scale (at most 1) that keeps a w x h picture within both limits."""
    if w <= 0 or h <= 0:
        return 1.0
    return min(1.0, PICTURE_MAX_SIDE / max(w, h), math.sqrt(PICTURE_MAX_PIXELS / (w * h)))


def _keep_aspect():
    from PySide6.QtCore import Qt
    return Qt.AspectRatioMode.KeepAspectRatio


def _smooth():
    from PySide6.QtCore import Qt
    return Qt.TransformationMode.SmoothTransformation
