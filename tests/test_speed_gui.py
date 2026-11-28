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


def _phases(*verdicts):
    return [{"level": lv, "fps": 30.0, "late": 0.5, "verdict": v}
            for lv, v in zip(("full", "lighter", "lightest"), verdicts)]


def test_old_unfair_check_with_nothing_smooth_is_not_shown_again(make_backend, home):
    """1.7.6's check could only make a level look slower than it is: its all-slow answer (Dino's PC
    drew a drag at 8.3 ms a frame) says nothing, so the card offers the button and no verdict."""
    old = {"id": "796e1b326b47ff5e", "state": "done", "error": "", "refresh": 120, "pick": "full",
           "phases": [{"level": "full", "fps": 34.2, "late": 0.691, "verdict": "slow"},
                      {"level": "lighter", "fps": 14.5, "late": 0.954, "verdict": "slow"},
                      {"level": "lightest", "fps": 9, "late": 0.966, "verdict": "slow"}]}
    status(home, check=old, lastDone=old)
    b = make_backend()
    b._start_speed_watch()
    assert b.property("speedState") == "idle"
    assert dict(b.property("speedResult")) == {}


def test_old_check_with_a_smooth_level_still_shows(make_backend, home):
    old = {"id": "a" * 16, "state": "done", "error": "", "refresh": 60.0, "pick": "full",
           "phases": _phases("ok", "smooth", "smooth")}
    status(home, check=old, lastDone=old)
    b = make_backend()
    b._start_speed_watch()
    assert b.property("speedState") == "done"
    assert b.property("speedResult")["id"] == "a" * 16


def test_marked_check_shows_whatever_it_found(make_backend, home):
    done = {"id": "c" * 16, "state": "done", "error": "", "refresh": 60.0, "pick": "full", "method": 2,
            "phases": _phases("slow", "slow", "slow")}
    status(home, check=done, lastDone=done)
    b = make_backend()
    b._start_speed_watch()
    assert b.property("speedState") == "done"
    assert b.property("speedResult")["id"] == "c" * 16


def test_answer_to_a_check_asked_for_now_shows_even_without_the_mark(make_backend, home):
    """The Shell may still run the extension from before an update, which writes no mark."""
    b = make_backend()
    b._glass_live = True
    b.checkSpeed()
    rid = json.loads((home / "config/liquid-glass/speed-check.json").read_text())["id"]
    status(home, check={"id": rid, "state": "done", "error": "", "refresh": 60.0, "pick": "full",
                        "phases": _phases("slow", "slow", "slow")})
    b._poll_speed()
    assert b.property("speedState") == "done"
    assert b.property("speedResult")["id"] == rid


def test_last_drag_in_words(make_backend, home):
    """speed.js times each window drag (its `drag` object); the Speed card says how it went."""
    b = make_backend()
    assert b.property("speedDrag") == ""
    status(home, drag={"at": 1, "frames": 56, "median_ms": 15, "p95_ms": 20, "refresh": 60, "windows": 4})
    b._on_speed_file()
    assert b.property("speedDrag") == "Last window drag with 4 windows open: about 60 frames a second, smooth."
    status(home, drag={"at": 1, "frames": 56, "median_ms": 54, "p95_ms": 86.8, "refresh": 60, "windows": 1})
    b._on_speed_file()
    assert b.property("speedDrag") == "Last window drag: about 19 frames a second, slow."
    # A fast screen is judged like the speed check: 60 frames a second or more is smooth.
    status(home, drag={"at": 1, "frames": 500, "median_ms": 11.1, "p95_ms": 13.9, "refresh": 144, "windows": 1})
    b._on_speed_file()
    assert b.property("speedDrag") == "Last window drag: about 90 frames a second, smooth."
    status(home, drag={"at": 1, "frames": 500, "median_ms": 25, "p95_ms": 40, "refresh": 144, "windows": 1})
    b._on_speed_file()
    assert b.property("speedDrag") == "Last window drag: about 40 frames a second, a little uneven."
    for bad in ({"median_ms": "x", "p95_ms": 1}, {"median_ms": 0, "p95_ms": 5}, {"p95_ms": 5}, [1, 2],
                {"median_ms": 10, "p95_ms": 20, "refresh": float("nan")}):
        status(home, drag=bad)
        b._on_speed_file()
        assert b.property("speedDrag") == ""
