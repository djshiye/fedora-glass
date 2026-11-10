#!/bin/sh
# Early warning for a new GNOME: is the gnome-shell that Fedora Rawhide ships newer than the
# highest version the Shell extension says it supports?
#
#   packaging/check-gnome-next.sh METADATA_JSON GNOME_SHELL_VERSION
#
# Exits 1 with a GitHub error titled "GNOME NN is coming: add it to Fedora Glass and test"
# when it is. Run weekly by .github/workflows/gnome-next.yml.
set -eu
meta="$1"
shell="$2"
case "$shell" in [0-9]*) ;; *) echo "::error title=Could not read the GNOME version::Rawhide's gnome-shell version is '$shell'"; exit 2 ;; esac
major="${shell%%[!0-9]*}"
ours="$(python3 -I -c '
import json, sys
print(max(int(v.split(".")[0]) for v in json.load(open(sys.argv[1]))["shell-version"]))
' "$meta")"
echo "Rawhide has gnome-shell $shell (GNOME $major). Fedora Glass supports up to GNOME $ours."
if [ "$major" -gt "$ours" ]; then
    # ":" and "," in an annotation's title are written %3A and %2C.
    echo "::error title=GNOME $major is coming%3A add it to Fedora Glass and test::Fedora Rawhide has gnome-shell $shell, and the extension's metadata.json lists GNOME up to $ours. Add \"$major\" to shell-version, then run the release checks on it (qa/desktop)."
    if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
        echo "### GNOME $major is coming: add it to Fedora Glass and test" >> "$GITHUB_STEP_SUMMARY"
        echo "Rawhide has gnome-shell $shell; \`metadata.json\` lists GNOME up to $ours." >> "$GITHUB_STEP_SUMMARY"
    fi
    exit 1
fi
