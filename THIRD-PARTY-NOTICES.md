# Third-party notices

## AndroidLiquidGlass (Backdrop)

The glass lens in the GNOME Shell extension
(`liquidglass/data/extension/liquid-glass@djshiye.github.io/glass.js`) and in the app's preview
(`liquidglass/gui/qml/LiquidGlass/shaders/glass.frag`) builds on Kyant's
[AndroidLiquidGlass](https://github.com/Kyant0/AndroidLiquidGlass): the rounded-rectangle
distance field and its gradient and the circular edge profile come from it. They were rewritten
from AGSL to GLSL and changed to fit GNOME Shell and Qt Quick, and the light transport (Snell
refraction, Cauchy dispersion, Fresnel reflection, Beer-Lambert absorption) was added on top.

Copyright 2025 Kyant. Licensed under the Apache License, Version 2.0. See
[LICENSES/Apache-2.0.txt](LICENSES/Apache-2.0.txt).
