import pytest
from pydantic import ValidationError

from app.domain.models import Decision, Runtime, SimSettings
from tests.conftest import make_order, make_product


def test_valid_product():
    assert make_product().id == "milk"


@pytest.mark.parametrize(
    "kw",
    [
        dict(stock=31),  # > max_stock
        dict(stock=-1),
        dict(reorder_point=30),  # must be < max_stock
        dict(max_stock=0),
        dict(max_stock=1000),
        dict(sell_weight=0),
        dict(sell_weight=11),
        dict(lead_time_s=4),
        dict(lead_time_s=601),
        dict(id="Cold Drink"),  # not a slug
    ],
)
def test_invalid_product(kw):
    with pytest.raises(ValidationError):
        make_product(**kw)


def test_order_open_until_delivered():
    assert make_order().is_open
    assert not make_order(status="DELIVERED", delivered_at_s=60).is_open


def test_order_id_format():
    with pytest.raises(ValidationError):
        make_order(id="7")


def test_runtime_defaults_and_settings():
    rt = Runtime()
    assert rt.run_id == 1 and rt.sim_s == 0
    assert rt.speed == 0 and rt.last_speed == 1  # fresh start is paused
    assert rt.counters.sales == 0
    assert rt.settings() == SimSettings()


@pytest.mark.parametrize(
    "speed, last, expected_last",
    [(5, 1, 5), (0.5, 5, 0.5), (0, 5, 5), (0, 1, 1)],
)
def test_paused_for_startup_remembers_running_speed(speed, last, expected_last):
    rt = Runtime(speed=speed, last_speed=last, sim_s=42).paused_for_startup()
    assert rt.speed == 0 and rt.last_speed == expected_last and rt.sim_s == 42


def test_last_speed_is_never_zero():
    with pytest.raises(ValidationError):
        Runtime(last_speed=0)


def test_runtime_rejects_unknown_speed():
    with pytest.raises(ValidationError):
        Runtime(speed=2)


def test_runtime_json_roundtrip():
    rt = Runtime(sim_s=12.5, speed=0.5, rush_hour=True, agent_mode="gemini")
    assert Runtime.model_validate(rt.model_dump(mode="json")) == rt


def test_decision_literals():
    Decision(product_id="milk", action="order", qty=5, reason="x", source="rules")
    with pytest.raises(ValidationError):
        Decision(product_id="milk", action="buy", qty=5, source="rules")
    with pytest.raises(ValidationError):
        Decision(product_id="milk", action="order", qty=5, source="gpt")
