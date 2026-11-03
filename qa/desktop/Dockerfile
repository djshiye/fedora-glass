# Test desktop for the release checks: GNOME 50 on Wayland (headless, software GL),
# with Dino's extension set, Orchis, Ptyxis, Files, and an Electron window.
#
# Every download is pinned: the base image by digest, each extension by git commit
# (checked after cloning), Orchis by tag commit, Electron by SHA-256. Extensions are
# put together with glib tools only; no third-party build script runs.
FROM mirror.gcr.io/library/ubuntu@sha256:6a06111c3b0a8600feadb270aec771dc239bf407b25625f93f44ab00e11f4d3c

ENV DEBIAN_FRONTEND=noninteractive

# Only for sandboxes that intercept HTTPS: drop a CA into extra-ca/ (git-ignored). Empty in CI.
COPY extra-ca/ /usr/local/share/ca-certificates/extra/
RUN set -e; if ls /usr/local/share/ca-certificates/extra/*.crt >/dev/null 2>&1; then \
      sed -i 's|http://|https://|g' /etc/apt/sources.list.d/ubuntu.sources; \
      echo 'Acquire::https::CAInfo "/usr/local/share/ca-certificates/extra/proxy.crt";' > /etc/apt/apt.conf.d/99extra-ca; \
    fi; \
    apt-get update -qq; \
    apt-get install -y -qq --no-install-recommends ca-certificates >/dev/null; update-ca-certificates >/dev/null

RUN apt-get install -y -qq --no-install-recommends \
      gnome-shell gnome-shell-extensions gnome-shell-extension-prefs mutter xwayland dbus dbus-x11 gjs gnome-menus \
      gsettings-desktop-schemas libglib2.0-bin libglib2.0-dev-bin dconf-cli \
      nautilus ptyxis adwaita-icon-theme fonts-cantarell fonts-dejavu-core \
      python3 python3-gi python3-numpy python3-pil git curl unzip libxml2-utils procps xz-utils \
      libnss3 libatk-bridge2.0-0t64 libgtk-3-0t64 libgbm1 libasound2t64 libcups2t64 libxss1 libxtst6 libsecret-1-0 \
      libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libnotify4 >/dev/null \
    && rm -rf /var/lib/apt/lists/*

# ---- Pinned third-party pieces ------------------------------------------------------------
ARG DTP=db578c4f0061686609ed0bd1422967dfee2554d6        # Dash to Panel v74
ARG ARCMENU=c0b8a4d3e303e1d8abce1cf069b01ec6a6fa7b80    # ArcMenu v70.0
ARG BMS=b1e415cc5ff3dffef72a69b552d8c64ae7d28a45        # Blur my Shell v77
ARG JP=ae48fd2d75a5747bbda1bdb2b039e9a3384ddf4c         # Just Perfection 37.0
ARG APPIND=52da5222a17f7a862e8a47d2bc523f29abf59964     # AppIndicator v66
ARG EXTLIST=8f5b9366a245f1b50a60b1f07f423d5fa9454aca    # Extension List 50.2
ARG DEJA=c2cac5444a1bd56e6a287f0d688728cfea4bf7c4       # Deja Window (no tags; 2026-10-10)
ARG ORCHIS=29975e38624ec93d8e460f8ea17129bcb68c05ef     # Orchis 2026-07-07
ARG ELECTRON=v44.10.1
ARG ELECTRON_SHA256=2be868b71b0aa71f30e6b5567a106a35a049385e963183c074aad1975ead5167

COPY assemble-extensions.sh /opt/lgqa/assemble-extensions.sh
RUN bash /opt/lgqa/assemble-extensions.sh \
      "home-sweet-gnome/dash-to-panel@$DTP" "gitlab:arcmenu/ArcMenu@$ARCMENU" "aunetx/blur-my-shell@$BMS" \
      "jrahmatzadeh/just-perfection@$JP" "ubuntu/gnome-shell-extension-appindicator@$APPIND" \
      "tuberry/extension-list@$EXTLIST" "ihpled/deja-window@$DEJA" "vinceliuice/Orchis-theme@$ORCHIS"

RUN set -e; cd /tmp; \
    curl -sSfL -o electron.zip "https://github.com/electron/electron/releases/download/$ELECTRON/electron-$ELECTRON-linux-x64.zip"; \
    echo "$ELECTRON_SHA256  electron.zip" | sha256sum -c --quiet; \
    mkdir -p /opt/electron && unzip -q electron.zip -d /opt/electron && rm electron.zip

# Ptyxis starts shells through systemd-run, which a container does not have.
RUN printf '#!/bin/sh\nwhile [ "${1#-}" != "$1" ]; do shift; done\nexec "$@"\n' > /usr/local/bin/systemd-run && chmod 755 /usr/local/bin/systemd-run

COPY make-wallpaper.py /opt/lgqa/
RUN python3 /opt/lgqa/make-wallpaper.py /opt/lgqa/wallpaper.png

# The checks, app scripts and settings are not baked in: run.sh mounts this folder at
# /opt/lgqa/suite, so the image only changes when a pinned piece changes.
RUN usermod -l dino -d /home/dino -m ubuntu && groupmod -n dino ubuntu
