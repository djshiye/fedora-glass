# How the packages are signed

The Fedora Glass packages in the dnf repository, and the repository's own index, are signed with
Dino's own OpenPGP key. The signing happens on Dino's PC. The private key is never on GitHub, in
GitHub Actions, or anywhere online.

```
GitHub Actions          Dino's PC                      GitHub Actions          Your PC
Release workflow   ->   fedora-glass-sign         ->   DNF repository     ->   sudo dnf upgrade
builds the RPMs         checks the RPMs, signs         checks every            checks every
(unsigned)              them and the index, uploads    signature, publishes    signature
```

- **Release** (`release.yml`) builds the RPMs and attaches them to the GitHub release, as before.
- **`fedora-glass-sign`** (`packaging/fedora-glass-sign`), run by Dino, downloads that release and
  the two before it, checks them against each release's `SHA256SUMS`, signs every package with
  `rpmsign`, builds the repository index with `createrepo_c` and signs it (`repomd.xml.asc`). It
  then checks everything the way dnf will, uploads the result to the release as
  `dnf-repo.tar.gz` and starts the DNF repository workflow.
- **DNF repository** (`dnf-repo.yml`) has no key and can't sign. It publishes only if every package
  and the index are signed by the key in `packaging/RPM-GPG-KEY-fedora-glass` on `main`, and never
  goes back to an older version.
- **dnf** on each PC checks the index and every package against the key that came with the
  package (`/etc/pki/rpm-gpg/RPM-GPG-KEY-fedora-glass`). It never fetches a key from the web, so
  nobody can swap the key through the website or the repository. `gpgcheck=1` and
  `repo_gpgcheck=1` are set in `packaging/fedora-glass.repo`.

The first time a PC meets the key, `sudo dnf upgrade` shows its fingerprint and asks
`Is this ok [y/N]` (once for the index, once for the packages). Check that the fingerprint is the
one below, then answer `y`.

Signing key fingerprint: see `packaging/RPM-GPG-KEY-fedora-glass`
(`gpg --show-keys packaging/RPM-GPG-KEY-fedora-glass`).

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

## Each release

When the Release workflow has finished:

```sh
fedora-glass-sign            # signs and publishes the latest release (or: fedora-glass-sign v1.5.11)
```

gpg asks for the key's passphrase. A couple of minutes later the repository serves the new version
and `sudo dnf upgrade --refresh` picks it up.

## Lost key

If the key is gone and there is no backup, PCs with Fedora Glass keep working: they only refuse new
updates, because nothing new is signed by the key they trust. To move on to a new key:

1. Make a new key (`gpg --quick-gen-key "Your Name <you@example.com>" default default never`) and
   run `fedora-glass-sign setup` and `fedora-glass-sign backup ...` with it.
2. Replace `packaging/RPM-GPG-KEY-fedora-glass` on `main` with the new public key, release a new
   version, and run `fedora-glass-sign` for it.
3. On each PC, once, install that release from GitHub (it brings the new key with it):

   ```sh
   sudo dnf install https://github.com/djshiye/fedora-glass/releases/latest/download/fedora-glass.noarch.rpm
   ```

   The next `sudo dnf upgrade` shows the new key's fingerprint and asks once. From then on updates
   come as before.

This step is by hand on purpose: if dnf took a new key from the website by itself, anyone who got
into the GitHub account could swap the key and ship their own packages.
