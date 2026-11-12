Name:           fedora-glass
Version:        1.5.28
Release:        1%{?dist}
# This package's version-release, fixed here: the liquid-glass package below has its own.
%global fg_evr  %{version}-%{release}
Summary:        Glass theme for Fedora GNOME, with a customizer
License:        MIT AND Apache-2.0 AND GPL-3.0-only AND GPL-2.0-only AND CC-BY-SA-4.0
URL:            https://github.com/djshiye/fedora-glass
Source0:        %{url}/archive/v%{version}/fedora-glass-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  systemd-rpm-macros
# For %%py_byte_compile.
BuildRequires:  python-rpm-macros
# For the tests in %%check.
BuildRequires:  python3
BuildRequires:  python3-pytest
BuildRequires:  python3-gobject
# The login screen tests build a theme with the real GLib tools (gresource and
# glib-compile-resources, the same files the package asks for below); without them they skip.
BuildRequires:  /usr/bin/gresource
BuildRequires:  /usr/bin/glib-compile-resources
# For the store files' checks in %%check.
BuildRequires:  desktop-file-utils
BuildRequires:  appstream
Requires:       python3
Requires:       python3-gobject
Requires:       python3-pyside6
# GNOME 50 or newer, as on Ubuntu. The ~ also lets in Fedora's test releases of 50
# (50~alpha, 50~beta, 50~rc sort before 50.0, and after 50~), and 49.x stays out.
Requires:       gnome-shell >= 50~
Requires:       gnome-shell-extension-user-theme
# For the login screen glass (whichever package has them).
Requires:       /usr/bin/gresource
Requires:       /usr/bin/glib-compile-resources
Requires:       polkit
# runuser: dnf remove puts each person's original look back as that person (undo-for-users),
# with setsid keeping that apart from root's terminal.
Requires:       util-linux-core
Requires:       /usr/bin/setsid
# dnf remove runs the undo as each person inside a private session bus (undo-for-users).
Requires:       /usr/bin/dbus-run-session
Recommends:     adw-gtk3-theme
Recommends:     kvantum

# Fedora Glass was called Liquid Glass up to 1.4.4: this package replaces it, and
# `dnf upgrade` swaps one for the other with the settings kept.
Provides:       liquid-glass = %{fg_evr}
Obsoletes:      liquid-glass < %{fg_evr}

%description
A glass look for GNOME Shell, GTK and Qt apps, Dash to Panel, ArcMenu and Spawn,
drawn by its own GNOME Shell extension, with a Qt app to tune it from clear
liquid glass to calm frost. The app changes only your own user settings and
can restore your original look at any time. Formerly called Liquid Glass.

# A PC set up for Liquid Glass has a dnf repository file that only lets through
# packages named liquid-glass, so it can't see fedora-glass yet. This package
# carries the same app under the old name, plus the new repository file: the
# first `dnf upgrade` installs it, and the next one replaces it with fedora-glass.
%package -n liquid-glass
Version:        %{version}
Release:        0%{?dist}
Summary:        Fedora Glass under its old name, Liquid Glass (moves you to fedora-glass)
Requires:       python3
Requires:       python3-gobject
Requires:       python3-pyside6
Requires:       gnome-shell >= 50~
Requires:       gnome-shell-extension-user-theme
Requires:       /usr/bin/gresource
Requires:       /usr/bin/glib-compile-resources
Requires:       polkit
Requires:       util-linux-core
Requires:       /usr/bin/setsid
Requires:       /usr/bin/dbus-run-session

%description -n liquid-glass
Liquid Glass is now called Fedora Glass. This is the same app under the old
package name, with the repository file for the new name, so the next
`dnf upgrade` moves to the fedora-glass package. Your settings stay as they are.

%prep
%autosetup -n fedora-glass-%{version}

%build
# Pure Python and QML: nothing to build.

