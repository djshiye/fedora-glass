"""Files below a folder that another program can change at any moment: never through a link.

A Flatpak app can write anything inside ~/.var/app/<its id>, a Snap inside ~/snap/<its
name>, and an Obsidian vault takes in whatever a sync, a git pull or a sandboxed Obsidian
puts there. Fedora Glass runs with all of the person's rights: a folder in there swapped
for a link, between any two of its steps, must never lead a read or a write anywhere else
(the app could have it write the app's own bytes into ~/.bashrc.d, say).

So below such a folder (the *box*) every step walks down from the box one name at a time,
holding each folder open, and does its work in the folder it holds: a link, or anything
that is not a folder, on the way stops it with LinkInside or NotADirectoryError. A check
first and a call by path after would not do: the app can swap the folder in between.
The folders above the box (~, ~/.var/app, the way to a vault) are the person's own, and
links there are followed as everywhere else.
"""

from __future__ import annotations

import contextlib
import errno
import os
import secrets
import stat
from collections.abc import Iterator
from pathlib import Path

from .i18n import N_, gettext as tr

# Shown for a part, or a file on Restore, with a link inside an app's own folder.
LINK_INSIDE = N_("Left alone: {folder} is a link, and links inside an app's own folder are not followed.")

# Far more than any app's own settings file below a box (a few KB): one bigger than this
# is not read at all, so the app can't have us fill every byte of memory.
APP_FILE_MAX = 16 * 1024 * 1024

_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_READ = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC     # a FIFO must not hang us
_TMP_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789_"                      # as tempfile.mkstemp's


def _tilde(path: Path, home: Path | None) -> str:
    return "~/" + str(path.relative_to(home)) if home is not None and path.is_relative_to(home) else str(path)


class LinkInside(OSError):
    """A link where a folder or file below a box was expected: nothing went through it."""

    def __init__(self, folder: Path, home: Path | None = None):
        super().__init__(errno.ELOOP, "a link inside an app's own folder", str(folder))
        self.folder = folder
        self.home = home

    def __str__(self) -> str:
        return tr(LINK_INSIDE).format(folder=_tilde(self.folder, self.home))


def box_root(path: Path, home: Path) -> Path | None:
    """The box `path` is below (never the box itself), or None. Worked out from the path
    alone, so a record an earlier version made is guarded as well: ~/.var/app/<id>,
    ~/snap/<name>, or the vault that holds the .obsidian folder on the path; the outermost
    one when there are two."""
    parts, hp = path.parts, home.parts
    n, cut = len(hp), 0
    if parts[:n] == hp:
        if parts[n:n + 2] == (".var", "app") and len(parts) > n + 3:
            cut = n + 3
        elif parts[n:n + 1] == ("snap",) and len(parts) > n + 2:
            cut = n + 2
    if ".obsidian" in parts:
        i = parts.index(".obsidian")
        if 0 < i and (not cut or i < cut):
            cut = i
    return Path(*parts[:cut]) if cut else None


def read_app_text(path: Path, home: Path) -> str | None:
    """The UTF-8 text of an app's own file below a box (its own line endings kept), or None
    when it can't be read, isn't a plain file, or a link is at it or on the way."""
    root = box_root(path, home)
    assert root is not None
    try:
        return Box(root, home).read_bytes(path).decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


