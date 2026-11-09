#!/bin/sh
# Builds the Ubuntu/Debian package: packaging/deb/build-deb.sh VERSION OUT_DIR
# Needs dpkg-deb only. Run from the source folder.
set -eu
ver="$1"
out="$2"
case "$ver" in *[!0-9.]*|'') echo "bad version: $ver" >&2; exit 1 ;; esac
src="$(pwd)"
root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT
sh packaging/install-tree.sh "$src" "$root"
# Debian keeps licences with the docs.
install -d "$root/usr/share/doc/fedora-glass"
mv "$root/usr/share/licenses/fedora-glass/"* "$root/usr/share/doc/fedora-glass/"
rm -r "$root/usr/share/licenses"
{ echo "Fedora Glass is MIT licensed, with Apache-2.0 parts; see LICENSE, Apache-2.0.txt and THIRD-PARTY-NOTICES.md here."; } > "$root/usr/share/doc/fedora-glass/copyright"
# The repository it updates from, its key and the pin that lets only fedora-glass through.
install -Dm644 packaging/deb/fedora-glass.sources "$root/etc/apt/sources.list.d/fedora-glass.sources"
install -Dm644 packaging/deb/fedora-glass.pref "$root/etc/apt/preferences.d/fedora-glass.pref"
install -Dm644 packaging/RPM-GPG-KEY-fedora-glass "$root/usr/share/keyrings/fedora-glass.asc"

install -d "$root/DEBIAN"
size="$(du -sk --exclude=DEBIAN "$root" | cut -f1)"
sed -e "s/@VERSION@/$ver-1/" -e "s/@SIZE@/$size/" packaging/deb/control.in > "$root/DEBIAN/control"
install -m755 packaging/deb/postinst packaging/deb/prerm "$root/DEBIAN/"
printf '%s\n' /etc/apt/sources.list.d/fedora-glass.sources /etc/apt/preferences.d/fedora-glass.pref > "$root/DEBIAN/conffiles"
(cd "$root" && find . -path ./DEBIAN -prune -o -type f -printf '%P\n' | LC_ALL=C sort | xargs -d '\n' md5sum) > "$root/DEBIAN/md5sums"
mkdir -p "$out"
# xz for both members, so the signing script can read the control file with Python alone.
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git log -1 --format=%ct 2>/dev/null || date +%s)}" \
    dpkg-deb --root-owner-group -Zxz --build "$root" "$out/fedora-glass_${ver}-1_all.deb" >/dev/null
echo "$out/fedora-glass_${ver}-1_all.deb"
