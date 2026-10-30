"""Apply and revert: runs target plans with a first-touch backup.

Backup lives in ~/.local/state/liquid-glass/backup. For every file or
gsettings key a target changes, the state from *before Liquid Glass ever
touched it* is recorded once, tagged with the target id. Reverting a target
puts exactly those things back; reverting everything restores the desktop
as it was before the first Apply. Shared lists (enabled extensions, Flatpak
overrides) are recorded item by item, so only our own items are undone.
"""

from __future__ import annotations

import ast
import configparser
import contextlib
import errno
import fcntl
import hashlib
import io
import json
import os
import shutil
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from . import palette
from .env import Env
from .settings import Settings, config_dir
from .targets import all_targets
from .targets.base import Action, Command, Context, FlatpakOverride, GReset, GSet, ListEdit, Target, WriteFile


@dataclass
class Result:
    target: str
    name: str
    status: str        # "applied", "info" (nothing to change, see notes), "skipped", "reverted", "failed"
    message: str = ""


def atomic_write(path: Path, data: bytes, mode: int = 0o644) -> None:
    """Write via a fresh temp file in the same folder (O_EXCL, so a planted link can't redirect it)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()       # never write through a link into someone else's file
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".lg-tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _remove_empty(dirs: set[str]) -> None:
    """Take away folders an Apply created, deepest first, and only while empty."""
    for d in sorted(dirs, key=len, reverse=True):
        with contextlib.suppress(OSError):
            os.rmdir(d)


def parse_strv(text: str | None) -> list[str]:
    """gsettings 'as' text ("['a', 'b']" or "@as []") to a list."""
    if not text:
        return []
    text = text.strip().removeprefix("@as").strip()
    try:
        v = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return []
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def format_strv(items: list[str]) -> str:
    if not items:
        return "@as []"
    return "[" + ", ".join("'" + i.replace("\\", "\\\\").replace("'", "\\'") + "'" for i in items) + "]"


class Backup:
    SECTIONS = ("files", "gsettings", "commands", "lists", "flatpak", "dirlinks")

    def __init__(self, env: Env):
        self.env = env
        self.root = env.state / "liquid-glass/backup"
        self.manifest_path = self.root / "manifest.json"
        self.data: dict[str, dict] = {k: {} for k in self.SECTIONS}
        try:
            loaded = json.loads(self.manifest_path.read_text())
            if isinstance(loaded, dict):
                for k in self.data:
                    self.data[k] = dict(loaded.get(k, {}))
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        if self.env.dry_run:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        atomic_write(self.manifest_path, json.dumps(self.data, indent=1).encode(), 0o600)

    # ---- recording ----------------------------------------------------------
    def linked_folder(self, path: Path) -> Path | None:
        """The first folder above `path` that is a symlink, looking only below the user's
        config, data and state folders (those roots may be links on purpose: dotfiles,
        Silverblue's /home). A theme installer often links ~/.config/gtk-4.0 into its own
        theme folder, and writing through that link would overwrite the theme."""
        roots = sorted((r for r in (self.env.config, self.env.data, self.env.state)
                        if path.is_relative_to(r)), key=lambda r: len(r.parts), reverse=True)
        if not roots:
            return None
        d = roots[0]
        for part in path.parent.relative_to(roots[0]).parts:
            d = d / part
            if d.is_symlink():
                return d
        return None

    def unlink_folder(self, target: str, folder: Path) -> None:
        """Turn a linked folder into a real one, so writes land in the user's own config.

        The new folder links back to every entry of the old target (assets, gtk-dark.css,
        ...), so whatever the theme provided keeps working. Files an earlier version wrote
        through the link are put back first, which repairs the theme folder."""
        key = str(folder)
        if key in self.data["dirlinks"] or self.env.dry_run:
            return
        new_dirs: set[str] = set()
        problems = []
        for k in [k for k in self.data["files"] if Path(k).is_relative_to(folder)]:
            e = self.data["files"][k]
            if self.is_ours(Path(k), e):
                if (problem := self._restore_file(k, e, new_dirs)):
                    problems.append(problem)
            else:
                # The theme has replaced that file since (an update, say): a repair would put
                # an old copy over a newer one, so the record goes and the theme's file stays.
                self._forget_file(k, e)
        _remove_empty(new_dirs)
        if problems:
            raise OSError("; ".join(problems))
        link = os.readlink(folder)
        real = folder.resolve()
        tmp = Path(tempfile.mkdtemp(dir=folder.parent, prefix=f".{folder.name}.", suffix=".lg-tmp"))
        made = []
        try:
            if real.is_dir():
                for entry in sorted(real.iterdir()):
                    (tmp / entry.name).symlink_to(entry)
                    made.append(entry.name)
            os.chmod(tmp, 0o755)
            # Record before swapping, so an interrupted Apply can still be reverted.
            self.data["dirlinks"][key] = {"target": target, "link": link, "made": made}
            self.save()
            folder.unlink()
            os.rename(tmp, folder)
        except BaseException:
            self.data["dirlinks"].pop(key, None)
            if not folder.exists() and not folder.is_symlink():
                folder.symlink_to(link)
            shutil.rmtree(tmp, ignore_errors=True)
            raise

    @staticmethod
    def is_ours(path: Path, e: dict) -> bool:
        """Whether `path` still holds what Apply wrote there: the same bytes, or (for
        records older than that check) one of our generated files."""
        try:
            data = path.read_bytes() if path.is_file() else None
        except OSError:
            return False
        if data is None:
            return False
        if e.get("wrote"):
            return hashlib.sha256(data).hexdigest() == e["wrote"]
        return b"Liquid Glass" in data[:512]

    @staticmethod
    def _has_header(path: Path) -> bool:
        """A regular file (not a link) that one of our Applies wrote: covers an Apply killed
        after the write but before the manifest was saved, so its file never looks foreign."""
        try:
            if path.is_symlink() or not path.is_file():
                return False
            with open(path, "rb") as f:
                return b"Liquid Glass" in f.read(512)
        except OSError:
            return False

    def _forget_file(self, key: str, e: dict) -> None:
        if e.get("kind") == "file":
            with contextlib.suppress(OSError):
                os.unlink(e["copy"])
        del self.data["files"][key]

    def tidy_folders(self) -> None:
        """Before an Apply: finish or clear a folder swap an earlier Apply was stopped in
        the middle of, and keep the links in each folder we made in step with the theme
        folder it stands in for (new theme files get a link, removed ones lose theirs)."""
        if self.env.dry_run:
            return
        for parent in {self.env.config} | {Path(k).parent for k in self.data["dirlinks"]}:
            if not parent.is_dir():
                continue
            for stray in parent.glob(".*.lg-tmp"):
                if not stray.is_dir() or stray.is_symlink():
                    continue            # atomic_write's temp files are files, and not ours to sweep
                base = parent / stray.name[1:-len(".lg-tmp")].rsplit(".", 1)[0]
                with contextlib.suppress(OSError):
                    if str(base) in self.data["dirlinks"] and not base.exists() and not base.is_symlink():
                        os.rename(stray, base)      # stopped between unlink and rename
                    else:
                        shutil.rmtree(stray)
        for key, e in self.data["dirlinks"].items():
            folder = Path(key)
            if folder.is_symlink() or not folder.is_dir():
                continue
            real = (folder.parent / e["link"]).resolve()
            made = e.setdefault("made", [])
            for name in list(made):
                q = folder / name
                if q.is_symlink() and not q.exists():           # the theme dropped that file
                    q.unlink()
                if not q.is_symlink() and not q.exists():
                    made.remove(name)
            if real.is_dir():
                for entry in sorted(real.iterdir()):
                    q = folder / entry.name
                    if not q.exists() and not q.is_symlink():
                        q.symlink_to(entry)
                        made.append(entry.name)
        self.save()

    def overwritten(self) -> list[str]:
        """Targets whose files were replaced by something else since Apply (a theme
        update relinking gtk.css, for one), so their look is gone until the next Apply."""
        lost = set()
        for key, e in self.data["files"].items():
            if e.get("wrote") and not self.is_ours(Path(key), e):
                lost.add(e["target"])
        return sorted(lost)

    def record_file(self, target: str, path: Path) -> None:
        if (folder := self.linked_folder(path)) is not None:
            self.unlink_folder(target, folder)
        key = str(path)
        if self.env.dry_run:
            return
        if (old := self.data["files"].get(key)) is not None:
            if not old.get("wrote") or self.is_ours(path, old) or self._has_header(path):
                return
            # Something else replaced what we wrote (a theme update relinking gtk.css):
            # that is the user's look now, so Revert should bring that back, not the old one.
            # The old copy goes only once the new original is safely stored (below).
        entry: dict = {"target": target}
        if path.is_dir() and not path.is_symlink():
            # A folder is never ours to replace (and revert must never delete it).
            raise IsADirectoryError(f"{path} is a folder")
        if path.is_symlink():
            entry.update(kind="symlink", link=os.readlink(path))
        elif path.is_file():
            store = self.root / "files"
            store.mkdir(parents=True, exist_ok=True)
            os.chmod(self.root, 0o700)
            digest = hashlib.sha256(key.encode()).hexdigest()[:16]
            copy = store / f"{digest}-{path.name}"
            fresh = copy.with_name(copy.name + ".new")
            shutil.copy2(path, fresh)
            os.replace(fresh, copy)       # never a moment without a stored original
            entry.update(kind="file", copy=str(copy), mode=path.stat().st_mode & 0o777)
        else:
            # Folders this write will create, so revert can take them away again.
            new_dirs, d = [], path.parent
            while d != d.parent and not d.exists():
                new_dirs.append(str(d))
                d = d.parent
            entry.update(kind="missing", new_dirs=new_dirs)
        if old is not None and old.get("copy") and old["copy"] != entry.get("copy"):
            self._forget_file(key, old)
        self.data["files"][key] = entry

    def record_gsetting(self, target: str, env: Env, g: GSet) -> bool:
        key = f"{g.schema}|{g.path or ''}|{g.key}"
        if key in self.data["gsettings"]:
            return True
        old = env.gsettings_get(g.schema, g.key, g.path)
        if old is None:
            return False
        self.data["gsettings"][key] = {"target": target, "value": old}
        return True

    def reset_gsetting(self, target: str, env: Env, g: GReset) -> str | None:
        """Undo this target's change to one key. Returns a problem, or None."""
        key = f"{g.schema}|{g.path or ''}|{g.key}"
        e = self.data["gsettings"].get(key)
        if not e or e["target"] != target:
            return None
        if self.changed_since(env, key, e):
            del self.data["gsettings"][key]     # the user's own choice now; leave it
            return None
        r = env.gsettings_set(g.schema, g.key, e["value"], g.path)
        if not r.ok:
            return f"{g.schema} {g.key}: {r.err.strip()}"
        if not env.dry_run:
            del self.data["gsettings"][key]
        return None

    @staticmethod
    def changed_since(env: Env, key: str, e: dict) -> bool:
        """Whether the user changed a key we marked as theirs to keep after we set it."""
        if "ours" not in e:
            return False
        schema, path, k = key.split("|", 2)
        return env.gsettings_get(schema, k, path or None) != e["ours"]

    def record_command(self, target: str, c: Command) -> None:
        if c.undo:
            self.data["commands"][" ".join(c.argv)] = {"target": target, "undo": list(c.undo)}

    # ---- restoring ------------------------------------------------------------
    def restore(self, target: str | None = None) -> list[str]:
        """Restore one target (or all). Returns problems, empty if clean."""
        problems: list[str] = []
        mine = lambda e: not target or e["target"] == target  # noqa: E731
        new_dirs: set[str] = set()
        for key, e in list(self.data["files"].items()):
            if mine(e) and (problem := self._restore_file(key, e, new_dirs)):
                problems.append(problem)
        _remove_empty(new_dirs)
        for key, e in list(self.data["dirlinks"].items()):
            if mine(e) and (problem := self._restore_folder(key, e)):
                problems.append(problem)
        for key, e in list(self.data["gsettings"].items()):
            if not mine(e):
                continue
            schema, path, k = key.split("|", 2)
            if self.changed_since(self.env, key, e):
                del self.data["gsettings"][key]
                continue
            r = self.env.gsettings_set(schema, k, e["value"], path or None)
            if r.ok:
                del self.data["gsettings"][key]
            else:
                problems.append(f"{schema} {k}: {r.err.strip()}")
        for key, e in list(self.data["lists"].items()):
            if not mine(e):
                continue
            schema, path, k = key.split("|", 2)
            items = parse_strv(self.env.gsettings_get(schema, k, path or None))
            items = [i for i in items if i not in e["added"]]
            items += [i for i in e["removed"] if i not in items]
            r = self.env.gsettings_set(schema, k, format_strv(items), path or None)
            if r.ok:
                del self.data["lists"][key]
            else:
                problems.append(f"{schema} {k}: {r.err.strip()}")
        for tid, e in list(self.data["flatpak"].items()):
            if not mine(e):
                continue
            try:
                _flatpak_undo(self.env, e)
                del self.data["flatpak"][tid]
            except (OSError, configparser.Error) as err:
                problems.append(f"Flatpak overrides: {err}")
        for key, e in list(self.data["commands"].items()):
            if not mine(e):
                continue
            r = self.env.run(e["undo"])
            if r.ok:
                del self.data["commands"][key]
            else:
                problems.append(f"{' '.join(e['undo'])}: {r.err.strip()}")
        self.save()
        return problems

    def _restore_file(self, key: str, e: dict, new_dirs: set[str]) -> str | None:
        """Put one recorded file back. Returns a problem, or None."""
        p = Path(key)
        try:
            if p.is_dir() and not p.is_symlink():
                # Not something we wrote: never delete a folder the user made there.
                if e["kind"] != "missing":
                    raise IsADirectoryError("is now a folder, left as it is")
                del self.data["files"][key]
                return None
            # Read the copy first, so a lost backup never costs the current file.
            original = Path(e["copy"]).read_bytes() if e["kind"] == "file" else None
            if p.is_symlink() or p.exists():
                p.unlink()
            if e["kind"] == "symlink":
                p.parent.mkdir(parents=True, exist_ok=True)
                p.symlink_to(e["link"])
            elif original is not None:
                atomic_write(p, original, e.get("mode", 0o644))
                with contextlib.suppress(OSError):
                    os.unlink(e["copy"])
            new_dirs.update(e.get("new_dirs", []))
            del self.data["files"][key]
        except OSError as err:
            return f"{p}: {err}"
        return None

    def _restore_folder(self, key: str, e: dict) -> str | None:
        """Turn a folder we made back into the link it was. Anything the user has since
        put in it stays, and then so does the folder."""
        p = Path(key)
        try:
            if p.is_symlink():
                del self.data["dirlinks"][key]      # already a link again
                return None
            if p.is_dir():
                for name in e.get("made", []):
                    q = p / name
                    if q.is_symlink():
                        q.unlink()
                p.rmdir()                           # fails while the user's own files are in it
            p.symlink_to(e["link"])
            del self.data["dirlinks"][key]
        except OSError as err:
            owner = Path(e["link"]).parent.name or e["link"]
            if err.errno in (errno.ENOTEMPTY, errno.EEXIST):
                return (f"Kept your {p.name} folder because it has files you added. "
                        f"Your link to {owner} was not restored.")
            return f"Couldn't restore your {p.name} link to {owner}: {err.strerror or err}."
        return None

    def targets_with_changes(self) -> set[str]:
        return {e["target"] for section in self.data.values() for e in section.values()}


# ---- Flatpak global override (a GLib keyfile flatpak itself reads) ---------------
def _flatpak_file(env: Env) -> Path:
    return env.data / "flatpak/overrides/global"


def _flatpak_read(path: Path) -> configparser.RawConfigParser:
    cp = configparser.RawConfigParser(delimiters=("=",), comment_prefixes=("#",), strict=False)
    cp.optionxform = str  # keys are case-sensitive
    if path.is_file():
        cp.read_string(path.read_text(encoding="utf-8"))
    return cp


def _flatpak_write(path: Path, cp: configparser.RawConfigParser) -> None:
    buf = io.StringIO()
    cp.write(buf, space_around_delimiters=False)
    atomic_write(path, buf.getvalue().encode(), 0o644)


def _fs_list(cp: configparser.RawConfigParser) -> list[str]:
    raw = cp.get("Context", "filesystems", fallback="")
    return [x for x in raw.split(";") if x]


def _set_fs(cp: configparser.RawConfigParser, items: list[str]) -> None:
    if items:
        if not cp.has_section("Context"):
            cp.add_section("Context")
        cp.set("Context", "filesystems", ";".join(items) + ";")
    elif cp.has_option("Context", "filesystems"):
        cp.remove_option("Context", "filesystems")


def _flatpak_apply(env: Env, target: str, a: FlatpakOverride, backup: Backup) -> None:
    path = _flatpak_file(env)
    cp = _flatpak_read(path)
    rec = backup.data["flatpak"].setdefault(target, {"target": target, "filesystems": [], "env": {}})
    fs = _fs_list(cp)
    for f in a.filesystems:
        if f not in fs:
            fs.append(f)
            if f not in rec["filesystems"]:
                rec["filesystems"].append(f)
    _set_fs(cp, fs)
    for k, v in a.env:
        if not cp.has_section("Environment"):
            cp.add_section("Environment")
        if k not in rec["env"]:
            rec["env"][k] = cp.get("Environment", k, fallback=None)  # None: wasn't set
        cp.set("Environment", k, v)
    if not env.dry_run:
        _flatpak_write(path, cp)


def _flatpak_undo(env: Env, rec: dict) -> None:
    path = _flatpak_file(env)
    if not path.is_file():
        return
    cp = _flatpak_read(path)
    _set_fs(cp, [f for f in _fs_list(cp) if f not in rec.get("filesystems", [])])
    for k, old in rec.get("env", {}).items():
        if old is None:
            if cp.has_option("Environment", k):
                cp.remove_option("Environment", k)
        else:
            cp.set("Environment", k, old)
    for sec in ("Context", "Environment"):
        if cp.has_section(sec) and not cp.items(sec):
            cp.remove_section(sec)
    _flatpak_write(path, cp)


class Engine:
    def __init__(self, env: Env | None = None, targets: list[Target] | None = None):
        self.env = env or Env()
        self.targets = targets if targets is not None else all_targets()

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        """One Apply/Revert at a time (the app and the dark/light watcher may race)."""
        d = self.env.state / "liquid-glass"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "lock", "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def context(self, settings: Settings) -> Context:
        accent = self.env.system_accent()
        dark = palette.build(settings, dark=True, system_accent=accent)
        light = palette.build(settings, dark=False, system_accent=accent)
        if settings.scheme == "auto":
            use_dark = self.env.prefers_dark()
        else:
            use_dark = settings.scheme == "dark"
        return Context(settings=settings, tokens=dark if use_dark else light,
                       dark=dark, light=light, env=self.env)

    def plan(self, settings: Settings) -> dict[str, list[Action]]:
        ctx = self.context(settings)
        out: dict[str, list[Action]] = {}
        for t in self.targets:
            if settings.target_enabled(t.id) and t.detect(self.env).available:
                out[t.id] = t.plan(ctx)
        return out

    def is_applied(self) -> bool:
        """True while anything Liquid Glass changed is still in place."""
        return bool(Backup(self.env).targets_with_changes())

    def apply(self, settings: Settings, only: set[str] | None = None) -> list[Result]:
        with self._locked():
            return self._apply(settings, only)

    def _apply(self, settings: Settings, only: set[str] | None) -> list[Result]:
        ctx = self.context(settings)
        backup = Backup(self.env)
        backup.tidy_folders()
        results: list[Result] = []
        for t in self.targets:
            if only and t.id not in only:
                continue
            if not settings.target_enabled(t.id):
                if t.id in backup.targets_with_changes():
                    probs = backup.restore(t.id)
                    results.append(Result(t.id, t.name, "failed" if probs else "reverted", "; ".join(probs)))
                continue
            det = t.detect(self.env)
            if not det.available:
                results.append(Result(t.id, t.name, "skipped", det.detail))
                continue
            actions: list[Action] = []
            try:
                actions = t.plan(ctx)
                errs = self._run(t.id, actions, backup)
            except Exception as e:  # a broken target must not stop the others
                errs = [f"{type(e).__name__}: {e}"]
            backup.save()
            if errs:
                results.append(Result(t.id, t.name, "failed", "; ".join(errs)))
            elif not actions:
                results.append(Result(t.id, t.name, "info", " ".join(t.live_notes(ctx)) or t.summary))
            else:
                results.append(Result(t.id, t.name, "applied"))
        self._write_tokens(ctx)
        return results

    def revert(self, target: str | None = None) -> list[str]:
        with self._locked():
            problems = Backup(self.env).restore(target)
            if target is None and not problems and not self.env.dry_run:
                for name in ("tokens.json", "tokens-dark.json", "tokens-light.json"):
                    with contextlib.suppress(OSError):
                        (config_dir() / name).unlink()   # apps that read them go back to their own look
            return problems

    # ---- internals ------------------------------------------------------------
    def _run(self, tid: str, actions: list[Action], backup: Backup) -> list[str]:
        errs: list[str] = []
        for a in actions:
            if isinstance(a, WriteFile):
                backup.record_file(tid, a.path)
                if not self.env.dry_run:
                    data = a.content.encode() if isinstance(a.content, str) else a.content
                    atomic_write(a.path, data, a.mode)
                    if (rec := backup.data["files"].get(str(a.path))) is not None:
                        rec["wrote"] = hashlib.sha256(data).hexdigest()
            elif isinstance(a, GSet):
                if a.key not in self.env.gsettings_keys(a.schema, a.path):
                    if not a.optional:
                        errs.append(f"missing setting {a.schema} {a.key}")
                    continue
                if not backup.record_gsetting(tid, self.env, a):
                    continue
                r = self.env.gsettings_set(a.schema, a.key, a.value, a.path)
                if not r.ok:
                    errs.append(f"{a.schema} {a.key}: {r.err.strip()}")
                elif a.keep_user_change and not self.env.dry_run:
                    backup.data["gsettings"][f"{a.schema}|{a.path or ''}|{a.key}"]["ours"] = a.value
            elif isinstance(a, GReset):
                if (err := backup.reset_gsetting(tid, self.env, a)):
                    errs.append(err)
            elif isinstance(a, ListEdit):
                if a.key not in self.env.gsettings_keys(a.schema, a.path):
                    continue
                items = parse_strv(self.env.gsettings_get(a.schema, a.key, a.path))
                key = f"{a.schema}|{a.path or ''}|{a.key}"
                rec = backup.data["lists"].get(key, {"target": tid, "added": [], "removed": []})
                changed = False
                for i in a.add:
                    if i not in items:
                        items.append(i)
                        changed = True
                        if i not in rec["added"]:
                            rec["added"].append(i)
                for i in a.remove:
                    if i in items:
                        items.remove(i)
                        changed = True
                        if i not in rec["removed"]:
                            rec["removed"].append(i)
                if changed:
                    # Only a real change is recorded, so an untouched list doesn't count as applied.
                    backup.data["lists"][key] = rec
                    r = self.env.gsettings_set(a.schema, a.key, format_strv(items), a.path)
                    if not r.ok:
                        errs.append(f"{a.schema} {a.key}: {r.err.strip()}")
            elif isinstance(a, FlatpakOverride):
                _flatpak_apply(self.env, tid, a, backup)
            elif isinstance(a, Command):
                if not self.env.which(a.argv[0]):
                    continue
                for p in a.touches:
                    backup.record_file(tid, p)
                backup.record_command(tid, a)
                if self.env.dry_run:
                    continue
                r = self.env.run(list(a.argv), timeout=120)
                if not r.ok:
                    errs.append(f"{a.argv[0]}: {r.err.strip()[:200]}")
        return errs

    def _write_tokens(self, ctx: Context) -> None:
        if self.env.dry_run:
            return
        d = config_dir()
        atomic_write(d / "tokens-dark.json", ctx.dark.to_json().encode())
        atomic_write(d / "tokens-light.json", ctx.light.to_json().encode())
        atomic_write(d / "tokens.json", ctx.tokens.to_json().encode())