%install
install -d %{buildroot}%{_datadir}/fedora-glass
cp -r fedoraglass %{buildroot}%{_datadir}/fedora-glass/
# Stray byte code from a working copy is dropped, and ours is made fresh: nobody can write
# next to the code under /usr/share, so without it every start would compile the app again
# in memory. (Fedora byte-compiles only the system Python folders by itself.)
find %{buildroot}%{_datadir}/fedora-glass -name '__pycache__' -prune -exec rm -rf {} +
%py_byte_compile %{python3} %{buildroot}%{_datadir}/fedora-glass

# -I keeps Python from importing anything from the current folder or PYTHONPATH.
install -d %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/fedora-glass <<'LAUNCHER'
#!/bin/sh
exec /usr/bin/python3 -I -c 'import sys; sys.path.insert(0, "/usr/share/fedora-glass"); from fedoraglass.__main__ import main; sys.exit(main())' "$@"
LAUNCHER
chmod 755 %{buildroot}%{_bindir}/fedora-glass
# The old command name keeps working (older copies of the Shell extension call it).
ln -s fedora-glass %{buildroot}%{_bindir}/liquid-glass

install -Dm644 data/io.github.djshiye.LiquidGlass.desktop %{buildroot}%{_datadir}/applications/io.github.djshiye.LiquidGlass.desktop
sed -i 's|^Exec=.*|Exec=fedora-glass gui|' %{buildroot}%{_datadir}/applications/io.github.djshiye.LiquidGlass.desktop
install -Dm644 data/icons/io.github.djshiye.LiquidGlass.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/io.github.djshiye.LiquidGlass.svg
install -Dm644 data/io.github.djshiye.LiquidGlass.metainfo.xml %{buildroot}%{_datadir}/metainfo/io.github.djshiye.LiquidGlass.metainfo.xml

# The mouse pointer styles (built by packaging/cursors/build.py): checked against their
# checksums, then unpacked where every app and the login screen can find them.
python3 -I packaging/cursors/unpack.py . %{buildroot}%{_datadir}/icons

# Opt-in glass on the login screen: the only part that runs as root, through pkexec
# after your password. Standard library only, run with python3 -I -S.
install -Dm755 fedoraglass/login_screen.py %{buildroot}%{_libexecdir}/liquid-glass-login-screen
install -Dm644 data/io.github.djshiye.LiquidGlass.policy %{buildroot}%{_datadir}/polkit-1/actions/io.github.djshiye.LiquidGlass.policy

# dnf remove runs this first: Restore original for each person with a look applied, as them.
install -Dm755 packaging/undo-for-users.sh %{buildroot}%{_libexecdir}/fedora-glass-undo-for-users

# Re-applies the parts that can't follow GNOME's dark/light switch by themselves.
# The unit keeps its old file name, so an upgrade leaves it turned on as it was.
install -d %{buildroot}%{_userunitdir}
cat > %{buildroot}%{_userunitdir}/liquid-glass-watch.service <<'UNIT'
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
# Brings the glass up to date at the first login after an update installed while logged
# out. Pulled in by GNOME's own session target (a link shipped here), so an upgrade turns it
# on too: the unit has no [Install] section to enable.
cat > %{buildroot}%{_userunitdir}/fedora-glass-before-login.service <<'UNIT'
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
install -d %{buildroot}%{_userunitdir}/gnome-session-pre.target.wants
ln -s ../fedora-glass-before-login.service %{buildroot}%{_userunitdir}/gnome-session-pre.target.wants/fedora-glass-before-login.service
# Turned on for every user's session at install (the preset is applied by %%post).
install -Dm644 /dev/stdin %{buildroot}%{_userpresetdir}/80-liquid-glass.preset <<'PRESET'
enable liquid-glass-watch.service
PRESET

# Where `dnf upgrade` finds new versions.
install -Dm644 packaging/fedora-glass.repo %{buildroot}%{_sysconfdir}/yum.repos.d/fedora-glass.repo
# The public key that the packages in that repository are signed with.
install -Dm644 packaging/RPM-GPG-KEY-fedora-glass %{buildroot}%{_sysconfdir}/pki/rpm-gpg/RPM-GPG-KEY-fedora-glass

