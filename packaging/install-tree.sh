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
find "$dest/usr/share/fedora-glass" -name '__pycache__' -prune -exec rm -rf {} +
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

# Opt-in glass on the login screen: the only part that runs as root, through pkexec.
install -Dm755 "$src/fedoraglass/login_screen.py" "$dest/usr/libexec/liquid-glass-login-screen"
install -Dm644 "$src/data/io.github.djshiye.LiquidGlass.policy" "$dest/usr/share/polkit-1/actions/io.github.djshiye.LiquidGlass.policy"

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

install -Dm644 "$src/LICENSE" "$dest/usr/share/licenses/fedora-glass/LICENSE"
install -Dm644 "$src/LICENSES/Apache-2.0.txt" "$dest/usr/share/licenses/fedora-glass/Apache-2.0.txt"
install -Dm644 "$src/THIRD-PARTY-NOTICES.md" "$dest/usr/share/licenses/fedora-glass/THIRD-PARTY-NOTICES.md"
