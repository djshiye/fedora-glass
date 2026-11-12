"""Settings written in this process, one change per schema (Env.gsettings_batch): a dark/light
switch no longer starts a `gsettings set` for each of its ~40 keys. Driven through a fake Gio
and dconf here (PyGObject's Gio is not needed, nor GNOME); the real one is the same calls."""
from __future__ import annotations

import pytest

from fedoraglass.engine import Engine
from fedoraglass.env import Env, RunResult
from fedoraglass.settings import Settings
from fedoraglass.targets.base import GReset, GSet, Target


class Dconf:
    """GNOME's settings store: what is written, and each change as it goes out."""

    def __init__(self):
        self.values: dict[str, dict[str, str]] = {}
        self.changes: list[tuple[str, dict]] = []
        self.syncs = 0
        self.locked: set[tuple[str, str]] = set()
        self.fail_apply = False


class Variant:
    def __init__(self, text):
        self.text = text

    def print_(self, annotate):
        return self.text


class Key:
    def __init__(self, name):
        self.name = name

    def get_value_type(self):
        return "s"

    def range_check(self, v):
        return v.text != "'out-of-range'"


class Schema:
    def __init__(self, store, sid):
        self.store, self.sid = store, sid

    def has_key(self, key):
        return key in self.store.values.get(self.sid, {})

    def get_key(self, key):
        return Key(key)

    def get_path(self):
        return "/" + self.sid.replace(".", "/") + "/"

    def list_keys(self):
        return list(self.store.values.get(self.sid, {}))


def fake_gi(store):
    class Settings:
        @staticmethod
        def new_full(schema, backend, path):
            return Settings(schema)

        @staticmethod
        def sync():
            store.syncs += 1

        def __init__(self, schema):
            self.schema, self.delayed, self.pending = schema, False, {}

        def delay(self):
            self.delayed = True

        def is_writable(self, key):
            return (self.schema.sid, key) not in store.locked

        def set_value(self, key, v):
            assert self.delayed, "only delayed settings are written here"
            self.pending[key] = v.text
            return True

        def get_value(self, key):
            return Variant(store.values[self.schema.sid][key])

        def apply(self):
            if store.fail_apply:
                raise RuntimeError("no dconf")
            store.values[self.schema.sid].update(self.pending)
            store.changes.append((self.schema.sid, dict(self.pending)))
            self.pending = {}

    class Gio:
        pass
    Gio.Settings = Settings

    class GLib:
        class Variant:
            @staticmethod
            def parse(vtype, text, limit, endptr):
                if not text.startswith("'"):
                    raise ValueError("expected a string")
                return Variant(text)
    return Gio, GLib


