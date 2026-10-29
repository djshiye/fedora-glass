<h1 align="center">
  <img src="data/icons/io.github.djshiye.LiquidGlass.svg" width="96" alt=""><br>
  Liquid Glass for Fedora
</h1>

<p align="center">A glass theme for the whole Fedora GNOME desktop, with an app to tune it from liquid to frosted.</p>

<p align="center"><img src="docs/screenshots/desktop-liquid-dark.jpg" width="860" alt="GNOME desktop with Liquid Glass: Files, Text Editor, ArcMenu and Dash to Panel"></p>

Liquid Glass makes GNOME Shell, Dash to Panel, ArcMenu, GTK 4 and libadwaita apps, GTK 3 apps,
Nautilus, Ptyxis, Qt apps and a long list of everyday apps look like layered glass: translucent
surfaces with real blur and refraction behind them, a bright rim of light along the top edge, and
rounded, calm controls. One slider takes everything from clear **liquid** glass to milky **frosted**
glass, and every change can be undone with one click.

Made for **Fedora 44 Workstation with GNOME 50**.

## The app

<p align="center"><img src="docs/screenshots/app-look-dark.jpg" width="860" alt="The Liquid Glass app: live preview and the Liquid to Frosted slider"></p>

- **Live preview** of your own desktop (your wallpaper, panel, menu and windows) that follows every
  change as you drag.
- **Liquid ↔ Frosted** slider, plus presets: Liquid, Clear, Balanced, Frosted, Solid.
- Accent colour (follows GNOME's by default), glass tint, corner roundness, rim light, a floating or
  docked panel, blur behind app windows, terminal opacity and a Reduce transparency switch.
- **Apps** page: every part of the desktop it can theme, whether it's installed, and a switch for each.
- **Show changes** lists every file and setting Apply will touch, before it touches anything.
- **Restore original** puts your desktop back exactly as it was before the first Apply.

<p align="center">
  <img src="docs/screenshots/app-apps-dark.jpg" width="420" alt="Apps page">
  <img src="docs/screenshots/app-look-light.jpg" width="420" alt="The app in light style">
</p>

## Install

```sh
git clone https://github.com/djshiye/fedora-liquid-glass
cd fedora-liquid-glass
./install.sh
```

The installer works in your home folder and needs no root, except to add missing Fedora packages,
which it lists and asks about first: `python3-pyside6` (the app), `adw-gtk3-theme` (GTK 3 apps),
`kvantum` (Qt apps) and `gnome-shell-extension-user-theme` (the Shell theme). Then open **Liquid
Glass** from the app grid, pick a look and press **Apply**.

Blur and refraction behind the Shell come from the
[Blur my Shell](https://github.com/aunetx/blur-my-shell) extension; with a version that has its
Liquid Glass (refraction) effect you get real refraction, otherwise a plain blur.

**Update:** `git pull && ./install.sh`. **Uninstall:** `./uninstall.sh` (restores your original look first).

## What it themes

| Part | How |
|---|---|
| GNOME Shell | A Shell theme: menus, quick settings, calendar, notifications, dialogs, OSD, overview |
| Blur my Shell | Liquid Glass pipelines behind the panel, menus, overview and app windows; your own pipelines are kept |
| Dash to Panel | Glass panel, floating or docked, hover and running-app dots. Your layout is untouched |
| ArcMenu | Glass menu, menu button and search pill |
| GTK 4 and libadwaita | Every GTK 4 app, Nautilus included. Switches dark/light live with the system |
| GTK 3 | On top of adw-gtk3 (Lutris, LibreOffice and other older apps) |
| Flatpak apps | Lets sandboxed GTK apps read the theme |
| Ptyxis, GNOME Terminal | Glass palette and window opacity on every profile |
| btop, micro | Matching colour themes with a see-through background |
| Qt apps | A Kvantum theme built from your settings (qBittorrent, btrfs-assistant, ProtonUp-Qt...) |
| Discord (Vencord), VS Code, Obsidian, qBittorrent, Prism Launcher | Their own theme formats, installed and selected |
| Brave, Helium | A Chromium theme extension, loaded once by hand |
| Clipperino, RGBeast, Wheelguard | Clipperino and RGBeast through GTK 4; Wheelguard reads the Liquid Glass colours itself |

Some apps can't be themed and the app says so plainly: Steam, Zoom and Claude Desktop draw their own
UI, and Slack only takes a pasted colour string (the app shows it, ready to copy).

<p align="center">
  <img src="docs/screenshots/desktop-frosted-dark.jpg" width="420" alt="Frosted">
  <img src="docs/screenshots/desktop-light.jpg" width="420" alt="Light style">
</p>
<p align="center">
  <img src="docs/screenshots/ptyxis.jpg" width="420" alt="Ptyxis">
  <img src="docs/screenshots/qt-apps.jpg" width="420" alt="Qt apps with Kvantum">
</p>

## Safe by design

- Everything runs as you. No root, no `sudo` from the app, no network access.
- Before the first change to any file or setting, the original is saved in
  `~/.local/state/liquid-glass/backup`. Turning a part off restores just that part; **Restore
  original** restores everything. Shared lists (enabled extensions, Flatpak permissions) are undone
  item by item, so changes you made since are kept.
- It never writes through symbolic links into other themes, and Flatpak apps only get read-only
  access to the theme files.
- Text stays readable: content areas are always more solid than chrome, and the colours are tested
  for 4.5:1 contrast at every slider position.

## Command line

```sh
liquid-glass                       # open the app
liquid-glass apply --frost 0.3     # 0 = liquid, 1 = frosted
liquid-glass apply --preset Frosted
liquid-glass plan                  # what apply would change
liquid-glass status                # which parts are available
liquid-glass revert                # restore the original look
```

A small user service (`liquid-glass-watch`) re-applies the parts that can't follow the system
dark/light switch by themselves (Shell theme, GTK 3, terminals, Qt) when you flip Dark Style.

## For app developers

Liquid Glass writes its colours to `~/.config/liquid-glass/tokens*.json` on every Apply, so an app
that draws its own UI can match the desktop. See [docs/TOKENS.md](docs/TOKENS.md).

## Development

```sh
python3 -m pytest -q          # tests
python3 -m liquidglass gui    # run the app from the source tree
```

## License

[MIT](LICENSE)
