#!/bin/bash
# Uses the app the way an installed package is used, in a throwaway home folder: Apply
# must give the glass look, Restore must bring the user's own file back byte for byte,
# and the window must open. Run by the package jobs (packages.yml) after the install,
# so a missing dependency or a file the package forgot shows up before a release.
#   sh qa/package-smoke.sh [command]     (default: the installed fedora-glass)
#   bash qa/package-smoke.sh --removed   after the package was removed: nothing of the glass
#                                        login screen may be left on the system
set -euo pipefail

if [ "${1:-}" = --removed ]; then
    left=""
    for f in /usr/libexec/fedora-glass-login \
             /usr/share/gdm/greeter/gnome-shell/extensions/fedora-glass-login@djshiye.github.io \
             /usr/lib/systemd/system/fedora-glass-login-guard.service \
             /usr/lib/systemd/system/fedora-glass-login-guard-check.path \
             /usr/lib/systemd/system/fedora-glass-login-guard-check.service \
             /usr/lib/systemd/system/graphical.target.wants/fedora-glass-login-guard.service \
             /usr/lib/systemd/system/graphical.target.wants/fedora-glass-login-guard-check.path \
             /etc/dconf/db/fedora-glass-login /etc/fedora-glass /var/lib/fedora-glass \
             /etc/dconf/db/*.d/90-fedora-glass-login /etc/dconf/db/*.d/locks/90-fedora-glass-login; do
        # -L too: a link whose target is gone still counts.
        if [ -e "$f" ] || [ -L "$f" ]; then left="$left $f"; fi
    done
    if grep -qsx 'system-db:fedora-glass-login' /etc/dconf/profile/gdm; then left="$left /etc/dconf/profile/gdm(profile line)"; fi
    [ -z "$left" ] || { echo "the glass login screen left behind:$left"; exit 1; }
    echo "nothing of the glass login screen is left"
    exit 0
fi
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

# The glass login screen's files are all there with the right owner and mode.
# stat prints "owner mode"; the helper runs as root, so nobody else may own or write it.
mode_of() { stat -c '%U %a' "$1"; }
helper=/usr/libexec/fedora-glass-login
[ "$(mode_of $helper)" = "root 755" ] || { echo "$helper is not root-owned 0755"; exit 1; }
addon=/usr/share/gdm/greeter/gnome-shell/extensions/fedora-glass-login@djshiye.github.io
for f in metadata.json extension.js; do
    [ -f "$addon/$f" ] || { echo "login add-on file missing: $f"; exit 1; }
done
# Every shared module named in the list (the same list the package was built from).
shared_list=/usr/share/fedora-glass/fedoraglass/data/login-extension/shared-modules.txt
[ -f "$shared_list" ] || { echo "shared-modules.txt is not installed"; exit 1; }
n=0
for name in $(sed -e 's/#.*//' "$shared_list"); do
    [ -f "$addon/$name" ] || { echo "login add-on shared module missing: $name"; exit 1; }
    n=$((n + 1))
done
[ "$n" -gt 0 ] || { echo "shared-modules.txt lists nothing"; exit 1; }
[ ! -e "$addon/shared-modules.txt" ] || { echo "shared-modules.txt must not be in the login add-on"; exit 1; }
if [ -n "$(find "$addon" ! -user root -print -quit)" ]; then echo "login add-on is not all root-owned"; exit 1; fi
if [ -n "$(find "$addon" -perm /022 -print -quit)" ]; then echo "login add-on is writable by others"; exit 1; fi
units=/usr/lib/systemd/system
for u in fedora-glass-login-guard.service fedora-glass-login-guard-check.path fedora-glass-login-guard-check.service; do
    [ "$(mode_of $units/$u)" = "root 644" ] || { echo "$u is missing or not root-owned 0644"; exit 1; }
done
for u in fedora-glass-login-guard.service fedora-glass-login-guard-check.path; do
    [ "$(readlink $units/graphical.target.wants/$u)" = "../$u" ] || { echo "graphical.target.wants link missing: $u"; exit 1; }
done
# status works without root and without GDM (in a container "available" is false, that is
# fine); it must print one JSON object, and nothing is on, so the state is "off".
python3 -I -c 'import json, subprocess, sys
r = subprocess.run([sys.argv[1], "status"], capture_output=True, text=True, timeout=60)
assert r.returncode == 0, r.stderr
d = json.loads(r.stdout)
assert d.get("state") == "off", d
assert isinstance(d.get("available"), bool), d' "$helper" || { echo "fedora-glass-login status did not print valid JSON with state off"; exit 1; }

# The window opens and draws (offscreen): the Qt parts the package depends on are all there.
run $app gui --screenshot "$home/window.png" >/dev/null
[ -s "$home/window.png" ] || { echo "The window did not open"; exit 1; }
echo "package smoke check passed"
