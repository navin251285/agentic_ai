from app.services.engines.rate_limiter import LlmRateLimiter, VirtualClock, max_calls_in_window


def make(**kw) -> tuple[LlmRateLimiter, VirtualClock]:
    vc = VirtualClock()
    return LlmRateLimiter(clock=vc, **kw), vc


def test_min_gap_between_calls():
    limiter, vc = make()
    assert limiter.try_acquire()
    vc.advance(5.9)
    assert not limiter.try_acquire()
    assert round(limiter.next_call_allowed_in_s(), 1) == 0.1
    vc.advance(0.1)
    assert limiter.try_acquire()
    assert limiter.total == 2


def test_denied_call_is_not_counted():
    limiter, _ = make()
    limiter.try_acquire()
    for _ in range(5):
        limiter.try_acquire()
    assert limiter.total == 1 and limiter.calls_last_window() == 1


def test_window_cap_is_a_backstop():
    limiter, vc = make()
    limiter.min_gap_s = 0  # bypass (b) to check (a) on its own
    assert all(limiter.try_acquire() for _ in range(10))
    assert not limiter.try_acquire()
    vc.advance(59.9)
    assert not limiter.try_acquire()
    vc.advance(0.1)
    assert limiter.try_acquire()


def test_config_can_lower_but_never_raise_the_budget():
    assert LlmRateLimiter(max_calls=50, min_gap_s=1).max_calls == 10
    assert LlmRateLimiter(max_calls=50, min_gap_s=1).min_gap_s == 6
    limiter, vc = make(max_calls=3)
    for _ in range(3):
        assert limiter.try_acquire()
        vc.advance(6)
    assert not limiter.try_acquire()  # 3 calls in the last 60s
    assert round(limiter.next_call_allowed_in_s()) == 42
    assert limiter.calls_last_window() == 3


def test_max_calls_in_window():
    assert max_calls_in_window([]) == 0
    assert max_calls_in_window([0, 30, 59.9, 60, 61]) == 4  # 30, 59.9, 60, 61
