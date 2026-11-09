#!/bin/bash
# Fedora Glass release checks on a test desktop that matches Dino's PC as closely as a
# container can: GNOME 50 on Wayland, 125 % scaling, Orchis Dark, Dino's extensions and
# settings, the overview off, a terminal, Files and an Electron window.
#
#   qa/desktop/run.sh [--source DIR] [--only looks,leftovers,resize,speed,lock,restart,log,spawn]
#                     [--update-references] [--out DIR] [--keep] [--start-only] [--screen WxH]
#
# --source              the Fedora Glass tree to test (default: this checkout). Lets you run
#                       today's checks against an older release.
# --from DIR            also check the upgrade from an older tree (Fedora Glass before 1.5.0) (the last
#                       release): it is applied first, then this version arrives the way
#                       dnf upgrade brings it, with two restarts and no Apply.
# --update-references   save this run's pictures as the new reference pictures.
# --start-only          start the test desktop and leave it running (for working on the checks).
# --screen WxH          size of each of the two screens in real pixels (default 2000x1125).
#                       --screen 2560x1440 is Dino's PC. Pictures are compared only at sizes
#                       that have their own reference pictures (references/WxH/).
# --gnome 50|51         the GNOME version (default 50: Ubuntu 26.04; 51: Ubuntu 26.10). GNOME 51 keeps
#                       its own reference pictures in references/gnome51/ (and gnome51/WxH/).
# --ubuntu-desktop      instead of Dino's desktop: the stock Ubuntu desktop (Ubuntu Dock, Desktop
#                       Icons, Yaru, Ubuntu's defaults) on that GNOME's Ubuntu, one screen at 100 %,
#                       and the Ubuntu checks (Apply and Restore original from the running desktop).
#                       WxH@R sets the refresh rate too: --screen 2560x1440@144.
# --stock-desktop       instead of Dino's desktop: stock GNOME as it ships (top bar, Activities, the
#                       overview's dash, Adwaita), no extensions, one screen at 100 %, and the stock
#                       checks (Apply, the overview's dash and search, Restore original).
# --with-dock           with --stock-desktop: Dash to Dock on, as many stock users add it.
# LGQA_BUILD_ARGS / LGQA_RUN_ARGS: extra arguments for docker build / docker run (podman on SELinux
#                       needs LGQA_RUN_ARGS="--security-opt label=disable" to read the mounted folders).
# Exit code: 0 all passed, 1 a check failed, 2 the test desktop did not start.
set -euo pipefail
SUITE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$SUITE/../.." && pwd)
SRC=$ROOT OUT=$ROOT/qa-report ONLY="" UPDATE="" KEEP="" START_ONLY="" FROM="" SCREEN=2000x1125 GNOME=50 UBUNTU="" STOCK="" STOCK_EXTS="" NAME=${LGQA_NAME:-lgqa-$$}
while [ $# -gt 0 ]; do
    case $1 in
        --source) SRC=$(cd "$2" && pwd); shift ;;
        --from) FROM=$(cd "$2" && pwd); shift ;;
        --only) ONLY="--only $2"; shift ;;
        --update-references) UPDATE=--update-references ;;
        --out) OUT=$2; shift ;;
        --keep) KEEP=1 ;;
        --screen) SCREEN=$2; shift ;;
        --gnome) GNOME=$2; shift ;;
        --ubuntu-desktop) UBUNTU=1 ;;
        --stock-desktop) STOCK=1 ;;
        --with-dock) STOCK_EXTS=dash-to-dock@micxgx.gmail.com ;;
        --start-only) KEEP=1 START_ONLY=1 ;;
        *) echo "unknown option $1" >&2; exit 64 ;;
    esac
    shift
done

if ! [[ $SCREEN =~ ^[1-9][0-9]{2,3}x[1-9][0-9]{2,3}(@[1-9][0-9]{1,2})?$ ]]; then echo "--screen needs a size like 2560x1440 (or 2560x1440@144 for a 144 Hz screen)" >&2; exit 64; fi

