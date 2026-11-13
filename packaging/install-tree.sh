#!/bin/sh
# Puts Fedora Glass's files into a package tree, for the Ubuntu (.deb) and Arch
# (.pkg.tar.zst) packages. The Fedora RPM (fedora-glass.spec) lays out the same files.
#
#   packaging/install-tree.sh SOURCE_DIR DEST_DIR
#
# Paths are the same on all three: /usr/share/fedora-glass, /usr/bin, /usr/libexec (the
# polkit policy names /usr/libexec/liquid-glass-login-screen), /usr/lib/systemd/user.
set -eu
src="$1"
dest="$2"

install -d "$dest/usr/share/fedora-glass"
cp -r "$src/fedoraglass" "$dest/usr/share/fedora-glass/"
# Stray byte code from a working copy is dropped (other Python, other paths), and ours is
# made fresh: nobody can write next to the code under /usr/share, so without it every start
# would compile the whole app again in memory. unchecked-hash: the file's date is not part
# of it (the same bytes on every build) and the package never changes a .py behind its back.
find "$dest/usr/share/fedora-glass" -name '__pycache__' -prune -exec rm -rf {} +
python3 -I -m compileall -q --invalidation-mode unchecked-hash -d /usr/share/fedora-glass "$dest/usr/share/fedora-glass"
find "$dest/usr/share/fedora-glass" -type d -exec chmod 755 {} +
find "$dest/usr/share/fedora-glass" -type f -exec chmod 644 {} +

# -I keeps Python from importing anything from the current folder or PYTHONPATH.
install -d "$dest/usr/bin"
cat > "$dest/usr/bin/fedora-glass" <<'LAUNCHER'
#!/bin/sh
exec /usr/bin/python3 -I -c 'import sys; sys.path.insert(0, "/usr/share/fedora-glass"); from fedoraglass.__main__ import main; sys.exit(main())' "$@"
LAUNCHER
chmod 755 "$dest/usr/bin/fedora-glass"
# The old command name keeps working (older copies of the Shell extension call it).
ln -sf fedora-glass "$dest/usr/bin/liquid-glass"

install -Dm644 "$src/data/io.github.djshiye.LiquidGlass.desktop" "$dest/usr/share/applications/io.github.djshiye.LiquidGlass.desktop"
sed -i 's|^Exec=.*|Exec=fedora-glass gui|' "$dest/usr/share/applications/io.github.djshiye.LiquidGlass.desktop"
install -Dm644 "$src/data/icons/io.github.djshiye.LiquidGlass.svg" "$dest/usr/share/icons/hicolor/scalable/apps/io.github.djshiye.LiquidGlass.svg"
# What software centres (GNOME Software, Discover) show about the app.
install -Dm644 "$src/data/io.github.djshiye.LiquidGlass.metainfo.xml" "$dest/usr/share/metainfo/io.github.djshiye.LiquidGlass.metainfo.xml"

# The mouse pointer styles (built by packaging/cursors/build.py): checked against their
# checksums, then unpacked where every app and the login screen can find them.
python3 -I "$src/packaging/cursors/unpack.py" "$src" "$dest/usr/share/icons"

# Opt-in glass on the login screen: the only part that runs as root, through pkexec.
install -Dm755 "$src/fedoraglass/login_screen.py" "$dest/usr/libexec/liquid-glass-login-screen"
install -Dm644 "$src/data/io.github.djshiye.LiquidGlass.policy" "$dest/usr/share/polkit-1/actions/io.github.djshiye.LiquidGlass.policy"

# The glass login screen (opt-in; the contract of the pieces is in the helper's header).
# The root helper, one self-contained file, run by pkexec, by the boot-time guard and by
# `sudo fedora-glass login-screen`. The polkit file above names it for its second action.
install -Dm755 "$src/fedoraglass/login_glass.py" "$dest/usr/libexec/fedora-glass-login"

# The add-on the login screen's own GNOME Shell loads (GDM puts /usr/share/gdm/greeter
# first in the greeter's data folders, so normal sessions never see it). Root-owned, as
# the greeter only reads it.
login_ext=fedora-glass-login@djshiye.github.io
login_dir="$dest/usr/share/gdm/greeter/gnome-shell/extensions/$login_ext"
install -d "$login_dir"
cp -r "$src/fedoraglass/data/login-extension/$login_ext/." "$login_dir/"
# Files it shares with the desktop extension are copied in, one name per line in the list
# (blank lines and # comments ignored). A name that is missing, or that tries to leave
# the folder, stops the build: a half-built add-on must never ship.
shared_list="$src/fedoraglass/data/login-extension/shared-modules.txt"
shared_dir="$src/fedoraglass/data/extension/liquid-glass@djshiye.github.io"
shared_count=0
while IFS= read -r name; do
    [ -n "$name" ] || continue
    case "$name" in */*|.*) echo "bad name in shared-modules.txt: $name" >&2; exit 1 ;; esac
    [ -f "$shared_dir/$name" ] || { echo "shared module missing: $name" >&2; exit 1; }
    install -m644 "$shared_dir/$name" "$login_dir/$name"
    shared_count=$((shared_count + 1))
done <<LIST
$(sed -e 's/#.*//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' "$shared_list")
LIST
[ "$shared_count" -gt 0 ] || { echo "shared-modules.txt lists nothing" >&2; exit 1; }
find "$login_dir" -name '__pycache__' -prune -exec rm -rf {} +
find "$login_dir" -type d -exec chmod 755 {} +
find "$login_dir" -type f -exec chmod 644 {} +

