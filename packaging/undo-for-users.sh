#!/bin/sh
# Run by `dnf remove fedora-glass` (as root, before the app's files go away).
#
# Fedora Glass changes only each person's own files and settings, so only that person can
# put them back. For everyone with a look applied, this runs `fedora-glass on-remove` as
# that person (never as root): it does what Restore original does, unless they turned
# "Undo my look when Fedora Glass is removed" off in the app. A person who is logged in
# gets it in their running session; anyone else in a short private session.
#
# Each person's run is detached from root's terminal (setsid: a new session with no
# terminal, input from /dev/null), so nothing running as them can type into root's
# terminal (TIOCSTI on older kernels). Its output still shows here.
#
# It never stops the removal: a problem is reported and the backup is kept.
PATH=/usr/sbin:/usr/bin:/sbin:/bin
app=/usr/bin/fedora-glass
[ -x "$app" ] || exit 0
for tool in runuser setsid; do
    command -v "$tool" >/dev/null 2>&1 || { echo "Fedora Glass: $tool is missing, so your look was left as it is. Run: fedora-glass revert"; exit 0; }
done

uid_min=$(awk '$1 == "UID_MIN" { print $2 }' /etc/login.defs 2>/dev/null)
case "$uid_min" in ''|*[!0-9]*) uid_min=1000 ;; esac

getent passwd | while IFS=: read -r name _pw uid _gid _gecos home _shell; do
    case "$uid" in ''|*[!0-9]*) continue ;; esac
    [ "$uid" -ge "$uid_min" ] && [ "$uid" -lt 60000 ] || continue      # people, not system users or nobody
    case "$home" in /*) ;; *) continue ;; esac
    [ -f "$home/.local/state/liquid-glass/backup/manifest.json" ] || continue
    echo "Fedora Glass: checking the look for $name"
    run=/run/user/$uid
    if [ -S "$run/bus" ]; then
        # Logged in: change the settings in the running session, so the desktop updates now.
        setsid -w timeout 120 runuser -u "$name" -- env -i HOME="$home" USER="$name" LOGNAME="$name" \
            PATH=/usr/bin:/bin XDG_RUNTIME_DIR="$run" DBUS_SESSION_BUS_ADDRESS="unix:path=$run/bus" \
            "$app" on-remove </dev/null
    elif command -v dbus-run-session >/dev/null 2>&1; then
        setsid -w timeout 120 runuser -u "$name" -- env -i HOME="$home" USER="$name" LOGNAME="$name" \
            PATH=/usr/bin:/bin dbus-run-session -- "$app" on-remove </dev/null 2>/dev/null   # the private bus is chatty
    else
        echo "Fedora Glass: $name is not logged in and dbus-run-session is missing; their look stays. They can run: fedora-glass revert"
        continue
    fi || echo "Fedora Glass: some of $name's look could not be put back; their backup is kept"
done
exit 0
