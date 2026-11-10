#!/bin/bash
# Uses the app the way an installed package is used, in a throwaway home folder: Apply
# must give the glass look, Restore must bring the user's own file back byte for byte,
# and the window must open. Run by the package jobs (packages.yml) after the install,
# so a missing dependency or a file the package forgot shows up before a release.
#   sh qa/package-smoke.sh [command]     (default: the installed fedora-glass)
set -euo pipefail
app="${1:-fedora-glass}"
home="$(mktemp -d)"
trap 'rm -rf "$home"' EXIT
export HOME="$home" QT_QPA_PLATFORM=offscreen
unset XDG_CONFIG_HOME XDG_DATA_HOME XDG_STATE_HOME XDG_CACHE_HOME
mkdir -p "$home/.config/gtk-4.0"
printf '/* my own look */\n' > "$home/.config/gtk-4.0/gtk.css"

# gsettings wants a session bus; a bare container has none.
run() { if command -v dbus-run-session >/dev/null; then dbus-run-session -- "$@"; else "$@"; fi; }

run $app status >/dev/null
run $app apply >/dev/null
grep -q 'Fedora Glass' "$home/.config/gtk-4.0/gtk.css" || { echo "Apply did not write the GTK 4 look"; exit 1; }
run $app revert >/dev/null
[ "$(cat "$home/.config/gtk-4.0/gtk.css")" = '/* my own look */' ] || { echo "Restore did not bring the original file back"; exit 1; }
[ -z "$(find "$home/.local/state/liquid-glass/backup/files" -type f 2>/dev/null)" ] || { echo "Restore left stored originals behind"; exit 1; }

# The window opens and draws (offscreen): the Qt parts the package depends on are all there.
run $app gui --screenshot "$home/window.png" >/dev/null
[ -s "$home/window.png" ] || { echo "The window did not open"; exit 1; }
echo "package smoke check passed"
