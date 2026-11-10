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
{ echo "Fedora Glass is MIT licensed, with Apache-2.0 parts and pointer styles under GPL-3.0-or-later, GPL-2.0 or CC-BY-SA-4.0; see LICENSE, Apache-2.0.txt, GPL-3.0.txt, GPL-2.0.txt, CC-BY-SA-4.0.txt and THIRD-PARTY-NOTICES.md here."; } > "$root/usr/share/doc/fedora-glass/copyright"
# The repository it updates from, its key and the pin that lets only fedora-glass through.
# The source and the pin are not conffiles: postinst puts them in /etc/apt from here and
# postrm takes them out again, so `apt remove` never leaves a source whose key is gone.
install -Dm644 packaging/deb/fedora-glass.sources "$root/usr/share/fedora-glass/apt/fedora-glass.sources"
install -Dm644 packaging/deb/fedora-glass.pref "$root/usr/share/fedora-glass/apt/fedora-glass.pref"
install -Dm644 packaging/RPM-GPG-KEY-fedora-glass "$root/usr/share/keyrings/fedora-glass.asc"

install -d "$root/DEBIAN"
size="$(du -sk --exclude=DEBIAN "$root" | cut -f1)"
sed -e "s/@VERSION@/$ver-1/" -e "s/@SIZE@/$size/" packaging/deb/control.in > "$root/DEBIAN/control"
install -m755 packaging/deb/preinst packaging/deb/postinst packaging/deb/prerm "$root/DEBIAN/"
# postrm knows our source and pin by their entries (comments aside), as postinst does.
entries_sum() { sed -e 's/[[:space:]]*$//' -e '/^#/d' -e '/^$/d' "$1" | sha256sum | cut -d' ' -f1; }
sed -e "s/@SOURCES_SUM@/$(entries_sum packaging/deb/fedora-glass.sources)/" \
    -e "s/@PREF_SUM@/$(entries_sum packaging/deb/fedora-glass.pref)/" packaging/deb/postrm > "$root/DEBIAN/postrm"
chmod 755 "$root/DEBIAN/postrm"
(cd "$root" && find . -path ./DEBIAN -prune -o -type f -printf '%P\n' | LC_ALL=C sort | xargs -d '\n' md5sum) > "$root/DEBIAN/md5sums"
mkdir -p "$out"
# xz for both members, so the signing script can read the control file with Python alone.
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git log -1 --format=%ct 2>/dev/null || date +%s)}" \
    dpkg-deb --root-owner-group -Zxz --build "$root" "$out/fedora-glass_${ver}-1_all.deb" >/dev/null
echo "$out/fedora-glass_${ver}-1_all.deb"
