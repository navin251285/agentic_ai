import pytest

from app.domain.models import Runtime
from app.services import clock


@pytest.mark.parametrize(
    "sim_s, expected",
    [
        (0, "Day 1 · 08:00"),
        (0.5, "Day 1 · 08:02"),
        (1, "Day 1 · 08:05"),
        (12, "Day 1 · 09:00"),
        (191, "Day 1 · 23:55"),
        (192, "Day 2 · 00:00"),
        (384, "Day 2 · 16:00"),
        (480, "Day 3 · 00:00"),
    ],
)
def test_shop_time(sim_s, expected):
    assert clock.shop_time(sim_s) == expected


def test_pause_freezes_and_play_resumes_last_speed():
    rt = Runtime()
    clock.set_speed(rt, 5)
    assert clock.sim_dt(rt) == 2.5
    clock.set_speed(rt, 0)
    assert clock.sim_dt(rt) == 0 and rt.last_speed == 5
    assert clock.play(rt) == 5 and rt.speed == 5


def test_rejects_unknown_speed():
    with pytest.raises(ValueError):
        clock.set_speed(Runtime(), 2)
