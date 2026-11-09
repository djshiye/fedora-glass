#!/bin/bash
# A stock GNOME desktop (run.sh --stock-desktop): GNOME as GNOME ships it, the way a new
# Fedora Workstation user has it. The top bar, Activities, the overview with its dash and
# app grid, Adwaita, one screen at 100 %, and no extensions at all, or only the ones in
# LGQA_STOCK_EXTS (for example Dash to Dock, to check Fedora Glass beside a dock).
# Fedora Glass is not applied here: checks/stock_checks.py takes pictures of the stock
# desktop first, then Applies from the running desktop and logs in again. It asks for the
# new login by creating /out/relogin; this script then stops GNOME Shell and starts it again.
set -u
export HOME=/home/dino USER=dino XDG_RUNTIME_DIR=/run/user/1000 XDG_SESSION_TYPE=wayland
export XDG_CURRENT_DESKTOP=GNOME XDG_SESSION_DESKTOP=gnome
export LIBGL_ALWAYS_SOFTWARE=1 PYTHONDONTWRITEBYTECODE=1 NO_AT_BRIDGE=1
export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
dbus-daemon --session --address="$DBUS_SESSION_BUS_ADDRESS" --fork
OUT=/out; mkdir -p "$OUT"

for d in Desktop Documents Downloads Music Pictures Videos; do mkdir -p "$HOME/$d"; done
mkdir -p "$HOME/.config/liquid-glass"
cp -r /src "$HOME/fedora-glass-src"      # the version under test (read-only mount)

# Only what a container needs (no screen lock timer, no welcome tour). Everything else
# stays at GNOME's defaults: the overview opens at login, the hot corner works.
gsettings set org.gnome.desktop.screensaver lock-enabled false
gsettings set org.gnome.desktop.session idle-delay 0
gsettings set org.gnome.desktop.notifications show-banners false
gsettings set org.gnome.shell welcome-dialog-last-shown-version '999'
gsettings set org.gnome.shell favorite-apps "['org.gnome.Nautilus.desktop', 'org.gnome.Ptyxis.desktop', 'org.gnome.gedit.desktop']"
# A wallpaper with colour and detail, so the glass has something to show.
[ -f /opt/lgqa/wallpaper.png ] && gsettings set org.gnome.desktop.background picture-uri "file:///opt/lgqa/wallpaper.png" \
    && gsettings set org.gnome.desktop.background picture-uri-dark "file:///opt/lgqa/wallpaper.png"
EXTS=""
mkdir -p "$HOME/.local/share/gnome-shell/extensions"
for u in ${LGQA_STOCK_EXTS:-}; do
    # Extensions the image put together (Dash to Panel, ArcMenu, Dash to Dock, ...) install
    # per user, as from extensions.gnome.org.
    [ -d "/opt/lgqa/ext/$u" ] && cp -r "/opt/lgqa/ext/$u" "$HOME/.local/share/gnome-shell/extensions/"
    EXTS="$EXTS${EXTS:+, }'$u'"
done
gsettings set org.gnome.shell enabled-extensions "[$EXTS]"
# The software renderer always runs late, which the automatic quality would answer by
# stepping the glass down: pin full quality, as the Dino desktop does.
echo '{"glass_quality": "full"}' > "$HOME/.config/liquid-glass/settings.json"

SCREEN=${LGQA_SCREEN:-2000x1125}
export WAYLAND_DISPLAY=wayland-0
start_shell() {
    gnome-shell --headless --virtual-monitor "$SCREEN" --unsafe-mode --wayland >> "$OUT/shell.log" 2>&1 &
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
        rm -f "$XDG_RUNTIME_DIR"/wayland-0 "$XDG_RUNTIME_DIR"/wayland-0.lock "$OUT/relogin" "$OUT/relogged-in"
        start_shell
        (cd "$HOME/fedora-glass-src" && exec python3 -m fedoraglass watch) >> "$OUT/watch.txt" 2>&1 &
        WATCH_PID=$!
        touch "$OUT/relogged-in"
    fi
    sleep 1
done
