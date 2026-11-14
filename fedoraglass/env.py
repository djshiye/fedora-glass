"""The machine we theme: paths, commands and gsettings, behind one object.

Everything that touches the system goes through Env so tests can point it at
a temporary home and a fake command runner. Commands are always run as an
argument list (never through a shell) and never with elevated rights.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RunResult:
    code: int
    out: str
    err: str

    @property
    def ok(self) -> bool:
        return self.code == 0


@dataclass
class Env:
    home: Path = field(default_factory=Path.home)
    dry_run: bool = False
    # Per Apply/Restore (Engine._locked clears them): where each schema lives and its
    # keys. Without them every key set read every extension's schema files again and
    # ran `gsettings list-keys`, about 170 extra runs per Apply.
    _schemadirs: dict = field(default_factory=dict, repr=False, compare=False)
    _keys: dict = field(default_factory=dict, repr=False, compare=False)
    # Reading settings in this process (see _schema_here): the schema sources, per
    # schemadir, and whether PyGObject is there at all. An Apply reads about a hundred keys,
    # and starting a `gsettings get` for each was most of its time.
    _sources: dict = field(default_factory=dict, repr=False, compare=False)
    _gio: object = field(default=None, repr=False, compare=False)
    _glib: object = field(default=None, repr=False, compare=False)
    # Settings set inside gsettings_batch, not written yet: (schema, path) -> the delayed
    # Gio.Settings and the text of each key set in it. None outside a batch.
    _batch: dict | None = field(default=None, repr=False, compare=False)

    def forget_cache(self) -> None:
        self._schemadirs.clear()
        self._keys.clear()
        self._sources.clear()     # schemas installed or removed since are seen again

    # ---- XDG paths ----------------------------------------------------
    @property
    def config(self) -> Path:
        return Path(os.environ.get("XDG_CONFIG_HOME") or self.home / ".config")

    @property
    def data(self) -> Path:
        return Path(os.environ.get("XDG_DATA_HOME") or self.home / ".local/share")

    @property
    def cache(self) -> Path:
        return Path(os.environ.get("XDG_CACHE_HOME") or self.home / ".cache")

    @property
    def state(self) -> Path:
        return Path(os.environ.get("XDG_STATE_HOME") or self.home / ".local/state")

    # ---- commands -------------------------------------------------------
    def which(self, name: str) -> str | None:
        return shutil.which(name)

    def run(self, argv: list[str], timeout: float = 30) -> RunResult:
        if (r := self._shell_call_here(argv, timeout)) is not None:
            return r
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                               stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as e:
            return RunResult(127, "", str(e))
        return RunResult(p.returncode, p.stdout, p.stderr)

    # GNOME Shell's extension calls (is the glass running, switch an extension off and on)
    # come several times per Apply, and the app's Apply asks once per part. Made here on
    # the session bus, they answer in the text `gdbus call` prints, without starting it.
    _SHELL_CALLS = ("GetExtensionInfo", "EnableExtension", "DisableExtension")

    def _shell_call_here(self, argv: list[str], timeout: float) -> RunResult | None:
        if (len(argv) != 10 or argv[:3] != ["gdbus", "call", "--session"] or argv[3] != "--dest"
                or argv[4] != "org.gnome.Shell" or argv[5:7] != ["--object-path", "/org/gnome/Shell"]
                or argv[7] != "--method" or argv[8].rpartition(".")[0] != "org.gnome.Shell.Extensions"
                or argv[8].rpartition(".")[2] not in self._SHELL_CALLS):
            return None
        try:
            import gi
            gi.require_version("Gio", "2.0")
            gi.require_version("GLib", "2.0")
            from gi.repository import Gio, GLib
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception:
            return None     # gdbus answers instead
        try:
            out = bus.call_sync("org.gnome.Shell", "/org/gnome/Shell", "org.gnome.Shell.Extensions",
                                argv[8].rpartition(".")[2], GLib.Variant("(s)", (argv[9],)), None,
                                Gio.DBusCallFlags.NONE, int(timeout * 1000), None)
        except GLib.Error as e:
            return RunResult(1, "", f"Error: {e.message}\n")
        except Exception:
            return None
        return RunResult(0, out.print_(True) + "\n", "")

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    # ---- GNOME Shell extensions ----------------------------------------
    def extension_dirs(self) -> list[Path]:
        return [self.data / "gnome-shell/extensions",
                Path("/usr/local/share/gnome-shell/extensions"),
                Path("/usr/share/gnome-shell/extensions")]

    def extension_path(self, uuid: str) -> Path | None:
        for d in self.extension_dirs():
            p = d / uuid
            if (p / "metadata.json").is_file():
                return p
        return None

    def extension_enabled(self, uuid: str) -> bool:
        v = self.gsettings_get("org.gnome.shell", "enabled-extensions")
        return v is not None and f"'{uuid}'" in v

    def extensions_switched_off(self) -> bool:
        """GNOME's "Extensions" switch is off (disable-user-extensions): none of them run."""
        return (self.gsettings_get("org.gnome.shell", "disable-user-extensions") or "").strip() == "true"

    def extension_on(self, uuid: str) -> bool:
        """The one rule for "the user has this extension": installed, on GNOME's list of
        switched-on extensions, not on its switched-off list (that one wins in GNOME too),
        and extensions not switched off altogether. Settings, not what runs this second:
        while GNOME Shell restarts an extension is briefly not running, but still on."""
        if self.extension_path(uuid) is None or not self.extension_enabled(uuid):
            return False
        off = self.gsettings_get("org.gnome.shell", "disabled-extensions")
        return not (off is not None and f"'{uuid}'" in off) and not self.extensions_switched_off()

    # ---- gsettings --------------------------------------------------------
    def _schemadir_for(self, schema: str) -> Path | None:
        """Extension schemas often live only inside the extension folder."""
        if schema not in self._schemadirs:
            self._schemadirs[schema] = self._find_schemadir(schema)
        return self._schemadirs[schema]

    def _find_schemadir(self, schema: str) -> Path | None:
        if "" not in self._schemadirs:
            self._schemadirs[""] = self._schema_index()
        return self._schemadirs[""].get(schema)

    def _schema_index(self) -> dict[str, Path]:
        """Every extension schema and the folder it lives in, the first folder found winning:
        read once per Apply, not once per schema asked about (most never are in one)."""
        index: dict[str, Path] = {}
        for d in self.extension_dirs():
            if not d.is_dir():
                continue
            for sd in sorted(d.glob("*/schemas")):    # same answer on every filesystem
                if not (sd / "gschemas.compiled").exists():
                    continue
                for xml in sorted(sd.glob("*.gschema.xml")):
                    index.setdefault(xml.name.removesuffix(".gschema.xml"), sd)
                    # Child schemas (e.g. blur-my-shell.popup) live in the parent's file.
                    try:
                        text = xml.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
                    for sid in re.findall(r'\bid="([^"]+)"', text):
                        index.setdefault(sid, sd)
        return index

    def _gs(self, schema: str, path: str | None) -> tuple[list[str], str]:
        argv = ["gsettings"]
        if (sd := self._schemadir_for(schema)) is not None:
            argv += ["--schemadir", str(sd)]
        return argv, f"{schema}:{path}" if path else schema

    # ---- reading settings in this process --------------------------------
    # The same answers `gsettings list-keys` and `gsettings get` give, without starting a
    # program for each: the same schemas (the extension's own folder first, then the
    # user's and the system's, looked up afresh after each forget_cache) and the same
    # text for each value. Writes still go through `gsettings`. When something can't be
    # told here (no PyGObject, an unusual schema), the old way answers.
    _NOT_HERE = object()

    def _gio_module(self):
        if type(self).run is not Env.run:
            return None     # commands are faked (tests): answer through them
        if self._gio is None:
            try:
                import gi
                gi.require_version("Gio", "2.0")
                from gi.repository import Gio
                # Only GNOME's own store (dconf) is read here: it sees another program's
                # write at once, on every read. GLib's stand-ins don't (memory forgets,
                # a keyfile is read again only when the main loop runs).
                backend = type(Gio.SettingsBackend.get_default()).__name__
                self._gio = Gio if "DConf" in backend else False
            except Exception:
                self._gio = False
        return self._gio or None

    def _schema_source(self, Gio, schemadir: Path | None):
        """GLib's own search order, built afresh: GSETTINGS_SCHEMA_DIR, then the user's data
        folder, then XDG_DATA_DIRS in order (GLib's default source is made once per process
        and would never see a schema installed while the app is open)."""
        if schemadir in self._sources:
            return self._sources[schemadir]
        if None not in self._sources:
            dirs = [d for d in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":") if d]
            found = [Path(d) / "glib-2.0/schemas" for d in dirs]
            found.insert(0, self.data / "glib-2.0/schemas")
            found[:0] = reversed([Path(d) for d in (os.environ.get("GSETTINGS_SCHEMA_DIR") or "").split(":") if d])
            src = None
            for d in reversed(found):           # lowest priority first: it is the parent
                if (d / "gschemas.compiled").is_file():
                    try:
                        src = Gio.SettingsSchemaSource.new_from_directory(str(d), src, False)
                    except Exception:
                        continue
            self._sources[None] = src
        src = self._sources[None]
        if schemadir is not None:
            try:
                src = Gio.SettingsSchemaSource.new_from_directory(str(schemadir), src, False)
            except Exception:
                src = self._NOT_HERE
            self._sources[schemadir] = src
        return src

    def _schema_here(self, schema: str, path: str | None):
        """The schema, for reading here; None when gsettings would fail too (no such
        schema, a path where none fits); _NOT_HERE when only gsettings can tell."""
        Gio = self._gio_module()
        if Gio is None:
            return self._NOT_HERE
        try:
            src = self._schema_source(Gio, self._schemadir_for(schema))
            if src is self._NOT_HERE:
                return self._NOT_HERE
            found = src.lookup(schema, True) if src is not None else None
            if found is not None and path is not None:
                # GLib aborts the whole program on a bad path: check it the way gsettings does.
                if found.get_path() is not None or not path.startswith("/") or not path.endswith("/") or "//" in path:
                    return None
            return found
        except Exception:
            return self._NOT_HERE

    def gsettings_keys(self, schema: str, path: str | None = None) -> set[str]:
        if (schema, path) in self._keys:
            return set(self._keys[(schema, path)])
        here = self._schema_here(schema, path)
        if here is None:
            return set()
        if here is not self._NOT_HERE:
            keys = set(here.list_keys())
            self._keys[(schema, path)] = keys
            return set(keys)
        argv, sid = self._gs(schema, path)
        r = self.run(argv + ["list-keys", sid])
        keys = set(r.out.split()) if r.ok else set()
        if r.ok:
            self._keys[(schema, path)] = keys
        return set(keys)

    def gsettings_get(self, schema: str, key: str, path: str | None = None) -> str | None:
        if self._batch and key in (pending := self._batch.get((schema, path), {})).get("values", {}):
            return pending["values"][key]       # set in this batch, not written yet
        found = self._schema_here(schema, path)
        if found is None:
            return None
        if found is not self._NOT_HERE:
            if not found.has_key(key) or (path is None and found.get_path() is None):
                return None     # no such key, or a relocatable schema without its path
            try:
                Gio = self._gio_module()
                return Gio.Settings.new_full(found, None, path).get_value(key).print_(True)
            except Exception:
                pass    # fall through to gsettings
        argv, sid = self._gs(schema, path)
        r = self.run(argv + ["get", sid, key])
        return r.out.strip() if r.ok else None

    def gsettings_set(self, schema: str, key: str, value: str, path: str | None = None) -> RunResult:
        argv, sid = self._gs(schema, path)
        if self.dry_run:
            return RunResult(0, "", "")
        if self._batch is not None and (r := self._set_here(schema, key, value, path)) is not None:
            return r
        return self.run(argv + ["set", sid, key, value])

    def gsettings_reset(self, schema: str, key: str, path: str | None = None) -> RunResult:
        """Take the user's own value away, so the key follows its default again."""
        argv, sid = self._gs(schema, path)
        if self.dry_run:
            return RunResult(0, "", "")
        self._flush_batch()     # what was set before it goes out first, in its order
        return self.run(argv + ["reset", sid, key])

    # ---- writing settings in this process ------------------------------------
    # A dark/light switch sets some 40 keys (Dash to Panel, ArcMenu, Spawn, User Themes),
    # and starting a `gsettings set` for each was most of its time. Inside a batch they are
    # set here instead, through GNOME's own store (dconf only, as for reading), and go out
    # together at its end: one change per schema, so Dash to Panel hears of them once.
    # Whatever can't be done here (no PyGObject, a value or schema only gsettings can tell
    # about, a key that is locked) goes through `gsettings`, which says why it failed.
    @contextlib.contextmanager
    def gsettings_batch(self):
        if self._batch is not None or self.dry_run:
            yield               # already in one: it goes out at the end of that one
            return
        self._batch = {}
        try:
            yield
        finally:
            try:
                self._flush_batch()
            finally:
                self._batch = None

    def _glib_module(self):
        if self._glib is None:
            try:
                import gi
                gi.require_version("GLib", "2.0")
                from gi.repository import GLib
                self._glib = GLib
            except Exception:
                self._glib = False
        return self._glib or None

    def _set_here(self, schema: str, key: str, value: str, path: str | None) -> RunResult | None:
        """Set one key in the batch, as `gsettings set` would. None: gsettings does it."""
        found = self._schema_here(schema, path)
        if found is None or found is self._NOT_HERE:
            return None
        Gio, GLib = self._gio_module(), self._glib_module()
        if Gio is None or GLib is None:
            return None
        try:
            if not found.has_key(key) or (path is None and found.get_path() is None):
                return None
            k = found.get_key(key)
            try:
                v = GLib.Variant.parse(k.get_value_type(), value, None, None)
            except Exception:
                return None     # gsettings says what is wrong with the value
            if not k.range_check(v):
                return None
            entry = self._batch.get((schema, path))
            if entry is not None and key in entry["values"]:
                # The same key twice (User Themes' name, away and back so it loads the new
                # style sheet): the first value goes out on its own first. In one change
                # dconf would see only the last, which it already has, and drop it.
                self._flush_batch()
                entry = None
            if entry is None:
                gs = Gio.Settings.new_full(found, None, path)
                gs.delay()
                entry = {"settings": gs, "values": {}}
            gs = entry["settings"]
            if not gs.is_writable(key) or not gs.set_value(key, v):
                return None     # locked by the administrator: gsettings says so
            entry["values"][key] = v.print_(True)
            self._batch[(schema, path)] = entry
        except Exception:
            return None
        return RunResult(0, "", "")

    def _flush_batch(self) -> None:
        """Write what the batch holds now, and wait until GNOME's store has it."""
        batch = self._batch
        if not batch:
            return
        self._batch = {}
        try:
            for entry in batch.values():
                entry["settings"].apply()
            self._gio_module().Settings.sync()
        except Exception:
            # Written here or not, `gsettings` sets them again (the same value twice
            # changes nothing).
            for (schema, path), entry in batch.items():
                argv, sid = self._gs(schema, path)
                for key, text in entry["values"].items():
                    self.run(argv + ["set", sid, key, text])

    def gsettings_is_default(self, schema: str, key: str, value: str, path: str | None = None) -> bool | None:
        """Whether `value` (as `gsettings get` prints it) is the key's default. None when
        that can't be told (no PyGObject, an unknown schema); then nothing changes."""
        try:
            import gi
            gi.require_version("GLib", "2.0")
            gi.require_version("Gio", "2.0")
            from gi.repository import Gio, GLib
            default = Gio.SettingsSchemaSource.get_default()
            sd = self._schemadir_for(schema)
            src = Gio.SettingsSchemaSource.new_from_directory(str(sd), default, False) if sd else default
            found = src.lookup(schema, True) if src is not None else None
            if found is None or not found.has_key(key):
                return None
            k = found.get_key(key)
            return GLib.Variant.parse(k.get_value_type(), value, None, None).equal(k.get_default_value())
        except Exception:      # a broken schema or value: keep the old way
            return None

    # ---- desktop state -----------------------------------------------------
    def prefers_dark(self) -> bool:
        v = self.gsettings_get("org.gnome.desktop.interface", "color-scheme") or ""
        return "dark" in v

    def high_contrast(self) -> bool:
        """GNOME's High Contrast switch (Accessibility). Glass goes opaque while it is on."""
        v = self.gsettings_get("org.gnome.desktop.a11y.interface", "high-contrast") or ""
        return v.strip() == "true"

    def system_accent(self) -> str | None:
        v = self.gsettings_get("org.gnome.desktop.interface", "accent-color")
        return v.strip("'") if v else None

    def wallpaper(self) -> Path | None:
        key = "picture-uri-dark" if self.prefers_dark() else "picture-uri"
        v = self.gsettings_get("org.gnome.desktop.background", key) or ""
        v = v.strip("'")
        if v.startswith("file://"):
            from urllib.parse import unquote, urlparse
            p = Path(unquote(urlparse(v).path))
            return p if p.is_file() else None
        return None

    def flatpak_installed(self, app_id: str) -> bool:
        """The Flatpak app is really installed, for the user or system-wide: it has its
        `current` link, or a branch with an `active` build (the link can be missing while a
        second branch is still there). Flatpak keeps an app's data in ~/.var/app after an
        uninstall, so that folder proves nothing."""
        roots = (Path(os.environ.get("FLATPAK_USER_DIR") or self.data / "flatpak"),
                 Path(os.environ.get("FLATPAK_SYSTEM_DIR") or "/var/lib/flatpak"))
        for r in roots:
            app = r / "app" / app_id
            try:
                if (app / "current").exists() or (app / "current").is_symlink() or any(app.glob("*/*/active")):
                    return True
            except OSError:
                continue
        return False
