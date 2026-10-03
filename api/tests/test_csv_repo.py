import json
import os

import pytest

from app.domain.models import EventType, Runtime
from app.repositories.base import ScenarioNotFound
from app.repositories.csv_repo import CsvInventoryRepository
from tests.conftest import make_event, make_order, make_product

SEED = {
    "milk": (18, 30, 12, 5, 60),
    "bread": (18, 25, 9, 4, 45),
    "eggs": (22, 40, 13, 4, 60),
    "rice": (22, 30, 10, 2, 90),
    "sugar": (16, 24, 10, 2, 90),
    "biscuits": (25, 40, 12, 3, 90),
    "chips": (22, 30, 9, 4, 45),
    "soap": (12, 15, 7, 1, 90),
    "toothpaste": (12, 15, 7, 1, 90),
    "cold-drink": (20, 36, 9, 4, 30),
}


# ---- scenarios ------------------------------------------------------------


def test_list_scenarios(repo):
    assert repo.list_scenarios() == ["low_stock_start", "normal_day", "rush_hour"]


def test_normal_day_matches_spec(repo):
    products = repo.load_scenario("normal_day")
    got = {p.id: (p.stock, p.max_stock, p.reorder_point, p.sell_weight, p.lead_time_s) for p in products}
    assert got == SEED
    assert {p.id: p.name for p in products}["rice"] == "Rice 1kg"


def test_rush_hour_same_products(repo):
    assert repo.load_scenario("rush_hour") == repo.load_scenario("normal_day")


def test_low_stock_start_two_above_mark(repo):
    normal = {p.id: p for p in repo.load_scenario("normal_day")}
    low = {p.id: p for p in repo.load_scenario("low_stock_start")}
    changed = {pid for pid in low if low[pid] != normal[pid]}
    assert changed == {"milk", "eggs", "chips", "cold-drink"}
    for pid in changed:
        assert low[pid].stock == low[pid].reorder_point + 2


@pytest.mark.parametrize("name", ["nope", "../products", "normal_day.csv", ""])
def test_unknown_scenario(repo, name):
    with pytest.raises(ScenarioNotFound):
        repo.load_scenario(name)


# ---- load / startup -------------------------------------------------------


def test_first_start_copies_default_scenario(repo, data_dir):
    snap = repo.load()
    assert (data_dir / "products.csv").exists()
    assert snap.products == repo.load_scenario("normal_day")
    assert snap.orders == [] and snap.events == []
    assert snap.runtime == Runtime()


def test_runtime_defaults_are_applied_under_saved_values(data_dir):
    repo = CsvInventoryRepository(data_dir, runtime_defaults={"agent_mode": "gemini", "agent_interval_s": 7})
    assert repo.load().runtime.agent_mode == "gemini"
    repo.save_runtime({"agent_interval_s": 3})
    rt = repo.load().runtime
    assert rt.agent_mode == "gemini" and rt.agent_interval_s == 3


@pytest.mark.parametrize(
    "content",
    [
        "id,name,stock\nmilk,Milk,not-a-number\n",  # bad value
        "id,name,stock,max_stock,reorder_point,sell_weight,lead_time_s\n",  # header only
        "",  # empty file
    ],
)
def test_invalid_products_is_quarantined_then_scenario_used(repo, data_dir, caplog, content):
    (data_dir / "products.csv").write_text(content, encoding="utf-8")
    snap = repo.load()

    assert snap.products == repo.load_scenario("normal_day")
    bad = list(data_dir.glob("products.csv.bad-*"))
    assert len(bad) == 1
    assert bad[0].read_text(encoding="utf-8") == content  # original kept as-is
    assert "products.csv is INVALID and was moved to products.csv.bad-" in caplog.text


def test_quarantine_never_overwrites_an_earlier_bad_file(repo, data_dir):
    for _ in range(2):
        (data_dir / "products.csv").write_text("garbage", encoding="utf-8")
        repo.load()
    assert len(list(data_dir.glob("products.csv.bad-*"))) == 2


def test_missing_products_is_not_quarantined(repo, data_dir):
    repo.load()
    assert not list(data_dir.glob("products.csv.bad-*"))


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-8"])
def test_csv_read_accepts_with_and_without_bom(repo, data_dir, encoding):
    # Reads use utf-8-sig: a BOM (as Excel saves) is stripped, plain UTF-8 also works.
    text = "id,name,stock,max_stock,reorder_point,sell_weight,lead_time_s\nmilk,Milk · fresh,18,30,12,5,60\n"
    (data_dir / "products.csv").write_text(text, encoding=encoding)
    products = repo.load().products
    assert [(p.id, p.name) for p in products] == [("milk", "Milk · fresh")]


