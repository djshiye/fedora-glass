#!/bin/bash
# A stock Ubuntu desktop (run.sh --ubuntu-desktop): the Ubuntu session as Ubuntu ships it,
# with Ubuntu Dock, Desktop Icons, AppIndicator, Tiling Assistant and Yaru, Ubuntu's default
# settings, one screen at 100 %, and nobody's own extensions or theme. Fedora Glass is not
# applied here: the Ubuntu checks (checks/ubuntu_checks.py) take a picture of the stock
# desktop first, then Apply from the running desktop and log in again, the way a new user
# does it. They ask for the new login by creating /out/relogin; this script then stops
# GNOME Shell and starts it again.
set -u
export HOME=/home/dino USER=dino XDG_RUNTIME_DIR=/run/user/1000 XDG_SESSION_TYPE=wayland
export XDG_CURRENT_DESKTOP=ubuntu:GNOME XDG_SESSION_DESKTOP=ubuntu GNOME_SHELL_SESSION_MODE=ubuntu
export LIBGL_ALWAYS_SOFTWARE=1 PYTHONDONTWRITEBYTECODE=1 NO_AT_BRIDGE=1
export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
dbus-daemon --session --address="$DBUS_SESSION_BUS_ADDRESS" --fork
OUT=/out; mkdir -p "$OUT"

for d in Desktop Documents Downloads Music Pictures Videos; do mkdir -p "$HOME/$d"; done
mkdir -p "$HOME/.config/liquid-glass"
cp -r /src "$HOME/fedora-glass-src"      # the version under test (read-only mount)

# Only what a container needs (no screen lock timer, no welcome tour). Everything else
# stays at Ubuntu's defaults.
gsettings set org.gnome.desktop.screensaver lock-enabled false
gsettings set org.gnome.desktop.session idle-delay 0
gsettings set org.gnome.desktop.notifications show-banners false
gsettings set org.gnome.shell welcome-dialog-last-shown-version '999'
# The software renderer always runs late, which the automatic quality would answer by
# stepping the glass down: pin full quality, as the Dino desktop does.
echo '{"glass_quality": "full"}' > "$HOME/.config/liquid-glass/settings.json"

SCREEN=${LGQA_SCREEN:-2000x1125}
export WAYLAND_DISPLAY=wayland-0
start_shell() {
    gnome-shell --headless --virtual-monitor "$SCREEN" --unsafe-mode --wayland --mode=ubuntu >> "$OUT/shell.log" 2>&1 &
    SHELL_PID=$!
    for _ in $(seq 90); do
        gdbus call --session -d org.gnome.Shell -o /org/gnome/Shell -m org.gnome.Shell.Eval 'Main.layoutManager._startingUp ? 0 : 1' 2>/dev/null | grep -q "'1'" && break
        sleep 1
    done
}
start_shell
echo READY
while true; do
    if [ -e "$OUT/relogin" ]; then
        # Log out and in again: GNOME Shell and the Fedora Glass login helper stop, then start.
        [ -n "${WATCH_PID:-}" ] && kill "$WATCH_PID" 2>/dev/null
        kill "$SHELL_PID" 2>/dev/null; wait "$SHELL_PID" 2>/dev/null
        rm -f "$XDG_RUNTIME_DIR"/wayland-0 "$XDG_RUNTIME_DIR"/wayland-0.lock "$OUT/relogin"
        start_shell
        (cd "$HOME/fedora-glass-src" && exec python3 -m fedoraglass watch) >> "$OUT/watch.txt" 2>&1 &
        WATCH_PID=$!
        touch "$OUT/relogged-in"
    fi
    sleep 1
done
