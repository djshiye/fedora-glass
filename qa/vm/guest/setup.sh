#!/bin/bash
# Turns a fresh cloud image into a PC with a real login screen and the real package:
#   sudo bash setup.sh FAMILY VERSION      (FAMILY: fedora, ubuntu or arch)
# Run inside the test VM by qa/vm/login_boot.py, from /home/tester/lgv, which holds the source
# tarball fedora-glass-VERSION.tar.gz (made with `git archive`). The package is built here the
# same way .github/workflows/packages.yml builds it for that Linux, and installed with the
# Linux's own package manager, so its dependencies and scriptlets run as on a real PC.
set -euo pipefail
family="$1"
ver="$2"
here=/home/tester/lgv
tarball="$here/fedora-glass-$ver.tar.gz"
case "$ver" in *[!0-9.]*|'') echo "bad version: $ver" >&2; exit 1 ;; esac
test -f "$tarball"

say() { printf '>>> %s\n' "$*"; }

say "Waiting for cloud-init to finish its first boot"
cloud-init status --wait >/dev/null 2>&1 || cloud-init status --long || true
# Later boots need nothing from cloud-init, and skipping it makes each reboot quicker.
touch /etc/cloud/cloud-init.disabled

say "Kernel $(uname -r); graphics: $(ls /dev/dri 2>/dev/null | tr '\n' ' ' || echo none)"

src="$here/src"
rm -rf "$src" && mkdir -p "$src"
tar -xzf "$tarball" -C "$src"
tree="$src/fedora-glass-$ver"

case "$family" in
fedora)
    # Fedora Workstation's login screen, without the rest of Workstation. No
    # gnome-initial-setup: it would take over the first login.
    say "Installing GDM and GNOME Shell (dnf)"
    dnf -y -q --setopt=install_weak_deps=False install \
        gdm gnome-shell gnome-session gnome-settings-daemon mesa-dri-drivers dconf rpm-build tar
    # Names that moved between releases: whichever exist. (dnf 5 takes --skip-unavailable
    # only after the word install.)
    dnf -y -q --setopt=install_weak_deps=False install --skip-unavailable \
        gnome-session-wayland-session adwaita-sans-fonts cantarell-fonts audit policycoreutils kernel-modules
    say "Installing what the spec builds with"
    mapfile -t breq < <(awk '/^BuildRequires:/ { print $2 }' "$tree/packaging/fedora-glass.spec")
    dnf -y -q --setopt=install_weak_deps=False install "${breq[@]}"
    say "Building the rpm (rpmbuild --nocheck: the tests ran in the other workflows)"
    mkdir -p /root/rpmbuild/SOURCES
    cp "$tarball" /root/rpmbuild/SOURCES/
    rpmbuild -bb --nocheck "$tree/packaging/fedora-glass.spec" >"$here/rpmbuild.log" 2>&1 || { tail -n 60 "$here/rpmbuild.log"; exit 1; }
    rpm="$(ls /root/rpmbuild/RPMS/noarch/fedora-glass-[0-9]*.noarch.rpm)"
    say "Installing $rpm (dnf)"
    dnf -y -q install "$rpm"
    ;;
ubuntu)
    export DEBIAN_FRONTEND=noninteractive
    apt_get() { apt-get -o DPkg::Lock::Timeout=600 -o Acquire::Retries=3 "$@"; }
    have() { apt-cache show "$1" >/dev/null 2>&1; }
    # The daily update timers would hold the package lock in the middle of the steps.
    systemctl stop unattended-upgrades.service apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true
    systemctl disable unattended-upgrades.service apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true
    apt_get update -qq
    extra=()
    for p in libgl1-mesa-dri mesa-libgallium dbus-user-session fonts-cantarell "linux-modules-extra-$(uname -r)"; do
        if have "$p"; then extra+=("$p"); fi
    done
    say "Installing GDM and GNOME Shell (apt): gdm3 gnome-shell gnome-session dconf-cli ${extra[*]}"
    apt_get install -y -qq --no-install-recommends gdm3 gnome-shell gnome-session gnome-settings-daemon dconf-cli "${extra[@]}" >/dev/null
    say "Building the deb (packaging/deb/build-deb.sh)"
    (cd "$tree" && sh packaging/deb/build-deb.sh "$ver" out)
    say "Installing the deb (apt)"
    apt_get install -y -qq "$tree/out/fedora-glass_${ver}-1_all.deb" >/dev/null
    ;;
