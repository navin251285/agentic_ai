"""Simulation clock and speed.

sim_s advances by real_dt × speed; it does not move while paused (speed 0).
The shop clock is cosmetic: day 1 starts at 08:00 and 1 sim second = 5 shop minutes.
"""

from app.domain.models import PlaySpeed, Runtime, Speed

TICK_REAL_S = 0.5
DAY_START_MIN = 8 * 60
SHOP_MIN_PER_SIM_S = 5
SPEEDS: tuple[Speed, ...] = (0, 0.5, 1, 5)


def shop_time(sim_s: float) -> str:
    """'Day N · HH:MM'; wraps past midnight into the next day."""
    total = DAY_START_MIN + int(sim_s * SHOP_MIN_PER_SIM_S)
    day, minute = divmod(total, 24 * 60)
    return f"Day {day + 1} · {minute // 60:02d}:{minute % 60:02d}"


def set_speed(runtime: Runtime, speed: Speed) -> None:
    """0 pauses; any other speed is remembered so Play resumes it."""
    if speed not in SPEEDS:
        raise ValueError(f"speed must be one of {SPEEDS}")
    runtime.speed = speed
    if speed:
        runtime.last_speed = speed


def play(runtime: Runtime) -> PlaySpeed:
    set_speed(runtime, runtime.last_speed)
    return runtime.last_speed


def sim_dt(runtime: Runtime, real_dt: float = TICK_REAL_S) -> float:
    """Sim seconds that pass during real_dt at the current speed."""
    return real_dt * runtime.speed


def advance(runtime: Runtime, dt_sim: float) -> None:
    runtime.sim_s += dt_sim
