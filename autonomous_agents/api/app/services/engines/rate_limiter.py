"""Hard cap on Gemini calls: ≤ 10 in any 60 real seconds AND ≥ 6 real seconds apart.

Every call counts (warm-up, decisions, failures). Check BEFORE building the request; when it says no,
nothing is sent. Uses real time (time.monotonic) so sim speed cannot exceed the budget; --fast runs and
tests pass a VirtualClock advanced by tick instead.
"""

import time
from collections import deque
from collections.abc import Callable

HARD_MAX_CALLS = 10
HARD_MIN_GAP_S = 6.0
WINDOW_S = 60.0


class VirtualClock:
    """A monotonic clock that only moves when told to (one tick = 0.5 virtual real seconds)."""

    def __init__(self, start: float = 0.0):
        self.now = start

    def advance(self, dt: float) -> None:
        self.now += dt

    def __call__(self) -> float:
        return self.now


class LlmRateLimiter:
    def __init__(
        self,
        max_calls: int = HARD_MAX_CALLS,
        min_gap_s: float = HARD_MIN_GAP_S,
        clock: Callable[[], float] = time.monotonic,
    ):
        # Config may lower the budget, never raise it.
        self.max_calls = max(1, min(max_calls, HARD_MAX_CALLS))
        self.min_gap_s = max(min_gap_s, HARD_MIN_GAP_S)
        self.clock = clock
        self._window: deque[float] = deque()
        self.history: deque[float] = deque(maxlen=1000)  # recent call times, for reports and tests
        self.total = 0

    def _prune(self, now: float) -> None:
        while self._window and now - self._window[0] >= WINDOW_S:
            self._window.popleft()

    def calls_last_window(self) -> int:
        self._prune(self.clock())
        return len(self._window)

    def next_call_allowed_in_s(self) -> float:
        """Real seconds until a call would be allowed (0 = now)."""
        now = self.clock()
        self._prune(now)
        if not self._window:
            return 0.0
        wait = self._window[-1] + self.min_gap_s - now
        if len(self._window) >= self.max_calls:
            wait = max(wait, self._window[0] + WINDOW_S - now)
        return max(0.0, wait)

    def try_acquire(self) -> bool:
        """Record a call and return True if one is allowed right now; otherwise change nothing."""
        if self.next_call_allowed_in_s() > 0:
            return False
        now = self.clock()
        self._window.append(now)
        self.history.append(now)
        self.total += 1
        return True


def max_calls_in_window(times: list[float], window_s: float = WINDOW_S) -> int:
    """Most calls in any window_s-long span (half-open, like the limiter)."""
    times = sorted(times)
    best, lo = 0, 0
    for hi, t in enumerate(times):
        while t - times[lo] >= window_s:
            lo += 1
        best = max(best, hi - lo + 1)
    return best
