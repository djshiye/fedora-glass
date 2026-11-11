# Security

## Reporting a problem

Please report a security problem **privately**, not as a public issue: on GitHub open the
repository's **Security** tab and choose **Report a vulnerability**
(<https://github.com/djshiye/fedora-glass/security/advisories/new>). Only the maintainer sees
it, and a fix can be made before the problem is public.

Please include what you found, the Fedora Glass version (`fedora-glass --version`) and how to
reproduce it.

## What counts

Fedora Glass runs as your own user and changes only your own settings. Two parts run as root
and are the most important to get right: the opt-in login screen glass
(`fedoraglass/login_screen.py`, through `pkexec` after your password) and the package scripts
that run when the package is installed, upgraded or removed. Problems in how the packages
are built, signed and published (`docs/SIGNING.md`) count too.

## Supported versions

Only the newest release gets fixes. `dnf upgrade`, `apt upgrade` and `pacman -Syu` bring it.