# What changes with the GNOME version: the Ubuntu release under it (pinned by digest) and the
# extensions whose releases follow GNOME (the rest support both at the pinned commits).
case $GNOME in
    50) IMAGE=lgqa-desktop GNOME_ARGS=() ;;
    51) IMAGE=lgqa-desktop-51
        GNOME_ARGS=(--build-arg BASE=mirror.gcr.io/library/ubuntu@sha256:262df65c0ec6bf8d9dcc87454f4330a05fae4b97825f45854af3b136666584c2
                    --build-arg EXTLIST=c0c996c7bdf538e777ecfadef04f5a8fd771e88c     # Extension List 51.1
                    --build-arg EXTLIST_SHELL=51) ;;
    *) echo "--gnome needs 50 or 51" >&2; exit 64 ;;
esac

echo "Building the GNOME $GNOME test desktop image (cached after the first time)..."
docker build -q -t "$IMAGE" "${GNOME_ARGS[@]}" ${LGQA_BUILD_ARGS:-} "$SUITE" >/dev/null
SESSION=session CHECKS=run_checks.py
if [ -n "$UBUNTU" ]; then
    echo "Adding the stock Ubuntu desktop on top..."
    docker build -q -t "$IMAGE-ubuntu" --build-arg IMAGE="$IMAGE" -f "$SUITE/Dockerfile.ubuntu" ${LGQA_BUILD_ARGS:-} "$SUITE" >/dev/null
    IMAGE=$IMAGE-ubuntu SESSION=ubuntu-session CHECKS=ubuntu_checks.py
    [ -z "$ONLY$UPDATE" ] || { echo "--only and --update-references are for Dino's desktop" >&2; exit 64; }
fi
if [ -n "$STOCK" ]; then
    [ -z "$UBUNTU" ] || { echo "--stock-desktop and --ubuntu-desktop are two different desktops" >&2; exit 64; }
    echo "Adding Dash to Dock for the stock GNOME desktop..."
    docker build -q -t "$IMAGE-stock" --build-arg IMAGE="$IMAGE" -f "$SUITE/Dockerfile.stock" ${LGQA_BUILD_ARGS:-} "$SUITE" >/dev/null
    IMAGE=$IMAGE-stock SESSION=stock-session CHECKS=stock_checks.py
    [ -z "$ONLY$UPDATE" ] || { echo "--only and --update-references are for Dino's desktop" >&2; exit 64; }
elif [ -n "$STOCK_EXTS" ]; then
    echo "--with-dock goes with --stock-desktop" >&2; exit 64
fi

rm -rf "$OUT"; mkdir -p "$OUT"; chmod 0777 "$OUT"
cleanup() { [ -n "$KEEP" ] || docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# No network inside: nothing at run time needs it.
docker run -d --name "$NAME" --network none --hostname lgqa --shm-size 1g -e LGQA_SCREEN="$SCREEN" -e LGQA_GNOME="$GNOME" -e LGQA_SESSION="$SESSION" -e LGQA_STOCK_EXTS="$STOCK_EXTS" ${LGQA_RUN_ARGS:-} \
    -v "$SRC":/src:ro -v "$SUITE":/opt/lgqa/suite:ro -v "$OUT":/out ${FROM:+-v "$FROM":/from:ro} \
    "$IMAGE" /opt/lgqa/suite/container/start.sh >/dev/null

for _ in $(seq 120); do
    docker logs "$NAME" 2>&1 | grep -q READY && break
    if ! docker inspect -f '{{.State.Running}}' "$NAME" | grep -q true; then break; fi
    sleep 2
done
if ! docker logs "$NAME" 2>&1 | grep -q READY; then
    echo "The test desktop did not start. Last lines of its log:" >&2
    docker logs "$NAME" 2>&1 | tail -20 >&2
    tail -40 "$OUT/shell.log" >&2 2>/dev/null || true
    exit 2
fi

if [ -n "$START_ONLY" ]; then echo "Test desktop $NAME is running."; exit 0; fi
set +e
docker exec -u dino -e LGQA_OUT=/out "$NAME" python3 "/opt/lgqa/suite/checks/$CHECKS" $ONLY $UPDATE
rc=$?
set -e
if [ -n "$UPDATE" ] && [ -d "$OUT/new-references" ]; then
    REFDIR="$SUITE/references"; [ "$GNOME" = 50 ] || REFDIR="$REFDIR/gnome$GNOME"
    [ "${SCREEN%@*}" = 2000x1125 ] || REFDIR="$REFDIR/${SCREEN%@*}"
    mkdir -p "$REFDIR"
    cp "$OUT"/new-references/*.png "$REFDIR/"
    echo "Reference pictures updated in $REFDIR."
fi
echo "Report: $OUT/report/report.html"
exit $rc
