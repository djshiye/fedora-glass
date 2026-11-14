#!/bin/bash
# Installs, upgrades and removes the built Fedora packages the way dnf does, on a Fedora
# system (the Release workflow runs it in a Fedora container):
#
#   packaging/rpm-install-test.sh OUT_DIR VERSION REPOSITORY      (GH_TOKEN set, gh installed)
#
# 1. the new package on a clean system, then the smoke check, then remove;
# 2. the previous release's package, then the upgrade to the new one, then the smoke check;
# 3. Liquid Glass 1.4.4 (the last release under the old name), then the move to fedora-glass.
# The older packages come from the releases' own assets, checked against that release's
# SHA256SUMS. A step whose old package isn't among the assets is skipped, and says so; one
# whose package can't be fetched or doesn't match fails.
set -euo pipefail
out="$(realpath "$1")" ver="$2" repo="$3"
case "$ver" in *[!0-9.]*|'') echo "bad version: $ver" >&2; exit 1 ;; esac
src="$(cd "$(dirname "$0")/.." && pwd)"
new="$(ls "$out"/fedora-glass-"$ver"-*.noarch.rpm)"
bridge="$(ls "$out"/liquid-glass-"$ver"-*.noarch.rpm)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
# The package's own repository file is switched off: these checks are about the files in
# $out and the old releases, not about what the website serves.
# dnf refuses an option for a repository it doesn't know ("No matching repositories"), and on
# a clean PC there is none until the first package brings its file: so only those that exist.
own_repos_off() {
    local id
    for id in fedora-glass liquid-glass; do
        if grep -qs "^\[$id\]" /etc/yum.repos.d/*.repo; then printf -- '--setopt=%s.enabled=0\n' "$id"; fi
    done
}
dnf_install() { mapfile -t off < <(own_repos_off); dnf install -y -q --setopt=install_weak_deps=False "${off[@]}" "$@" >/dev/null; }
dnf_remove() { mapfile -t off < <(own_repos_off); dnf remove -y -q "${off[@]}" "$@" >/dev/null; }

say() { printf '\n== %s\n' "$*"; }

# Downloads one asset of a release (gh api, as the release page does) and checks it against
# the SHA256SUMS of the same release. Prints the file's path. Returns 2 when the release or
# the asset isn't there (the step is skipped), 1 for anything else: GitHub not answering, a
# download cut short, a file that doesn't match its SHA256SUMS. Every command is checked by
# hand: called as `x="$(fetch ...)" || ...`, set -e is off inside it.
fetch() {
    local tag="$1" name="$2" id d="$work/$1" n err
    mkdir -p "$d" || return 1
    for n in SHA256SUMS "$name"; do
        if ! id="$(gh api "repos/$repo/releases/tags/$tag" --jq ".assets[] | select(.name == \"$n\") | .id" 2>"$d/err")"; then
            err="$(cat "$d/err")"
            echo "could not ask GitHub about release $tag: $err" >&2
            case "$err" in *"HTTP 404"*) return 2 ;; *) return 1 ;; esac
        fi
        [ -n "$id" ] || { echo "$tag has no $n" >&2; return 2; }
        gh api -H 'Accept: application/octet-stream' "repos/$repo/releases/assets/$id" > "$d/$n" ||
            { echo "could not download $n of $tag" >&2; return 1; }
    done
    (cd "$d" && grep " $name\$" SHA256SUMS | sha256sum --quiet -c -) || { echo "$tag $name does not match its SHA256SUMS" >&2; return 1; }
    echo "$d/$name"
}

# fetch for a step that may be skipped: the path, or nothing when the release has no such
# asset. Any other failure ends the run: a step that couldn't be checked must not pass as
# "not tested".
fetch_or_skip() {
    local got rc=0
    got="$(fetch "$@")" || rc=$?
    case "$rc" in
        0) echo "$got" ;;
        2) ;;
        *) echo "fetching $2 of $1 failed" >&2; exit 1 ;;
    esac
}

installed_ok() {
    fedora-glass --version
    [ -f /usr/share/icons/fedora-glass-light/cursors/left_ptr ]
    bash "$src/qa/package-smoke.sh"
}

is_installed() { rpm -q "$1" >/dev/null 2>&1; }

# After a removal nothing is left: the app, and every file of the glass login screen.
gone() {
    if is_installed fedora-glass || is_installed liquid-glass; then return 1; fi
    [ ! -e /usr/share/icons/fedora-glass-light ] && [ ! -e /usr/share/fedora-glass ] || return 1
    # The marker only the main package ships, and its folder.
    [ ! -e /usr/lib/fedora-glass ] || { echo "/usr/lib/fedora-glass is left" >&2; return 1; }
    # The folders the add-on sat in: gdm may own them (then they stay), but a folder that
    # no package owns is one we left behind.
    local d
    for d in /usr/share/gdm /usr/share/gdm/greeter /usr/share/gdm/greeter/gnome-shell /usr/share/gdm/greeter/gnome-shell/extensions; do
        if [ -e "$d" ] && ! rpm -qf "$d" >/dev/null 2>&1; then echo "$d is left behind, owned by no package" >&2; return 1; fi
    done
    bash "$src/qa/package-smoke.sh" --removed
}

# A user's look, applied as that user in their own home (a bare container has no session
# bus), and checked from the file it writes. `liquid-glass` is the command every version
# since the old name has; the checks do not depend on the words a version writes.
# Each look gets a user of its own, so nothing one step left in a home reaches the next.
# What counts is the look in the file, not the exit code: an Apply also says "failed" when
# only some other part could not be done in a bare container. Fails when no look is there.
looks=0 look_home=""
a_look_is_applied() {
    looks=$((looks + 1))
    local user="glassuser$looks"
    look_home="/home/$user"
    useradd -m "$user" || { echo "could not add the test user $user" >&2; exit 1; }
    runuser -u "$user" -- env -i HOME="$look_home" PATH="$PATH" sh -c 'mkdir -p "$HOME/.config/gtk-4.0" &&
        printf "/* my own look */\n" > "$HOME/.config/gtk-4.0/gtk.css" &&
        if command -v dbus-run-session >/dev/null; then dbus-run-session -- liquid-glass apply; else liquid-glass apply; fi' >/dev/null ||
        echo "liquid-glass apply did not end cleanly for $user (checked by the look it left)" >&2
    the_look_is_still_applied
}
the_look_is_still_applied() { [ "$(cat "$look_home/.config/gtk-4.0/gtk.css")" != '/* my own look */' ]; }
the_look_is_undone() { [ "$(cat "$look_home/.config/gtk-4.0/gtk.css")" = '/* my own look */' ]; }
# The tools these checks themselves use. The package asks for runuser too, but dnf takes it
# away again with the package, and a step that starts from an old release must not depend
# on what that release asked for.
for tool in useradd runuser; do
    command -v "$tool" >/dev/null || { echo "this test needs $tool (dnf install shadow-utils util-linux-core)" >&2; exit 1; }
