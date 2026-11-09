#!/bin/sh
# Builds the Arch package from this source folder: packaging/arch/build-pkg.sh VERSION OUT_DIR
# Run as a normal user in an Arch system with base-devel (makepkg refuses root).
set -eu
ver="$1"
out="$(realpath -m "$2")"
case "$ver" in *[!0-9.]*|'') echo "bad version: $ver" >&2; exit 1 ;; esac
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
if [ -n "${FG_TARBALL:-}" ]; then
    cp "$FG_TARBALL" "$work/fedora-glass-$ver.tar.gz"      # made elsewhere with git archive
else
    git archive --format=tar.gz --prefix="fedora-glass-$ver/" -o "$work/fedora-glass-$ver.tar.gz" HEAD
fi
sum="$(sha256sum "$work/fedora-glass-$ver.tar.gz" | cut -d' ' -f1)"
sed -e "s/@VERSION@/$ver/" -e "s/@SHA256@/$sum/" packaging/arch/PKGBUILD > "$work/PKGBUILD"
cp packaging/arch/fedora-glass.install "$work/"
mkdir -p "$out"
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git log -1 --format=%ct 2>/dev/null || date +%s)}"
# xz, so the signing script can read the package with Python alone.
(cd "$work" && PKGEXT=.pkg.tar.xz PKGDEST="$out" PACKAGER="Dino Klisura <115914552+djshiye@users.noreply.github.com>" \
    makepkg --nodeps --noconfirm --clean --cleanbuild >/dev/null)
ls "$out"/fedora-glass-"$ver"-1-any.pkg.tar.xz
