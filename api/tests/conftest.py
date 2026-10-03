import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.domain.models import Event, EventType, Order, OrderStatus, Product
from app.repositories.csv_repo import CsvInventoryRepository

SCENARIOS = Path(__file__).resolve().parents[1] / "data" / "scenarios"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    shutil.copytree(SCENARIOS, tmp_path / "scenarios")
    return tmp_path


@pytest.fixture
def repo(data_dir: Path) -> CsvInventoryRepository:
    return CsvInventoryRepository(data_dir)


def make_product(**kw) -> Product:
    base = dict(
        id="milk", name="Milk", stock=18, max_stock=30, reorder_point=12, sell_weight=5, lead_time_s=60
    )
    return Product(**{**base, **kw})


def make_order(**kw) -> Order:
    base = dict(id="O-0001", product_id="milk", qty=10, status=OrderStatus.PLACED, placed_at_s=0, due_at_s=60)
    return Order(**{**base, **kw})


def make_event(**kw) -> Event:
    base = dict(
        run_id=1,
        ts_real=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        sim_s=0,
        shop_time="Day 1 · 08:00",
        type=EventType.SALE,
        product_id="milk",
        qty=1,
        stock_after=17,
        ref="C-0001",
        message="",
    )
    return Event(**{**base, **kw})


@pytest.fixture
def sim(repo):
    """A Simulation on normal_day with a fixed seed, in memory (scenarios read from the temp data dir)."""
    import random

    from app.repositories.memory_repo import InMemoryInventoryRepository
    from app.services.simulation import Simulation

    mem = InMemoryInventoryRepository(repo)
    s = Simulation(mem.load(), mem, random.Random(42))
    s.load_scenario("normal_day")
    return s
