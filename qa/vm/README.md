# The glass login screen, on a real boot

`.github/workflows/login-boot.yml` boots real Fedora 45, Fedora 44, Ubuntu 26.04, Ubuntu 26.10
and Arch virtual machines, each from the distribution's own cloud image, with a real GDM. In
each one it builds the real package the way `packages.yml` does for that Linux, installs it
with the Linux's own package manager, turns the glass login screen on, logs in for real
through the login screen (keys typed on the screen, not a shortcut), and breaks the glass on
purpose to show that nobody is ever locked out.

The container checks (`qa/desktop/`) can't prove this part: there the login screen is GNOME
Shell started by hand, without GDM, logind, SELinux, AppArmor, reboots or the boot-time guard.

## What it proves

| Step | What happens | It passes when |
|---|---|---|
| 1. baseline | The plain login screen after setup | a logind session of class `greeter` runs gnome-shell; the switch is off and available; picture `01-plain.png`; the gdm profile's dconf settings and a listing of `/etc/dconf` are kept for step 7 |
| 2. on | `sudo fedora-glass-login on '{"picture":"wallpaper"}'` with a test JPEG on stdin | it exits 0 and `status` says `trial`; look.json has a token. The log (and the Note column) says which dconf route the helper took, `route a (db gdm)` or `route b`, with the lines of the gdm dconf profile |
| 3. glass | GDM restarted | the add-on's health note says `ok` with that token; picture `02-glass.png` differs clearly from `01-plain.png`; no new SELinux (Fedora, which must be enforcing) or AppArmor (Ubuntu) denial mentions gnome-shell, dconf or fedora-glass |
| 4. login | Enter, the password, Enter, typed on the login screen | a logind session of `tester`, class `user`, type `wayland`, appears; within 20 s `status` says `on` (the trial was confirmed) and `fedora-glass-login-guard-check.path` is not in the `failed` state. The log says after how many seconds the state became `on` (the wait goes on to 60 s for the log only) and prints the two trial-watch units' `systemctl show` and journal, whatever the outcome |
| 5. update | `on '{"picture":"glow","clock":"thin"}'` | still `on`, the new values are in, the same token in look.json |
| 6. restart | Two plain reboots with the glass on, nothing changed | after each: `status` still says `on` with nothing in `stopped`; the health note says `ok` with this boot's id; the same token in look.json; `systemctl show -p Result,ExecMainStatus fedora-glass-login-guard.service` says success and 0; the guard's `silent_boots` in `/var/lib/fedora-glass/login/state.json` is 0. The guard's journal is printed each time, and on a failure also `systemd-analyze security` for it. The only step that shows the boot guard working in its real systemd sandbox without wrongly switching the glass off |
| 7. addon-update | A harmless comment line appended to the installed add-on's `extension.js` (as a package update changes it), the tester logged out, a reboot | the boot guard started a new trial: `status` says `trial` with nothing in `stopped`, a NEW token in look.json, `trial_boots` 1 in `state.json`; the health note says `ok` with the new token for this boot; the glass still shows (picture `03-addon-update-glass.png`); the trial-watch units and the guard are shown. Then a real login ends the trial in the same boot (within 20 s, as in step 4). `extension.js` is put back afterwards |
| 8. off | `sudo fedora-glass login-screen off` | `status` says off; `/etc/dconf` and the gdm profile's settings are as in step 1; `/etc/fedora-glass/login` is gone; after a GDM restart the screen looks like `01-plain.png` and a real login works |
| 9. crash | On again; GDM stopped; a `starting` note with the current token is put in the greeter's state folder, owned by the greeter's user, as a greeter that crashed leaves it; GDM started | the note turns `safe`, the screen looks plain, a real login works; after a reboot the switch is off with `stopped` = `crash` |
| 10. broken-addon | On again; `throw new Error("boot test");` put at the top of the installed add-on's `login.js`; GDM restarted | the note says `error`, the screen looks plain, a real login works; after a reboot the switch is off with `stopped` = `crash`. `login.js` is put back afterwards |
| 11. no-login | On again; two reboots without anybody logging in | the switch is off with `stopped` = `no-login`; the screen looks plain; a real login works |
| 12. removal | On again; the package removed with dnf, apt or pacman | no file under `/etc/dconf` holds our switch (the compiled database included), `/etc/fedora-glass/login` and root's state folder `/var/lib/fedora-glass/login` are gone, the greeter's extension list doesn't name the add-on; after a GDM restart the screen looks plain and a real login works |