%check
# The files the software centres read must be valid: an invalid one is dropped silently.
desktop-file-validate %{buildroot}%{_datadir}/applications/io.github.djshiye.LiquidGlass.desktop
appstreamcli validate --no-net %{buildroot}%{_datadir}/metainfo/io.github.djshiye.LiquidGlass.metainfo.xml
# The same tests a GitHub release runs: a build that fails them never reaches dnf.
python3 -m pytest -q tests

%post
%systemd_user_post liquid-glass-watch.service

%preun
%systemd_user_preun liquid-glass-watch.service
# Removing the app (not an upgrade) puts each person's original look back, unless they
# turned that off in the app, and the normal login screen if the glass was on there.
if [ $1 -eq 0 ]; then
    %{_libexecdir}/fedora-glass-undo-for-users || :
    %{_libexecdir}/liquid-glass-login-screen undo >/dev/null 2>&1 || :
fi

%postun
# Removing the app (not an upgrade): the login screen helper kept its saved original in
# /var/lib/liquid-glass, and the undo above deleted the files, so the folder is empty now.
# Only an empty folder goes (a file left there stays).
if [ $1 -eq 0 ]; then
    rmdir %{_sharedstatedir}/liquid-glass 2>/dev/null || :
fi

%posttrans
# The old repository file (added by hand from the Liquid Glass instructions) only lets
# through the old name, and fedora-glass.repo now does its job: set it aside, but only
# if it is exactly ours.
old=%{_sysconfdir}/yum.repos.d/liquid-glass.repo
if [ -f "$old" ] && ! [ -L "$old" ] && grep -qxE 'baseurl=https://djshiye.github.io/(fedora-liquid-glass|fedora-glass)/rpms/' "$old" \
   && grep -qx 'includepkgs=liquid-glass' "$old"; then
    mv -f "$old" "$old.rpmsave" || :
fi
# Glass on the login screen (only if a user turned it on): bring it up to this version's
# rules with the colours of their last Apply, so no Apply or password is needed after an
# update. Each user's own desktop parts follow at their next login (fedora-glass watch).
%{_libexecdir}/liquid-glass-login-screen refresh >/dev/null 2>&1 || :
:

%triggerpostun -- liquid-glass < %{fg_evr}
# The watcher unit kept its name, so removing liquid-glass (when fedora-glass replaces
# it) turns the unit off after fedora-glass has turned it on: turn it on again, the same
# way a first install does.
if [ $2 -eq 0 ] && [ -x /usr/lib/systemd/systemd-update-helper ]; then
    /usr/lib/systemd/systemd-update-helper install-user-units liquid-glass-watch.service || :
fi

%post -n liquid-glass
%systemd_user_post liquid-glass-watch.service

%preun -n liquid-glass
%systemd_user_preun liquid-glass-watch.service
# No login-screen undo here: this package goes away when fedora-glass replaces it,
# and that must not take the login screen glass off.

%files
%license LICENSE LICENSES/Apache-2.0.txt LICENSES/GPL-3.0.txt LICENSES/GPL-2.0.txt LICENSES/CC-BY-SA-4.0.txt THIRD-PARTY-NOTICES.md
%doc README.md
%{_bindir}/fedora-glass
%{_bindir}/liquid-glass
%{_datadir}/fedora-glass/
%{_datadir}/applications/io.github.djshiye.LiquidGlass.desktop
%{_datadir}/icons/hicolor/scalable/apps/io.github.djshiye.LiquidGlass.svg
%{_datadir}/metainfo/io.github.djshiye.LiquidGlass.metainfo.xml
%{_datadir}/icons/fedora-glass-*/
%{_userunitdir}/liquid-glass-watch.service
%{_userunitdir}/fedora-glass-before-login.service
%dir %{_userunitdir}/gnome-session-pre.target.wants
%{_userunitdir}/gnome-session-pre.target.wants/fedora-glass-before-login.service
%{_userpresetdir}/80-liquid-glass.preset
%{_libexecdir}/liquid-glass-login-screen
%{_libexecdir}/fedora-glass-undo-for-users
%{_datadir}/polkit-1/actions/io.github.djshiye.LiquidGlass.policy
%config(noreplace) %{_sysconfdir}/yum.repos.d/fedora-glass.repo
%{_sysconfdir}/pki/rpm-gpg/RPM-GPG-KEY-fedora-glass

