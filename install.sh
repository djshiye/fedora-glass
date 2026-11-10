#!/usr/bin/env bash
# Install Fedora Glass for the current user (no root needed, except to add
# missing system packages (dnf, apt or pacman), which it asks about first).
#
#   ./install.sh            install, then open the customizer
#   ./install.sh --no-gui   install only
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
data="${XDG_DATA_HOME:-$HOME/.local/share}"
config="${XDG_CONFIG_HOME:-$HOME/.config}"
prefix="$data/liquid-glass"
bin="$HOME/.local/bin"
open_gui=1
[[ "${1:-}" == "--no-gui" ]] && open_gui=0

say() { printf '\033[1m%s\033[0m\n' "$*"; }

if [[ $EUID -eq 0 ]]; then
  echo "Run this as your normal user, not root. It installs into your home folder." >&2
  exit 1
fi
# Paths end up in a launcher, a .desktop file and a systemd unit: keep them plain.
case "$prefix$bin" in
  *[!A-Za-z0-9._/@+-]*) echo "Your home or data folder path has spaces or special characters ($prefix). Please install manually." >&2; exit 1;;
esac
# ---- system packages ------------------------------------------------------------
# PySide6: the customizer app. adw-gtk3: GTK 3 apps. Kvantum: Qt apps. User Themes: lets
# GNOME Shell load the theme. Named differently on each Linux.
missing=()
if command -v dnf >/dev/null && command -v rpm >/dev/null; then
  pm="sudo dnf install -y"
  want=(python3-gobject python3-pyside6 adw-gtk3-theme kvantum gnome-shell-extension-user-theme)
  for p in "${want[@]}"; do rpm -q "$p" >/dev/null 2>&1 || missing+=("$p"); done
elif command -v apt-get >/dev/null && command -v dpkg-query >/dev/null; then
  pm="sudo apt-get install -y"
  want=(python3-gi gir1.2-glib-2.0 python3-pyside6.qtquick python3-pyside6.qtquickcontrols2 qml6-module-qtquick-controls
        qml6-module-qtquick-effects qml6-module-qtquick-shapes qml6-module-qtquick-window qt6-style-kvantum
        gnome-shell-extension-user-theme)
  for p in "${want[@]}"; do dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q 'ok installed' || missing+=("$p"); done
elif command -v pacman >/dev/null; then
  pm="sudo pacman -S --needed --noconfirm"
  want=(python-gobject pyside6 qt6-declarative adw-gtk-theme kvantum gnome-shell-extensions)
  for p in "${want[@]}"; do pacman -Q "$p" >/dev/null 2>&1 || missing+=("$p"); done
else
  echo "Note: Fedora Glass is made for Fedora, Ubuntu and Arch. Continuing anyway."
fi
if ((${#missing[@]})); then
  say "These packages are missing: ${missing[*]}"
  read -r -p "Install them now with ${pm%% -*}? [Y/n] " ans || ans=n   # no terminal: don't install
  if [[ -z "$ans" || "$ans" =~ ^[Yy] ]]; then
    $pm "${missing[@]}"
  else
    echo "Skipped. The parts that need them will show as unavailable in the app."
  fi
fi

# ---- the app ------------------------------------------------------------------
say "Installing Fedora Glass to $prefix"
rm -rf "$prefix/fedoraglass.new"
mkdir -p "$prefix" "$bin"
cp -r "$here/fedoraglass" "$prefix/fedoraglass.new"
find "$prefix/fedoraglass.new" -name '__pycache__' -prune -exec rm -rf {} +
rm -rf "$prefix/fedoraglass"
mv "$prefix/fedoraglass.new" "$prefix/fedoraglass"
rm -rf "$prefix/liquidglass"      # the code folder's name up to 1.5.10

cat > "$bin/fedora-glass" <<EOF
#!/bin/sh
# Fedora Glass launcher. -I keeps Python from importing anything from the
# current folder or PYTHONPATH.
exec /usr/bin/python3 -I -c 'import sys; sys.path.insert(0, "$prefix"); from fedoraglass.__main__ import main; sys.exit(main())' "\$@"
EOF
chmod 755 "$bin/fedora-glass"
# The old command name (Liquid Glass) keeps working.
ln -sfn fedora-glass "$bin/liquid-glass"

install -Dm644 "$here/data/io.github.djshiye.LiquidGlass.desktop" "$data/applications/io.github.djshiye.LiquidGlass.desktop"
sed -i "s|^Exec=.*|Exec=\"$bin/fedora-glass\"|" "$data/applications/io.github.djshiye.LiquidGlass.desktop"
install -Dm644 "$here/data/icons/io.github.djshiye.LiquidGlass.svg" "$data/icons/hicolor/scalable/apps/io.github.djshiye.LiquidGlass.svg"
gtk-update-icon-cache -q "$data/icons/hicolor" 2>/dev/null || true
update-desktop-database -q "$data/applications" 2>/dev/null || true

# The mouse pointer styles, checked against their checksums (see packaging/cursors/build.py).
python3 -I "$here/packaging/cursors/unpack.py" "$here" "$data/icons"

# ---- follow dark/light switches ---------------------------------------------------
# A tiny user service re-applies the parts that can't switch by themselves
# (Shell theme, GTK 3, terminal, Qt) when you flip Dark Style.
mkdir -p "$config/systemd/user"
cat > "$config/systemd/user/liquid-glass-watch.service" <<EOF
[Unit]
Description=Fedora Glass: follow GNOME dark and light style
PartOf=graphical-session.target
After=graphical-session.target

[Service]
ExecStart="$bin/fedora-glass" watch
Restart=on-failure
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=graphical-session.target
EOF
systemctl --user daemon-reload 2>/dev/null || true
systemctl --user enable liquid-glass-watch.service 2>/dev/null || true
# restart, not just start: after an upgrade the old watcher would keep running the old code
systemctl --user restart liquid-glass-watch.service 2>/dev/null || true

say "Done. Open Fedora Glass from the app grid, or run: fedora-glass"
case ":$PATH:" in *":$bin:"*) ;; *) echo "(Add $bin to your PATH to use the fedora-glass command.)";; esac
if ((open_gui)) && [[ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ]]; then
  nohup "$bin/fedora-glass" >/dev/null 2>&1 &
fi
