#!/usr/bin/env python3
"""Unpacks the shipped pointer styles into an icons folder, after checking each archive
against data/cursors/SHA256SUMS. Used by the packages and install.sh, so their builds need
only Python (no xz or sha256sum tools).

    python3 -I packaging/cursors/unpack.py SOURCE_DIR ICONS_DIR
"""

import hashlib
import shutil
import sys
import tarfile
from pathlib import Path


def main(src: str, dest: str) -> int:
    folder = Path(src) / "data/cursors"
    out = Path(dest)
    out.mkdir(parents=True, exist_ok=True)
    sums = (folder / "SHA256SUMS").read_text(encoding="ascii").splitlines()
    if not sums:
        sys.exit("no pointer styles listed in SHA256SUMS")
    for line in sums:
        digest, name = line.split()
        if "/" in name or not name.endswith(".tar.xz"):
            sys.exit(f"unexpected name in SHA256SUMS: {name}")
        data = (folder / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            sys.exit(f"{name}: checksum does not match SHA256SUMS")
        theme = name.removesuffix(".tar.xz")
        shutil.rmtree(out / theme, ignore_errors=True)
        with tarfile.open(folder / name, "r:xz") as tf:
            for m in tf.getmembers():
                if m.name != theme and not m.name.startswith(theme + "/"):
                    sys.exit(f"{name}: {m.name} is outside the theme folder")
            # "data": no absolute paths, no links out of the folder, no device files,
            # ordinary permissions.
            tf.extractall(out, filter="data")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