%files -n liquid-glass
%license LICENSE LICENSES/Apache-2.0.txt LICENSES/GPL-3.0.txt LICENSES/GPL-2.0.txt LICENSES/CC-BY-SA-4.0.txt THIRD-PARTY-NOTICES.md
%doc README.md
%{_bindir}/fedora-glass
%{_bindir}/liquid-glass
%{_datadir}/fedora-glass/
%{_datadir}/applications/io.github.djshiye.LiquidGlass.desktop
%{_datadir}/icons/hicolor/scalable/apps/io.github.djshiye.LiquidGlass.svg
%{_datadir}/metainfo/io.github.djshiye.LiquidGlass.metainfo.xml
%{_datadir}/icons/fedora-glass-*/
%{_userunitdir}/liquid-glass-watch.service
%{_userunitdir}/fedora-glass-before-login.service
%dir %{_userunitdir}/gnome-session-pre.target.wants
%{_userunitdir}/gnome-session-pre.target.wants/fedora-glass-before-login.service
%{_userpresetdir}/80-liquid-glass.preset
%{_libexecdir}/liquid-glass-login-screen
%{_libexecdir}/fedora-glass-undo-for-users
%{_datadir}/polkit-1/actions/io.github.djshiye.LiquidGlass.policy
%config(noreplace) %{_sysconfdir}/yum.repos.d/fedora-glass.repo
%{_sysconfdir}/pki/rpm-gpg/RPM-GPG-KEY-fedora-glass

%changelog
* Thu Nov 12 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.28-1
- The taskbar's top edge no longer flashes as the pointer passes the middle of it, also while you press and drag
- The pointer's light turns smoothly across menus and the taskbar instead of snapping at their middle
- Slack, Discord, VS Code and other apps that draw their own window get glass behind their title bar again, instead of a see-through bar showing the desktop

* Wed Nov 11 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.27-1
- The taskbar no longer flickers when you press and drag along it over a maximized window
- A new How liquid slider on the Motion page makes the taskbar press firmer or more liquid

* Wed Nov 11 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.26-1
- Apps on the Apps without glass list get a plain solid window instead of a see-through one
- The app shows when the glass is paused from Quick Settings, with a Resume button
- A look that matches your wallpaper follows a new wallpaper by itself, even with the app closed

* Wed Nov 11 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.25-1
- One restart is enough after an update, also when GNOME Software installs it while you restart
- The Colour page no longer says your wallpaper changed when only light and dark switched
- Saving a look to a USB stick works
- Match my wallpaper reads .jxl pictures and slideshows that list sizes
- App names in the app pickers show in your language
- The Open button in the Extensions app reads right in French and Italian

* Wed Nov 11 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.24-1
- The app speaks German, French, Spanish, Italian and Brazilian Portuguese, following your system language (English otherwise)
- So do the Quick Settings Glass tile, the lock screen greeting, the app's menu entry and the login screen password prompt
- Search finds settings by their translated words as well as the English ones
- Longer words fit: the Look buttons show just their icons when space is short, and long labels shrink before they are cut