class Box:
    """Reads and writes below one box, never through a link (see the module's words). The
    same questions and steps as for any other file, so the engine's decisions stay one."""

    def __init__(self, root: Path, home: Path | None = None):
        self.root = root
        self.home = home

    # ---- the walk -------------------------------------------------------------------------
    def _names(self, path: Path) -> list[str]:
        if not path.is_relative_to(self.root) or path == self.root:
            raise ValueError(f"{path} is not below {self.root}")
        names = list(path.relative_to(self.root).parts)
        if any(n in ("", ".", "..") for n in names):
            raise OSError(errno.EINVAL, "not a plain path", str(path))
        return names

    def _stop(self, fd: int, name: str, where: Path) -> OSError:
        """Why `name` in the folder held by `fd` could not be opened as a folder."""
        try:
            st = os.stat(name, dir_fd=fd, follow_symlinks=False)
        except OSError:
            return LinkInside(where, self.home)     # changed again meanwhile: not followed either
        if stat.S_ISLNK(st.st_mode):
            return LinkInside(where, self.home)
        return NotADirectoryError(errno.ENOTDIR, os.strerror(errno.ENOTDIR), str(where))

    def _step(self, fd: int, name: str, where: Path, create: bool) -> int:
        try:
            return os.open(name, _DIR, dir_fd=fd)
        except FileNotFoundError:
            if not create:
                raise
        except OSError as e:
            if e.errno in (errno.ENOTDIR, errno.ELOOP):
                raise self._stop(fd, name, where) from e
            raise
        # Made here, one by one: mkdir never follows a link in its place (a dangling one
        # makes it fail), and the open after it says what is there.
        with contextlib.suppress(FileExistsError):
            os.mkdir(name, 0o777, dir_fd=fd)
        try:
            return os.open(name, _DIR, dir_fd=fd)
        except OSError as e:
            if e.errno in (errno.ENOTDIR, errno.ELOOP):
                raise self._stop(fd, name, where) from e
            raise

    def _open_root(self, create: bool) -> int:
        try:
            return os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        except FileNotFoundError:
            if not create:
                raise
        os.makedirs(self.root, exist_ok=True)       # the way to the box is the person's own
        return os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)

    def _open_dir(self, names: list[str], create: bool) -> int:
        fd = self._open_root(create)
        where = self.root
        try:
            for name in names:
                where = where / name
                nfd = self._step(fd, name, where, create)
                os.close(fd)
                fd = nfd
        except BaseException:
            os.close(fd)
            raise
        return fd

    @contextlib.contextmanager
    def _parent(self, path: Path, create: bool = False) -> Iterator[tuple[int, str]]:
        """The folder `path` is in, held open, and the name of `path` in it."""
        names = self._names(path)
        fd = self._open_dir(names[:-1], create)
        try:
            yield fd, names[-1]
        finally:
            os.close(fd)

    @contextlib.contextmanager
    def folder(self, path: Path) -> Iterator[int]:
        """`path` itself (the box, or a folder below it), held open."""
        fd = self._open_dir([] if path == self.root else self._names(path), False)
        try:
            yield fd
        finally:
            os.close(fd)

    # ---- questions --------------------------------------------------------------------------
    def lstat(self, path: Path) -> os.stat_result | None:
        """What is at `path` itself (a link is a link), or None when nothing is. A link on
        the way there raises LinkInside."""
        try:
            with self._parent(path) as (fd, name):
                return os.stat(name, dir_fd=fd, follow_symlinks=False)
        except (FileNotFoundError, NotADirectoryError):
            return None

    def _is(self, path: Path, test) -> bool:
        st = self.lstat(path)
        return st is not None and test(st.st_mode)

    def is_dir(self, path: Path) -> bool:
        return self._is(path, stat.S_ISDIR)

    def is_file(self, path: Path) -> bool:
        return self._is(path, stat.S_ISREG)

    def is_symlink(self, path: Path) -> bool:
        return self._is(path, stat.S_ISLNK)

    def exists(self, path: Path) -> bool:
        return self.lstat(path) is not None

    def mode(self, path: Path) -> int:
        st = self.lstat(path)
        if st is None:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), str(path))
        return st.st_mode & 0o777

    def kept_mode(self, path: Path, mode: int) -> int:
        """As engine._kept_mode: never more open than the plain file there now."""
        try:
            st = self.lstat(path)
        except OSError:
            return mode
        return mode & st.st_mode & 0o777 if st is not None and stat.S_ISREG(st.st_mode) else mode

    # ---- reading ----------------------------------------------------------------------------
    @contextlib.contextmanager
    def _reading(self, path: Path) -> Iterator[tuple[int, os.stat_result]]:
        with self._parent(path) as (dfd, name):
            try:
                fd = os.open(name, _READ, dir_fd=dfd)
            except OSError as e:
                if e.errno == errno.ELOOP:
                    raise LinkInside(path, self.home) from e
                raise
        try:
            st = os.fstat(fd)
            if stat.S_ISDIR(st.st_mode):
                raise IsADirectoryError(errno.EISDIR, os.strerror(errno.EISDIR), str(path))
            if not stat.S_ISREG(st.st_mode):
                # A FIFO or a device: nothing of an app's settings, and reading could hang.
                raise OSError(errno.EINVAL, "not a plain file", str(path))
            yield fd, st
        finally:
            os.close(fd)

    def read_bytes(self, path: Path, limit: int = APP_FILE_MAX) -> bytes:
        """The whole file; OSError (EFBIG) when it holds more than `limit` bytes."""
        with self._reading(path) as (fd, _st):
            chunks, size = [], 0
            while (b := os.read(fd, min(1 << 20, limit + 1 - size))):
                chunks.append(b)
                size += len(b)
                if size > limit:
                    raise OSError(errno.EFBIG, f"over {limit} bytes", str(path))
        return b"".join(chunks)

    def read_text(self, path: Path) -> str:
        """UTF-8 text with its own line endings, as open(..., newline="") reads it."""
        return self.read_bytes(path).decode("utf-8")

    def head(self, path: Path, n: int) -> bytes:
        with self._reading(path) as (fd, _st):
            return os.read(fd, n)

    def same_file(self, path: Path, data: bytes, mode: int) -> bool:
        """As engine.same_file: a plain file with exactly these bytes and this mode."""
        try:
            st = self.lstat(path)
            if st is None or not stat.S_ISREG(st.st_mode) or st.st_mode & 0o777 != mode or st.st_size != len(data):
                return False
            return self.read_bytes(path, len(data)) == data
        except OSError:
            return False

    def copy(self, path: Path, dest: Path) -> int:
        """Copy the plain file at `path` to `dest` (outside every box) with its mode and
        times, as shutil.copy2 does, and give its mode. Never through a link: the app could
        point one at a secret of the person's and have it handed back at Restore."""
        with self._reading(path) as (fd, st):
            with open(dest, "wb") as out:
                while (b := os.read(fd, 1 << 20)):
                    out.write(b)
        os.chmod(dest, stat.S_IMODE(st.st_mode))
        os.utime(dest, ns=(st.st_atime_ns, st.st_mtime_ns))
        return st.st_mode & 0o777

    def readlink(self, path: Path) -> str:
        with self._parent(path) as (fd, name):
            return os.readlink(name, dir_fd=fd)

    def missing_dirs(self, path: Path) -> list[str]:
        """The folders a write of `path` makes, deepest first (as Backup.record_file lists them)."""
        names = self._names(path)[:-1]
        if not self.root.exists():
            out, d = [], self.root
            while d != d.parent and not d.exists():
                out.append(str(d))
                d = d.parent
            return [str(self.root.joinpath(*names[:i])) for i in range(len(names), 0, -1)] + out
        fd = self._open_dir([], False)
        where = self.root
        try:
            for i, name in enumerate(names):
                where = where / name
                try:
                    nfd = self._step(fd, name, where, False)
                except FileNotFoundError:
                    return [str(self.root.joinpath(*names[:j])) for j in range(len(names), i, -1)]
                os.close(fd)
                fd = nfd
        finally:
            os.close(fd)
        return []

    # ---- changes ----------------------------------------------------------------------------
    def write(self, path: Path, data: bytes, mode: int = 0o644) -> None:
        """As engine.atomic_write: a fresh temp file in the same folder, renamed over the old
        one (a link there is replaced, never written through). Missing folders are made."""
        with self._parent(path, create=True) as (dfd, name):
            for _try in range(100):
                tmp = f".{name}.{''.join(secrets.choice(_TMP_CHARS) for _i in range(8))}.lg-tmp"
                try:
                    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                 0o600, dir_fd=dfd)
                    break
                except FileExistsError:
                    continue
            else:
                raise FileExistsError(errno.EEXIST, "no free temporary name", str(path))
            try:
                try:
                    view = memoryview(data)
                    while view:
                        view = view[os.write(fd, view):]
                    os.fchmod(fd, mode)
                finally:
                    os.close(fd)
                os.replace(tmp, name, src_dir_fd=dfd, dst_dir_fd=dfd)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(tmp, dir_fd=dfd)
                raise

    def unlink(self, path: Path) -> None:
        with self._parent(path) as (fd, name):
            os.unlink(name, dir_fd=fd)

    def rmdir(self, path: Path) -> None:
        with self._parent(path) as (fd, name):
            os.rmdir(name, dir_fd=fd)

    def symlink(self, link: str, path: Path) -> None:
        """Make the link at `path` (folders on the way are made too)."""
        with self._parent(path, create=True) as (fd, name):
            os.symlink(link, name, dir_fd=fd)

    def write_if_changed(self, path: Path, data: bytes, mode: int = 0o644) -> None:
        if not self.same_file(path, data, mode):
            self.write(path, data, mode)

    def sweep(self, folder: Path, drop) -> None:
        """Delete each plain file in `folder` for which `drop(name, lstat)` says so (the temp
        files of a write that was killed half way, see engine.sweep_temps)."""
        try:
            with self.folder(folder) as fd:
                for n in os.listdir(fd):
                    with contextlib.suppress(OSError):
                        st = os.stat(n, dir_fd=fd, follow_symlinks=False)
                        if stat.S_ISREG(st.st_mode) and drop(n, st):
                            os.unlink(n, dir_fd=fd)
        except OSError:
            pass