In every step that judges the glass as showing (3, both boots of 6, and 7), the step also
fails if GNOME Shell's journal since the step began holds an error of the add-on (a line naming
`fedora-glass-login` with `JS ERROR`, `had error` or an extension error, or a `JS ERROR` whose stack
names the add-on's folder). In every step that restarts GDM or reboots, the log counts GDM's
"Session never registered" lines (a greeter that was started again): it is reported, in the step's
Note and in a closing line after the table (glass on and off apart), and never judged.

Steps 2 to 8 build on each other (7 builds on 6; 8, off, needs only 2); a step whose groundwork failed is skipped. Steps 9 to 12
each start clean (switch off, nobody logged in, GDM restarted), so they still run when an
earlier step failed. Before a real login the tester is logged out
(`loginctl terminate-user tester`) and the login screen comes back. The run fails if any
step fails.

## Seeing the result

- The job log has a `PASS`/`FAIL` line for every step, and every check prints what it saw.
- Pictures 01, 02 and the first failure are also in the job log as a small PNG (240 px wide):
  copy the lines between `----- BEGIN PNG name -----` and `----- END PNG name -----` into a
  file and run `base64 -d file > name.png`.
- On a failure the log also shows the end of the serial console, `journalctl -b -u gdm`,
  GNOME Shell's journal, the helper's `status`, the health note and the logind sessions.
- The artifact `login-boot-<distro>` (kept 3 days) has every picture in full size, the serial
  log, QEMU's log, the guest setup's output, and the journal of every boot.
- A table of the steps goes to the job summary.
- After the table, the end of the job log has a failure digest: for each failed step its `FAIL`
  lines and the last 25 lines it logged (without thumbnails, journals and serial console dumps).
  The job summary gets the `FAIL` lines only, when they are few.

## Running it

On a pull request: add the label `login-boot` (each push then runs it again). Or start
"Login screen, real boot" from the Actions tab.

On your own PC with KVM (any Linux; about 5 GB of free space for the image and the disk):

```sh
sudo dnf install qemu-kvm qemu-img genisoimage gnupg2 openssh-clients   # or apt / pacman
python3 -I qa/vm/login_boot.py --distro fedora-45 --out /tmp/login-boot
python3 -I qa/vm/login_boot.py --distro arch --out /tmp/login-boot --steps crash
```

`--steps` runs only the steps named (and the ones they build on). `--image FILE` uses a cloud
image you already have (it is then not checked). `--find-image-only` finds the image and
checks its signed checksum without downloading it. Your user must be able to open
`/dev/kvm`; the Ubuntu cloud image key is read from
`/usr/share/keyrings/ubuntu-cloudimage-keyring.gpg` (the `ubuntu-keyring` package).

The VM is `qemu-system-x86_64 -enable-kvm -cpu host -smp 4 -m 6G` with a virtio disk (a 20 GB
qcow2 overlay on the cloud image), virtio network with SSH forwarded to `127.0.0.1:2222`,
`virtio-vga` with no window, a QMP socket and the serial console in a file. cloud-init makes
the user `tester` (password `glasstest1`: lower-case letters and digits, so it types the same
on any layout), with password-free sudo and an SSH key made for the run. SSH doesn't check
the VM's host key: it is a throwaway VM on the loopback address, with a key made for the run.

## How the images are checked

- **Fedora**: the newest `Fedora-Cloud-Base-Generic-<release>-<compose>.x86_64.qcow2` on
  `dl.fedoraproject.org` (releases, then development), and its
  `Fedora-Cloud-<release>-<compose>-x86_64-CHECKSUM`, both taken from `dl.fedoraproject.org`
  only. The CHECKSUM file's clear signature is checked with gpgv against Fedora's published
  keyring (`https://fedoraproject.org/fedora.gpg`); the signing key must be the pinned primary
  key of that release (Fedora 44 `36F612DCF27F7D1A48A835E4DBFCF71C6D9F90A6`, Fedora 45
  `4F50A6114CD5C6976A7F1179655A4B02F577861E`) and carry the uid `Fedora (<release>)`; only the
  signed text is read for the SHA-256. The image is downloaded from the mirror redirector
  (`download.fedoraproject.org`, which answers 302 to a nearby mirror) first, then from
  `dl.fedoraproject.org`. A mirror is not trusted: a file counts only if its SHA-256 is the
  one in the signed list; a failure or mismatch is logged and the next source tried, and the
  run fails only when both fail.
- **Downloads** that end early (the body stops with no error) are noticed by comparing the
  bytes with the promised length, and carried on with a `Range` request (up to 5 times; a server
  that answers 200 to it is asked again from zero). Every byte is hashed once, in order.
