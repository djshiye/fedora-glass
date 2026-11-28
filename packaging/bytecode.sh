#!/bin/sh
# Keeps the byte code in Fedora Glass's code folder right for this PC's Python. Run as root
# by the package scripts, installed as /usr/libexec/fedora-glass-bytecode:
#
#   fedora-glass-bytecode fit    at the end of an install or an update (rpm and .deb only:
#                                pacman refuses to write over files no package owns, so byte
#                                code made here would block the next Arch upgrade)
#   fedora-glass-bytecode drop   on a removal, before the package manager takes the files
#
# The package ships the byte code of the Python it was built with and names that Python's
# cache tag (cpython-314) in bytecode-tag. A PC with another Python (one rpm serves two
# Fedora releases) cannot use it, and nobody can write next to
# the code, so every start would compile the whole app again. `fit` compiles for this PC's
# Python too, hash-checked: Python compares the source's content, never its date, as all
# files of a release share one date. `drop` takes away all byte code the package did not
# ship, so the package manager can remove the folder. Shipped byte code is never touched.
# After an update of Python alone, the byte code fits again at the next Fedora Glass update.
#
# Nothing is done when the folder or its tag is missing or unusual, links are never
# followed, and it always ends with 0: it must never fail an install or a removal.
# A second argument names another folder (for the tests only).
umask 022
LC_ALL=C
export LC_ALL
dir="${2:-/usr/share/fedora-glass}"
python=/usr/bin/python3

plain() { case "$1" in ''|[!a-z]*|*[!a-z0-9_-]*) return 1 ;; esac; }

case "${1:-}" in fit|drop) ;; *) exit 0 ;; esac
# A slash or a dot at the end would let the link check look through a link.
case "$dir" in */|*/.|*/..) exit 0 ;; esac
{ [ -d "$dir" ] && ! [ -L "$dir" ]; } || exit 0
{ [ -f "$dir/bytecode-tag" ] && ! [ -L "$dir/bytecode-tag" ]; } || exit 0
tag="$(cat "$dir/bytecode-tag" 2>/dev/null)" || exit 0
plain "$tag" || exit 0

# Byte code that is not the package's own: Python's cache folders only, real files only.
find "$dir" -type f -path '*/__pycache__/*.pyc' ! -name "*.$tag.pyc" ! -name "*.$tag.opt-[0-9].pyc" \
    -exec rm -f {} + 2>/dev/null

if [ "$1" = drop ]; then
    find "$dir" -depth -type d -name __pycache__ -exec rmdir {} + 2>/dev/null
    exit 0
fi

[ -x "$python" ] || exit 0
now="$("$python" -I -c 'import sys; print(sys.implementation.cache_tag or "")' 2>/dev/null)" || exit 0
plain "$now" || exit 0
[ "$now" != "$tag" ] || exit 0
# A link inside could lead the compiler's writes out of the folder: then nothing is compiled.
[ -z "$(find "$dir" -type l 2>/dev/null | head -n 1)" ] || exit 0
"$python" -I -m compileall -q --invalidation-mode checked-hash "$dir"
exit 0
