# Test desktop for the release checks: GNOME 50 on Wayland (headless, software GL),
# with Dino's extension set, Orchis, Ptyxis, Files, and an Electron window.
#
# Every download is pinned: the base image by digest, each extension by git commit
# (checked after cloning), Orchis by tag commit, Electron and Spawn by SHA-256. Extensions
# are put together with glib tools only; no third-party build script runs.
# The base decides the GNOME version: Ubuntu 26.04 has GNOME 50 (the default), Ubuntu 26.10
# GNOME 51 (run.sh --gnome 51 passes its digest and the GNOME 51 pins below).
ARG BASE=mirror.gcr.io/library/ubuntu@sha256:6a06111c3b0a8600feadb270aec771dc239bf407b25625f93f44ab00e11f4d3c
FROM $BASE

ENV DEBIAN_FRONTEND=noninteractive

# Only for sandboxes that intercept HTTPS: drop a CA into extra-ca/ (git-ignored). Empty in CI.
COPY extra-ca/ /usr/local/share/ca-certificates/extra/
RUN set -e; if ls /usr/local/share/ca-certificates/extra/*.crt >/dev/null 2>&1; then \
      sed -i 's|http://|https://|g' /etc/apt/sources.list.d/ubuntu.sources; \
      echo 'Acquire::https::CAInfo "/usr/local/share/ca-certificates/extra/proxy.crt";' > /etc/apt/apt.conf.d/99extra-ca; \
    fi; \
    apt-get update -qq; \
    apt-get install -y -qq --no-install-recommends ca-certificates >/dev/null; update-ca-certificates >/dev/null

# The package mirror drops a download now and then (seen three times in one day on the
# GNOME 51 base). Each download is retried, and a failed install gets a fresh package list
# and two more tries. apt's own messages are printed when a try fails, so the cause shows.
RUN set -e; n=1; \
    until apt-get install -y -qq --no-install-recommends -o Acquire::Retries=3 \
      gnome-shell gnome-shell-extensions gnome-shell-extension-prefs mutter xwayland dbus dbus-x11 gjs gnome-menus \
      gsettings-desktop-schemas libglib2.0-bin libglib2.0-dev-bin dconf-cli \
      nautilus ptyxis gedit adwaita-icon-theme fonts-cantarell fonts-dejavu-core \
      python3 python3-gi python3-numpy python3-pil git curl unzip libxml2-utils procps xz-utils libarchive-tools \
      libnss3 libatk-bridge2.0-0t64 libgtk-3-0t64 libgbm1 libasound2t64 libcups2t64 libxss1 libxtst6 libsecret-1-0 \
      libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libnotify4 >/tmp/apt.log 2>&1; do \
      echo "Package install try $n failed:"; tail -n 30 /tmp/apt.log; \
      [ "$n" -lt 3 ] || exit 1; n=$((n+1)); sleep 20; apt-get update -qq || true; \
    done; \
    rm -rf /var/lib/apt/lists/* /tmp/apt.log

# ---- Pinned third-party pieces ------------------------------------------------------------
ARG DTP=db578c4f0061686609ed0bd1422967dfee2554d6        # Dash to Panel v74
ARG ARCMENU=c0b8a4d3e303e1d8abce1cf069b01ec6a6fa7b80    # ArcMenu v70.0
ARG BMS=b1e415cc5ff3dffef72a69b552d8c64ae7d28a45        # Blur my Shell v77
ARG JP=ae48fd2d75a5747bbda1bdb2b039e9a3384ddf4c         # Just Perfection 37.0
ARG APPIND=52da5222a17f7a862e8a47d2bc523f29abf59964     # AppIndicator v66
ARG EXTLIST=8f5b9366a245f1b50a60b1f07f423d5fa9454aca    # Extension List 50.2 (GNOME 51: 51.1, set by run.sh)
ARG EXTLIST_SHELL=50                                     # the one GNOME version Extension List's metadata names
ARG DEJA=c2cac5444a1bd56e6a287f0d688728cfea4bf7c4       # Deja Window (no tags; 2026-10-10)
ARG ORCHIS=29975e38624ec93d8e460f8ea17129bcb68c05ef     # Orchis 2026-07-07
ARG ELECTRON=v44.10.1
ARG ELECTRON_SHA256=2be868b71b0aa71f30e6b5567a106a35a049385e963183c074aad1975ead5167
# Spawn (the owner's own ArcMenu replacement) is only published as a noarch RPM in a DNF repository,
# which keeps just its newest 3 builds. The URL is that build's file at a fixed gh-pages commit,
# which stays reachable however many builds follow. Content is checked by SHA-256 as well.
ARG SPAWN_RPM=gnome-shell-extension-spawn-1.0.0-1.46.fc45.noarch.rpm
# (gh-pages commit "Publish gnome-shell-extension-spawn-1.0.0-1.46")
ARG SPAWN_REPO_COMMIT=9fcbc1b9c946992643fbbc82ba04a031a09d4657
ARG SPAWN_SHA256=c9eeec61d2e4d603223caef0347ca812619f62a880ce62eebdaca28e739491a6

COPY assemble-extensions.sh /opt/lgqa/assemble-extensions.sh
RUN EXTLIST_SHELL=$EXTLIST_SHELL bash /opt/lgqa/assemble-extensions.sh \
      "home-sweet-gnome/dash-to-panel@$DTP" "gitlab:arcmenu/ArcMenu@$ARCMENU" "aunetx/blur-my-shell@$BMS" \
      "jrahmatzadeh/just-perfection@$JP" "ubuntu/gnome-shell-extension-appindicator@$APPIND" \
      "tuberry/extension-list@$EXTLIST" "ihpled/deja-window@$DEJA" "vinceliuice/Orchis-theme@$ORCHIS"

RUN set -e; cd /tmp; \
    curl -sSfL -o electron.zip "https://github.com/electron/electron/releases/download/$ELECTRON/electron-$ELECTRON-linux-x64.zip"; \
    echo "$ELECTRON_SHA256  electron.zip" | sha256sum -c --quiet; \
    mkdir -p /opt/electron && unzip -q electron.zip -d /opt/electron && rm electron.zip

# Spawn: unpacked from its RPM the way dnf puts it on a PC, extension and schema in the system
# folders (bsdtar reads RPM files; no scriptlet runs). It stays switched off in the normal session,
# because Dino's PC runs ArcMenu; the "spawn" check switches it on.
RUN set -e; d=$(mktemp -d); cd "$d"; \
    curl -sSfL -o spawn.rpm "https://raw.githubusercontent.com/djshiye/spawn/$SPAWN_REPO_COMMIT/fedora-45/$SPAWN_RPM"; \
    echo "$SPAWN_SHA256  spawn.rpm" | sha256sum -c --quiet; \
    mkdir root && bsdtar -xf spawn.rpm -C root; \
    cp -r root/usr/share/gnome-shell/extensions/spawn@djshiye.github.io /usr/share/gnome-shell/extensions/; \
    cp root/usr/share/glib-2.0/schemas/org.gnome.shell.extensions.spawn.gschema.xml /usr/share/glib-2.0/schemas/; \
    glib-compile-schemas --strict /usr/share/glib-2.0/schemas; \
    test -f /usr/share/gnome-shell/extensions/spawn@djshiye.github.io/metadata.json; \
    rm -rf "$d"

# Ptyxis starts shells through systemd-run, which a container does not have.
RUN printf '#!/bin/sh\nwhile [ "${1#-}" != "$1" ]; do shift; done\nexec "$@"\n' > /usr/local/bin/systemd-run && chmod 755 /usr/local/bin/systemd-run

COPY make-wallpaper.py /opt/lgqa/
RUN python3 /opt/lgqa/make-wallpaper.py /opt/lgqa/wallpaper.png

# The checks, app scripts and settings are not baked in: run.sh mounts this folder at
# /opt/lgqa/suite, so the image only changes when a pinned piece changes.
RUN usermod -l dino -d /home/dino -m ubuntu && groupmod -n dino ubuntu
