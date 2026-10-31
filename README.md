<h1 align="center">
  <img src="data/icons/io.github.djshiye.LiquidGlass.svg" width="96" alt=""><br>
  Liquid Glass for Fedora
</h1>

<p align="center">A glass look for the whole Fedora GNOME desktop, with an app to tune it from liquid to frosted.</p>

<p align="center"><img src="docs/screenshots/glass-desktop.jpg" width="860" alt="Glass panel and ArcMenu: the rounded edge bends the stripes behind it and catches the light"></p>

Made for **Fedora 44 with GNOME 50**. It draws its own glass, so you don't need Blur my Shell.

## Install

```sh
sudo dnf install https://github.com/djshiye/fedora-liquid-glass/releases/latest/download/liquid-glass.noarch.rpm
```

1. Open **Liquid Glass** from the app grid.
2. Pick a look with the **Liquid ↔ Frosted** slider and press **Apply**.
3. Log out and back in once, so GNOME loads the glass. From then on, changes show up live.

To update, run the same command again. Signed updates through `sudo dnf upgrade`
([Fedora COPR](docs/COPR.md)) are coming soon.

## Undo or remove

- **Restore original** in the app puts your desktop back exactly as it was before the first Apply.
- To remove it completely, run these as your normal user:

  ```sh
  liquid-glass revert
  sudo dnf remove liquid-glass
  ```

## Blur my Shell

You can uninstall it. Liquid Glass covers what Blur my Shell did (the panel, menus, overview and app
windows) with its own extension. If Blur my Shell is still installed, Liquid Glass turns off the
parts that would blur the same things twice, and **Restore original** turns them back on.

```sh
gnome-extensions uninstall blur-my-shell@aunetx   # or: sudo dnf remove gnome-shell-extension-blur-my-shell
```

## Straight to the desktop

GNOME logs in to your desktop instead of the Activities overview (**Start on the desktop**, on by
default). **Turn off the overview** goes further: the hot corner, the Super key and the three-finger
swipe stop opening Activities, and you start apps from ArcMenu or Dash to Panel. Without ArcMenu the
app grid still opens, so there is always a way to start an app. If Dash to Panel or Just Perfection
is installed, their own start-up option is set to match, and turning ours off puts theirs back.

## What it themes

GNOME Shell, Dash to Panel, ArcMenu, GTK 4 and libadwaita apps (Nautilus included), GTK 3 apps,
Flatpak apps, Ptyxis and GNOME Terminal, Qt apps (through Kvantum), btop, micro, Discord (Vencord),
VS Code, Obsidian, qBittorrent, Prism Launcher, Brave, Helium, Clipperino, RGBeast and Wheelguard.
The app's **Apps** page lists every part, shows which you have installed, and has a switch for each.

<p align="center"><img src="docs/screenshots/app-look-dark.jpg" width="860" alt="The Liquid Glass app: live preview and the Liquid to Frosted slider"></p>

## How the glass works

Each panel and menu sits on a live, blurred copy of what's behind it, seen through a slab of glass
with a rounded edge. The shader follows real optics:

- **Refraction:** light bends where it enters the curved edge (Snell's law), so the rim magnifies
  what's behind it while the flat middle stays true.
- **Dispersion:** each colour bends slightly differently, so the edge splits light into a faint
  rainbow.
- **Reflection:** the glass reflects about 4% of light head-on and almost all of it at grazing
  angles (Fresnel). The edge mirrors what really lies beyond it, the wallpaper and your windows, so
  it changes as they move. No outline or glow is drawn on.
- **Colour bleed:** coloured icons light up the glass around them, and their light comes out again
  at the nearest edge, so a blue icon tints the glass near it. White and grey text cast nothing, so
  the glass never turns milky.
- **Light that follows you:** the edge light turns towards the pointer when it comes near, and
  menus settle with a small spring as they open. Both stop when you stop, so idle glass costs
  nothing, and **Reduce animation** turns both off.
- **Absorption:** light slanting through the edge crosses more glass, so the edge is a shade darker
  and greener (Beer-Lambert).

The edge shape builds on Kyant's [AndroidLiquidGlass](https://github.com/Kyant0/AndroidLiquidGlass).

## Safe by design

- It runs as you: no root, no network access, and it changes only your own settings.
- Every file and setting is backed up before its first change. **Show changes** lists everything
  before **Apply** touches it.

## Command line

```sh
liquid-glass                     # open the app
liquid-glass apply --frost 0.3   # 0 = liquid, 1 = frosted
liquid-glass status              # which parts are available
liquid-glass revert              # restore the original look
```

## From source

```sh
git clone https://github.com/djshiye/fedora-liquid-glass && cd fedora-liquid-glass
./install.sh      # installs to your home folder; ./uninstall.sh removes it
```

App developers can match the desktop's colours with [docs/TOKENS.md](docs/TOKENS.md).

## License

[MIT](LICENSE). The edge shape from AndroidLiquidGlass is Apache 2.0, see
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
