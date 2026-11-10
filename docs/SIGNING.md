# How the packages are signed

The Fedora Glass packages in the dnf, apt and pacman repositories, and each repository's own
index, are signed with Dino's own OpenPGP key. The signing happens on Dino's PC. The private key
is never on GitHub, in GitHub Actions, or anywhere online.

```
GitHub Actions           Dino's PC                      GitHub Actions          Your PC
Release workflow    ->   fedora-glass-sign         ->   DNF repository     ->   sudo dnf upgrade
builds the packages      checks where they came         checks every            checks every
(unsigned) and signs     from, signs them and the       signature, publishes    signature
a provenance record      index, uploads
```

- **Release** (`release.yml`) runs only for a commit that is on `main` (a pushed `v*` tag that
  points anywhere else is refused, and a run from the Actions tab must run on `main`). It builds
  the RPMs, the `.deb` and the Arch package, attaches them to the GitHub release with their
  `SHA256SUMS`, and records a **build provenance attestation** for each package: a statement,
  signed through GitHub's Sigstore service with a certificate that only this workflow run can
  get, saying "release.yml built this file from commit X".
- **`fedora-glass-sign`** (`packaging/fedora-glass-sign`), run on Dino's PC, checks before it
  signs anything that:
  1. the release's tag points at a commit that is on `main`;
  2. every package matches the release's `SHA256SUMS` and has the right name and version;
  3. every package has a build provenance attestation from this repository's `release.yml`,
     for exactly that commit, made on GitHub's own runners (`gh attestation verify`).

  If any check fails it signs nothing, stops with an error, and (when it runs by itself) shows a
  notification that the release was **not** signed and why. Otherwise it signs the new release's
  packages, builds and signs the indexes (`repomd.xml.asc`, apt `InRelease`, the pacman database),
  checks everything the way dnf, apt and pacman will, uploads the result to the release as
  `dnf-repo.tar.gz` and starts the DNF repository workflow.
- **The two releases before it** stay in the repository, so `dnf downgrade` can go back. They are
  not signed again: their packages are taken from the earlier signed repository, and each one is
  kept only if Dino's signature on it (for Ubuntu: on the index that lists its checksum) still
  verifies. Anything else is left out.
- **DNF repository** (`dnf-repo.yml`) has no key and can't sign. It publishes only if every package
  and index is signed by the key in `packaging/RPM-GPG-KEY-fedora-glass` on `main`, real `apt`
  (Ubuntu 26.04) and `pacman` (Arch) accept the repositories, and the version is not older than
  the one the site serves.
- **Your PC** checks the index and every package against the key it trusts. It never takes a new
  key from the web by itself.

Signing key: Dino Klisura (djshiye package signing), RSA 4096, fingerprint
`D49A 3081 6825 7FDB F9D5 AE14 BD1A C1C6 F56A 7252` (dnf shows it as
`D49A308168257FDBF9D5AE14BD1AC1C6F56A7252`, without spaces).

## First install

