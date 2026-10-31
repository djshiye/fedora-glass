# Publishing on Fedora COPR

Liquid Glass is published at <https://copr.fedorainfracloud.org/coprs/djshiye/liquid-glass/>.
Users run `sudo dnf copr enable djshiye/liquid-glass` once, and then `sudo dnf upgrade` keeps it
up to date.

## How a release reaches users

1. The **Release** workflow tests the code, builds the RPM for the GitHub release and creates the
   tag `v<version>`.
2. GitHub tells COPR that a tag was created (a repository webhook that sends only "Branch or tag
   creation" events).
3. COPR clones this public repository at that tag and runs `.copr/Makefile`, which makes the source
   package. It refuses to build unless the commit is exactly the tag `v<Version>` from the spec, so
   nothing between releases can ship.
4. COPR builds the RPM from that source package, runs the same tests (`%check`), signs it with the
   project's own key and publishes it. `dnf` checks that signature before every install.

No token or password is stored in this repository or in GitHub secrets. COPR reads the repository
anonymously, and the signing key never leaves COPR.

## One-time setup

You need a free Fedora account: <https://accounts.fedoraproject.org> (**Create an account**).

**On COPR** (<https://copr.fedorainfracloud.org>, **Log in** with the Fedora account):

1. **New project**. Name `liquid-glass`. Description: *A Liquid Glass look for Fedora GNOME, with an
   app to tune it.* Instructions: *sudo dnf copr enable djshiye/liquid-glass, then sudo dnf
   install liquid-glass.*
2. Chroots: tick **fedora-44-x86_64**. Under *Other options*, tick **Follow Fedora branching** so new
   Fedora versions are added by themselves. Leave **Enable internet access during builds** off.
   Press **Create**.
3. **Packages → New package → SCM**:
   - Package name `liquid-glass`
   - Clone URL `https://github.com/djshiye/fedora-liquid-glass.git`
   - Committish: leave empty. Subdirectory: leave empty.
   - Spec file `packaging/liquid-glass.spec`
   - Type **git**, SRPM build method **make_srpm**
   - Tick **Auto-rebuild**, then **Submit**.
4. **Settings → Integrations**: copy the **GitHub** webhook URL. It looks like
   `https://copr.fedorainfracloud.org/webhooks/github/<number>/<code>/`.

**On GitHub** (this repository → **Settings → Webhooks → Add webhook**):

1. Payload URL: the COPR URL with `liquid-glass/` added to the end, so it ends in
   `/<code>/liquid-glass/`. The package name at the end is needed: without it COPR ignores tags
   named `v1.2.3`.
2. Content type **application/json**. Secret: leave empty. SSL verification: on.
3. **Let me select individual events**: tick only **Branch or tag creation**, untick **Pushes**.
4. **Add webhook**.

Treat the webhook URL like a password: anyone with it can ask COPR to rebuild a tag that is already
in this repository (nothing else). If it leaks, use **Regenerate** on the COPR Integrations page
and paste the new URL into the GitHub webhook.

## Building a version by hand

If a release's COPR build didn't start (the webhook was missing or failed), open the package on
COPR, press **Rebuild**, and set **Committish** to the tag, for example `v1.3.1`. Building with an
empty Committish fails on purpose, because `main` is not a release.
