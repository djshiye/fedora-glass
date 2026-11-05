# Release checks

Automatic checks that run before every release, on a test desktop set up like Dino's PC.
A release is only built when all of them pass (`.github/workflows/release.yml` waits for
`release-checks.yml`).

## What the test desktop is

- GNOME 50 on Wayland, two screens side by side at **125 %** scaling
- **Orchis Dark**, with `~/.config/gtk-4.0` linked into it
- Spawn is installed but switched off, as Dino's PC runs ArcMenu; only the Spawn check switches to it
- Dino's extensions in Dino's order, with Dino's panel, menu and blur settings
  (`dino-settings.ini`, layout keys only): Extension List, ArcMenu, Dash to Panel,
  AppIndicator, Blur my Shell, Just Perfection, Deja Window, then Fedora Glass
- The overview off and "start on the desktop", as Dino uses it
- Apps: Ptyxis (terminal), Files, gedit (GTK 3), and an **Electron** window (like Claude Desktop) on
  Wayland and on XWayland
- Fedora Glass is applied the way an update does it: Apply, then a fresh login

It runs in a container with software rendering, so it has no graphics card. There the
glass always keeps the processor busy while anything moves, on every version, so
smoothness on a real graphics card can't be judged here. The speed check therefore counts
the glass's own work (redraws while idle, redraws of glass a busy app doesn't touch), and
shows processor use and frame rates only for information. Smoothness on the PC stays with
`tools/hardware-check`. For the same reason the test desktop pins the glass quality to "full"; the automatic
quality (which steps down when frames are late) is not exercised here.

## The checks

| Check | What it does | Bug it would have caught |
|---|---|---|
| The glass looks right | Desktop, panel, ArcMenu, Quick Settings, Extension List menu and windows against reference pictures; window glass brightness against the wallpaper | 1.3.0 black glass, 1.4.2 dark box in menus at 125 % |
| No leftover pieces of windows | Moves, resizes, minimizes, closes Electron windows; across the screen edge, in corners, maximized on the second screen; behind a terminal's glass | 1.4.3 window pieces and the glass strip at the screen edge |
| Window content stays in place while resizing | Corner drags, app resizes, maximize and restore for the terminal, Files and Electron | app content sliding away from the window corner (a general guard) |
| Light on the processor | Waits for the desktop to settle, then: almost no redraws while nothing moves, no redraws of a panel's glass while the pointer moves near it (only its rim light changes), and no redraws of glass that a streaming app (like Claude writing) does not touch. Processor use and frame rates are shown for information | redraw loops; 1.5.3 re-rendered the panel's glass for every pointer move near it |
| Extensions come back after restarts | Switches each extension off and on in Dino's order | 1.4.2 ArcMenu red |
| Restore original and Apply | Restore original and Apply with the start order that broke 1.4.3. After Restore original, every setting must be what it was before the first Apply, the same extensions switched on, and no Fedora Glass file left in the home folder; then only "Fedora Glass effects" turned off and Apply, and back on | 1.4.3 ArcMenu red after Restore; a Restore that leaves something behind; 1.5.2 ArcMenu red and the glass left on GNOME's list after turning the effects off |
| Pop-ups and title bars show the glass | The volume pop-up and Alt+Tab (with an app's window previews) under Just Perfection's theme; gedit's title bar corners | 1.5.2: Alt+Tab and the volume pop-up near-black with Just Perfection's theme on; square grey corners behind gedit's title bar |
| Locking the screen works | Lock screen and password screen against references, unlock, three times; after that one theme change must reload the Shell theme once; then the screens change scale while locked; the second screen is unplugged and plugged back in and every panel must keep its glass; the login screen's glass must look the same on every screen | 1.5.2 left part of a screen without lock glass after a screen change; 1.5.2 lit only the main login screen; 1.5.4: each lock made every later dark/light switch reload the Shell theme once more (GNOME's User Themes leak), and unplugging a screen left the other panel with no glass |
| Quick restarts keep the glass on | Before the test login the PC restarts twice within seconds of logging in; safe mode must stay off and the glass must draw | 1.5.2 counted a clean restart as a crash and switched the glass off |
| No errors from Fedora Glass | Apply output and GNOME Shell's log | |
| Upgrading from the last release | With `--from` (CI passes the last release tag): the last release is applied and used for one session, then this version arrives the way `dnf upgrade` brings it, nobody presses Apply, and the PC restarts twice. The new glass must run with Dino's settings kept | every release up to 1.4.4: after `dnf upgrade` the glass stayed the old version until Apply |
| Spawn gets the glass | Switches ArcMenu off and Spawn (the owner's own start menu) on mid-session, Applies with the Spawn target, opens Spawn's menu: picture against a reference, glass under its box pointer, and Fedora Glass treated it as the ArcMenu part. Then Fedora Glass off and on (Spawn must come back running, not red), Restore original (every Spawn setting back to before Apply), and ArcMenu back. Runs last | Spawn's menu without the glass, or Spawn red after a restart of the glass |

The limits are in `limits.toml`, with a note on each.

## Proof that it catches the old bugs (2026-11-02)

| Version | What the checks said |
|---|---|
| 1.3.0 | Window glass at 28 % of the wallpaper's brightness ("too dark, like 1.3.0's black glass"); ArcMenu red from the start |
| 1.4.2 | A dark patch in the Extension List menu and on the lock screen at 125 %; ArcMenu red from the start |
| 1.4.3 | A strip of glass on the first screen with a window maximized on the second; ArcMenu red after Restore original; User Themes broken after ArcMenu's auto-recovery (a new find) |

## Running it

Needs Docker (podman works as `docker`; on SELinux add `LGQA_RUN_ARGS="--security-opt label=disable"`). From the repository folder:

```sh
qa/desktop/run.sh                          # everything, about 15 minutes
qa/desktop/run.sh --only looks,leftovers   # some checks
qa/desktop/run.sh --only spawn             # just the Spawn check, about a minute
qa/desktop/run.sh --source ../old-tree     # today's checks against another version
qa/desktop/run.sh --from ../last-release   # also check the upgrade from the last release
qa/desktop/run.sh --screen 2560x1440       # at the size of Dino's two screens
```

The screens are 2000x1125 by default, which keeps a run quick. `--screen 2560x1440` runs
the same checks on two screens the size of Dino's, against the pictures in
`references/2560x1440/`. A size with no pictures of its own runs every other check and
says the pictures were not compared.

The report is `qa-report/report/report.html`. In GitHub it is the run's
`release-check-report` download, and a short table is on the run's summary page.

On a pull request the checks run only when it has the `release-checks` label, to keep
Actions use down. They always run before a release and can be started by hand from the
Actions tab ("Release checks", "Run workflow").

## When the look changes on purpose

The reference pictures in `references/` show how the glass should look. After a change
that is meant to look different, run `qa/desktop/run.sh --update-references`, look at the
new pictures, and commit them with the change so the review shows the old and new look.

## Pinned downloads

Everything the test desktop downloads is pinned: the base image by digest, each extension
and Orchis by git commit (checked after cloning), and Electron and Spawn by SHA-256 (see the
`Dockerfile`; Spawn's RPM is fetched from its gh-pages commit, because its DNF repository keeps only the
newest 3 builds). Extensions are assembled with glib tools only; no third-party build script
runs. The container has no network while the checks run.