The install commands in the [README](../README.md#install) download the key from the site and
refuse it unless its fingerprint is exactly the one above (and it is the only key in the file).
Only then do they trust it and install `fedora-glass` from the signed repository:

- **Fedora**: the key goes to `/etc/pki/rpm-gpg/RPM-GPG-KEY-fedora-glass` and into rpm, a
  temporary `fedora-glass-setup.repo` (with `gpgcheck=1` and `repo_gpgcheck=1`) installs the
  package, and is removed again. From then on the package's own `fedora-glass.repo` is used.
- **Ubuntu**: the key goes to `/usr/share/keyrings/fedora-glass.asc` (the same file the package
  ships), a temporary `fedora-glass-setup.sources` with `Signed-By` installs the package, and is
  removed again.
- **Arch**: `pacman-key --lsign-key` trusts only the key with that fingerprint.

If dnf asks `Is this ok [y/N]` about the key, check that it shows the fingerprint above, then
answer `y`.

## What this protects, and what it does not

Protected:

- **Someone who can change the GitHub releases** (upload or replace files, or edit `SHA256SUMS`)
  can't get a package signed: their files have no attestation from `release.yml`.
- **A `v*` tag pushed for a commit that is not on `main`** (for example from a side branch) is
  refused twice: the Release workflow stops, and `fedora-glass-sign` refuses it.
- **Someone who can change the website** (GitHub Pages) can't change a package or the key your PC
  trusts: every package and index must be signed by the key, which your PC already has. The first
  install refuses any key with another fingerprint.
- **The private key** never leaves Dino's PC.

Not protected:

- **Code that reaches `main`.** The checks prove that a package was built by the Release workflow
  from a commit on `main`, not that the commit is good. Anyone who can push or merge to `main` (or
  who gets into Dino's GitHub account) can release, and Dino's PC will sign it. Branch protection
  on `main` and reviewing what is merged are what guard that.
- **Dino's PC.** Whoever controls it can sign anything with the key.
- **Holding updates back.** Someone who controls the website can stop serving new versions, or keep
  serving the current signed one. They can't serve an unsigned or changed package.
- **Releases signed before the provenance checks.** Those were signed after checking only their `SHA256SUMS`. They
  stay as they are (still signed by the same key), and are only carried along while they are among
  the last three releases.
- **The fingerprint you check.** It is printed here and in the README. If both were changed on
  GitHub, a new install that follows them would trust the wrong key; PCs that already have Fedora
  Glass would not.

## One-time setup (Dino's PC)

```sh
sudo dnf install rpm-sign createrepo_c gh
gh auth status || gh auth login
mkdir -p ~/.local/bin
curl -fsSL https://raw.githubusercontent.com/djshiye/fedora-glass/main/packaging/fedora-glass-sign -o ~/.local/bin/fedora-glass-sign
chmod +x ~/.local/bin/fedora-glass-sign
fedora-glass-sign setup
```

`setup` picks your signing key (if you have several it lists them: run it again with the one you
want), checks that it can sign, and saves the public key to
`~/.config/fedora-glass-signing/RPM-GPG-KEY-fedora-glass`. That public key goes into
`packaging/RPM-GPG-KEY-fedora-glass` on `main`.

## Update the signer (once, for the provenance checks)

The signer from before this change does not check where a release came from. Replace it once.
Automatic signing keeps working (the timer runs the same file), nothing else changes:

```sh
curl -fsSL https://raw.githubusercontent.com/djshiye/fedora-glass/main/packaging/fedora-glass-sign -o ~/.local/bin/fedora-glass-sign.new &&
bash -n ~/.local/bin/fedora-glass-sign.new &&
grep -q 'gh attestation verify' ~/.local/bin/fedora-glass-sign.new &&
gh attestation verify --help >/dev/null &&
chmod +x ~/.local/bin/fedora-glass-sign.new &&
mv ~/.local/bin/fedora-glass-sign.new ~/.local/bin/fedora-glass-sign &&
sha256sum ~/.local/bin/fedora-glass-sign
```

Compare the printed checksum with the one given when this change was merged. If
`gh attestation verify --help` fails, your `gh` is too old: `sudo dnf upgrade gh`, then run the
block again.

## Protect the v* tags (once, in GitHub's settings)

So nobody can move or delete a release tag after the fact:

1. On GitHub open the repository's **Settings → Rules → Rulesets → New ruleset → New tag
   ruleset**.
2. Name it `Release tags`, set **Enforcement status** to **Active**.
3. Under **Target tags** choose **Add target → Include by pattern** and enter `v*`.
4. Tick **Restrict updates**, **Restrict deletions** and **Block force pushes**, then **Create**.

Leave **Restrict creations** off: releases started from the Actions tab create their tag from the
workflow, and that rule would stop them. (Tags for commits that are not on `main` are refused
anyway, see above.)

## Back up the key (once, and keep it offline)

```sh
fedora-glass-sign backup /run/media/$USER/<your USB stick>
```

This writes `fedora-glass-signing-key-backup.asc`: your private key, encrypted with a new password
that you choose (store that password in your password manager), plus the key's revocation
certificate if gpg made one. Keep the stick somewhere safe. Never put the backup in this repository,
in GitHub, or in a cloud-synced folder.

To restore it on a reset or new PC:

```sh
gpg -d /run/media/$USER/<your USB stick>/fedora-glass-signing-key-backup.asc | gpg --import
fedora-glass-sign setup
```

## Each release: automatic

Turn it on once:

```sh
fedora-glass-sign enable-auto
```

If gpg opens a password window, tick **Save in password manager**, so GNOME's keyring can unlock the
key from then on. This adds a small systemd user timer (`fedora-glass-sign.timer`) that looks for a
new release every 10 minutes while you are logged in. When one appears, it checks and signs it as
above and shows **"signed, publishing it now"**. A later run shows **"published"** once the website
really serves the new version.

If the website stays behind (the publish workflow sometimes times out), the timer starts the
publish workflow again, at most 3 times and at least 20 minutes apart, and says so each time. After
that it stops and shows **"signed but NOT published"**, with a link to the workflow runs.

If a release fails a check, it shows **"was NOT signed"** and why. If something else goes wrong (for
example the password window was closed) it shows why. Either way it tries again an hour later. The
details of the last run are in `~/.config/fedora-glass-signing/auto.log`.

The key still never leaves your PC. If your PC is off when a release comes out, it is signed a few
minutes after you next log in.

To turn it off: `fedora-glass-sign disable-auto`. To sign a release by hand:
`fedora-glass-sign` (latest) or `fedora-glass-sign vX.Y.Z`. A release made before the provenance
checks has no attestation, so it can't be signed again.

## Lost key

If the key is gone and there is no backup, PCs with Fedora Glass keep working: they only refuse new
updates, because nothing new is signed by the key they trust. To move on to a new key:

1. Make a new key (`gpg --quick-gen-key "Your Name <you@example.com>" default default never`) and
   run `fedora-glass-sign setup` and `fedora-glass-sign backup ...` with it.
2. Replace `packaging/RPM-GPG-KEY-fedora-glass` on `main` with the new public key, put the new
   fingerprint in the README's install commands and in this file, release a new version, and run
   `fedora-glass-sign` for it. Packages of older releases are signed by the old key, so the new
   repository holds only the new release.
3. On each PC, once, run the install commands from the README again (they check the new
   fingerprint and trust the new key), then `sudo dnf upgrade --refresh` (Ubuntu:
   `sudo apt update && sudo apt upgrade`, Arch: `sudo pacman -Syu`).

This step is by hand on purpose: if a PC took a new key from the website by itself, anyone who got
into the GitHub account could swap the key and ship their own packages.