def test_csv_writes_start_with_bom(repo, data_dir):
    repo.save_products([make_product()])
    repo.append_event(make_event())
    repo.append_event(make_event())
    for name in ("products.csv", "events.csv"):
        raw = (data_dir / name).read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf") and raw.count(b"\xef\xbb\xbf") == 1


def test_corrupt_runtime_uses_defaults(repo, data_dir):
    (data_dir / "runtime.json").write_text("{not json", encoding="utf-8")
    assert repo.load().runtime == Runtime()
    (data_dir / "runtime.json").write_text(json.dumps({"speed": 3}), encoding="utf-8")
    assert repo.load().runtime == Runtime()


def test_full_roundtrip(repo):
    products = [make_product(), make_product(id="cold-drink", name="Cold drink, 500ml", stock=0)]
    orders = [
        make_order(placed_at_s=12.25, due_at_s=72.25),
        make_order(id="O-0002", status="DELIVERED", delivered_at_s=99.5),
    ]
    rt = Runtime(
        run_id=3, sim_s=101.5, speed=0.5, counters={"sales": 4, "missed_sales": 1, "orders_placed": 2}
    )
    assert repo.save_products(products)
    assert repo.save_orders(orders)
    assert repo.save_runtime(rt.model_dump(mode="json"))
    repo.append_event(make_event(run_id=3, message='said "hi", then left'))

    snap = repo.load()
    assert snap.products == products
    assert snap.orders == orders
    assert snap.runtime == rt
    assert [e.message for e in snap.events] == ['said "hi", then left']


# ---- events ---------------------------------------------------------------


def test_events_append_and_filter_by_run(repo, data_dir):
    repo.append_event(make_event(run_id=1, sim_s=1))
    repo.append_event(make_event(run_id=2, sim_s=0, type=EventType.RESET, ref="", qty=None))
    repo.append_event(make_event(run_id=2, sim_s=2.5, product_id=None, stock_after=None, qty=None))

    lines = (data_dir / "events.csv").read_text(encoding="utf-8-sig").splitlines()
    assert lines[0].startswith("run_id,ts_real,sim_s,shop_time,type,product_id")
    assert len(lines) == 4  # one header, three rows

    run2 = repo.read_events(2)
    assert [e.sim_s for e in run2] == [0, 2.5]
    assert run2[0].type == EventType.RESET and run2[0].qty is None
    assert run2[1].product_id is None
    assert repo.read_events(1)[0].shop_time == "Day 1 · 08:00"


def test_events_survive_new_repo_instance(repo, data_dir):
    repo.append_event(make_event())
    again = CsvInventoryRepository(data_dir)
    again.append_event(make_event(sim_s=3))
    assert [e.sim_s for e in again.read_events(1)] == [0, 3]


# ---- failure handling -----------------------------------------------------


def _fail_replace(monkeypatch):
    def boom(*a, **k):
        raise PermissionError("locked by Excel")

    monkeypatch.setattr(os, "replace", boom)


def test_failed_save_keeps_old_file_and_does_not_raise(repo, data_dir, monkeypatch, caplog):
    repo.save_products([make_product(stock=18)])
    _fail_replace(monkeypatch)
    assert repo.save_products([make_product(stock=1)]) is False
    monkeypatch.undo()

    assert "Could not save products.csv" in caplog.text
    assert not (data_dir / "products.csv.tmp").exists()
    assert repo.load().products[0].stock == 18
    assert repo.save_products([make_product(stock=1)]) is True  # retry next save works
    assert repo.load().products[0].stock == 1


def test_failed_event_appends_are_queued_and_written_in_order(repo, data_dir, monkeypatch):
    repo.append_event(make_event(sim_s=1))
    real_open = type(data_dir).open

    def locked_open(self, mode="r", *a, **k):
        if self.name == "events.csv" and "a" in mode:
            raise PermissionError("locked by Excel")
        return real_open(self, mode, *a, **k)

    monkeypatch.setattr(type(data_dir), "open", locked_open)
    assert repo.append_event(make_event(sim_s=2)) is False
    assert repo.append_event(make_event(sim_s=3)) is False
    assert repo.pending_event_count == 2
    monkeypatch.undo()

    assert repo.append_event(make_event(sim_s=4)) is True
    assert repo.pending_event_count == 0
    assert [e.sim_s for e in repo.read_events(1)] == [1, 2, 3, 4]


def test_pending_events_flush_on_next_successful_save(repo, data_dir, monkeypatch):
    real_open = type(data_dir).open

    def locked_open(self, mode="r", *a, **k):
        if self.name == "events.csv":
            raise PermissionError("locked")
        return real_open(self, mode, *a, **k)

    monkeypatch.setattr(type(data_dir), "open", locked_open)
    repo.append_event(make_event(sim_s=7))
    monkeypatch.undo()

    repo.save_orders([])
    assert [e.sim_s for e in repo.read_events(1)] == [7]
