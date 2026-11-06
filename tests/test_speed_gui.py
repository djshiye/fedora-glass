"""Speed, backend side: the status file the extension writes and the check request the app writes."""
from __future__ import annotations

import json
import os
import re

import pytest

pytest.importorskip("PySide6.QtGui")
from test_gui_backend import app, home, make_backend  # noqa: E402,F401


def status(home, **kw):
    d = {"version": 1, "quality": "auto", "level": "lighter", "reason": "slow", "since": 1, "check": None}
    d.update(kw)
    p = home / "cache/liquid-glass/speed.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d))
    return p


@pytest.fixture(autouse=True)
def cache(monkeypatch, home):
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / "cache"))


def test_reads_status(make_backend, home):
    b = make_backend()
    assert b.property("speedLevel") == "" and b.property("speedState") == "idle"
    status(home)
    b._on_speed_file()
    assert (b.property("speedLevel"), b.property("speedReason")) == ("lighter", "slow")


def test_ignores_bad_status(make_backend, home):
    b = make_backend()
    p = status(home, level="warp", reason="??")
    b._on_speed_file()
    assert b.property("speedLevel") == "" and b.property("speedReason") == ""
    p.write_text("[1, 2]")
    assert b._read_speed_status() == {}
    p.write_text("{nope")
    assert b._read_speed_status() == {}
    p.write_text(json.dumps({"level": "full", "pad": "x" * 70000}))
    assert b._read_speed_status() == {}
    p.unlink()
    real = home / "real.json"
    real.write_text(json.dumps({"level": "full"}))
    os.symlink(real, p)
    assert b._read_speed_status() == {}


def test_check_refused_when_not_live(make_backend, home):
    b = make_backend()
    b.checkSpeed()
    assert b.property("speedState") == "noanswer"
    assert not (home / "config/liquid-glass/speed-check.json").exists()


def test_check_writes_request_and_finishes(make_backend, home):
    b = make_backend()
    b._glass_live = True
    b.checkSpeed()
    req = home / "config/liquid-glass/speed-check.json"
    data = json.loads(req.read_text())
    assert re.fullmatch(r"[0-9a-f]{16}", data["id"]) and list(data) == ["id"]
    assert req.stat().st_mode & 0o777 == 0o644
    assert b.property("speedState") == "running"
    check = {"id": "0" * 16, "state": "done"}
    status(home, check=check)
    b._poll_speed()
    assert b.property("speedState") == "running", "someone else's id is ignored"
    check = {"id": data["id"], "state": "done", "error": "", "refresh": 60.0, "pick": "full",
             "phases": [{"level": "full", "fps": 58.2, "late": 0.03, "verdict": "smooth"}]}
    status(home, check=check)
    b._poll_speed()
    assert b.property("speedState") == "done"
    assert b.property("speedResult")["pick"] == "full"
    assert not b._speed_poll.isActive()


def test_check_failed_and_gives_up(make_backend, home):
    b = make_backend()
    b._glass_live = True
    b.checkSpeed()
    rid = json.loads((home / "config/liquid-glass/speed-check.json").read_text())["id"]
    status(home, check={"id": rid, "state": "failed", "error": "noglass"})
    b._poll_speed()
    assert b.property("speedState") == "failed" and b.property("speedResult")["error"] == "noglass"
    b.checkSpeed()
    b._speed_deadline = 0
    b._poll_speed()
    assert b.property("speedState") == "noanswer" and not b._speed_poll.isActive()
    b.shutdown()


def test_use_quality(make_backend):
    b = make_backend()
    b.useQuality("lightest")
    assert b.property("glassQuality") == "lightest"
    b.useQuality("bogus")
    assert b.property("glassQuality") == "lightest"
    b.setProperty("glassQuality", "full")
    assert b.settings().glass_quality == "full"


def test_last_finished_check_shows_after_an_aborted_one(make_backend, home):
    done = {"id": "a" * 16, "state": "done", "error": "", "refresh": 60.0, "pick": "full",
            "phases": [{"level": "full", "fps": 60.0, "late": 0.0, "verdict": "smooth"}]}
    status(home, check={"id": "b" * 16, "state": "failed", "error": "locked"}, lastDone=done)
    b = make_backend()
    b._start_speed_watch()
    assert b.property("speedState") == "done"
    assert b.property("speedResult")["id"] == "a" * 16
