#!/bin/bash
# Fedora Glass release checks on a test desktop that matches Dino's PC as closely as a
# container can: GNOME 50 on Wayland, 125 % scaling, Orchis Dark, Dino's extensions and
# settings, the overview off, a terminal, Files and an Electron window.
#
#   qa/desktop/run.sh [--source DIR] [--only looks,leftovers,resize,speed,lock,restart,log]
#                     [--update-references] [--out DIR] [--keep] [--start-only] [--screen WxH]
#
# --source              the Fedora Glass tree to test (default: this checkout). Lets you run
#                       today's checks against an older release.
# --from DIR            also check the upgrade from an older tree (Liquid Glass before 1.5.0) (the last
#                       release): it is applied first, then this version arrives the way
#                       dnf upgrade brings it, with two restarts and no Apply.
# --update-references   save this run's pictures as the new reference pictures.
# --start-only          start the test desktop and leave it running (for working on the checks).
# --screen WxH          size of each of the two screens in real pixels (default 2000x1125).
#                       --screen 2560x1440 is Dino's PC. Pictures are compared only at sizes
#                       that have their own reference pictures (references/WxH/).
# Exit code: 0 all passed, 1 a check failed, 2 the test desktop did not start.
set -euo pipefail
SUITE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$SUITE/../.." && pwd)
SRC=$ROOT OUT=$ROOT/qa-report ONLY="" UPDATE="" KEEP="" START_ONLY="" FROM="" SCREEN=2000x1125 NAME=${LGQA_NAME:-lgqa-$$}
while [ $# -gt 0 ]; do
    case $1 in
        --source) SRC=$(cd "$2" && pwd); shift ;;
        --from) FROM=$(cd "$2" && pwd); shift ;;
        --only) ONLY="--only $2"; shift ;;
        --update-references) UPDATE=--update-references ;;
        --out) OUT=$2; shift ;;
        --keep) KEEP=1 ;;
        --screen) SCREEN=$2; shift ;;
        --start-only) KEEP=1 START_ONLY=1 ;;
        *) echo "unknown option $1" >&2; exit 64 ;;
    esac
    shift
done

if ! [[ $SCREEN =~ ^[1-9][0-9]{2,3}x[1-9][0-9]{2,3}$ ]]; then echo "--screen needs a size like 2560x1440" >&2; exit 64; fi

echo "Building the test desktop image (cached after the first time)..."
docker build -q -t lgqa-desktop ${LGQA_BUILD_ARGS:-} "$SUITE" >/dev/null

rm -rf "$OUT"; mkdir -p "$OUT"; chmod 0777 "$OUT"
cleanup() { [ -n "$KEEP" ] || docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# No network inside: nothing at run time needs it.
docker run -d --name "$NAME" --network none --hostname lgqa --shm-size 1g -e LGQA_SCREEN="$SCREEN" \
    -v "$SRC":/src:ro -v "$SUITE":/opt/lgqa/suite:ro -v "$OUT":/out ${FROM:+-v "$FROM":/from:ro} \
    lgqa-desktop /opt/lgqa/suite/container/start.sh >/dev/null

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
docker exec -u dino -e LGQA_OUT=/out "$NAME" python3 /opt/lgqa/suite/checks/run_checks.py $ONLY $UPDATE
rc=$?
set -e
if [ -n "$UPDATE" ] && [ -d "$OUT/new-references" ]; then
    REFDIR="$SUITE/references"; [ "$SCREEN" = 2000x1125 ] || REFDIR="$REFDIR/$SCREEN"
    mkdir -p "$REFDIR"
    cp "$OUT"/new-references/*.png "$REFDIR/"
    echo "Reference pictures updated in $REFDIR."
fi
echo "Report: $OUT/report/report.html"
exit $rc