arch)
    if ! pacman-key --list-keys >/dev/null 2>&1; then
        pacman-key --init && pacman-key --populate archlinux
    fi
    say "Installing GDM and GNOME Shell (pacman)"
    pacman -Sy --noconfirm --needed archlinux-keyring >/dev/null
    pacman -Su --noconfirm --needed gdm gnome-shell gnome-session gnome-settings-daemon dconf mesa cantarell-fonts base-devel >/dev/null
    say "Building the package (packaging/arch/build-pkg.sh, as tester: makepkg refuses root)"
    chown -R tester: "$src"
    su tester -c "cd '$tree' && FG_TARBALL='$tarball' sh packaging/arch/build-pkg.sh '$ver' out"
    say "Installing the package (pacman)"
    pacman -U --noconfirm "$tree"/out/fedora-glass-"$ver"-1-any.pkg.tar.xz >/dev/null
    ;;
*)
    echo "unknown family: $family" >&2; exit 1 ;;
esac

# GDM lists the people AccountsService knows. A user made by cloud-init has never logged in,
# so AccountsService gets its record now; otherwise the list could be empty and the test
# would have to type a user name. This is what the Settings app writes for a new user.
install -d -m 0755 /var/lib/AccountsService/users
printf '[User]\nSystemAccount=false\n' > /var/lib/AccountsService/users/tester
chmod 0600 /var/lib/AccountsService/users/tester
# No first-login wizard, whatever pulled it in.
install -d -o tester -g tester /home/tester/.config
echo yes > /home/tester/.config/gnome-initial-setup-done
chown tester: /home/tester/.config/gnome-initial-setup-done

# Ubuntu's gdm3 has its unit as gdm.service too (gdm3.service is a second name for it).
# Looked up as a file: on Fedora 44 `systemctl cat gdm.service` failed right after the
# install although the unit was there, so systemd is asked nothing before it has read the
# new units again.
systemctl daemon-reload || echo "(systemctl daemon-reload failed, going on)"
gdm_unit=""
for unit in gdm.service gdm3.service; do
    for dir in /etc/systemd/system /usr/lib/systemd/system /lib/systemd/system; do
        if [ -e "$dir/$unit" ]; then gdm_unit="$unit"; break 2; fi
    done
done
if [ -z "$gdm_unit" ]; then
    echo "no unit file of GDM found" >&2
    ls -l /etc/systemd/system/display-manager.service /usr/lib/systemd/system/ 2>&1 | grep -i -E "dm|display" >&2 || true
    exit 1
fi
systemctl cat "$gdm_unit" >/dev/null || echo "(systemctl cat $gdm_unit failed, going on: the file is there)"
say "Starting the login screen at every boot ($gdm_unit, graphical.target)"
systemctl enable "$gdm_unit"
systemctl set-default graphical.target
echo "$gdm_unit" > "$here/gdm-unit"

say "Installed:"
gnome-shell --version || true
case "$family" in
fedora) rpm -q fedora-glass gdm gnome-shell ;;
ubuntu) dpkg-query -W fedora-glass gdm3 gnome-shell ;;
arch) pacman -Q fedora-glass gdm gnome-shell ;;
esac
ls -l /usr/libexec/fedora-glass-login
ls /usr/share/gdm/greeter/gnome-shell/extensions/ || true
/usr/libexec/fedora-glass-login status || true
say "Setup done"
