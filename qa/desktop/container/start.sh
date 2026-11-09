#!/bin/bash
# Container entry (root): a system bus, a stand-in for logind (so GNOME Shell starts and
# can lock the screen), then Dino's session as the user "dino".
set -e
cp /opt/lgqa/suite/container/gdm-test.conf /usr/share/dbus-1/system.d/lgqa-gdm-test.conf
mkdir -p /run/dbus /run/systemd/seats && dbus-daemon --system --fork
(gjs /opt/lgqa/suite/container/login1-stub.js >/dev/null 2>&1 &)
sleep 1
mkdir -p /run/user/1000 /out && chown dino:dino /run/user/1000 /out && chmod 700 /run/user/1000
exec runuser -u dino --whitelist-environment=LGQA_SCALE,LGQA_SCREEN,LGQA_GNOME -- "/opt/lgqa/suite/container/${LGQA_SESSION:-session}.sh"
