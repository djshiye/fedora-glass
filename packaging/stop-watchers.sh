#!/bin/sh
# Run by `apt remove fedora-glass` and `pacman -R fedora-glass` (as root, before the app's
# files go away).
#
# `systemctl --global disable` only keeps the dark/light watcher from starting at the next
# login: in a running session it would go on until logout, re-applying the look the
# removal is putting back. This stops it in every running session, the way the rpm's
# %systemd_user_preun does: systemctl asks each person's own service manager to stop
# their unit, so nothing of theirs runs here, as root or on root's terminal.
#
# It never stops the removal.
PATH=/usr/sbin:/usr/bin:/sbin:/bin
unit=liquid-glass-watch.service
[ -d /run/systemd/system ] || exit 0       # no systemd running (a container, a chroot)
command -v systemctl >/dev/null 2>&1 || exit 0

systemctl list-units --legend=no --plain 'user@*.service' 2>/dev/null |
    sed -n -E 's/^[[:space:]]*user@([0-9]+)\.service.*/\1/p' |
    while read -r uid; do
        # Detached from root's terminal, and given up after a while, like undo-for-users.
        setsid -w timeout 30 systemctl --user -M "$uid@" stop "$unit" </dev/null >/dev/null 2>&1 ||
            echo "Fedora Glass: the watcher of user $uid could not be stopped; it ends at their next logout"
    done
exit 0
