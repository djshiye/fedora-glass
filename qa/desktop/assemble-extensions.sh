#!/bin/bash
# assemble-extensions.sh OWNER/REPO@COMMIT ...  (image build step)
#
# Clones each source at an exact commit, checks the commit, and puts the extension
# together with glib tools only (copy files, compile schemas and resources).
# No build script from these projects runs. Output: /opt/lgqa/ext/<uuid>, /opt/lgqa/themes.
set -euo pipefail
SRC=/opt/lgqa/src EXT=/opt/lgqa/ext
mkdir -p "$SRC" "$EXT" /opt/lgqa/themes

fetch() {  # fetch NAME HOST/REPO COMMIT
    local dir=$SRC/$1 url=$2 want=$3
    git init -q "$dir"
    git -C "$dir" fetch -q --depth 1 "$url" "$want"
    git -C "$dir" checkout -q FETCH_HEAD
    local got; got=$(git -C "$dir" rev-parse HEAD)
    [ "$got" = "$want" ] || { echo "PIN MISMATCH for $url: wanted $want, got $got" >&2; exit 1; }
    echo "pinned $url @ $got"
}

for spec in "$@"; do
    repo=${spec%@*} commit=${spec#*@}
    case $repo in
        gitlab:*) url=https://gitlab.com/${repo#gitlab:}.git ;;
        *) url=https://github.com/$repo ;;
    esac
    fetch "$(basename "$repo")" "$url" "$commit"
done

# Dash to Panel
d=$EXT/dash-to-panel@jderose9.github.com; s=$SRC/dash-to-panel; mkdir -p "$d/ui" "$d/img" "$d/schemas"
cp "$s"/src/*.js "$s"/src/stylesheet.css "$s"/metadata.json "$d"/; cp "$s"/ui/*.ui "$d"/ui/; cp -r "$s"/img/* "$d"/img/
cp "$s"/schemas/*.xml "$d"/schemas/; glib-compile-schemas "$d"/schemas

# ArcMenu
d=$EXT/arcmenu@arcmenu.com; s=$SRC/ArcMenu; mkdir -p "$d/schemas" "$d/data"
cp -r "$s"/src/* "$s"/metadata.json "$d"/
cp "$s"/schemas/*.xml "$d"/schemas/; glib-compile-schemas --strict "$d"/schemas
files=$(cd "$s/data" && find . -mindepth 2 -type f -name '*.svg' | sed 's|^\./||' | sort -V | \
        sed 's|.*|    <file compressed="true" preprocess="xml-stripblanks">&</file>|')
printf '<?xml version="1.0" encoding="UTF-8"?>\n<gresources>\n  <gresource prefix="/org/gnome/shell/extensions/arcmenu">\n%s\n  </gresource>\n</gresources>\n' "$files" > /tmp/arcmenu.gresource.xml
glib-compile-resources --sourcedir="$s/data" --target="$d/data/resources.gresource" /tmp/arcmenu.gresource.xml

# Blur my Shell
d=$EXT/blur-my-shell@aunetx; s=$SRC/blur-my-shell; mkdir -p "$d/schemas"
cp -r "$s"/src/* "$d"/; rm -rf "$d/styles"
cat "$s"/src/styles/panel.css "$s"/src/styles/dash.css "$s"/src/styles/popup/base.css "$s"/src/styles/popup/transparent.css \
    "$s"/src/styles/popup/light.css "$s"/src/styles/popup/dark.css "$s"/src/styles/popup/menu-items.css \
    "$s"/src/styles/overview.css "$s"/src/styles/appfolders.css "$s"/src/styles/panel-light-text.css > "$d/stylesheet.css"
cp "$s"/metadata.json "$d"/
cp -r "$s"/resources/icons "$s"/resources/ui "$d"/      # plain files, as its own packing does
cp "$s"/schemas/*.xml "$d"/schemas/; glib-compile-schemas "$d"/schemas

# Just Perfection
d=$EXT/just-perfection-desktop@just-perfection; mkdir -p "$d"; cp -r "$SRC"/just-perfection/src/* "$d"/; glib-compile-schemas "$d"/schemas

# AppIndicator
d=$EXT/appindicatorsupport@rgcjonas.gmail.com; s=$SRC/gnome-shell-extension-appindicator; mkdir -p "$d/schemas"
cp "$s"/*.js "$s"/metadata.json "$d"/; cp -r "$s"/interfaces-xml "$s"/icons "$s"/tools "$d"/ 2>/dev/null || true
[ -d "$s/preferences" ] && cp -r "$s/preferences" "$d"/
cp "$s"/schemas/*.xml "$d"/schemas/; glib-compile-schemas "$d"/schemas

# Deja Window
d=$EXT/deja-window@mcast.gnomext.com; mkdir -p "$d"; cp -r "$SRC"/deja-window/src/* "$d"/
[ -d "$d/schemas" ] && glib-compile-schemas "$d"/schemas

# Extension List (fill in the meson template values by hand; no stylesheet, it is optional)
d=$EXT/extension-list@tu.berry; s=$SRC/extension-list; mkdir -p "$d/schemas"
cp "$s"/src/*.js "$d"/
sed -e 's|@name@|Extension List|; s|@description@|Manage extensions from the top panel|; s|@uuid@|extension-list@tu.berry|' \
    -e 's|@gettext@|gnome-shell-extension-extension-list|; s|@rdnn@|org.gnome.shell.extensions.extension-list|' \
    -e 's|"@shell@"|"50"|; s|@version@||; s|@url@|https://github.com/tuberry/extension-list|' \
    "$s/res/data/metadata.json.in" > "$d/metadata.json"
sed -e 's|@gettext@|gnome-shell-extension-extension-list|; s|@rdnn@|org.gnome.shell.extensions.extension-list|' \
    -e 's|@path@|/org/gnome/shell/extensions/extension-list/|' \
    "$s/res/schema/schemas.gschema.xml.in" > "$d/schemas/org.gnome.shell.extensions.extension-list.gschema.xml"
glib-compile-schemas --strict "$d"/schemas

# Orchis: the project's own prebuilt release archive, from the pinned commit
tar -xJf "$SRC/Orchis-theme/release/Orchis.tar.xz" -C /opt/lgqa/themes
test -d /opt/lgqa/themes/Orchis-Dark/gtk-4.0

rm -rf "$SRC"
ls "$EXT"
