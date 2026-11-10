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
package is built. Each keeps its upstream licence, named under it below: the GNU General
Public License version 3 or later ([LICENSES/GPL-3.0.txt](LICENSES/GPL-3.0.txt)), version 2
([LICENSES/GPL-2.0.txt](LICENSES/GPL-2.0.txt)), or Creative Commons Attribution-ShareAlike 4.0
([LICENSES/CC-BY-SA-4.0.txt](LICENSES/CC-BY-SA-4.0.txt)). The source is each upstream
repository at the commit named here, plus the build script.

### Bibata Cursor

Glass Light, Glass Dark, Bibata Ice and Bibata Classic (`fedora-glass-light`,
`fedora-glass-dark`, `fedora-glass-bibata-ice`, `fedora-glass-bibata-classic`) are rendered from
the "Modern" SVGs of [Bibata Cursor](https://github.com/ful1e5/Bibata_Cursor) at commit
`ddb09273cde49faeb6a32282660ff4293f52d6e0`, with its hotspots and cursor names. Glass Light and
Glass Dark change its colours to see-through glass bodies; Bibata Ice and Classic keep its own.

Bibata Sharp Ice and Bibata Sharp Classic (`fedora-glass-bibata-original`,
`fedora-glass-bibata-original-classic`) are rendered the same way from its "Original" SVGs, in
Bibata Original Ice's and Classic's own colours. Amber (`fedora-glass-amber`) uses Bibata Modern Amber's orange
with a dark rim in place of its white one, so the pointer still stands out on white pages.

Copyright Abdulkaiz Khatri. GPL-3.0-or-later.

### Banana Cursor

Banana (`fedora-glass-banana`) is rendered from the SVGs of
[Banana Cursor](https://github.com/ful1e5/banana-cursor) at commit
`6d1f8ba67e1547bf1bf5ab6acb43eb3abb5bca9f`, with its hotspots and cursor names, in its own
colours.

Copyright Abdulkaiz Khatri. GPL-3.0-or-later.

### Phinger Cursors

Phinger Light and Phinger Dark (`fedora-glass-phinger-light`, `fedora-glass-phinger-dark`) are
rendered from the 24 and 32 px SVGs of
[Phinger Cursors](https://github.com/phisch/phinger-cursors) at commit
`d8196cd133e5c168adbc84838da673ca0b8593b5`, with the hotspot each SVG marks and the names in its
`cursor-theme.json`. Changes: the busy spinner is turned in 10 degree steps to make the
animation frames, two joke shapes no app asks for (`middle_finger`, `rock_and_roll`) are left
out, and other common names for the same shapes are added as links.

Copyright Philipp Schaffrath. CC-BY-SA-4.0. These two pointer styles, as changed here, are
shared under the same licence.

### Catppuccin Cursors

Catppuccin Mauve and Catppuccin Sky (`fedora-glass-catppuccin-mauve`,
`fedora-glass-catppuccin-sky`) are rendered from the SVGs of
[Catppuccin Cursors](https://github.com/catppuccin/cursors) at commit
`a7eb08527dcce01010fa0ec46fa2bc4c3154f0d4`, coloured as its own build colours the Mocha Mauve
and Mocha Sky themes, with the hotspot each SVG marks and its cursor names. Catppuccin Cursors
are based on [Volantes cursors](https://github.com/varlesh/volantes-cursors) by Alexey
Varfolomeev, coloured with the Catppuccin palette by elkrien and others (see its `AUTHORS`).

GPL-2.0.

### Oreo Cursors

Oreo Pink and Oreo Teal (`fedora-glass-oreo-pink`, `fedora-glass-oreo-teal`) are rendered from
the base SVGs of [Oreo Cursors](https://github.com/varlesh/oreo-cursors) at commit
`7483f2dec06ae0fce182f9e9fe96c7db23b312b5`, coloured as its generator colours its
`spark_pink` and `teal` themes, with the hotspots from its `src/config` files and its cursor
names. Colours by Sourav Goswami.

Copyright Alexey Varfolomeev. GPL-2.0.

### WhiteSur cursors

WhiteSur (`fedora-glass-whitesur`) is the prebuilt theme from
[WhiteSur cursors](https://github.com/vinceliuice/WhiteSur-cursors) at commit
`e190baf618ed95ee217d2fd45589bd309b37672b` (its `dist/` folder), unchanged apart from its
`index.theme` (the name, and Adwaita for any shape it lacks). WhiteSur cursors are based on
[capitaine-cursors](https://github.com/keeferrourke/capitaine-cursors) by Keefer Rourke.

Copyright Vince Liuice. GPL-3.0-or-later.
