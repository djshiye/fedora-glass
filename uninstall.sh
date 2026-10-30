#!/usr/bin/env bash
# Restore your original look and remove Liquid Glass.
set -euo pipefail

data="${XDG_DATA_HOME:-$HOME/.local/share}"
config="${XDG_CONFIG_HOME:-$HOME/.config}"
state="${XDG_STATE_HOME:-$HOME/.local/state}"
bin="$HOME/.local/bin"

# Stop the dark/light watcher first so it can't re-apply anything mid-way.
systemctl --user disable --now liquid-glass-watch.service 2>/dev/null || true

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
lg=()
if [[ -x "$bin/liquid-glass" ]]; then
  lg=("$bin/liquid-glass")
elif [[ -d "$here/liquidglass" ]]; then
  # launcher gone: run the copy next to this script, so the backup is still restored
  lg=(/usr/bin/python3 -I -c 'import sys; sys.path.insert(0, sys.argv.pop(1)); from liquidglass.__main__ import main; sys.exit(main())' "$here")
fi
if ((${#lg[@]})); then
  echo "Restoring your original settings and files..."
  if ! "${lg[@]}" revert; then
    echo "Some items could not be restored (see above). Liquid Glass is left installed so you can retry:"
    echo "  liquid-glass revert && ./uninstall.sh"
    exit 1
  fi
elif [[ -f "$state/liquid-glass/backup/manifest.json" ]]; then
  # never delete the only record of your original look
  echo "Cannot run Liquid Glass to restore your original look; the backup in $state/liquid-glass is kept." >&2
  exit 1
fi

rm -f "$config/systemd/user/liquid-glass-watch.service"
systemctl --user daemon-reload 2>/dev/null || true

rmdir "$data/gnome-shell/extensions/liquid-glass@djshiye.github.io" 2>/dev/null || true
rm -rf "$data/liquid-glass" "$data/themes/LiquidGlass" "$state/liquid-glass"
rm -f "$bin/liquid-glass" \
      "$data/applications/io.github.djshiye.LiquidGlass.desktop" \
      "$data/icons/hicolor/scalable/apps/io.github.djshiye.LiquidGlass.svg"

read -r -p "Also delete your Liquid Glass settings ($config/liquid-glass)? [y/N] " ans || ans=n
[[ "$ans" =~ ^[Yy] ]] && rm -rf "$config/liquid-glass"
echo "Liquid Glass is removed. Log out and back in to clear it from GNOME Shell completely."
