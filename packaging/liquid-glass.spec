Name:           liquid-glass
Version:        1.3.1
Release:        1%{?dist}
Summary:        Liquid Glass theme for Fedora GNOME, with a customizer
License:        MIT AND Apache-2.0
URL:            https://github.com/djshiye/fedora-liquid-glass
Source0:        %{url}/archive/v%{version}/fedora-liquid-glass-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  systemd-rpm-macros
Requires:       python3
Requires:       python3-gobject
Requires:       python3-pyside6
Requires:       gnome-shell
Requires:       gnome-shell-extension-user-theme
Recommends:     adw-gtk3-theme
Recommends:     kvantum

%description
A Liquid Glass look for GNOME Shell, GTK and Qt apps, Dash to Panel and
ArcMenu, drawn by its own GNOME Shell extension, with a Qt app to tune it
from clear liquid glass to calm frost. The app changes only your own user
settings and can restore your original look at any time.

%prep
%autosetup -n fedora-liquid-glass-%{version}

%build
# Pure Python and QML: nothing to build.

%install
install -d %{buildroot}%{_datadir}/%{name}
cp -r liquidglass %{buildroot}%{_datadir}/%{name}/
find %{buildroot}%{_datadir}/%{name} -name '__pycache__' -prune -exec rm -rf {} +

# -I keeps Python from importing anything from the current folder or PYTHONPATH.
install -d %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/%{name} <<'LAUNCHER'
#!/bin/sh
exec /usr/bin/python3 -I -c 'import sys; sys.path.insert(0, "/usr/share/liquid-glass"); from liquidglass.__main__ import main; sys.exit(main())' "$@"
LAUNCHER
chmod 755 %{buildroot}%{_bindir}/%{name}

install -Dm644 data/io.github.djshiye.LiquidGlass.desktop %{buildroot}%{_datadir}/applications/io.github.djshiye.LiquidGlass.desktop
sed -i 's|^Exec=.*|Exec=liquid-glass gui|' %{buildroot}%{_datadir}/applications/io.github.djshiye.LiquidGlass.desktop
install -Dm644 data/icons/io.github.djshiye.LiquidGlass.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/io.github.djshiye.LiquidGlass.svg

# Re-applies the parts that can't follow GNOME's dark/light switch by themselves.
install -d %{buildroot}%{_userunitdir}
cat > %{buildroot}%{_userunitdir}/liquid-glass-watch.service <<'UNIT'
[Unit]
Description=Liquid Glass: follow GNOME dark and light style
PartOf=graphical-session.target
After=graphical-session.target

[Service]
ExecStart=/usr/bin/liquid-glass watch
Restart=on-failure
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=graphical-session.target
UNIT
# Turned on for every user's session at install (the preset is applied by %%post).
install -Dm644 /dev/stdin %{buildroot}%{_userpresetdir}/80-liquid-glass.preset <<'PRESET'
enable liquid-glass-watch.service
PRESET

%post
%systemd_user_post liquid-glass-watch.service

%preun
%systemd_user_preun liquid-glass-watch.service

%files
%license LICENSE LICENSES/Apache-2.0.txt THIRD-PARTY-NOTICES.md
%doc README.md
%{_bindir}/%{name}
%{_datadir}/%{name}/
%{_datadir}/applications/io.github.djshiye.LiquidGlass.desktop
%{_datadir}/icons/hicolor/scalable/apps/io.github.djshiye.LiquidGlass.svg
%{_userunitdir}/liquid-glass-watch.service
%{_userpresetdir}/80-liquid-glass.preset

%changelog
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
