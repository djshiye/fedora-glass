# Third-party notices

## AndroidLiquidGlass (Backdrop)

The glass lens in the GNOME Shell extension
(`fedoraglass/data/extension/liquid-glass@djshiye.github.io/glass.js`) and in the app's preview
(`fedoraglass/gui/qml/FedoraGlass/shaders/glass.frag`) builds on Kyant's
[AndroidLiquidGlass](https://github.com/Kyant0/AndroidLiquidGlass): the rounded-rectangle
distance field and its gradient and the circular edge profile come from it. They were rewritten
from AGSL to GLSL and changed to fit GNOME Shell and Qt Quick, and the light transport (Snell
refraction, Cauchy dispersion, Fresnel reflection, Beer-Lambert absorption) was added on top.

Copyright 2025 Kyant. Licensed under the Apache License, Version 2.0. See
[LICENSES/Apache-2.0.txt](LICENSES/Apache-2.0.txt).

## Mouse pointer styles

The pointer styles in the app's Mouse pointer picker are installed to
`/usr/share/icons/fedora-glass-*` from the archives in [`data/cursors/`](data/cursors/), which
[`packaging/cursors/build.py`](packaging/cursors/build.py) builds from the pinned upstream
commits below. Each archive's SHA-256 is in `data/cursors/SHA256SUMS` and is checked before a
package is built. They are licensed under the GNU General Public License, version 3 or later;
see [LICENSES/GPL-3.0.txt](LICENSES/GPL-3.0.txt). The source is each upstream repository at
the commit named here, plus the build script.

### Bibata Cursor

Glass Light, Glass Dark, Bibata Ice and Bibata Classic (`fedora-glass-light`,
`fedora-glass-dark`, `fedora-glass-bibata-ice`, `fedora-glass-bibata-classic`) are rendered from
the "Modern" SVGs of [Bibata Cursor](https://github.com/ful1e5/Bibata_Cursor) at commit
`ddb09273cde49faeb6a32282660ff4293f52d6e0`, with its hotspots and cursor names. Glass Light and
Glass Dark change its colours to see-through glass bodies; Bibata Ice and Classic keep its own.

Copyright Abdulkaiz Khatri. GPL-3.0-or-later.

### WhiteSur cursors

WhiteSur (`fedora-glass-whitesur`) is the prebuilt theme from
[WhiteSur cursors](https://github.com/vinceliuice/WhiteSur-cursors) at commit
`e190baf618ed95ee217d2fd45589bd309b37672b` (its `dist/` folder), unchanged apart from its
`index.theme` (the name, and Adwaita for any shape it lacks). WhiteSur cursors are based on
[capitaine-cursors](https://github.com/keeferrourke/capitaine-cursors) by Keefer Rourke.

Copyright Vince Liuice. GPL-3.0-or-later.
