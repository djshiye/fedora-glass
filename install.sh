#!/usr/bin/env bash
# Install Liquid Glass for the current user (no root needed, except to add
# missing Fedora packages, which it asks about first).
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
if ! grep -q '^ID=fedora' /etc/os-release 2>/dev/null; then
  echo "Note: Liquid Glass is made for Fedora. Continuing anyway."
fi

# ---- Fedora packages ----------------------------------------------------------
# python3-pyside6: the customizer app. adw-gtk3-theme: GTK 3 apps.
# kvantum: Qt apps. user-theme: lets GNOME Shell load the theme.
want=(python3-gobject python3-pyside6 adw-gtk3-theme kvantum gnome-shell-extension-user-theme)
missing=()
for p in "${want[@]}"; do rpm -q "$p" >/dev/null 2>&1 || missing+=("$p"); done
if ((${#missing[@]})) && command -v dnf >/dev/null; then
  say "These Fedora packages are missing: ${missing[*]}"
  read -r -p "Install them now with sudo dnf? [Y/n] " ans || ans=n   # no terminal: don't install
  if [[ -z "$ans" || "$ans" =~ ^[Yy] ]]; then
    sudo dnf install -y "${missing[@]}"
  else
    echo "Skipped. The parts that need them will show as unavailable in the app."
  fi
fi

# ---- the app ------------------------------------------------------------------
say "Installing Liquid Glass to $prefix"
rm -rf "$prefix/liquidglass.new"
mkdir -p "$prefix" "$bin"
cp -r "$here/liquidglass" "$prefix/liquidglass.new"
find "$prefix/liquidglass.new" -name '__pycache__' -prune -exec rm -rf {} +
rm -rf "$prefix/liquidglass"
mv "$prefix/liquidglass.new" "$prefix/liquidglass"

cat > "$bin/liquid-glass" <<EOF
#!/bin/sh
# Liquid Glass launcher. -I keeps Python from importing anything from the
# current folder or PYTHONPATH.
exec /usr/bin/python3 -I -c 'import sys; sys.path.insert(0, "$prefix"); from liquidglass.__main__ import main; sys.exit(main())' "\$@"
EOF
chmod 755 "$bin/liquid-glass"

install -Dm644 "$here/data/io.github.djshiye.LiquidGlass.desktop" "$data/applications/io.github.djshiye.LiquidGlass.desktop"
sed -i "s|^Exec=.*|Exec=\"$bin/liquid-glass\"|" "$data/applications/io.github.djshiye.LiquidGlass.desktop"
install -Dm644 "$here/data/icons/io.github.djshiye.LiquidGlass.svg" "$data/icons/hicolor/scalable/apps/io.github.djshiye.LiquidGlass.svg"
gtk-update-icon-cache -q "$data/icons/hicolor" 2>/dev/null || true
update-desktop-database -q "$data/applications" 2>/dev/null || true

# ---- follow dark/light switches ---------------------------------------------------
# A tiny user service re-applies the parts that can't switch by themselves
# (Shell theme, GTK 3, terminal, Qt) when you flip Dark Style.
mkdir -p "$config/systemd/user"
cat > "$config/systemd/user/liquid-glass-watch.service" <<EOF
[Unit]
Description=Liquid Glass: follow GNOME dark and light style
PartOf=graphical-session.target
After=graphical-session.target

[Service]
ExecStart="$bin/liquid-glass" watch
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

say "Done. Open Liquid Glass from the app grid, or run: liquid-glass"
case ":$PATH:" in *":$bin:"*) ;; *) echo "(Add $bin to your PATH to use the liquid-glass command.)";; esac
if ((open_gui)) && [[ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ]]; then
  nohup "$bin/liquid-glass" >/dev/null 2>&1 &
fi