- **Ubuntu**: `releases/<codename>/release/ubuntu-<version>-server-cloudimg-amd64.img` on
  `cloud-images.ubuntu.com`; `SHA256SUMS` checked against `SHA256SUMS.gpg` with the runner's
  ubuntu-keyring, signed by key `D2EB44626FDDC30B513D5BB71A5D6C4C7DB87C81` (pinned).
- **Arch**: the dated `Arch-Linux-x86_64-cloudimg-<date>.qcow2` on
  `geo.mirror.pkgbuild.com/images/latest/`, its `.sig` checked against the arch-boxes release
  key from the arch-boxes README (copy in `keys/arch-boxes.asc`, primary key
  `1B9A16984A4E8CB448712D2AE0B78BF4326C6F8F`, pinned).

## TO CONFIRM ON FIRST RUN

Nothing here could be run where it was written (no KVM, no access to Fedora's or Arch's
servers), so the first runs on GitHub have to confirm these. Each one is printed in the log.

Confirmed already (2026-11-13): the Ubuntu paths, file names and signing key above
(`--find-image-only` passed for both Ubuntu releases against the real servers), the
arch-boxes key's fingerprint (computed from the key block in the README), and Fedora's
file names and the two release signing keys (seen on the CHECKSUM signatures of the first
run and matched with the key files of the distribution-gpg-keys collection; both are pinned).

What could be tested without a VM is in `tests/test_login_boot_lane.py`: the QMP messages,
the pictures (PPM to PNG, shrinking, the difference score, the log thumbnails), the keys, the
image and checksum names, the signature status, the step planner, and every step run once
against a pretend PC that keeps the contract (and against ones whose guard or glass doesn't
work, which must fail the right steps).

- **Arch image name**: a dated `Arch-Linux-x86_64-cloudimg-<date>.qcow2` (the plain name is
  used when there is none); the arch-boxes key (its signing subkey expires in 2027).
- **Package names per Linux** in `guest/setup.sh`: Fedora `gdm gnome-shell gnome-session
  gnome-settings-daemon mesa-dri-drivers dconf` (plus, when they exist,
  `gnome-session-wayland-session adwaita-sans-fonts cantarell-fonts audit kernel-modules`);
  Ubuntu `gdm3 gnome-shell gnome-session gnome-settings-daemon dconf-cli` (plus, when they
  exist, `libgl1-mesa-dri mesa-libgallium dbus-user-session fonts-cantarell
  linux-modules-extra-<kernel>`); Arch `gdm gnome-shell gnome-session gnome-settings-daemon
  dconf mesa cantarell-fonts base-devel`. Whether these are enough for GDM to draw on
  `virtio-vga` with software rendering.
- **The GDM unit**: `gdm.service` everywhere (Ubuntu's `gdm3.service` is used only if there is no
  `gdm.service`).
- **The user list**: GDM shows `tester` (given an AccountsService record by `setup.sh`) and the
  list has the keyboard focus, so Enter picks it.
- **Sessions in loginctl**: the login screen shows up as a session of class `greeter` whose user
  runs `gnome-shell` (GDM 49 and later use throwaway users such as `gdm-greeter`); a login as
  class `user`, type `wayland`.
- **Keys for QMP `send-key`**: the QKeyCode names `ret`, `esc`, `shift`, `a`-`z`, `0`-`9`, and that
  they reach the login screen through the PS/2 keyboard of QEMU's q35 machine.
- **The greeter's state folder**: `/var/lib/gdm/seat0/state` (Ubuntu `/var/lib/gdm3/...`). That GDM
  hands it, with everything inside, to each new greeter user is no longer an open question:
  `gdm_ensure_dir(..., recursive_chown=TRUE)` (common/gdm-file-utils.c) re-owns it recursively
  at every greeter start, so the crash note written in the "crash" step stays readable.
- **Picture thresholds**: glass vs plain differs by at least 12, plain vs plain by at most 6
  (mean difference per colour channel at 160 px wide). Both numbers are printed every time.
- **The health note `error` in the broken-addon step** holds by design: extension.js loads `login.js`
  with a dynamic import inside try/catch, so a `throw` at its top reaches the add-on's own
  error handling. Only the real run's note is left to see.
- **The guard unit**: named `fedora-glass-login-guard.service`, and `state.json` has `silent_boots`.
- **Times**: setup (packages and build) takes most of the 45 minutes on Fedora; 7 reboots and
  about 10 GDM restarts follow. If a Linux runs out of time: drop the reboot after setup
  (start graphical.target instead), then check the crash and broken-addon steps' guard
  verdicts after one shared reboot instead of one each.