@pytest.fixture
def dconf(tmp_path, monkeypatch):
    """An Env reading and writing a fake dconf in this process; `gsettings` runs are noted."""
    store = Dconf()
    env = Env(home=tmp_path)
    Gio, GLib = fake_gi(store)
    env._gio_module = lambda: Gio
    env._glib_module = lambda: GLib
    env._schema_here = lambda schema, path: Schema(store, schema) if schema in store.values else None
    ran = []

    def run(argv, timeout=30):
        ran.append(list(argv))
        if argv[:1] == ["gsettings"] and argv[-3:-2] and argv[1] == "set":
            store.values.setdefault(argv[2], {})[argv[3]] = argv[4]
        return RunResult(0, "", "")
    env.run = run
    for var, sub in (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"), ("XDG_STATE_HOME", ".local/state")):
        monkeypatch.setenv(var, str(tmp_path / sub))
    return env, store, ran


DTP = "org.gnome.shell.extensions.dash-to-panel"
THEME = "org.gnome.shell.extensions.user-theme"


def _sets(ran):
    return [a for a in ran if a[:1] == ["gsettings"] and "set" in a]


def test_a_batch_writes_each_schema_once_without_gsettings(dconf):
    env, store, ran = dconf
    store.values = {DTP: {f"k{i}": "'old'" for i in range(13)}, THEME: {"name": "'Other'"}}
    with env.gsettings_batch():
        for i in range(13):
            assert env.gsettings_set(DTP, f"k{i}", f"'v{i}'").ok
        assert env.gsettings_set(THEME, "name", "'FedoraGlass'").ok
        assert env.gsettings_get(DTP, "k3") == "'v3'", "read back before it goes out"
        assert store.changes == []
    assert ran == []
    assert [c[0] for c in store.changes] == [DTP, THEME]
    assert store.changes[0][1] == {f"k{i}": f"'v{i}'" for i in range(13)}
    assert store.syncs == 1
    assert env.gsettings_get(DTP, "k12") == "'v12'"


def test_the_same_key_twice_goes_out_twice_in_order(dconf):
    """User Themes loads a new style sheet only when its name changes: away and back."""
    env, store, ran = dconf
    store.values = {THEME: {"name": "'FedoraGlass'"}}
    with env.gsettings_batch():
        env.gsettings_set(THEME, "name", "''")
        env.gsettings_set(THEME, "name", "'FedoraGlass'")
    assert store.changes == [(THEME, {"name": "''"}), (THEME, {"name": "'FedoraGlass'"})]
    assert store.syncs == 2 and ran == []


def test_a_reset_waits_for_what_was_set_before_it(dconf):
    env, store, ran = dconf
    store.values = {DTP: {"a": "'1'", "b": "'2'"}}
    with env.gsettings_batch():
        env.gsettings_set(DTP, "a", "'x'")
        env.gsettings_reset(DTP, "b")
        assert store.changes == [(DTP, {"a": "'x'"})], "written before the reset ran"
    assert ran[-1][-3:] == ["reset", DTP, "b"]


def test_outside_a_batch_gsettings_writes_as_before(dconf):
    env, store, ran = dconf
    store.values = {DTP: {"a": "'1'"}}
    env.gsettings_set(DTP, "a", "'x'")
    assert _sets(ran) == [["gsettings", "set", DTP, "a", "'x'"]] and store.changes == []


@pytest.mark.parametrize("value, why", (("5", "a value only gsettings can explain"),
                                        ("'out-of-range'", "outside the key's range"),
                                        ("'v'", "a locked key")))
def test_what_cant_be_set_here_goes_through_gsettings(dconf, value, why):
    env, store, ran = dconf
    store.values = {DTP: {"a": "'1'"}}
    store.locked = {(DTP, "a")} if why == "a locked key" else set()
    with env.gsettings_batch():
        env.gsettings_set(DTP, "a", value)
    assert _sets(ran) == [["gsettings", "set", DTP, "a", value]], why
    assert store.changes == []


def test_an_unknown_schema_goes_through_gsettings(dconf):
    env, store, ran = dconf
    with env.gsettings_batch():
        env.gsettings_set("org.example.gone", "a", "'1'")
    assert _sets(ran) == [["gsettings", "set", "org.example.gone", "a", "'1'"]]


def test_without_pygobject_gsettings_writes(dconf):
    env, store, ran = dconf
    store.values = {DTP: {"a": "'1'"}}
    env._gio_module = lambda: None
    env._glib_module = lambda: None
    with env.gsettings_batch():
        env.gsettings_set(DTP, "a", "'x'")
    assert _sets(ran) == [["gsettings", "set", DTP, "a", "'x'"]]


def test_a_store_that_fails_is_written_by_gsettings_instead(dconf):
    env, store, ran = dconf
    store.values = {DTP: {"a": "'1'", "b": "'2'"}}
    store.fail_apply = True
    with env.gsettings_batch():
        env.gsettings_set(DTP, "a", "'x'")
        env.gsettings_set(DTP, "b", "'y'")
    assert sorted(map(tuple, _sets(ran))) == [("gsettings", "set", DTP, "a", "'x'"),
                                              ("gsettings", "set", DTP, "b", "'y'")]
    assert store.values[DTP] == {"a": "'x'", "b": "'y'"}


def test_dry_run_writes_nothing(dconf):
    env, store, ran = dconf
    store.values = {DTP: {"a": "'1'"}}
    env.dry_run = True
    with env.gsettings_batch():
        env.gsettings_set(DTP, "a", "'x'")
    assert ran == [] and store.changes == [] and store.values[DTP]["a"] == "'1'"


class Panelish(Target):
    """Dash to Panel's 13 colour keys and the Shell theme's name bounce, by style."""

    def __init__(self):
        super().__init__(id="panelish", name="Panelish")

    def plan(self, ctx):
        v = "'dark'" if ctx.tokens.dark else "'light'"
        acts = [GSet(DTP, f"k{i}", v) for i in range(13)]
        acts.append(GReset(DTP, "animate"))
        return acts + [GSet(THEME, "name", "''"), GSet(THEME, "name", "'FedoraGlass'")]


def test_a_dark_light_switch_starts_no_gsettings(dconf):
    env, store, ran = dconf
    store.values = {DTP: {f"k{i}": "'theirs'" for i in range(13)} | {"animate": "true"},
                    THEME: {"name": "'FedoraGlass'"},
                    "org.gnome.desktop.interface": {"color-scheme": "'prefer-dark'"},
                    "org.gnome.desktop.a11y.interface": {"high-contrast": "'false'"}}
    eng = Engine(env, [Panelish()])
    eng.apply(Settings())
    store.changes.clear()
    ran.clear()
    store.values["org.gnome.desktop.interface"]["color-scheme"] = "'default'"
    got = eng.apply(Settings(), if_applied=True, applied_only=True)
    assert [r.status for r in got] == ["applied"]
    assert _sets(ran) == [], "no gsettings started for the switch"
    assert store.changes == [(DTP, {f"k{i}": "'light'" for i in range(13)}),
                             (THEME, {"name": "''"}), (THEME, {"name": "'FedoraGlass'"})]
    # Restore original still puts everything back.
    assert eng.revert() == []
    assert set(store.values[DTP][f"k{i}"] for i in range(13)) == {"'theirs'"}
