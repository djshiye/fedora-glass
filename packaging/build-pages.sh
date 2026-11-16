#!/bin/sh
# Builds the project page into the GitHub Pages site (dnf-repo.yml). Usage:
#   packaging/build-pages.sh SITE_DIR VERSION
# Run from the repository root. It only adds the page's own files and never replaces
# anything already in SITE_DIR (the signed rpms/, apt/, arch/ repositories, the key,
# the .repo files and version.txt).
set -eu
site=$1
version=$2
printf '%s' "$version" | grep -Eqx '[0-9A-Za-z.~^_+-]+' || { echo "bad version: $version"; exit 1; }
[ -d "$site" ] || { echo "no site folder: $site"; exit 1; }

for f in pages/* pages/.[!.]*; do
  [ -e "$f" ] || continue
  name=${f#pages/}
  [ ! -e "$site/$name" ] || { echo "refusing: pages/$name would replace $site/$name"; exit 1; }
done
[ ! -e "$site/screenshots" ] && [ ! -e "$site/icon.svg" ] || { echo "refusing: screenshots or icon.svg already in $site"; exit 1; }

cp -R pages/. "$site/"
mkdir "$site/screenshots"
cp docs/screenshots/*.jpg docs/screenshots/*.png "$site/screenshots/"
cp data/icons/io.github.djshiye.LiquidGlass.svg "$site/icon.svg"
sed -i "s/@VERSION@/$version/g" "$site/index.html"
! grep -q '@VERSION@' "$site/index.html"
