# Fedora COPR runs this to make the source package (SRPM) for each build:
#   make -f .copr/Makefile srpm outdir=<dir> spec=<path to liquid-glass.spec>
# COPR then builds and signs the RPM from that SRPM.
#
# It only builds a released version: the commit must carry the tag v<Version>
# from the spec. A build of any other commit (say, main between releases) stops
# here, so nothing unreleased can reach `dnf upgrade`.

spec ?= packaging/liquid-glass.spec
outdir ?= $(CURDIR)/out

srpm:
	command -v git >/dev/null || dnf -y install git-core
	command -v rpmbuild >/dev/null || dnf -y install rpm-build
	rpm -q systemd-rpm-macros >/dev/null || dnf -y install systemd-rpm-macros
	set -eu; \
	top="$$(git rev-parse --show-toplevel)"; \
	ver="$$(rpmspec -q --qf '%{version}\n' --srpm "$(spec)")"; \
	tag="v$$ver"; \
	git -C "$$top" rev-parse -q --verify "refs/tags/$$tag" >/dev/null \
	  || { echo "No tag $$tag for spec version $$ver: release it first"; exit 1; }; \
	test "$$(git -C "$$top" rev-parse "$$tag^{commit}")" = "$$(git -C "$$top" rev-parse HEAD)" \
	  || { echo "This commit is not $$tag: build the tag, not a branch"; exit 1; }; \
	src="$$(mktemp -d)"; \
	git -C "$$top" archive --format=tar.gz --prefix="fedora-liquid-glass-$$ver/" \
	  -o "$$src/fedora-liquid-glass-$$ver.tar.gz" HEAD; \
	rpmbuild -bs "$(spec)" --define "_sourcedir $$src" --define "_srcrpmdir $(outdir)"; \
	rm -rf "$$src"

.PHONY: srpm
