#!/bin/bash
# The GDM login screen (run.sh --login-screen), as close as a container gets without GDM
# itself: GNOME Shell in its "gdm" session mode, run as a greeter user with the
# environment GDM gives its greeter (dconf profile "gdm", GDM's greeter data folder first,
# a state folder per seat), and a user "Dino" with a password in the user list. GNOME's
# own test switch GDM_GREETER_TEST=1 lets the login dialog run without GDM's daemon.
#
# Runs as root (the container's entry). It installs the Fedora Glass login add-on the way
# the package does (root-owned, into GDM's extension folder, with the shared modules
# copied next to it), then starts the greeter. checks/login_checks.py switches the add-on
# on and off (as the root helper does) and asks for a fresh greeter by creating
# /out/relogin; this script then stops the greeter and starts it again, and creates
# /out/relogged-in ("kill" in /out/relogin kills GNOME Shell first, as a crash would).
# Nothing here switches the add-on on.
set -u
OUT=/out
SRC=/src
UUID=fedora-glass-login@djshiye.github.io
GREETER=gdm-greeter
EXT_DIR=/usr/share/gdm/greeter/gnome-shell/extensions/$UUID

cp /opt/lgqa/suite/container/gdm-test.conf /usr/share/dbus-1/system.d/lgqa-gdm-test.conf
mkdir -p /run/dbus /run/systemd/seats && dbus-daemon --system --fork
(gjs /opt/lgqa/suite/container/login1-stub.js >/dev/null 2>&1 &)
sleep 1
mkdir -p "$OUT" && chmod 0777 "$OUT"

# The greeter's user and folders, as GDM 49+ makes them: home /var/lib/gdm3, a state and
# a config folder per seat (the health note goes into seat0/state, mode 0700).
id "$GREETER" >/dev/null 2>&1 || useradd -r -d /var/lib/gdm3 -s /usr/sbin/nologin "$GREETER"
G=$(id -u "$GREETER")
mkdir -p /var/lib/gdm3/seat0/state /var/lib/gdm3/seat0/config "/run/user/$G"
chown -R "$GREETER:" /var/lib/gdm3 "/run/user/$G"
chmod 0700 "/run/user/$G" /var/lib/gdm3/seat0/state

# Dino in the user list: AccountsService lists a user that has logged in before and whose
# account is not locked (the image's dino has no password: locked).
echo 'dino:glass' | chpasswd
chfn -f Dino dino
mkdir -p /var/lib/AccountsService/users /var/lib/AccountsService/icons
printf '[User]\nSystemAccount=false\n' > /var/lib/AccountsService/users/dino
pkill -x accounts-daemon 2>/dev/null || true

