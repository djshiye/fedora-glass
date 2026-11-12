#!/bin/sh
# Compares the container images pinned by digest in the workflows (`container: fedora:44@sha256:...`)
# with what the registry serves for the same tag today, and fails with the new digest named,
# so the owner can change the pin in one line. Dependabot can't update a `container:` line in a
# workflow file, so without this the pins would never be refreshed (and the security updates of
# the base image would never reach the builds).
#
#   check-pinned-images.sh FILE...        (the workflow files to look at)
#
# Read-only: it asks the registry's public API for a manifest digest (no login, no secrets) and
# prints GitHub annotations. Docker Hub official images only (`fedora`, `ubuntu`, `archlinux`):
# any other registry in a `container:` line is reported as unsupported rather than skipped.
# Exit 0: all pins are current. 1: at least one pin is out of date. 2: a registry could not be asked.
set -eu

ACCEPT='application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json'
HUB_AUTH='https://auth.docker.io/token?service=registry.docker.io'
HUB_REGISTRY='https://registry-1.docker.io/v2'

# current_digest NAME TAG -> the digest the tag points at now (the manifest list, as `docker pull` pins it)
current_digest() {
    token="$(curl -fsSL --retry 3 --retry-all-errors --max-time 30 "$HUB_AUTH&scope=repository:library/$1:pull" | sed -n 's/.*"token" *: *"\([^"]*\)".*/\1/p' | head -n 1)"
    [ -n "$token" ] || return 1
    curl -fsSI --retry 3 --retry-all-errors --max-time 30 -H "Authorization: Bearer $token" -H "Accept: $ACCEPT" "$HUB_REGISTRY/library/$1/manifests/$2" \
        | tr -d '\r' | awk 'tolower($1) == "docker-content-digest:" { print $2; exit }'
}

stale=0
failed=0
work="$(mktemp -d)"
list="$work/list"
trap 'rm -rf "$work"' EXIT
# The same image is pinned in several files: ask the registry once for each.
asked() {
    mark="$work/$(printf '%s' "$1:$2" | tr '/:' '__')"
    [ -f "$mark" ] || { current_digest "$1" "$2" > "$mark" || : ; }
    cat "$mark"
}
for file in "$@"; do
    # Lines like:   container: fedora:44@sha256:<64 hex>  # pinned; bump on purpose
    grep -nE '^[[:space:]]*container:[[:space:]]' "$file" | while IFS= read -r hit; do
        line="${hit%%:*}"
        ref="$(printf '%s\n' "${hit#*:}" | sed -E 's/^[[:space:]]*container:[[:space:]]*//; s/[[:space:]]*#.*$//')"
        echo "$line $ref"
    done > "$list"
    while read -r line ref; do
        case "$ref" in
            *@sha256:*) ;;
            *) echo "::error file=$file,line=$line,title=Image not pinned by digest::$ref has no @sha256: digest"; stale=1; continue ;;
        esac
        pinned="${ref#*@}"
        image="${ref%@*}"
        name="${image%%:*}"
        tag=latest
        case "$image" in *:*) tag="${image#*:}" ;; esac
        case "$name" in
            */*|*.*) echo "::error file=$file,line=$line,title=Registry not supported::$name is not a Docker Hub official image; check its pin by hand"; stale=1; continue ;;
        esac
        now="$(asked "$name" "$tag")"
        case "$now" in
            sha256:[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]*) ;;
            *) echo "::error file=$file,line=$line,title=Could not ask the registry::no digest for $name:$tag"; failed=1; continue ;;
        esac
        if [ "$now" = "$pinned" ]; then
            echo "$name:$tag is current ($pinned)"
        else
            echo "::error file=$file,line=$line,title=$name:$tag has a newer image::In $file line $line change $pinned to $now (the registry serves it for $name:$tag now), run the tests, and commit."
            stale=1
        fi
    done < "$list"
done
[ "$stale" -eq 0 ] || exit 1
[ "$failed" -eq 0 ] || exit 2
exit 0
