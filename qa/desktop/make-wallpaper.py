"""Draw the test wallpaper: a dark starry sky with a purple glow, like Dino's.

Seeded, so every run gets the same picture. Sized for a 2000x1125 screen (1600x900 at 125 %).
"""
import sys

import numpy as np
from PIL import Image

W, H = 2000, 1125
rng = np.random.default_rng(3)
yy, xx = np.mgrid[0:H, 0:W] / np.array([H, W])[:, None, None]
glow = np.exp(-(((xx - 0.72) / 0.40) ** 2 + ((yy - 0.45) / 0.30) ** 2))
band = np.exp(-(((yy - 0.55 + 0.35 * (xx - 0.5)) / 0.10) ** 2))
sky = np.stack([0.02 + 0.26 * glow + 0.05 * band, 0.02 + 0.10 * glow + 0.04 * band, 0.05 + 0.34 * glow + 0.10 * band], -1)
stars = np.zeros((H, W))
n = 1400
stars[rng.integers(0, H, n), rng.integers(0, W, n)] = rng.uniform(0.4, 1, n)
img = np.clip(sky + stars[..., None], 0, 1)
Image.fromarray((img * 255).astype(np.uint8)).save(sys.argv[1])