* Wed Nov 11 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.23-1
- Apply only counts as done when it is: a failed Apply keeps your changes unapplied, and a part that didn't change says so
- A damaged settings file never turns into the default look; the last good copy is used and only Apply writes it again
- Background helper: one process instead of four, and a disk problem no longer makes it restart every 5 seconds
- Login screen glass can't get stuck on if its helper is interrupted; one helper run at a time
- Dragging a big window over many windows takes about 40 % less time per frame; the Speed card tells how smooth your last drag was
- App: closing or Apply wait for removal and the login screen step; presets, search, small screens, wallpaper preview and screen readers fixed; starts faster
- Restore finishes with an unusual Flatpak file, and doesn't wait 15 s for a GNOME Shell that isn't running
- After login, Dash to Panel and the Shell theme no longer stay unstyled for a minute when GNOME is slow to report the glass
- New: save your own looks, share them as a file and add one from a file
- New: See changes says what changed in plain words, page by page, with a dot on pages that changed
- New: go back to the look before your last Apply, and forward again
- New: the glass tint and accent can match your wallpaper
- New: opt-in Fedora Glass colours for Firefox, taken away exactly by Restore original
- New: lighter glass on battery or in Power Saver
- New: your own list of apps whose windows get no glass
- New: a Glass switch in Quick Settings pauses all the glass until the next login; menus stay readable while it is paused
- Ubuntu: the light/dark follower comes back after a remove and install
- Releases stay hidden until they are signed; the Fedora package is installed and upgraded in the checks; ships in GNOME Software listings

* Tue Nov 10 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.22-1
- A preview big enough to judge the glass: about half the page beside the settings, and Home's preview fills the room above the looks
- Close up by default: the desktop at about half its real size, looking at the start menu, Quick Settings or the calendar; drag to look around, or switch to the whole screen
- The preview's switches sit in a bar under it, so nothing covers the glass
- In a small window the preview sits above the settings; the lock screen preview grows too
- Uses a little less memory than 1.5.21

* Tue Nov 10 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.21-1
- A simpler app: a sidebar of pages (Home, Colour, Glass, Panel and windows, Motion, Pointer and desktop, Lock and login, Apps, Advanced, About and restore) instead of one long page
- Search settings (Ctrl+F): finds any setting, opens its page and points it out
- Home: the looks, how much glass, light or dark, accent and four quick switches in one place
- Motion: one Motion style (Off, Calm, GNOME, Lively, Playful) and one speed; each animation can still be tuned in its own fold
- Login screen next to the lock screen; Restore original and Remove on About and restore
- Part by part: click a part of the preview to give it its own look
- The app opens about twice as fast and uses about 80 MB less memory

* Tue Nov 10 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.20-1
- Mouse pointer styles: 15 to pick from, with a Just for fun group; set on Apply and undone by Restore original
- Sliders show their default and a Default button, each card has a Reset, and Reset all to defaults has its own card on the More tab
- Clearer app: a Restart button when a restart finishes the job, plain-word notes on what each part changes, and a welcome that says what was found on this PC
- Updates bring your look up to date by themselves at the next login, the login screen included
- The app says why the glass can't start (extensions switched off, GNOME version not supported yet, an error) instead of asking for a restart that can't help
- Dash to Panel, ArcMenu and Spawn count only when they are switched on; "System" accent follows the system accent colour
- Backups: an Apply that is cut short, a damaged backup list or a lost backup copy no longer costs your original look
- Signing: a release is signed only when GitHub proves it was built from main; the first install is checked against the key fingerprint
- Ubuntu: apt update keeps working after Fedora Glass is removed; the watcher stops at removal on Ubuntu and Arch
- Panel icons keep their hover lift and the taskbar glide while a menu is open, also over full-screen games
- Glass looks: readable title bars and text on bright wallpapers, a visible lock card on two screens, glass in the screenshot tool, the Disks sidebar and Alt+Tab

* Tue Nov 10 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.19-1
- Glass memory: pictures kept at the screen's real size, about 60 % less memory per window at 125 % scaling
- Glass shader: 13-28 % cheaper per pane with the same look, and no second full redraw when one frame already drew it all
- Dragging a window repaints only the moving glass, not the other screen and every window behind it
- Less CPU when idle: a clock or other small change in a window no longer redraws all the glass over it (GNOME 51), and a window that never stops changing is followed at half rate
- Faster Apply and lock screen: settings read in-process, unchanged files left alone
* Mon Nov 09 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.18-1
- Full-screen games and videos get direct display and variable refresh rate again: the window glass steps out of full-screen windows
- Glass of windows that are minimized, on another workspace or behind a maximized window frees its memory (about 230 MB per maximized window on 1440p screens) and comes back as soon as the window shows
- A dragged window's glass copies only the windows behind it that can be seen

