"""The pointer's light turns smoothly across a long, thin bar (the taskbar).

Up to 1.5.27 the light pointed straight at the pointer from the pane's middle. On
the taskbar (2000 x 55 px) it swung from the side to straight above within a few
px as the pointer passed the middle, so the whole top edge flashed: Dino saw it
while dragging along the taskbar. The light is now turned by how far the pointer
is along the pane's own half size.
"""
import math
import re
from pathlib import Path

GLASS = Path(__file__).resolve().parents[1] / "fedoraglass/data/extension/liquid-glass@djshiye.github.io/glass.js"

ROOM = (math.cos(math.radians(-125)), math.sin(math.radians(-125)))   # DEFAULT_LOOK lightAngle


def _norm(x, y):
    n = math.hypot(x, y)
    return (x / n, y / n)


def light_now(to_ptr, h, k):
    """lightDir() as the shader has it now (kept in step by test_shader_matches)."""
    lp = [max(-1.0, min(1.0, to_ptr[i] / max(h[i], 1.0))) for i in (0, 1)]
    return _norm(ROOM[0] + (lp[0] - ROOM[0]) * k + 1e-4, ROOM[1] + (lp[1] - ROOM[1]) * k + 1e-4)


def light_old(to_ptr, _h, k):
    """lightDir() up to 1.5.27."""
    n = max(math.hypot(*to_ptr), 1.0)
    lp = (to_ptr[0] / n, to_ptr[1] / n)
    return _norm(ROOM[0] + (lp[0] - ROOM[0]) * k + 1e-4, ROOM[1] + (lp[1] - ROOM[1]) * k + 1e-4)


def _biggest_turn(light):
    """Largest change of the light's angle, in degrees, per px of pointer travel
    along the taskbar, the pointer 8 px above the bar's middle line."""
    h = (1024.0, 27.5)
    k = 0.8
    worst, prev = 0.0, None
    for x in range(-1100, 1101):
        d = light((float(x), -8.0), h, k)
        a = math.degrees(math.atan2(d[1], d[0]))
        if prev is not None:
            worst = max(worst, abs((a - prev + 180) % 360 - 180))
        prev = a
    return worst


def test_shader_matches():
    src = GLASS.read_text()
    body = re.search(r"vec2 lightDir\(vec2 toPtr, vec2 h\) \{(.*?)\n\}", src, re.S)
    assert body, "lightDir() takes the pane's half size"
    assert "clamp(toPtr / max(h, vec2(1.0)), -1.0, 1.0)" in body.group(1)
    assert "mix(vec2(hl_x, hl_y), Lp, ptr_k)" in body.group(1)
    assert "vec2 L = lightDir(toPtr, h);" in src


def test_light_turns_smoothly_along_the_taskbar():
    assert _biggest_turn(light_now) < 0.5


def _turn_across_middle(light):
    """How far the light turns, in degrees, as the pointer moves 20 px across the
    taskbar's middle."""
    a = [math.degrees(math.atan2(d[1], d[0]))
         for d in (light((x, -8.0), (1024.0, 27.5), 0.8) for x in (-10.0, 10.0))]
    return abs((a[1] - a[0] + 180) % 360 - 180)


def test_old_light_snapped_at_the_middle():
    # What Dino saw: the old light swung over 80 degrees within 20 px of the middle.
    assert _biggest_turn(light_old) > 5
    assert _turn_across_middle(light_old) > 60


def test_new_light_barely_turns_at_the_middle():
    assert _turn_across_middle(light_now) < 5


def test_light_still_follows_the_pointer_at_the_ends():
    h = (1024.0, 27.5)
    right = light_now((1100.0, 0.0), h, 0.8)
    left = light_now((-1100.0, 0.0), h, 0.8)
    assert right[0] > 0.5 and left[0] < -0.5


def test_no_pointer_light_is_the_room_light():
    for to_ptr in ((0.0, -8.0), (900.0, 3.0), (-50.0, 40.0)):
        d = light_now(to_ptr, (1024.0, 27.5), 0.0)
        assert abs(d[0] - ROOM[0]) < 1e-3 and abs(d[1] - ROOM[1]) < 1e-3
