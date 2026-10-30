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
| `radius`, `radius_small` | corner radii in px (the global setting) |
| `panel_radius`, `menu_radius`, `window_radius` | corner radius of the panel, the menus (quick settings) and app windows; equal to `radius` unless the user set one for that part |
| `panel_blur`, `menu_blur`, `window_blur` | blur radius in px behind each of those parts |
| `window_chrome` | sidebars and bars inside app windows (`chrome` is the panel's surface, `popover`, `dialog` and `osd` the quick settings', `window` and `view` the app windows') |
| `parts` | every part's look as an object, keyed `panel`, `arcmenu`, `quicksettings`, `calendar`, `overview`, `windows`, `terminal`. Each holds the colours `window`, `chrome`, `view`, `popover`, `dialog`, `osd`, `tint` (the tint colour, alpha 0) and the numbers `frost`, `radius`, `blur`, `lens_width`, `lens_bend`, `bleed`, `glare` |
| `bleed` | how much the colours of icons and text light up the glass around them, 0..1 (0 with reduced transparency) |
| `blur_radius`, `blur_brightness` | the blur behind glass |
| `lens_width`, `lens_bend`, `dispersion`, `vibrancy`, `glare` | the glass lens: rounded-edge width and slab thickness in px, rainbow edge 0..1, colour boost (1 = none), rim highlight 0..1 |
| `glass_panel_edges`, `glass_menu_edges` | true when the Liquid Glass extension draws the panel's or the menus' edges, so a theme should leave them without a border line |
| `terminal_opacity` | terminal background opacity |
| `panel_floating`, `panel_margin` | panel style |
| `blur_app_windows` | whether app windows get blur behind them |

## Drawing glass with the tokens

A glass surface is: fill `chrome` (or `window`/`view` for content), a 1 px `edge` border, a 1 px
`highlight` line along the top inside edge, `radius` corners and a soft `shadow`. Put text on `view`
or on `card`-over-`window` for the best readability.