* Mon Nov 09 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.17-1
- Works on stock GNOME with no extensions: glass on the top bar, the overview's dash and search, and the dash keeps all its app icons when starting on the desktop
- Glass behind Dash to Dock and Ubuntu Dock
- The app adapts to your desktop: its preview shows the top bar, a dock or Dash to Panel, and settings for extensions you do not use are hidden
- Start on the desktop is on by default only with Dash to Panel; GNOME's own desktop keeps its overview at login
- Readable search results on light glass

* Mon Nov 09 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.16-1
- Install and update on Ubuntu (26.04, 26.10) and Arch too: signed apt and pacman repositories next to the dnf one
- Checked on GNOME 50 and GNOME 51; roomier password field on the GNOME 51 lock and login screens
- Readable top bar on Ubuntu's own desktop (Yaru no longer forces it black under light glass)
- With two screens, the glass behind see-through title bars (Slack and other apps) no longer flickers while the other screen redraws
- The close button (and other title-bar buttons) of an unfocused window, such as Terminal, works on the first click again

* Mon Nov 09 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.15-1
- No more empty glass boxes left beside the Extension List menu after hovering its buttons

* Mon Nov 09 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.14-1
- No more flickering glow behind see-through title bars (Slack, other Electron apps) while windows behind them repaint

* Sun Nov 08 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.13-1
- No second see-through frame around Spawn's menu, RGBeast or Wheelguard over bright backgrounds
- Notifications stacked in the calendar no longer show through the card in front of them
- The panel's glass shine is even along its whole length (no darker right end)

* Sun Nov 08 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.12-1
- The login screen's password box is wide enough to show "Password" in full (and the lock screen's too)
- GNOME's screenshot tool shows window pictures again in Window mode

* Sun Nov 08 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.11-1
- Updates are signed with Dino's own key, and dnf checks every package and the repository index
- The first signed update asks once to accept the key (fingerprint D49A 3081 6825 7FDB F9D5 AE14 BD1A C1C6 F56A 7252)
- The right-click menu in Terminal (Ptyxis) is readable again

* Sun Nov 08 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.10-1
- Your desktop only changes when you press Apply; moving a slider changes the preview only
- Apply keeps the glass on the login screen up to date (it asks for your password when the login screen changes)
- Dragging a slider no longer makes the desktop stutter
- The panels on two screens match: a maximized window no longer lights up its panel

* Sat Nov 07 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.9-1
- After an upgrade, the glass no longer comes back by itself when an earlier Restore original kept one of your folders
- Restore original puts back your theme's links in a kept gtk-4.0 folder, and never writes into your theme's own files
- Choices you make yourself after Apply (gedit colours, terminal style, panel settings) stay put through Apply and dark/light switches
- The dark/light switch only touches the parts that are applied
- Safe mode no longer turns the glass off after a crash on waking from sleep; auto quality keeps trusting the last speed check after locking
- The glass cleans up properly if it fails while starting; fully opaque window previews stay opaque
- App: Undo refreshes the Apps page, no false "unapplied changes" prompt, Apply and close waits when a restart is needed, the welcome shows only once

* Fri Nov 06 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.8-1
- The app has a new look: a section bar on the Look page, clearer groups, and a short welcome on first start
- The app asks before closing with changes you have not applied, has Undo changes, and Tab keeps the focused option in view
- Lock screen: hidden notifications take no room and never wake the screen, the Middle clock clears notifications, greeting and weather are fresh after sleep, wrapped messages stay centred
- Glass for Dash to Panel's window previews and for Shell dialogs (Run a Command, Power Off, password prompts); notification stacks look clean
- Restore original sticks (nothing turns the glass back on by itself) and keeps your theme's folder links
- App windows: readable Delete buttons, light toggles in light mode, gedit colours that match the glass, tidier tabs and Qt buttons
- Steadier: auto quality trusts the speed check, no old screens kept after unplugging, old app caches removed

