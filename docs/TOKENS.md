# Liquid Glass tokens for app developers

Every time Liquid Glass applies, it writes its design tokens to:

| File | Contents |
|---|---|
| `~/.config/liquid-glass/tokens.json` | the scheme in use right now |
| `~/.config/liquid-glass/tokens-dark.json` | dark tokens |
| `~/.config/liquid-glass/tokens-light.json` | light tokens |

An app that draws its own UI (Qt Quick, Electron, games) can read these files and watch them for
changes to match the rest of the desktop. If the files don't exist, Liquid Glass isn't in use: keep
your own look.

## Format

```json
{
  "version": 1,
  "dark": true,
  "frost": 0.45,
  "window": "#2c2f36c7",
  "chrome": "#2c2f3670",
  "...": "..."
}
```

Colours are `#RRGGBBAA`. Numbers are plain JSON numbers. New keys may appear in later versions;
`version` changes only if an existing key changes meaning.

| Key | Meaning |
|---|---|
| `dark` | `true` for the dark scheme |
| `frost` | 0 = liquid (clear), 1 = frosted (milky) |
| `window` | window background |
| `chrome` | header bars, sidebars, panels: the most transparent layer |
| `view` | lists, text areas: the most solid layer, for reading |
| `card` | cards and grouped lists, drawn over `window` or `view` |
| `popover`, `dialog`, `osd` | menus, dialogs, on-screen overlays |
| `hover`, `active` | washes for hovered and pressed controls |
| `highlight` | the specular rim light along the top edge of glass |
| `edge` | the 1 px glass border |
| `divider`, `shadow` | separators and drop shadows |
| `fg`, `fg_dim`, `fg_faint` | text: primary, secondary, disabled/placeholder |
| `accent`, `accent_fg`, `accent_text` | accent fill, text on accent, accent used as text on glass |
| `selection` | selection wash |
| `destructive`, `success`, `warning` | status colours |
| `radius`, `radius_small` | corner radii in px |
| `blur_radius`, `blur_brightness` | the blur behind glass |
| `lens_width`, `lens_bend`, `dispersion`, `vibrancy`, `glare` | the glass lens: rim width and bend in px, rainbow edge 0..1, colour boost (1 = none), rim highlight 0..1 |
| `terminal_opacity` | terminal background opacity |
| `panel_floating`, `panel_margin` | panel style |
| `blur_app_windows` | whether app windows get blur behind them |

## Drawing glass with the tokens

A glass surface is: fill `chrome` (or `window`/`view` for content), a 1 px `edge` border, a 1 px
`highlight` line along the top inside edge, `radius` corners and a soft `shadow`. Put text on `view`
or on `card`-over-`window` for the best readability.
