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
# Someone who moved their XDG folders (XDG_STATE_HOME and so on, set in
# ~/.config/environment.d/*.conf, which is how GNOME applications get them) keeps the
# backup there, and the app looks for it there. So those four are read from their
# environment.d files and handed to their run. The files are theirs, so they are read
# as them (a link out of their home gets them nothing they could not read anyway) and
# only looked at, never run (every look at a path under a home is made as that person,
# with a time limit: root may not see into a network home, and a hung one must not hold
# up the removal): plain NAME=VALUE lines (the value may be in one pair of quotes, as
# systemd allows), where only $HOME and ${HOME} are
# expanded and anything else with a $, a backtick or a control character, or a value
# that is not an absolute path, is ignored.
#
# It never stops the removal: a problem is reported and the backup is kept.
PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
export LC_ALL
app=/usr/bin/fedora-glass
[ -x "$app" ] || exit 0
for tool in runuser setsid; do
    command -v "$tool" >/dev/null 2>&1 || { echo "Fedora Glass: $tool is missing, so your look was left as it is. Run: fedora-glass revert"; exit 0; }
done

# Run "$@" as the person $name, apart from root's terminal and with a time limit. Used for
# every look at something under their home, so it works where root cannot see (an NFS home
# with root_squash) and a stuck home costs ten seconds, not the package transaction.
as_person() {
    setsid -w timeout 10 runuser -u "$name" -- "$@" </dev/null 2>/dev/null
}

# The value of NAME in the environment.d text $1 ($2: their home), or nothing. The last
# good assignment wins, as in systemd.
env_value() {
    printf '%s\n' "$1" | {
        found=
        while IFS= read -r line; do
            case $line in "$3="*) ;; *) continue ;; esac
            rest=${line#"$3="}
            # systemd takes a value in one pair of quotes ("$HOME/x" or '$HOME/x') the same
            # as without them. One with a backslash or another quote inside is ignored.
            case $rest in
                \"*\")
                    rest=${rest#\"}; rest=${rest%\"}
                    case $rest in *\"*|*\\*) continue ;; esac ;;
                \'*\')
                    rest=${rest#\'}; rest=${rest%\'}
                    case $rest in *\'*|*\\*) continue ;; esac ;;
            esac
            out=
            while :; do
                case $rest in
                    *'$'*) ;;
                    *) out=$out$rest; break ;;
                esac
                out=$out${rest%%\$*}
                after=${rest#*\$}
                case $after in
                    '{HOME}'*) out=$out$2; rest=${after#'{HOME}'} ;;
                    HOME*)
                        rest=${after#HOME}
                        case $rest in [A-Za-z0-9_]*) out='$'; break ;; esac
                        out=$out$2 ;;
                    *) out='$'; break ;;
                esac
            done
            case $out in
                *'$'*|*'`'*|*[[:cntrl:]]*) continue ;;
                /*) found=$out ;;
            esac
        done
        printf '%s' "$found"
    }
}

uid_min=$(awk '$1 == "UID_MIN" { print $2 }' /etc/login.defs 2>/dev/null)
case "$uid_min" in ''|*[!0-9]*) uid_min=1000 ;; esac

getent passwd | while IFS=: read -r name _pw uid _gid _gecos home _shell; do
    case "$uid" in ''|*[!0-9]*) continue ;; esac
    # People, not system users or nobody (65534). systemd-homed gives its people 60001 to 60513.
    { [ "$uid" -ge "$uid_min" ] && [ "$uid" -lt 60000 ]; } || { [ "$uid" -ge 60001 ] && [ "$uid" -le 60513 ]; } || continue
    case "$home" in /*) ;; *) continue ;; esac
    # The *.conf is spread by their shell, not root's; no such files just gives nothing.
    conf=$(as_person sh -c 'cat -- "$1"/.config/environment.d/*.conf' sh "$home")
    xs=$(env_value "$conf" "$home" XDG_STATE_HOME)
    xc=$(env_value "$conf" "$home" XDG_CONFIG_HOME)
    xk=$(env_value "$conf" "$home" XDG_CACHE_HOME)
    xd=$(env_value "$conf" "$home" XDG_DATA_HOME)
    if as_person test -f "${xs:-$home/.local/state}/liquid-glass/backup/manifest.json"; then
        :
    elif as_person test -f "$home/.local/state/liquid-glass/backup/manifest.json"; then
        xs='' xc='' xk='' xd=''     # the app would look in the default place
    else
        continue
    fi
    echo "Fedora Glass: checking the look for $name"
    run=/run/user/$uid
    if [ -S "$run/bus" ]; then
        # Logged in: change the settings in the running session, so the desktop updates now.
        setsid -w timeout 120 runuser -u "$name" -- env -i HOME="$home" USER="$name" LOGNAME="$name" \
            ${xs:+"XDG_STATE_HOME=$xs"} ${xc:+"XDG_CONFIG_HOME=$xc"} ${xk:+"XDG_CACHE_HOME=$xk"} ${xd:+"XDG_DATA_HOME=$xd"} \
            PATH=/usr/bin:/bin XDG_RUNTIME_DIR="$run" DBUS_SESSION_BUS_ADDRESS="unix:path=$run/bus" \
            "$app" on-remove </dev/null
    elif command -v dbus-run-session >/dev/null 2>&1; then
        setsid -w timeout 120 runuser -u "$name" -- env -i HOME="$home" USER="$name" LOGNAME="$name" \
            ${xs:+"XDG_STATE_HOME=$xs"} ${xc:+"XDG_CONFIG_HOME=$xc"} ${xk:+"XDG_CACHE_HOME=$xk"} ${xd:+"XDG_DATA_HOME=$xd"} \
            PATH=/usr/bin:/bin dbus-run-session -- "$app" on-remove </dev/null 2>/dev/null   # the private bus is chatty
    else
        echo "Fedora Glass: $name is not logged in and dbus-run-session is missing; their look stays. They can run: fedora-glass revert"
        continue
    fi || echo "Fedora Glass: some of $name's look could not be put back; their backup is kept"
done
exit 0