# The boot-time guard: before the display manager it turns the login screen glass off by
# itself if the last start crashed, nobody could log in, or fedora-glass-login=off is on
# the kernel line. Both units do nothing unless the feature is on (ConditionPathExists),
# and the links are shipped, so no `systemctl enable` is needed, also on an upgrade.
for unit in fedora-glass-login-guard.service fedora-glass-login-guard-check.path fedora-glass-login-guard-check.service; do
    install -Dm644 "$src/data/systemd/$unit" "$dest/usr/lib/systemd/system/$unit"
done
install -d "$dest/usr/lib/systemd/system/graphical.target.wants"
ln -sf ../fedora-glass-login-guard.service "$dest/usr/lib/systemd/system/graphical.target.wants/fedora-glass-login-guard.service"
ln -sf ../fedora-glass-login-guard-check.path "$dest/usr/lib/systemd/system/graphical.target.wants/fedora-glass-login-guard-check.path"

# Removing the package runs this first: Restore original for each person, as them.
install -Dm755 "$src/packaging/undo-for-users.sh" "$dest/usr/libexec/fedora-glass-undo-for-users"
# And this: stops the dark/light watcher in running sessions (the rpm's macros do it there).
install -Dm755 "$src/packaging/stop-watchers.sh" "$dest/usr/libexec/fedora-glass-stop-watchers"

install -d "$dest/usr/lib/systemd/user"
cat > "$dest/usr/lib/systemd/user/liquid-glass-watch.service" <<'UNIT'
[Unit]
Description=Fedora Glass: follow GNOME dark and light style
PartOf=graphical-session.target
After=graphical-session.target

[Service]
ExecStart=/usr/bin/fedora-glass watch
Restart=on-failure
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=graphical-session.target
UNIT
chmod 644 "$dest/usr/lib/systemd/user/liquid-glass-watch.service"
# Brings the glass up to date at the first login after an update installed while logged
# out. Pulled in by GNOME's own session target through the link, so an upgrade turns it on too.
cat > "$dest/usr/lib/systemd/user/fedora-glass-before-login.service" <<'UNIT'
[Unit]
Description=Fedora Glass: bring the glass up to date before GNOME Shell starts
# An update installed while logged out would otherwise need a second restart (see
# `fedora-glass before-login`). GNOME's session manager, and with it GNOME Shell, starts
# after gnome-session-pre.target; outside GNOME nothing pulls this in.
Before=gnome-session-pre.target

[Service]
Type=oneshot
ExecStart=/usr/bin/fedora-glass before-login
TimeoutStartSec=20
NoNewPrivileges=true
UNIT
chmod 644 "$dest/usr/lib/systemd/user/fedora-glass-before-login.service"
install -d "$dest/usr/lib/systemd/user/gnome-session-pre.target.wants"
ln -sf ../fedora-glass-before-login.service "$dest/usr/lib/systemd/user/gnome-session-pre.target.wants/fedora-glass-before-login.service"

install -Dm644 "$src/LICENSE" "$dest/usr/share/licenses/fedora-glass/LICENSE"
install -Dm644 "$src/LICENSES/Apache-2.0.txt" "$dest/usr/share/licenses/fedora-glass/Apache-2.0.txt"
install -Dm644 "$src/LICENSES/GPL-3.0.txt" "$dest/usr/share/licenses/fedora-glass/GPL-3.0.txt"
install -Dm644 "$src/LICENSES/GPL-2.0.txt" "$dest/usr/share/licenses/fedora-glass/GPL-2.0.txt"
install -Dm644 "$src/LICENSES/CC-BY-SA-4.0.txt" "$dest/usr/share/licenses/fedora-glass/CC-BY-SA-4.0.txt"
install -Dm644 "$src/THIRD-PARTY-NOTICES.md" "$dest/usr/share/licenses/fedora-glass/THIRD-PARTY-NOTICES.md"
