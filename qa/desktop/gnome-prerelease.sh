#!/bin/sh
# Is there a base image with the next GNOME yet? (the early-warning lane, run.sh --gnome 52)
#
#   qa/desktop/gnome-prerelease.sh [MAJOR]        (default 52)
#
# Asks Ubuntu's archive which gnome-shell its development series ("devel", the next Ubuntu)
# ships now. GNOME 52 is due in March 2027, so for a while this is still 51 and the lane waits;
# it starts by itself, on the first run after Ubuntu's development series uploads GNOME 52
# (an alpha or beta counts: "52~alpha" is major 52). Prints key=value lines:
#   series=tenacious    shell=51.0-2ubuntu3    major=51    ready=false
# and, only when ready, the base for run.sh:
#   base=mirror.gcr.io/library/ubuntu@sha256:<the digest ubuntu:devel has now>
# Read-only: public archive and registry pages, no login, no secrets. Exit 0 whether or not it
# is ready; 2 when it could not find out (the lane then fails visibly instead of looking skipped).
set -eu
target="${1:-52}"
case "$target" in ''|*[!0-9]*) echo "MAJOR must be a number" >&2; exit 64 ;; esac
ARCHIVE="${LGQA_UBUNTU_ARCHIVE:-https://archive.ubuntu.com/ubuntu}"
CURL="curl -fsSL --retry 3 --retry-all-errors --max-time 120"

series="$($CURL "$ARCHIVE/dists/devel/Release" | sed -n 's/^Codename: //p' | head -n 1)" || series=""
shell="$($CURL "$ARCHIVE/dists/devel/main/binary-amd64/Packages.gz" | gunzip | awk '/^Package: gnome-shell$/ { p = 1 } p && /^Version:/ { print $2; exit }')" || shell=""
[ -n "$series" ] && [ -n "$shell" ] || { echo "could not read gnome-shell from $ARCHIVE/dists/devel" >&2; exit 2; }
major="$(printf '%s' "$shell" | sed -E 's/^[0-9]+://; s/^([0-9]+).*/\1/')"
case "$major" in ''|*[!0-9]*) echo "odd gnome-shell version: $shell" >&2; exit 2 ;; esac
echo "series=$series"
echo "shell=$shell"
echo "major=$major"
if [ "$major" -lt "$target" ]; then
    echo "ready=false"
    exit 0
fi

# Ubuntu's development image at this moment, by digest (the same trust as the digests pinned
# in the Dockerfile, taken fresh because the development series moves). The image is only the
# starting point: the lane's image installs gnome-shell from the archive.
token="$($CURL "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/ubuntu:pull" | sed -n 's/.*"token" *: *"\([^"]*\)".*/\1/p' | head -n 1)" || token=""
[ -n "$token" ] || { echo "could not get a registry token" >&2; exit 2; }
digest="$(curl -fsSI --retry 3 --retry-all-errors --max-time 60 -H "Authorization: Bearer $token" \
    -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json' \
    https://registry-1.docker.io/v2/library/ubuntu/manifests/devel | tr -d '\r' | awk 'tolower($1) == "docker-content-digest:" { print $2; exit }')" || digest=""
case "$digest" in sha256:????????????????????????????????????????????????????????????????) ;; *) echo "could not read the digest of ubuntu:devel" >&2; exit 2 ;; esac
echo "ready=true"
echo "base=mirror.gcr.io/library/ubuntu@$digest"