* Fri Nov 06 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.7-1
- New Lock screen tab: a live preview, widgets on the lock screen, and privacy choices
- The app's preview now shows every setting live as you change it
- Login screen: a compact glass password prompt instead of one big flat box
- No extra glass frame around the Fedora Glass app's own window
- The calendar and menus never turn see-through over a window
- Faster glass: thinner window rims, menus keep their glass while they grow, a lighter shader
- Apply after Restore original finishes the top bar, panel and menus at once, with no restart
- Restore works after an app (like Spawn or ArcMenu) was removed, and keeps app settings you changed since Apply
- Small fixes: Activities hidden on the lock screen, hover lift after Dash to Panel restarts

* Thu Nov 05 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.6-1
- Spawn, the ArcMenu replacement, gets the same glass as ArcMenu: its own entry in the app, glass colours, corners and search pill, the start-menu glass, and tight shadows on its right-click menus
- With the overview off, the app grid stays closed while Spawn runs, as it does with ArcMenu
- The menu's look is now called "Start menu"; your settings for it carry over

* Thu Nov 05 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.5-1
- Glassier look: small glints of light on the corners facing the light, a faint sheen on top, and a clearer lens edge on the panel and menus
- Switching between dark and light no longer gets slower after each screen lock (GNOME's User Themes left a listener behind at every lock)
- Unplugging or switching off a screen no longer leaves the other panel without glass
- Restore original keeps a file another app or theme wrote after Apply, instead of deleting it or putting an older copy over it

* Wed Nov 04 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.4-1
- Much smoother with the pointer near the panel or a menu: only the light on the rim is redrawn, not all of the glass
- Taskbar icons keep their hover lift when a window opens or closes, and the panel glass no longer blinks when another extension restarts
- Restore original keeps settings you changed in other apps after Apply (VS Code, qBittorrent, btop and others)
- Apply never makes a private settings file readable by other users
- A Restore that was cut short can run again, and Restore sticks for apps removed since Apply
- Restore clicked right after Apply works; turning off terminal colours gives Ptyxis its own palette back
- Apply is quicker and no longer rewrites settings that are already right
* Wed Nov 04 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.3-1
- Login screen: the same glass on every screen, with no spotlight on the main one, and a brighter glass card
- Two quick restarts no longer switch the glass off (a clean restart was counted as a crash)
- Turning off only the glass effects no longer turns ArcMenu red or leaves the glass extension behind
- The lock screen glass follows screen changes while locked
- Alt+Tab and the volume pop-up show the glass again with Just Perfection's theme on; gedit's title bar has round corners
- Restore original now puts every setting back exactly, and a new Remove Fedora Glass button removes it cleanly
- dnf remove puts your original look back (can be turned off)
- Settings survive one damaged value, and High Contrast stays solid while you change sliders
* Wed Nov 04 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.2-1
- Claude Desktop and other apps that maximize as they open are no longer invisible until minimized
- The Wired and Wi-Fi menus in Quick Settings open right under their toggle again
- The login screen's glass now covers every screen, not only the main one
* Wed Nov 04 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.1-1
- Glass you can see through: less blur on Balanced menus, a stronger bend at the edge, and smoked dark glass that reads as a pane over dark wallpapers
- A thin iOS-style rim instead of the hard white line along the panel
- Smoother on fast screens: automatic glass quality no longer steps down on 120 and 144 Hz screens, and each frame redraws less
- Glass on the login screen now works on Fedora (GNOME 50 has no gdm.css)
- Terminal colours: prompt segments (starship, powerline) are readable again
* Tue Nov 03 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.5.0-1
- Liquid Glass is now Fedora Glass: the app, the Shell extension and the themes it adds to other apps
- The package is now fedora-glass; dnf upgrade moves to it by itself and keeps your settings
- The command is now fedora-glass (liquid-glass still works)
- Apple-style glass: a bright rim line, a wider squircle lens, and Clear and Frosted looks
- Menus open from their button and land exactly at full size, with the glass in the same frame
- A Check speed button, and glass that lightens itself when frames drop, while you drag a window, and under full-screen games and video
- Safe mode: glass that keeps failing turns itself off, with a button in the app to turn it back on
- Opt-in glass on the login screen, with one-click undo
- After an upgrade your look updates by itself at the next restart, no Apply needed
- Ready for GNOME 51 (Fedora 45)
- qBittorrent's side list and btop's background follow the glass colours
- With the overview off, GNOME no longer sometimes gets stuck starting up (second screen without wallpaper)

* Tue Nov 03 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.4.4-1
- No glass strip on the other screen beside a window maximized on a second screen
- Glass behind a window that keeps repainting redraws at most 20 times a second
- Restore original keeps ArcMenu working
- ArcMenu's recovery no longer loads its style twice, which could drop the Shell theme

* Mon Nov 02 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.4.3-1
- ArcMenu comes back by itself when GNOME restarts it before Dash to Panel
- No more stray glass box in menus and the panel at 125% display scaling

* Sun Nov 01 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.4.2-1
- Apply waits for the glass before changing the panel, menus and ArcMenu, and finishes after a restart
- Notes say "restart your PC" instead of "log out"

* Sat Oct 31 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.4.1-1
- Genie minimize now narrows smoothly into the icon when the window sits above it

* Sat Oct 31 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.4.0-1
- Text stays readable on window glass over bright wallpapers
- Flat, small GTK 3 checkboxes and radio buttons on Orchis
- Smoother window animations: glass behind a moving window holds still
- One corner-radius scale: rounded buttons instead of pills, 24 px window corners
- A glass highlight that glides between panel icons on hover
- Glass dropdowns and tooltips in the Liquid Glass app
- No blue halo around active Quick Settings toggles, no hard edge above ArcMenu
- Optional: Qt app title bars that match GNOME (through XWayland, off by default)
- Faster, safer shader engine (no stray "almost zero" settings)

* Sat Oct 31 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.3.1-1
- Fix window and panel glass rendering nearly black in 1.3.0

* Fri Oct 30 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.3.0-1
- Unified, flat window header bars for GTK 4, libadwaita and GTK 3 apps
- GTK 3 styling now works on top of any theme, including Orchis, without adw-gtk3
- Polished light mode glass with a fine dark hairline on the panel
- Glass Calculator keypad
- Keep theme files safe when ~/.config/gtk-4.0 or gtk-3.0 is linked into a theme
- Notice and one-click Re-apply when another app replaces the GTK look
- Keep window glass while a window briefly has no monitor
- Animation picker: choose minimize, open, close, launch bounce and panel hover
  animations, each with Intensity and Speed
- Glass lock screen with a slide-up sheet, adjustable in the app
- Stop idle panel repaints while an app is asking for attention
- Menus get their glass when first opened, and always show even if it fails
- No stale bright patch in the panel glass after minimizing a window

* Fri Oct 30 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.2.1-1
- Fix GNOME Shell crashing when a window is closed with window glass on

* Fri Oct 30 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.2.0-1
- Glass that reflects real pixels and takes colour from what it holds, with per-part controls
- Window header bars: height slider and see-through glass
- No glare, one even hairline, light that follows the pointer
- Caustic, contact shadow, parallax, press give and fine grain
- Start on the desktop, and an option to turn off the overview
- App windows: a real glass edge and a rim that mirrors the surroundings

* Fri Oct 30 2026 Dino Klisura <115914552+djshiye@users.noreply.github.com> - 1.1.0-1
- Own glass engine with physically based optics; no Blur my Shell needed
