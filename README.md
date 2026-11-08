<h1 align="center">
  <img src="data/icons/io.github.djshiye.LiquidGlass.svg" width="96" alt=""><br>
  Fedora Glass
</h1>

<p align="center">A glass look for the whole Fedora GNOME desktop, with an app to tune it from liquid to frosted.</p>

<p align="center"><img src="docs/screenshots/glass-desktop.jpg" width="860" alt="Fedora Glass on a GNOME desktop: glass panel, ArcMenu and app windows"></p>

Made for **Fedora 44 with GNOME 50**, and ready for GNOME 51 (Fedora 45).

## Install

```sh
sudo dnf install https://github.com/djshiye/fedora-glass/releases/latest/download/fedora-glass.noarch.rpm
```

1. Open **Fedora Glass** from the app grid.
2. Pick a look with the **Liquid ↔ Frosted** slider and press **Apply**.
3. Restart your PC once, so GNOME loads the glass.

Updates come with the rest of your system through `sudo dnf upgrade`: the package adds its own dnf
repository, built by this project's GitHub Actions from each release and served from GitHub Pages.
The packages are not GPG-signed.

## Works with

Fedora Glass is made to work with **Dash to Panel** and **ArcMenu** (or Spawn), and themes them to
match. It draws its own glass, so if you use **Blur my Shell** you can simply remove it. While it is
still installed, Fedora Glass switches off the parts that would blur the same things twice.

It also themes GTK 3, GTK 4 and libadwaita apps (Files included), Flatpak apps, Ptyxis and GNOME
Terminal, Qt apps (through Kvantum), the lock screen and, if you opt in, the login screen. The app's
**Apps** page lists every part, shows which ones you have, and has a switch for each.

<p align="center"><img src="docs/screenshots/app.png" width="860" alt="The Fedora Glass app: live preview and the Liquid to Frosted slider"></p>

## Undo or remove

- **Restore original** in the app puts your desktop back exactly as it was before the first Apply.
- **Remove Fedora Glass…** (at the bottom of the Look page), or `sudo dnf remove fedora-glass`,
  restores your original look and then removes the app.

## How the glass works

Each panel and menu sits on a live, blurred copy of what's behind it, seen through a slab of glass
with a rounded edge. The shader follows real optics: light bends at the curved edge (refraction),
splits into a faint rainbow (dispersion), reflects more at grazing angles (Fresnel), and picks up
colour from the icons beneath it. Idle glass costs nothing, and **Reduce animation** turns the
motion off.

The edge shape builds on Kyant's [AndroidLiquidGlass](https://github.com/Kyant0/AndroidLiquidGlass).

## Safe by design

- It runs as you, with no network access, and changes only your own settings. The one exception is
  the opt-in login screen glass, which asks for your password and changes only the login screen's
  part of GNOME Shell's theme.
- Every file and setting is backed up before its first change, and **Show changes** lists
  everything before **Apply** touches it.

## Command line

```sh
fedora-glass                     # open the app
fedora-glass apply --frost 0.3   # 0 = liquid, 1 = frosted
fedora-glass status              # which parts are available
fedora-glass revert              # restore the original look
```

## From source

```sh
git clone https://github.com/djshiye/fedora-glass && cd fedora-glass
./install.sh      # installs to your home folder; ./uninstall.sh removes it
```

App developers can match the desktop's colours with [docs/TOKENS.md](docs/TOKENS.md).

## License

[MIT](LICENSE). The edge shape from AndroidLiquidGlass is Apache 2.0, see
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
