"""A small sRGB colour type with the mixing helpers the renderers need."""

from __future__ import annotations

from dataclasses import dataclass


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * _clamp(t)


@dataclass(frozen=True)
class Color:
    r: float  # 0..1
    g: float
    b: float
    a: float = 1.0

    @classmethod
    def hex(cls, value: str) -> "Color":
        v = value.strip().lstrip("#")
        if len(v) == 3:
            v = "".join(c * 2 for c in v)
        if len(v) not in (6, 8) or any(c not in "0123456789abcdefABCDEF" for c in v):
            raise ValueError(f"not a hex colour: {value!r}")
        r, g, b = (int(v[i:i + 2], 16) / 255 for i in (0, 2, 4))
        a = int(v[6:8], 16) / 255 if len(v) == 8 else 1.0
        return cls(r, g, b, a)

    def with_alpha(self, a: float) -> "Color":
        return Color(self.r, self.g, self.b, _clamp(a))

    def mix(self, other: "Color", t: float) -> "Color":
        """Linear mix in sRGB: t=0 is self, t=1 is other."""
        t = _clamp(t)
        return Color(lerp(self.r, other.r, t), lerp(self.g, other.g, t),
                     lerp(self.b, other.b, t), lerp(self.a, other.a, t))

    def luminance(self) -> float:
        def ch(c: float) -> float:
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * ch(self.r) + 0.7152 * ch(self.g) + 0.0722 * ch(self.b)

    def contrast(self, other: "Color") -> float:
        hi, lo = sorted((self.luminance(), other.luminance()), reverse=True)
        return (hi + 0.05) / (lo + 0.05)

    # ---- output formats -------------------------------------------------
    def _bytes(self) -> tuple[int, int, int]:
        return tuple(round(_clamp(c) * 255) for c in (self.r, self.g, self.b))  # type: ignore[return-value]

    @property
    def css(self) -> str:
        """rgba() string, valid in GTK, GNOME Shell (St) and web CSS."""
        r, g, b = self._bytes()
        if self.a >= 0.999:
            return f"rgb({r},{g},{b})"
        return f"rgba({r},{g},{b},{self.a:.3f})"

    @property
    def hex6(self) -> str:
        r, g, b = self._bytes()
        return f"#{r:02x}{g:02x}{b:02x}"

    @property
    def hex8(self) -> str:
        """#RRGGBBAA (web, VS Code, Kvantum)."""
        return f"{self.hex6}{round(_clamp(self.a) * 255):02x}"

    @property
    def argb(self) -> str:
        """#AARRGGBB (Qt)."""
        return f"#{round(_clamp(self.a) * 255):02x}{self.hex6[1:]}"

    def __str__(self) -> str:  # handy in f-strings
        return self.css


WHITE = Color(1, 1, 1)
BLACK = Color(0, 0, 0)
