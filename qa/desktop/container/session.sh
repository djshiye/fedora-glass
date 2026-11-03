#!/bin/bash
# Dino's desktop, as close as a container gets: GNOME 50 on Wayland on two screens, Orchis Dark
# with ~/.config/gtk-4.0 linked into it, Dino's extensions in Dino's order with Dino's panel
# and menu settings, the overview turned off, 125 % scaling, then Liquid Glass applied the
# way an update does it (Apply, then a fresh login).
set -u
export HOME=/home/dino USER=dino XDG_RUNTIME_DIR=/run/user/1000 XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=GNOME
export LIBGL_ALWAYS_SOFTWARE=1 PYTHONDONTWRITEBYTECODE=1 NO_AT_BRIDGE=1
export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
dbus-daemon --session --address="$DBUS_SESSION_BUS_ADDRESS" --fork
OUT=/out; mkdir -p "$OUT"

# Home folder
for d in Desktop Documents Downloads Music Pictures Projects Videos; do mkdir -p "$HOME/$d"; done
EXT=$HOME/.local/share/gnome-shell/extensions; mkdir -p "$EXT" "$HOME/.themes" "$HOME/.config/liquid-glass"
cp -r /opt/lgqa/ext/. "$EXT"/
cp -a /opt/lgqa/themes/Orchis-Dark "$HOME/.themes/"
ln -sfn "$HOME/.themes/Orchis-Dark/gtk-4.0" "$HOME/.config/gtk-4.0"
cp -r /src "$HOME/liquid-glass-src"      # the version under test (read-only mount)

# GNOME settings
gsettings set org.gnome.desktop.interface color-scheme prefer-dark
gsettings set org.gnome.desktop.interface gtk-theme Orchis-Dark
gsettings set org.gnome.desktop.interface clock-format 24h
gsettings set org.gnome.desktop.interface cursor-blink false
gsettings set org.gnome.desktop.background picture-uri "file:///opt/lgqa/wallpaper.png"
gsettings set org.gnome.desktop.background picture-uri-dark "file:///opt/lgqa/wallpaper.png"
gsettings set org.gnome.desktop.notifications show-banners false
gsettings set org.gnome.desktop.screensaver lock-enabled true
gsettings set org.gnome.desktop.session idle-delay 0
gsettings set org.gnome.mutter experimental-features "['scale-monitor-framebuffer']"
gsettings set org.gnome.shell disable-user-extensions false
gsettings set org.gnome.shell welcome-dialog-last-shown-version '999'
gsettings set org.gnome.shell favorite-apps "['org.gnome.Nautilus.desktop','org.gnome.Ptyxis.desktop']"
# Dino's order (from their PC), Liquid Glass last as an update leaves it.
gsettings set org.gnome.shell enabled-extensions "['extension-list@tu.berry', 'arcmenu@arcmenu.com', 'dash-to-panel@jderose9.github.com', 'appindicatorsupport@rgcjonas.gmail.com', 'blur-my-shell@aunetx', 'just-perfection-desktop@just-perfection', 'deja-window@mcast.gnomext.com']"
dconf load /org/gnome/shell/extensions/ < /opt/lgqa/suite/dino-settings.ini

# Liquid Glass: Dino's choices (start on the desktop, no overview), then Apply.
echo '{"overview_off": true, "start_on_desktop": true}' > "$HOME/.config/liquid-glass/settings.json"
(cd "$HOME/liquid-glass-src" && python3 -m liquidglass apply) > "$OUT/apply.txt" 2>&1
echo "apply exit $?" >> "$OUT/apply.txt"

# The fresh login: GNOME Shell, then the Liquid Glass login helper (finishes held parts).
gnome-shell --headless --virtual-monitor 2000x1125 --virtual-monitor 2000x1125 --unsafe-mode --wayland > "$OUT/shell.log" 2>&1 &
export WAYLAND_DISPLAY=wayland-0
for _ in $(seq 90); do
    gdbus call --session -d org.gnome.Shell -o /org/gnome/Shell -m org.gnome.Shell.Eval 'Main.layoutManager._startingUp ? 0 : 1' 2>/dev/null | grep -q "'1'" && break
    sleep 1
done
(cd "$HOME/liquid-glass-src" && exec python3 -m liquidglass watch) > "$OUT/watch.txt" 2>&1 &
python3 /opt/lgqa/suite/checks/scale.py "${LGQA_SCALE:-1.25}" > "$OUT/scale.txt" 2>&1
echo READY
sleep infinity
