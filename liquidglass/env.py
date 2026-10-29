"""The machine we theme: paths, commands and gsettings, behind one object.

Everything that touches the system goes through Env so tests can point it at
a temporary home and a fake command runner. Commands are always run as an
argument list (never through a shell) and never with elevated rights.
"""

from __future__ import annotations

import os
import shutil
import subprocess
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

    # ---- XDG paths ----------------------------------------------------
    @property
    def config(self) -> Path:
        return Path(os.environ.get("XDG_CONFIG_HOME") or self.home / ".config")

    @property
    def data(self) -> Path:
        return Path(os.environ.get("XDG_DATA_HOME") or self.home / ".local/share")

    @property
    def state(self) -> Path:
        return Path(os.environ.get("XDG_STATE_HOME") or self.home / ".local/state")

    # ---- commands -------------------------------------------------------
    def which(self, name: str) -> str | None:
        return shutil.which(name)

    def run(self, argv: list[str], timeout: float = 30) -> RunResult:
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                               stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as e:
            return RunResult(127, "", str(e))
        return RunResult(p.returncode, p.stdout, p.stderr)

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

    # ---- gsettings --------------------------------------------------------
    def _schemadir_for(self, schema: str) -> Path | None:
        """Extension schemas often live only inside the extension folder."""
        for d in self.extension_dirs():
            if not d.is_dir():
                continue
            for sd in d.glob("*/schemas"):
                if not (sd / "gschemas.compiled").exists():
                    continue
                if (sd / f"{schema}.gschema.xml").exists():
                    return sd
                # Child schemas (e.g. blur-my-shell.popup) live in the parent's file.
                needle = f'id="{schema}"'
                for xml in sd.glob("*.gschema.xml"):
                    try:
                        if needle in xml.read_text(encoding="utf-8", errors="replace"):
                            return sd
                    except OSError:
                        continue
        return None

    def _gs(self, schema: str, path: str | None) -> tuple[list[str], str]:
        argv = ["gsettings"]
        if (sd := self._schemadir_for(schema)) is not None:
            argv += ["--schemadir", str(sd)]
        return argv, f"{schema}:{path}" if path else schema

    def gsettings_keys(self, schema: str, path: str | None = None) -> set[str]:
        argv, sid = self._gs(schema, path)
        r = self.run(argv + ["list-keys", sid])
        return set(r.out.split()) if r.ok else set()

    def gsettings_get(self, schema: str, key: str, path: str | None = None) -> str | None:
        argv, sid = self._gs(schema, path)
        r = self.run(argv + ["get", sid, key])
        return r.out.strip() if r.ok else None

    def gsettings_set(self, schema: str, key: str, value: str, path: str | None = None) -> RunResult:
        argv, sid = self._gs(schema, path)
        if self.dry_run:
            return RunResult(0, "", "")
        return self.run(argv + ["set", sid, key, value])

    # ---- desktop state -----------------------------------------------------
    def prefers_dark(self) -> bool:
        v = self.gsettings_get("org.gnome.desktop.interface", "color-scheme") or ""
        return "dark" in v

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
        for root in (self.data / "flatpak/app", Path("/var/lib/flatpak/app")):
            if (root / app_id).is_dir():
                return True
        return False