# The add-on, as the package installs it: its own files and the shared modules beside them.
rm -rf "$EXT_DIR"; mkdir -p "$EXT_DIR"
cp -r "$SRC/fedoraglass/data/login-extension/$UUID/." "$EXT_DIR/"
while read -r name; do
    name=${name%%#*}; name=$(echo "$name" | tr -d '[:space:]')
    [ -n "$name" ] || continue
    cp "$SRC/fedoraglass/data/extension/liquid-glass@djshiye.github.io/$name" "$EXT_DIR/$name"
done < "$SRC/fedoraglass/data/login-extension/shared-modules.txt"
chown -R root:root "$EXT_DIR"; chmod 0755 "$EXT_DIR"; chmod 0644 "$EXT_DIR"/*

# GDM's dconf profile for its greeter (GDM ships it; here it is written by hand) and
# the system database it names, which the root helper adds its locked keyfile to.
mkdir -p /usr/share/dconf/profile /etc/dconf/db/gdm.d/locks
printf 'user-db:user\nsystem-db:gdm\n' > /usr/share/dconf/profile/gdm
# Test only: fractional scaling for the two-screen check, and a still caret so a login screen
# at rest really is at rest (the idle check counts frames).
printf "[org/gnome/mutter]\nexperimental-features=['scale-monitor-framebuffer']\n\n[org/gnome/desktop/interface]\ncursor-blink=false\n" \
    > /etc/dconf/db/gdm.d/10-lgqa-test
dconf update

# What a real install has that a container lacks, so the root helper (fedoraglass/login_glass.py)
# can run here: GDM as the display manager, and the helper's boot guard enabled (the package
# enables it; systemd itself does not run here, so the guard never runs).
mkdir -p /etc/systemd/system/graphical.target.wants
ln -sf /usr/lib/systemd/system/gdm3.service /etc/systemd/system/display-manager.service
ln -sf /usr/lib/systemd/system/fedora-glass-login-guard.service \
    /etc/systemd/system/graphical.target.wants/fedora-glass-login-guard.service

# The greeter's session bus also lets root in (test only), so the checks can talk to
# GNOME Shell while they run as root.
cat > /etc/lgqa-greeter-bus.conf <<'EOF'
<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN" "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig><include>/usr/share/dbus-1/session.conf</include><policy context="default"><allow user="root"/></policy></busconfig>
EOF

SCREEN=${LGQA_SCREEN:-1920x1080}
start_greeter() {
    # LGQA_MONITORS=2: two screens (the checks ask for it by writing /out/monitors).
    local n=1 mons=""
    [ -s "$OUT/monitors" ] && n=$(tr -cd '0-9' < "$OUT/monitors")
    for _ in $(seq "${n:-1}"); do mons="$mons --virtual-monitor $SCREEN"; done
    runuser -u "$GREETER" -- env -i PATH=/usr/bin:/bin HOME=/var/lib/gdm3 USER=$GREETER LOGNAME=$GREETER \
        XDG_RUNTIME_DIR=/run/user/$G XDG_SESSION_TYPE=wayland XDG_SESSION_CLASS=greeter \
        XDG_STATE_HOME=/var/lib/gdm3/seat0/state XDG_CONFIG_HOME=/var/lib/gdm3/seat0/config \
        XDG_DATA_DIRS=/usr/share/gdm/greeter:/usr/local/share:/usr/share \
        DCONF_PROFILE=gdm RUNNING_UNDER_GDM=true GDM_GREETER_TEST=1 GDM_SEAT_ID=seat0 \
        LIBGL_ALWAYS_SOFTWARE=1 NO_AT_BRIDGE=1 LANG=C.UTF-8 \
        DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$G/bus WAYLAND_DISPLAY=wayland-0 \
        bash -c "cd /var/lib/gdm3; dbus-daemon --config-file=/etc/lgqa-greeter-bus.conf --address=unix:path=/run/user/$G/bus --fork --print-pid > /run/user/$G/bus.pid; exec gnome-shell --mode=gdm --headless $mons --unsafe-mode --wayland" \
        >> "$OUT/shell.log" 2>&1 &
    SHELL_PID=$!
    for _ in $(seq 90); do
        DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$G/bus gdbus call --session -d org.gnome.Shell -o /org/gnome/Shell \
            -m org.gnome.Shell.Eval 'Main.layoutManager._startingUp ? 0 : 1' 2>/dev/null | grep -q "'1'" && break
        sleep 1
    done
}
stop_greeter() {
    # "kill" in /out/relogin: GNOME Shell dies at once (SIGKILL, as in a crash): no clean stop.
    if [ "$(cat "$OUT/relogin" 2>/dev/null)" = kill ]; then
        pkill -KILL -x gnome-shell -u "$GREETER" 2>/dev/null; sleep 0.5
        echo "== greeter killed $(date +%T)" >> "$OUT/shell.log"
    fi
    kill "$SHELL_PID" 2>/dev/null; wait "$SHELL_PID" 2>/dev/null
    [ -s "/run/user/$G/bus.pid" ] && kill "$(cat "/run/user/$G/bus.pid")" 2>/dev/null
    pkill -u "$GREETER" 2>/dev/null; sleep 1
    rm -f "/run/user/$G"/wayland-0 "/run/user/$G"/wayland-0.lock "/run/user/$G"/bus "/run/user/$G/bus.pid"
}

echo "== greeter start $(date +%T)" >> "$OUT/shell.log"
start_greeter
echo READY
while true; do
    if [ -e "$OUT/relogin" ]; then
        rm -f "$OUT/relogged-in"
        stop_greeter
        rm -f "$OUT/relogin"
        echo "== greeter start $(date +%T)" >> "$OUT/shell.log"
        start_greeter
        touch "$OUT/relogged-in"
    fi
    sleep 0.5
done