done

say "Clean install of $ver"
dnf_install "$new"
installed_ok
dnf_remove fedora-glass
gone

say "Upgrade from the previous release"
# The newest published release that is older than this one.
# Asked first on its own: a failure inside <(...) would read as "no releases".
tags="$(gh api "repos/$repo/releases?per_page=30" --jq '.[] | select(.draft == false and .prerelease == false) | .tag_name')"
prev=""
while read -r t; do
    [ "$t" != "v$ver" ] || continue
    [ "$(printf '%s\n%s\n' "${t#v}" "$ver" | sort -V | tail -1)" = "$ver" ] || continue
    prev="$t"; break
done < <(printf '%s\n' "$tags" | grep -E '^v[0-9]+(\.[0-9]+)*$' || true)
old=""
if [ -n "$prev" ]; then
    old="$(fetch_or_skip "$prev" fedora-glass.noarch.rpm)"
fi
if [ -n "$old" ]; then
    echo "From $prev to v$ver"
    dnf_install "$old"
    [ "$(rpm -q --qf '%{version}' fedora-glass)" = "${prev#v}" ]
    dnf_install "$new"
    [ "$(rpm -q --qf '%{version}' fedora-glass)" = "$ver" ]
    installed_ok
    dnf_remove fedora-glass
    gone
else
    echo "No earlier release with a fedora-glass package found: upgrade not tested."
fi

say "Move from Liquid Glass 1.4.4 (the old package name)"
old="$(fetch_or_skip v1.4.4 liquid-glass.noarch.rpm)"
if [ -n "$old" ]; then
    # The two ways it happens: dnf upgrade brings the liquid-glass package of this release
    # first (the old repository file only lets that name through), then fedora-glass.
    dnf_install "$old"
    [ "$(rpm -q --qf '%{version}' liquid-glass)" = 1.4.4 ]
    dnf_install "$bridge"
    [ "$(rpm -q --qf '%{version}' liquid-glass)" = "$ver" ]
    a_look_is_applied
    dnf_install "$new"
    if is_installed liquid-glass; then echo "liquid-glass is still installed" >&2; exit 1; fi   # fedora-glass replaced it
    [ "$(rpm -q --qf '%{version}' fedora-glass)" = "$ver" ]
    # The move must not take anybody's look off.
    the_look_is_still_applied
    installed_ok
    dnf_remove fedora-glass
    the_look_is_undone
    gone
    # And straight to fedora-glass, as `dnf install fedora-glass` on an old PC does. Here
    # the look is applied by 1.4.4 itself. If that old version cannot apply one in a bare
    # container, the step runs without a look, and says so: that is not this version's fault.
    dnf_install "$old"
    look=yes
    a_look_is_applied || { look=""; echo "Liquid Glass 1.4.4 could not apply a look here: this step runs without one."; }
    dnf_install "$new"
    if is_installed liquid-glass; then echo "liquid-glass is still installed" >&2; exit 1; fi
    [ -z "$look" ] || the_look_is_still_applied
    installed_ok
    dnf_remove fedora-glass
    [ -z "$look" ] || the_look_is_undone
    gone
    # The old-name package on its own (no fedora-glass to take over): removing it undoes
    # everything, the same as removing fedora-glass does.
    dnf_install "$bridge"
    a_look_is_applied
    dnf_remove liquid-glass
    the_look_is_undone
    gone
else
    echo "No Liquid Glass 1.4.4 package found among the release assets: old-name upgrade not tested."
fi
echo "rpm install and upgrade checks passed"
